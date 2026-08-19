-- ============================================================================
-- Verification empirique du comportement des contraintes sur Snowflake
-- (C4.4.1, amorce du cahier de recettes)
--
-- Objectif different du script PostgreSQL equivalent : la ne s'agissait pas
-- de verifier que les contraintes rejettent les donnees invalides (elles le
-- font reellement sous PostgreSQL), mais de VERIFIER EMPIRIQUEMENT ce que
-- Snowflake applique vraiment. Snowflake declare la syntaxe PK/FK/NOT NULL
-- mais ne l'impose pas a l'ecriture, a l'exception de NOT NULL. Ce script
-- documente ce comportement plutot que de le supposer depuis la doc.
--
-- A executer dans Snowsight (ou via Claude Code) : premiere execution reelle
-- a faire cote utilisateur, les resultats observes sont a consigner ici en
-- remplacement des resultats attendus indiques en commentaire.
-- ============================================================================

USE WAREHOUSE gamelens_wh;
USE SCHEMA gamelens.mart;

-- Nettoyage prealable idempotent (memes principes que le script PostgreSQL)
DELETE FROM fact_prices WHERE game_id = 'test-0000-0000-0000-000000000001';
DELETE FROM fact_popularity_history WHERE game_id = 'test-0000-0000-0000-000000000001';
DELETE FROM dim_games WHERE game_id = 'test-0000-0000-0000-000000000001';
DELETE FROM dim_stores WHERE store_id = 'test-0000-0000-0000-000000000002';

-- Donnees de reference
INSERT INTO dim_games (game_id, unified_name, genre, metacritic_score, critical_tier)
VALUES ('test-0000-0000-0000-000000000001', 'Hades (test)', 'Roguelike', 93, 'Acclaimed');

INSERT INTO dim_stores (store_id, name, source_type)
VALUES ('test-0000-0000-0000-000000000002', 'GOG (test)', 'scraping');

-- TEST 1 : insertion valide -- ATTENDU : reussit
INSERT INTO fact_prices (game_id, store_id, price, collected_at)
VALUES ('test-0000-0000-0000-000000000001', 'test-0000-0000-0000-000000000002', 19.99, CURRENT_TIMESTAMP());

-- TEST 2 : unified_name NULL -- ATTENDU : ECHOUE (NOT NULL est le seul type de
-- contrainte reellement applique par Snowflake a l'ecriture)
INSERT INTO dim_games (game_id, unified_name) VALUES ('test-0000-0000-0000-000000000099', NULL);

-- TEST 3 : prix negatif -- ATTENDU (a confirmer empiriquement) : REUSSIT quand
-- meme, malgre le commentaire "doit rester > 0" sur la colonne : Snowflake
-- n'a pas de contrainte CHECK appliquee. Si ce test reussit sans erreur,
-- cela CONFIRME qu'un mecanisme d'integrite complementaire (test dbt) est
-- necessaire, ce n'est pas une anomalie du schema.
INSERT INTO fact_prices (game_id, store_id, price, collected_at)
VALUES ('test-0000-0000-0000-000000000001', 'test-0000-0000-0000-000000000002', -5.00, CURRENT_TIMESTAMP());

-- TEST 4 : game_id inexistant -- ATTENDU (a confirmer) : REUSSIT quand meme,
-- la contrainte REFERENCES n'est pas appliquee par Snowflake.
INSERT INTO fact_prices (game_id, store_id, price, collected_at)
VALUES ('inexistant-0000-0000-0000-000000000000', 'test-0000-0000-0000-000000000002', 9.99, CURRENT_TIMESTAMP());

-- TEST 5 : doublon (game_id, day) -- ATTENDU (a confirmer) : REUSSIT quand
-- meme, la PRIMARY KEY n'est pas appliquee par Snowflake.
INSERT INTO fact_popularity_history (game_id, day, avg_player_count) VALUES ('test-0000-0000-0000-000000000001', '2026-08-01', 5000);
INSERT INTO fact_popularity_history (game_id, day, avg_player_count) VALUES ('test-0000-0000-0000-000000000001', '2026-08-01', 5200);

-- TEST 6 : la vue self-service fonctionne -- ATTENDU : reussit, 1 ligne
SELECT unified_name, day, avg_player_count FROM v_popularity_dashboard WHERE unified_name = 'Hades (test)';

-- Nettoyage final
DELETE FROM fact_prices WHERE game_id IN ('test-0000-0000-0000-000000000001', 'inexistant-0000-0000-0000-000000000000');
DELETE FROM fact_popularity_history WHERE game_id = 'test-0000-0000-0000-000000000001';
DELETE FROM dim_games WHERE game_id IN ('test-0000-0000-0000-000000000001', 'test-0000-0000-0000-000000000099');
DELETE FROM dim_stores WHERE store_id = 'test-0000-0000-0000-000000000002';

-- A faire apres execution reelle : remplacer les commentaires "ATTENDU" par
-- les resultats effectivement observes, avec capture d'ecran ou export des
-- messages d'erreur/succes Snowsight pour le cahier de recettes final.
