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
-- Roles applicatifs.
--
-- Ce sont les MEMES trois roles que ceux du schema Gold (sql/schema_gold.sql),
-- eux-memes repris du modele de securite pose au Bloc 1 : etl_service,
-- analyst, dashboard_viewer, le quatrieme role admin etant tenu par le
-- proprietaire de la base. Une premiere version de ce fichier avait introduit
-- deux roles distincts, gamelens_etl et gamelens_reader, ce qui aurait donne
-- deux modeles de securite concurrents pour une seule plateforme.
--
-- La creation est gardee par IF NOT EXISTS dans les deux fichiers : chacun
-- reste executable seul, dans n'importe quel ordre, sans conflit.
--
-- Principe applique aux deux couches : le role de restitution n'accede jamais
-- aux tables, seulement aux vues agregees. PostgreSQL evalue les droits d'une
-- vue avec ceux de son proprietaire, pas ceux de l'appelant : dashboard_viewer
-- peut donc lire la vue sans posseder le moindre droit sur les tables sous
-- jacentes. C'est ce qui rend le cloisonnement reel et non declaratif.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'etl_service') THEN
        CREATE ROLE etl_service LOGIN PASSWORD 'devlocal_etl';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst LOGIN PASSWORD 'devlocal_analyst';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dashboard_viewer') THEN
        CREATE ROLE dashboard_viewer LOGIN PASSWORD 'devlocal_dashboard';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA speed TO etl_service, analyst, dashboard_viewer;

-- etl_service ecrit, mais ne supprime jamais : aucun DELETE n'est accorde.
-- Une anomalie du pipeline ou un compte compromis ne peut donc pas effacer
-- l'historique de collecte, seulement l'enrichir ou le corriger.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA speed TO etl_service;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA speed TO etl_service;

-- analyst : lecture large sur la couche Silver, y compris les evenements bruts.
GRANT SELECT ON ALL TABLES IN SCHEMA speed TO analyst;

-- dashboard_viewer : uniquement l'agregat journalier, jamais les evenements.
GRANT SELECT ON speed.v_daily_player_stats TO dashboard_viewer;

ALTER DEFAULT PRIVILEGES IN SCHEMA speed GRANT SELECT, INSERT, UPDATE ON TABLES TO etl_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA speed GRANT SELECT ON TABLES TO analyst;

-- ============================================================================
-- Dictionnaire de donnees : description de chaque colonne
-- ----------------------------------------------------------------------------
-- Ces commentaires ne sont pas decoratifs : ils sont la SOURCE du dictionnaire
-- de donnees publie en annexe de la documentation technique (C4.3.3), genere
-- par outils/generer_dictionnaire.py depuis le catalogue vivant.
--
-- Un dictionnaire recopie a la main diverge du schema en quelques semaines,
-- sans que rien ne le signale. Le decrire ici, a cote de la definition, rend
-- la divergence impossible : il n'existe qu'un seul endroit ou ecrire.
-- ============================================================================

COMMENT ON COLUMN speed.game_mapping.steam_appid IS
    'Identifiant Steam, clef naturelle du referentiel. Verifie en direct titre par titre.';
COMMENT ON COLUMN speed.game_mapping.unified_name IS
    'Nom canonique retenu par GameLens, arbitre entre les libelles divergents des sources.';
COMMENT ON COLUMN speed.game_mapping.developer IS 'Studio de developpement, renseigne manuellement.';
COMMENT ON COLUMN speed.game_mapping.genre IS
    'Genre principal. Sert de partition au classement distribue calcule par Snowpark.';
COMMENT ON COLUMN speed.game_mapping.steam_name IS
    'Libelle exact cote Steam, conserve pour tracer les ecarts avec unified_name.';
COMMENT ON COLUMN speed.game_mapping.twitch_game_id IS
    'Identifiant Twitch. Nul tant que la source de popularite diffusee n''est pas branchee.';
COMMENT ON COLUMN speed.game_mapping.rawg_id IS 'Identifiant RAWG, source catalogue.';
COMMENT ON COLUMN speed.game_mapping.is_active IS
    'Titre suivi par la collecte. Mis a faux plutot que supprime, pour ne pas orpheliner l''historique.';
COMMENT ON COLUMN speed.game_mapping.updated_at IS 'Derniere modification de la ligne de correspondance.';

COMMENT ON COLUMN speed.player_count_events.event_id IS 'Clef technique, sans signification metier.';
COMMENT ON COLUMN speed.player_count_events.steam_appid IS
    'Titre concerne. Reference game_mapping, sans clef etrangere pour ne pas bloquer l''ingestion.';
COMMENT ON COLUMN speed.player_count_events.player_count IS
    'Joueurs connectes a l''instant de l''appel. Zero est une mesure valide, pas une absence.';
COMMENT ON COLUMN speed.player_count_events.collected_at IS
    'Instant de l''appel a Steam, fourni par le producteur. Avec steam_appid, definit le grain.';
COMMENT ON COLUMN speed.player_count_events.ingested_at IS
    'Instant de l''ecriture en base. L''ecart avec collected_at mesure la latence du pipeline.';
COMMENT ON COLUMN speed.player_count_events.kafka_partition IS 'Partition Kafka d''origine, pour tracer un rejeu.';
COMMENT ON COLUMN speed.player_count_events.kafka_offset IS 'Offset Kafka d''origine, pour tracer un rejeu.';

COMMENT ON COLUMN speed.price_snapshots.snapshot_id IS 'Clef technique, sans signification metier.';
COMMENT ON COLUMN speed.price_snapshots.steam_appid IS 'Titre concerne.';
COMMENT ON COLUMN speed.price_snapshots.price_final IS
    'Prix effectivement paye, en euros. Converti depuis les centimes rendus par Steam.';
COMMENT ON COLUMN speed.price_snapshots.price_initial IS
    'Prix avant remise. Egal a price_final hors promotion.';
COMMENT ON COLUMN speed.price_snapshots.discount_percent IS
    'Remise en pourcentage, telle qu''annoncee par Steam. Zero hors promotion.';
COMMENT ON COLUMN speed.price_snapshots.currency IS 'Devise ISO 4217, EUR par construction (parametre cc=fr).';
COMMENT ON COLUMN speed.price_snapshots.collected_at IS
    'Instant du releve tarifaire. Avec steam_appid, definit le grain.';
COMMENT ON COLUMN speed.price_snapshots.ingested_at IS 'Instant de l''ecriture en base.';

COMMENT ON COLUMN speed.pipeline_runs.run_id IS 'Clef technique de l''execution.';
COMMENT ON COLUMN speed.pipeline_runs.component IS
    'Nom du composant execute. Valeurs attendues par la regle composant_muet de la supervision.';
COMMENT ON COLUMN speed.pipeline_runs.status IS 'started, success ou failed. Contraint par CHECK.';
COMMENT ON COLUMN speed.pipeline_runs.started_at IS 'Ouverture du contexte d''execution.';
COMMENT ON COLUMN speed.pipeline_runs.ended_at IS 'Fermeture. Nul si le processus a ete tue sans passer par son finally.';
COMMENT ON COLUMN speed.pipeline_runs.records_in IS
    'Enregistrements lus. Un succes avec zero lu et zero ecrit designe une execution sterile.';
COMMENT ON COLUMN speed.pipeline_runs.records_written IS 'Enregistrements reellement ecrits, doublons absorbes exclus.';
COMMENT ON COLUMN speed.pipeline_runs.error_message IS 'Type et message de l''exception, tronques a 2000 caracteres.';
