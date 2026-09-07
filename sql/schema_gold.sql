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
    gold_loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Cle naturelle d'unicite, ajoutee lors de la construction du DAG de
    -- promotion : sans elle, un rejeu du DAG dupliquerait les dimensions.
    -- La cle primaire reste l'UUID interne, conformement aux conventions du
    -- Bloc 2 ; cette contrainte ne sert qu'a ancrer le ON CONFLICT.
    CONSTRAINT uq_dim_games_steam_appid UNIQUE (steam_appid)
);

COMMENT ON TABLE mart.dim_games IS
    'Referentiel unifie des jeux suivis (portefeuille Kestrel Interactive + panel concurrent). Grain : un enregistrement par jeu.';
COMMENT ON COLUMN mart.dim_games.critical_tier IS
    'Acclaimed, Favorable ou Mixed. Vide a ce jour : la derivation depuis metacritic_score suppose un catalogue (RAWG ou IGDB) non branche.';

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
    'Boutiques suivies pour la tarification. Une seule a ce jour, Steam : le suivi GOG est hors perimetre depuis l''arbitrage du Bloc 3 (3.3).';

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
    collected_at    TIMESTAMPTZ NOT NULL,
    -- Meme raison que pour dim_games : ancre du ON CONFLICT rendant la
    -- promotion des prix rejouable sans duplication.
    CONSTRAINT uq_fact_prices_grain UNIQUE (game_id, store_id, collected_at)
);

COMMENT ON TABLE mart.fact_prices IS
    'Tarifs collectes par jeu et par boutique. Alimentee par l''API Steam appdetails (price_overview), qui remplace le scraping GOG sorti du perimetre par l''arbitrage du Bloc 3 (3.3).';

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

-- ============================================================================
-- Dictionnaire de donnees : description de chaque colonne
-- Source du dictionnaire genere par outils/generer_dictionnaire.py (C4.3.3).
-- ============================================================================

COMMENT ON COLUMN mart.dim_games.game_id IS
    'Clef primaire interne UUID, independante des identifiants sources (convention Bloc 2).';
COMMENT ON COLUMN mart.dim_games.unified_name IS 'Nom canonique, promu depuis speed.game_mapping.';
COMMENT ON COLUMN mart.dim_games.genre IS 'Genre principal. Partition du classement distribue.';
COMMENT ON COLUMN mart.dim_games.developer IS 'Studio de developpement.';
COMMENT ON COLUMN mart.dim_games.release_date IS 'Date de sortie commerciale. Non alimentee a ce jour.';
COMMENT ON COLUMN mart.dim_games.metacritic_score IS
    'Note critique agregee, attendue entre 0 et 100. Bornes verifiees par controle applicatif.';
COMMENT ON COLUMN mart.dim_games.critical_tier IS
    'Acclaimed, Favorable ou Mixed. Vide a ce jour : la derivation depuis metacritic_score suppose un catalogue (RAWG ou IGDB) non branche.';
COMMENT ON COLUMN mart.dim_games.steam_appid IS 'Identifiant Steam. Clef naturelle, contrainte UNIQUE.';
COMMENT ON COLUMN mart.dim_games.twitch_game_id IS 'Identifiant Twitch. Source non branchee a ce jour.';
COMMENT ON COLUMN mart.dim_games.gog_slug IS
    'Identifiant GOG. Conserve bien que le suivi GOG soit hors perimetre depuis le Bloc 3.';
COMMENT ON COLUMN mart.dim_games.rawg_id IS 'Identifiant RAWG, source catalogue. Source non branchee a ce jour.';
COMMENT ON COLUMN mart.dim_games.gold_loaded_at IS 'Instant de promotion vers la couche Gold.';

COMMENT ON COLUMN mart.dim_stores.store_id IS 'Clef primaire interne UUID.';
COMMENT ON COLUMN mart.dim_stores.name IS 'Nom de la boutique. Unique.';
COMMENT ON COLUMN mart.dim_stores.base_url IS 'Adresse racine de la boutique.';
COMMENT ON COLUMN mart.dim_stores.source_type IS 'api ou scraping. Valeur controlee.';

COMMENT ON COLUMN mart.fact_prices.price_id IS 'Clef primaire interne UUID.';
COMMENT ON COLUMN mart.fact_prices.game_id IS 'Jeu concerne. Clef etrangere vers dim_games.';
COMMENT ON COLUMN mart.fact_prices.store_id IS 'Boutique concernee. Clef etrangere vers dim_stores.';
COMMENT ON COLUMN mart.fact_prices.price IS 'Prix effectivement paye, en devise currency. Doit rester strictement positif.';
COMMENT ON COLUMN mart.fact_prices.currency IS 'Devise ISO 4217.';
COMMENT ON COLUMN mart.fact_prices.promotion_flag IS 'Vrai si le releve correspond a une remise en cours.';
COMMENT ON COLUMN mart.fact_prices.collected_at IS
    'Instant du releve. Avec game_id et store_id, definit le grain (contrainte UNIQUE).';

COMMENT ON COLUMN mart.fact_popularity_history.game_id IS 'Jeu concerne. Clef etrangere vers dim_games.';
COMMENT ON COLUMN mart.fact_popularity_history.day IS
    'Journee agregee. Avec game_id, forme la clef primaire et definit le grain journalier.';
COMMENT ON COLUMN mart.fact_popularity_history.avg_player_count IS
    'Moyenne des releves de frequentation de la journee. Colonne large, pas de modele EAV.';
COMMENT ON COLUMN mart.fact_popularity_history.max_player_count IS 'Pic de frequentation de la journee.';
COMMENT ON COLUMN mart.fact_popularity_history.avg_viewer_count IS
    'Moyenne de l''audience diffusee. Nulle tant que la source Twitch n''est pas branchee.';
COMMENT ON COLUMN mart.fact_popularity_history.max_viewer_count IS 'Pic d''audience diffusee. Non alimente.';
