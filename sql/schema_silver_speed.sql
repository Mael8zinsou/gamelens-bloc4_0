-- ============================================================================
-- GameLens - Couche Silver speed (PostgreSQL), Bloc 4 - C4.2.2
-- ----------------------------------------------------------------------------
-- Branche "speed" de l'architecture Lambda posee au Bloc 1 : elle recoit le
-- flux temps reel Steam consomme depuis Kafka, avant promotion journaliere
-- vers la couche Gold (Snowflake).
--
-- Execute automatiquement au premier demarrage du conteneur PostgreSQL
-- (monte dans /docker-entrypoint-initdb.d).
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS speed;

-- ----------------------------------------------------------------------------
-- game_mapping : resolution des identifiants cross-plateformes (Bloc 1).
-- Sert de referentiel local au consumer ; c'est aussi la table qui absorbe les
-- ecarts de nommage entre plateformes (ex : "Disco Elysium" cote GameLens,
-- "Disco Elysium - The Final Cut" cote Steam).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS speed.game_mapping (
    steam_appid     INTEGER PRIMARY KEY,
    unified_name    TEXT    NOT NULL,
    developer       TEXT,
    genre           TEXT,
    steam_name      TEXT,
    twitch_game_id  TEXT,
    rawg_id         INTEGER,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE speed.game_mapping IS
    'Referentiel de resolution des identifiants entre plateformes (Steam, Twitch, RAWG). Alimente depuis config/watchlist.json.';

-- ----------------------------------------------------------------------------
-- player_count_events : evenements bruts du flux temps reel.
--
-- La contrainte UNIQUE (steam_appid, collected_at) est le pivot de la
-- strategie de livraison : Kafka garantit un at-least-once, donc un evenement
-- peut etre reconsomme apres un redemarrage du consumer. L'ecriture se fait en
-- ON CONFLICT DO NOTHING, ce qui rend le puits idempotent et produit un
-- effectively-once de bout en bout sans transaction distribuee.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS speed.player_count_events (
    event_id        BIGSERIAL PRIMARY KEY,
    steam_appid     INTEGER     NOT NULL REFERENCES speed.game_mapping(steam_appid),
    player_count    INTEGER     NOT NULL CHECK (player_count >= 0),
    collected_at    TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    kafka_partition INTEGER,
    kafka_offset    BIGINT,
    CONSTRAINT uq_player_count_event UNIQUE (steam_appid, collected_at)
);

COMMENT ON TABLE speed.player_count_events IS
    'Evenements unitaires de frequentation Steam (GetNumberOfCurrentPlayers), consommes depuis Kafka. Grain : un appid, un instant de collecte.';
COMMENT ON COLUMN speed.player_count_events.ingested_at IS
    'Horodatage d ecriture en base, distinct de collected_at : leur ecart mesure la latence du pipeline (indicateur de supervision, C4.3.1).';

CREATE INDEX IF NOT EXISTS idx_player_events_appid_time
    ON speed.player_count_events (steam_appid, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_player_events_ingested
    ON speed.player_count_events (ingested_at DESC);

-- ----------------------------------------------------------------------------
-- price_snapshots : releves tarifaires Steam.
--
-- Note de coherence avec le Bloc 3 : l'arbitrage de la section 3.3 a sorti le
-- suivi tarifaire GOG du perimetre. La tarification est donc alimentee ici par
-- l'API Steam appdetails (price_overview), sans scraping, ce qui respecte
-- l'arbitrage tout en gardant fact_prices alimentee cote Gold.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS speed.price_snapshots (
    snapshot_id      BIGSERIAL PRIMARY KEY,
    steam_appid      INTEGER     NOT NULL REFERENCES speed.game_mapping(steam_appid),
    price_final      NUMERIC(10,2) NOT NULL CHECK (price_final >= 0),
    price_initial    NUMERIC(10,2) CHECK (price_initial >= 0),
    discount_percent SMALLINT    NOT NULL DEFAULT 0 CHECK (discount_percent BETWEEN 0 AND 100),
    currency         CHAR(3)     NOT NULL DEFAULT 'EUR',
    collected_at     TIMESTAMPTZ NOT NULL,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_price_snapshot UNIQUE (steam_appid, collected_at)
);

COMMENT ON TABLE speed.price_snapshots IS
    'Releves tarifaires Steam (appdetails/price_overview). Remplace le scraping GOG, sorti du perimetre par l arbitrage du Bloc 3 (3.3).';

-- ----------------------------------------------------------------------------
-- pipeline_runs : journal d execution, socle de la supervision (C4.3.1).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS speed.pipeline_runs (
    run_id          BIGSERIAL PRIMARY KEY,
    component       TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('started', 'success', 'failed')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    records_in      INTEGER,
    records_written INTEGER,
    error_message   TEXT
);

COMMENT ON TABLE speed.pipeline_runs IS
    'Journal des executions de chaque composant du pipeline. Source des indicateurs de supervision et des alertes (C4.3.1).';

-- ----------------------------------------------------------------------------
-- Vue d agregation journaliere : c est elle qui est promue vers la table Gold
-- fact_popularity_history (grain jeu x jour, colonnes larges).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_daily_player_stats AS
SELECT
    e.steam_appid,
    m.unified_name,
    (e.collected_at AT TIME ZONE 'UTC')::date       AS day,
    ROUND(AVG(e.player_count), 2)                   AS avg_player_count,
    MAX(e.player_count)                             AS max_player_count,
    MIN(e.player_count)                             AS min_player_count,
    COUNT(*)                                        AS observation_count
FROM speed.player_count_events e
JOIN speed.game_mapping m ON m.steam_appid = e.steam_appid
GROUP BY e.steam_appid, m.unified_name, (e.collected_at AT TIME ZONE 'UTC')::date;

COMMENT ON VIEW speed.v_daily_player_stats IS
    'Agregat journalier de la frequentation, promu vers mart.fact_popularity_history par le DAG Airflow. observation_count sert de controle de completude.';

-- ----------------------------------------------------------------------------
-- Roles applicatifs, declinaison locale des 4 roles poses au Bloc 1.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gamelens_etl') THEN
        CREATE ROLE gamelens_etl LOGIN PASSWORD 'devlocal_etl';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gamelens_reader') THEN
        CREATE ROLE gamelens_reader LOGIN PASSWORD 'devlocal_reader';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA speed TO gamelens_etl, gamelens_reader;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA speed TO gamelens_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA speed TO gamelens_etl;
GRANT SELECT ON speed.v_daily_player_stats TO gamelens_reader;
