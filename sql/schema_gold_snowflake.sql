-- ============================================================================
-- GameLens - Schema Gold (entrepot de donnees), Bloc 4 - C4.2.1
-- Version Snowflake reelle (compte d'essai), succedant au prototype PostgreSQL
-- (sql/schema_gold.sql) utilise pour la mise au point initiale.
--
-- A executer dans Snowsight ou via Claude Code (connecteur Python / SnowSQL).
-- Non teste depuis l'environnement de conception (pas d'acces reseau a
-- Snowflake depuis ce sandbox) : premiere execution reelle a faire cote
-- utilisateur. Documenter ici tout ajustement necessaire.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Warehouse : dimensionne au plus petit format, suspension automatique rapide
-- pour preserver les credits du compte d'essai (point de vigilance A4.1 :
-- estimation des couts).
-- ----------------------------------------------------------------------------
CREATE WAREHOUSE IF NOT EXISTS gamelens_wh
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Warehouse de developpement GameLens, XS avec suspension automatique a 60s.';

CREATE DATABASE IF NOT EXISTS gamelens
    COMMENT = 'Base GameLens, Kestrel Interactive - certification RNCP39586, Bloc 4.';

CREATE SCHEMA IF NOT EXISTS gamelens.mart
    COMMENT = 'Couche Gold : entrepot analytique en lecture pour les tableaux de bord et les analyses (Bloc 2).';

USE WAREHOUSE gamelens_wh;
USE SCHEMA gamelens.mart;

-- ----------------------------------------------------------------------------
-- Point d'architecture important, a assumer explicitement a l'oral :
-- Snowflake accepte la syntaxe PRIMARY KEY / FOREIGN KEY / CHECK mais ne les
-- IMPOSE PAS a l'ecriture (constraints informatives, NOT ENFORCED), a la
-- difference de PostgreSQL utilise au prototypage. Seul NOT NULL est reellement
-- applique. Elles sont neanmoins declarees ici : elles servent de metadonnees
-- au moteur d'optimisation (elimination de jointures) et aux outils de BI qui
-- lisent le dictionnaire de donnees.
-- L'integrite reelle (equivalent du CHECK price > 0, de la FK vers dim_games,
-- de l'unicite game_id+day) est reportee sur des tests dbt executes a chaque
-- run du pipeline (not_null, unique, relationships, expression_is_true) :
-- une violation fait echouer le run plutot que d'etre silencieusement
-- acceptee. Ce report est un choix d'architecture assume, pas un oubli.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- dim_games
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE gamelens.mart.dim_games (
    game_id           VARCHAR(36) DEFAULT UUID_STRING() PRIMARY KEY COMMENT 'Identifiant interne, independant des identifiants sources.',
    unified_name      VARCHAR NOT NULL,
    genre             VARCHAR,
    developer         VARCHAR,
    release_date      DATE,
    metacritic_score  NUMBER(3, 0) COMMENT 'Attendu entre 0 et 100 ; regle verifiee par test dbt, non appliquee par Snowflake.',
    critical_tier     VARCHAR COMMENT 'Acclaimed / Favorable / Mixed, derive de metacritic_score par le modele dbt (Bloc 1, Annexe 10).',
    steam_appid       NUMBER(10, 0),
    twitch_game_id    VARCHAR,
    gog_slug          VARCHAR,
    rawg_id           NUMBER(10, 0),
    gold_loaded_at    TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Referentiel unifie des jeux suivis (portefeuille Kestrel Interactive + panel concurrent). Grain : un enregistrement par jeu.';

-- ----------------------------------------------------------------------------
-- dim_stores
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE gamelens.mart.dim_stores (
    store_id     VARCHAR(36) DEFAULT UUID_STRING() PRIMARY KEY,
    name         VARCHAR NOT NULL UNIQUE,
    base_url     VARCHAR,
    source_type  VARCHAR NOT NULL COMMENT 'api ou scraping ; valeur controlee par test dbt accepted_values.'
)
COMMENT = 'Boutiques suivies pour la tarification (ex : Steam, GOG).';

-- ----------------------------------------------------------------------------
-- fact_prices (grain : un enregistrement par jeu, boutique, date de collecte)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE gamelens.mart.fact_prices (
    price_id        VARCHAR(36) DEFAULT UUID_STRING() PRIMARY KEY,
    game_id         VARCHAR(36) NOT NULL REFERENCES gamelens.mart.dim_games(game_id),
    store_id        VARCHAR(36) NOT NULL REFERENCES gamelens.mart.dim_stores(store_id),
    price           NUMBER(10, 2) NOT NULL COMMENT 'Doit rester > 0 ; verifie par test dbt expression_is_true.',
    currency        CHAR(3) NOT NULL DEFAULT 'EUR',
    promotion_flag  BOOLEAN NOT NULL DEFAULT FALSE,
    collected_at    TIMESTAMP_NTZ NOT NULL
)
COMMENT = 'Tarifs collectes par jeu et par boutique. Alimentee par le scraping GOG et les API de tarification (Bloc 1).';

-- ----------------------------------------------------------------------------
-- fact_popularity_history (grain : un enregistrement par jeu et par jour)
-- CLUSTER BY remplace les index PostgreSQL : c'est le levier de performance
-- ("rapidite", critere C4.2.1) propre au moteur Snowflake, qui organise le
-- stockage en micro-partitions plutot que d'utiliser des index classiques.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE TABLE gamelens.mart.fact_popularity_history (
    game_id           VARCHAR(36) NOT NULL REFERENCES gamelens.mart.dim_games(game_id),
    day               DATE NOT NULL,
    avg_player_count  NUMBER(12, 2),
    max_player_count  NUMBER(10, 0),
    avg_viewer_count  NUMBER(12, 2),
    max_viewer_count  NUMBER(10, 0),
    PRIMARY KEY (game_id, day)
)
CLUSTER BY (day)
COMMENT = 'Agregats journaliers de popularite jouee et diffusee, promus depuis la couche Silver speed (Bloc 1, 3.4).';

