-- ============================================================================
-- Documentation des colonnes de la couche Gold Snowflake
-- ----------------------------------------------------------------------------
-- Fichier SEPARE de sql/schema_gold_snowflake.sql, et ce n'est pas un caprice
-- d'organisation : le fichier de schema contient des CREATE OR REPLACE TABLE
-- et ne peut donc pas etre rejoue sur la base de demonstration sans la
-- detruire. Documenter une colonne oubliee imposerait alors de choisir entre
-- laisser le trou et perdre les donnees.
--
-- COMMENT ON est en revanche idempotent et non destructif : ce fichier se
-- rejoue autant de fois qu'on veut, sur n'importe quelle base.
--
-- Ces commentaires sont la SOURCE du dictionnaire publie en annexe de la
-- documentation technique, genere par :
--     python outils/generer_dictionnaire.py --cible snowflake
-- La chaine d'integration continue echoue si le dictionnaire n'est plus a jour.
-- ============================================================================

USE SCHEMA gamelens.mart;

-- ----------------------------------------------------------------------------
-- dim_games
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN dim_games.game_id IS
    'Clef primaire interne UUID, independante des identifiants sources (convention Bloc 2). Declaree PRIMARY KEY mais non appliquee par Snowflake.';
COMMENT ON COLUMN dim_games.unified_name IS
    'Nom canonique retenu par GameLens. NOT NULL reellement applique par le moteur.';
COMMENT ON COLUMN dim_games.genre IS
    'Genre principal. Sert de partition au classement distribue calcule par Snowpark.';
COMMENT ON COLUMN dim_games.developer IS 'Studio de developpement.';
COMMENT ON COLUMN dim_games.release_date IS 'Date de sortie commerciale. Non alimentee a ce jour.';
COMMENT ON COLUMN dim_games.metacritic_score IS
    'Note critique agregee, attendue entre 0 et 100. Bornes verifiees par verifier_gold.py, non par le moteur.';
COMMENT ON COLUMN dim_games.critical_tier IS
    'Acclaimed, Favorable ou Mixed. Vide a ce jour : la derivation depuis metacritic_score suppose un catalogue (RAWG ou IGDB) non branche.';
COMMENT ON COLUMN dim_games.steam_appid IS
    'Identifiant Steam, clef naturelle. Contrainte UNIQUE declaree mais non appliquee : le doublon est rattrape par controle applicatif.';
COMMENT ON COLUMN dim_games.twitch_game_id IS 'Identifiant de categorie Twitch, propage depuis speed.game_mapping. Resolu pour la totalite du panel depuis le 08/09/2026.';
COMMENT ON COLUMN dim_games.gog_slug IS
    'Identifiant GOG. Conserve bien que le suivi GOG soit hors perimetre depuis le Bloc 3.';
COMMENT ON COLUMN dim_games.rawg_id IS 'Identifiant RAWG, source catalogue. Source non branchee a ce jour.';
COMMENT ON COLUMN dim_games.gold_loaded_at IS 'Instant de promotion vers la couche Gold.';

-- ----------------------------------------------------------------------------
-- dim_stores
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN dim_stores.store_id IS 'Clef primaire interne UUID.';
COMMENT ON COLUMN dim_stores.name IS 'Nom de la boutique. UNIQUE declare, non applique.';
COMMENT ON COLUMN dim_stores.base_url IS 'Adresse racine de la boutique.';
COMMENT ON COLUMN dim_stores.source_type IS
    'api ou scraping. Valeur controlee par test dbt accepted_values, pas par le moteur.';

-- ----------------------------------------------------------------------------
-- fact_prices : grain (game_id, store_id, collected_at)
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN fact_prices.price_id IS 'Clef primaire interne UUID.';
COMMENT ON COLUMN fact_prices.game_id IS
    'Jeu concerne. REFERENCES dim_games declare, non applique : l''orphelin est rattrape par controle applicatif.';
COMMENT ON COLUMN fact_prices.store_id IS 'Boutique concernee. REFERENCES dim_stores declare, non applique.';
COMMENT ON COLUMN fact_prices.price IS
    'Prix effectivement paye, en devise currency. Doit rester strictement positif ; verifie par controle applicatif.';
COMMENT ON COLUMN fact_prices.currency IS 'Devise ISO 4217, sur 3 caracteres. Longueur reellement appliquee.';
COMMENT ON COLUMN fact_prices.promotion_flag IS 'Vrai si le releve correspond a une remise en cours.';
COMMENT ON COLUMN fact_prices.collected_at IS
    'Instant du releve. Avec game_id et store_id, definit le grain.';

-- ----------------------------------------------------------------------------
-- fact_popularity_history : grain journalier (game_id, day)
-- ----------------------------------------------------------------------------
COMMENT ON COLUMN fact_popularity_history.game_id IS
    'Jeu concerne. REFERENCES dim_games declare, non applique.';
COMMENT ON COLUMN fact_popularity_history.day IS
    'Journee agregee. Avec game_id, definit le grain. Sert egalement de clef de regroupement du stockage (CLUSTER BY).';
COMMENT ON COLUMN fact_popularity_history.avg_player_count IS
    'Moyenne des releves de frequentation de la journee. Colonne large, pas de modele EAV.';
COMMENT ON COLUMN fact_popularity_history.max_player_count IS 'Pic de frequentation de la journee.';
COMMENT ON COLUMN fact_popularity_history.avg_viewer_count IS
    'Moyenne journaliere de l''audience diffusee sur Twitch, somme des spectateurs des 100 streams les plus regardes. Nulle si le titre n''a pas de categorie Twitch resolue.';
COMMENT ON COLUMN fact_popularity_history.max_viewer_count IS 'Pic d''audience diffusee de la journee, sur les memes releves.';

-- ----------------------------------------------------------------------------
-- Commentaires de TABLE
-- ----------------------------------------------------------------------------
-- Ajoutes en session 13. Ce fichier n'avait jusque-la que des COMMENT ON COLUMN,
-- ce qui laissait les commentaires de table incorrigibles : ils ne vivaient que
-- dans la clause COMMENT = de sql/schema_gold_snowflake.sql, fichier qui ne peut
-- pas etre rejoue sans detruire la couche de demonstration. Deux d'entre eux
-- annoncaient donc encore le scraping GOG, hors perimetre depuis le Bloc 3, et
-- remontaient tels quels dans le dictionnaire publie en annexe.
--
-- Les quatre tables sont couvertes, y compris celles dont le texte etait juste :
-- le manque n'etait pas dans un commentaire, il etait dans l'absence de tout
-- moyen de les corriger.
COMMENT ON TABLE dim_games IS
    'Referentiel unifie des jeux suivis (portefeuille Kestrel Interactive + panel concurrent). Grain : un enregistrement par jeu.';
COMMENT ON TABLE dim_stores IS
    'Boutiques suivies pour la tarification. Une seule a ce jour, Steam : le suivi GOG est hors perimetre depuis l''arbitrage du Bloc 3 (3.3).';
COMMENT ON TABLE fact_prices IS
    'Tarifs collectes par jeu et par boutique. Alimentee par l''API Steam appdetails (price_overview), qui remplace le scraping GOG sorti du perimetre par l''arbitrage du Bloc 3 (3.3).';
COMMENT ON TABLE fact_popularity_history IS
    'Agregats journaliers de popularite jouee et diffusee, promus depuis la couche Silver speed (Bloc 1, 3.4).';
