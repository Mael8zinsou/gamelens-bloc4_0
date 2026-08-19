-- ============================================================================
-- GameLens - Schema Gold (entrepot de donnees), Bloc 4 - C4.2.1
-- ----------------------------------------------------------------------------
-- Substitution technique : Snowflake (retenu au Bloc 1) n'est pas accessible
-- depuis ce sandbox. PostgreSQL en tient lieu ici pour executer et valider
-- reellement le schema. La conception (types, contraintes, roles, grain)
-- reste directement transposable a Snowflake (types quasi identiques, memes
-- contraintes CHECK/FK, memes principes de roles).
--
-- Conventions de nommage : deja posees au Bloc 2 (1.3) - prefixe dim_/fact_,
-- snake_case, cle primaire interne UUID independante des identifiants sources.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mart;

-- ----------------------------------------------------------------------------
-- Roles (volet securite du critere C4.2.1)
-- Repris des 4 roles definis au Bloc 1 (schema d'architecture de securite) :
-- admin, etl_service, analyst, dashboard_viewer.
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

GRANT USAGE ON SCHEMA mart TO etl_service, analyst, dashboard_viewer;

-- ----------------------------------------------------------------------------
-- dim_games
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart.dim_games (
    game_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unified_name      TEXT NOT NULL,
    genre             TEXT,
    developer         TEXT,
    release_date      DATE,
    metacritic_score  SMALLINT CHECK (metacritic_score BETWEEN 0 AND 100),
    critical_tier     TEXT CHECK (critical_tier IN ('Acclaimed', 'Favorable', 'Mixed')),
    steam_appid       INTEGER,
    twitch_game_id    TEXT,
    gog_slug          TEXT,
    rawg_id           INTEGER,
    gold_loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE mart.dim_games IS
    'Referentiel unifie des jeux suivis (portefeuille Kestrel Interactive + panel concurrent). Grain : un enregistrement par jeu.';
COMMENT ON COLUMN mart.dim_games.critical_tier IS
    'Categorie derivee de metacritic_score par le modele dbt (Bloc 1, Annexe 10) : >=85 Acclaimed, >=70 Favorable, sinon Mixed.';

-- ----------------------------------------------------------------------------
-- dim_stores
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart.dim_stores (
    store_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL UNIQUE,
    base_url     TEXT,
    source_type  TEXT NOT NULL CHECK (source_type IN ('api', 'scraping'))
);

COMMENT ON TABLE mart.dim_stores IS
    'Boutiques suivies pour la tarification (ex : Steam, GOG).';

-- ----------------------------------------------------------------------------
-- fact_prices (grain : un enregistrement par jeu, boutique, date de collecte)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart.fact_prices (
    price_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    game_id         UUID NOT NULL REFERENCES mart.dim_games(game_id),
    store_id        UUID NOT NULL REFERENCES mart.dim_stores(store_id),
    price           NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    currency        CHAR(3) NOT NULL DEFAULT 'EUR',
    promotion_flag  BOOLEAN NOT NULL DEFAULT FALSE,
    collected_at    TIMESTAMPTZ NOT NULL
);

COMMENT ON TABLE mart.fact_prices IS
    'Tarifs collectes par jeu et par boutique. Alimentee par le scraping GOG et les API de tarification (Bloc 1).';

CREATE INDEX IF NOT EXISTS idx_fact_prices_game_id ON mart.fact_prices (game_id);
CREATE INDEX IF NOT EXISTS idx_fact_prices_collected_at ON mart.fact_prices (collected_at);

-- ----------------------------------------------------------------------------
-- fact_popularity_history (grain : un enregistrement par jeu et par jour)
-- Colonnes larges (wide), pas de modele EAV metric_type/metric_value :
-- decision deja actee et documentee (memoire de session).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mart.fact_popularity_history (
    game_id           UUID NOT NULL REFERENCES mart.dim_games(game_id),
    day               DATE NOT NULL,
    avg_player_count  NUMERIC(12, 2),
    max_player_count  INTEGER,
    avg_viewer_count  NUMERIC(12, 2),
    max_viewer_count  INTEGER,
    PRIMARY KEY (game_id, day)
);

COMMENT ON TABLE mart.fact_popularity_history IS
    'Agregats journaliers de popularite jouee et diffusee, promus depuis la couche Silver speed (Bloc 1, 3.4).';

CREATE INDEX IF NOT EXISTS idx_fact_popularity_day ON mart.fact_popularity_history (day);

-- ----------------------------------------------------------------------------
-- Vue d'acces en self-service (volet accessibilite du critere C4.2.1)
-- Expose une lecture agregee sans donner acces direct aux tables de faits,
-- pour le role dashboard_viewer (cf. Bloc 2, 1.3 organisation de la donnee).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW mart.v_popularity_dashboard AS
SELECT
    g.game_id,
    g.unified_name,
    g.genre,
    g.critical_tier,
    h.day,
    h.avg_player_count,
    h.avg_viewer_count
FROM mart.dim_games g
JOIN mart.fact_popularity_history h ON g.game_id = h.game_id;

COMMENT ON VIEW mart.v_popularity_dashboard IS
    'Vue de lecture agregee pour les tableaux de bord, sans acces direct aux tables de faits sous-jacentes.';

-- ----------------------------------------------------------------------------
-- Grants (etl_service : ecriture ; analyst : lecture large ; dashboard_viewer : vue uniquement)
-- ----------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA mart TO etl_service;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO analyst;
GRANT SELECT ON mart.v_popularity_dashboard TO dashboard_viewer;

ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT, INSERT, UPDATE ON TABLES TO etl_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO analyst;