-- ----------------------------------------------------------------------------
-- Vue d'acces en self-service (volet accessibilite du critere C4.2.1)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW gamelens.mart.v_popularity_dashboard
COMMENT = 'Vue de lecture agregee pour les tableaux de bord, sans acces direct aux tables de faits sous-jacentes.'
AS
SELECT
    g.game_id,
    g.unified_name,
    g.genre,
    g.critical_tier,
    h.day,
    h.avg_player_count,
    h.avg_viewer_count
FROM gamelens.mart.dim_games g
JOIN gamelens.mart.fact_popularity_history h ON g.game_id = h.game_id;

-- ----------------------------------------------------------------------------
-- Roles et droits (volet securite du critere C4.2.1)
-- Repris des 4 roles definis au Bloc 1 : admin (proprietaire), etl_service
-- (ecriture), analyst (lecture large), dashboard_viewer (vue uniquement).
-- Sur Snowflake, un role doit aussi recevoir l'usage du warehouse pour
-- pouvoir executer la moindre requete : oubli frequent, source classique de
-- "insufficient privileges" a l'execution malgre des GRANT SELECT corrects.
-- ----------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS gamelens_etl_service;
CREATE ROLE IF NOT EXISTS gamelens_analyst;
CREATE ROLE IF NOT EXISTS gamelens_dashboard_viewer;

GRANT USAGE ON WAREHOUSE gamelens_wh TO ROLE gamelens_etl_service;
GRANT USAGE ON WAREHOUSE gamelens_wh TO ROLE gamelens_analyst;
GRANT USAGE ON WAREHOUSE gamelens_wh TO ROLE gamelens_dashboard_viewer;

GRANT USAGE ON DATABASE gamelens TO ROLE gamelens_etl_service;
GRANT USAGE ON DATABASE gamelens TO ROLE gamelens_analyst;
GRANT USAGE ON DATABASE gamelens TO ROLE gamelens_dashboard_viewer;

GRANT USAGE ON SCHEMA gamelens.mart TO ROLE gamelens_etl_service;
GRANT USAGE ON SCHEMA gamelens.mart TO ROLE gamelens_analyst;
GRANT USAGE ON SCHEMA gamelens.mart TO ROLE gamelens_dashboard_viewer;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA gamelens.mart TO ROLE gamelens_etl_service;
GRANT SELECT ON ALL TABLES IN SCHEMA gamelens.mart TO ROLE gamelens_analyst;
GRANT SELECT ON gamelens.mart.v_popularity_dashboard TO ROLE gamelens_dashboard_viewer;

-- Droits par defaut pour les futures tables creees par le pipeline (dbt tourne
-- generalement sous le role etl_service).
GRANT SELECT, INSERT, UPDATE ON FUTURE TABLES IN SCHEMA gamelens.mart TO ROLE gamelens_etl_service;
GRANT SELECT ON FUTURE TABLES IN SCHEMA gamelens.mart TO ROLE gamelens_analyst;

-- A completer cote utilisateur : GRANT ROLE gamelens_etl_service TO USER <ton_user>;
-- (necessite de connaitre le nom d'utilisateur reel du compte d'essai)
