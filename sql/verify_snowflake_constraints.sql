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
--
-- CORRIGE le 20/08/2026 : la premiere version utilisait un identifiant de
-- 38 caracteres dans une colonne VARCHAR(36). L'insertion echouait donc sur la
-- LONGUEUR, avant meme que la clef etrangere ne soit evaluee, et le test
-- semblait prouver que la contrainte etait appliquee alors qu'il ne l'avait
-- jamais mise a l'epreuve. Enseignement collateral : Snowflake applique bien
-- les contraintes de TYPE, longueur comprise, en plus de NOT NULL.
INSERT INTO fact_prices (game_id, store_id, price, collected_at)
VALUES ('absent-0000-0000-0000-0000000000001', 'test-0000-0000-0000-000000000002', 9.99, CURRENT_TIMESTAMP());

-- TEST 5 : doublon (game_id, day) -- ATTENDU (a confirmer) : REUSSIT quand
-- meme, la PRIMARY KEY n'est pas appliquee par Snowflake.
INSERT INTO fact_popularity_history (game_id, day, avg_player_count) VALUES ('test-0000-0000-0000-000000000001', '2026-08-01', 5000);
INSERT INTO fact_popularity_history (game_id, day, avg_player_count) VALUES ('test-0000-0000-0000-000000000001', '2026-08-01', 5200);

-- TEST 6 : la vue self-service fonctionne -- ATTENDU : reussit, 1 ligne
SELECT unified_name, day, avg_player_count FROM v_popularity_dashboard WHERE unified_name = 'Hades (test)';

-- Nettoyage final
DELETE FROM fact_prices WHERE game_id IN ('test-0000-0000-0000-000000000001', 'absent-0000-0000-0000-0000000000001');
DELETE FROM fact_popularity_history WHERE game_id = 'test-0000-0000-0000-000000000001';
DELETE FROM dim_games WHERE game_id IN ('test-0000-0000-0000-000000000001', 'test-0000-0000-0000-000000000099');
DELETE FROM dim_stores WHERE store_id = 'test-0000-0000-0000-000000000002';

-- A faire apres execution reelle : remplacer les commentaires "ATTENDU" par
-- les resultats effectivement observes, avec capture d'ecran ou export des
-- messages d'erreur/succes Snowsight pour le cahier de recettes final.

-- ============================================================================
-- RESULTATS REELLEMENT OBSERVES, execution du 20/08/2026
-- Compte RTZSXDV-PM63908, region AWS_EU_WEST_3, Snowflake 10.29.101
-- Execute via : entrepot/executer_sql.py ... --continuer
-- ----------------------------------------------------------------------------
--
-- | Contrainte declaree          | Appliquee a l'ecriture ? | Preuve            |
-- |------------------------------|--------------------------|-------------------|
-- | NOT NULL                     | OUI                      | TEST 2 rejete     |
-- | Type et longueur, VARCHAR(36)| OUI                      | voir ci-dessous   |
-- | CHECK (price > 0)            | NON                      | TEST 3 accepte    |
-- | FOREIGN KEY (REFERENCES)     | NON                      | TEST 4 accepte    |
-- | PRIMARY KEY (game_id, day)   | NON                      | TEST 5 accepte 2x |
--
-- Detail des messages obtenus :
--   TEST 2 : 100072 (22000) DML operation to table DIM_GAMES failed on column
--            UNIFIED_NAME with error: NULL result in a non-nullable column
--   TEST 3 : 1 ligne inseree avec price = -5.00
--   TEST 4 : 1 ligne inseree avec un game_id absent de dim_games
--   TEST 5 : 2 lignes inserees pour le meme couple (game_id, day)
--   TEST 6 : la vue retourne 2 lignes la ou une seule etait attendue
--
-- ----------------------------------------------------------------------------
-- DEFAUT DU TEST, CORRIGE EN COURS D'EXECUTION
--
-- La premiere execution a fait echouer le TEST 4 avec
--   100078 (22000) ... String 'inexistant-0000-0000-0000-000000000000' is too long
-- L'identifiant de test faisait 38 caracteres pour une colonne VARCHAR(36) :
-- l'insertion etait rejetee sur la LONGUEUR avant que la clef etrangere ne soit
-- evaluee. Le test semblait donc prouver que la contrainte etait appliquee,
-- alors qu'il ne l'avait jamais mise a l'epreuve. Identifiant raccourci a
-- 35 caracteres, le TEST 4 reussit alors : la clef etrangere n'est bien pas
-- appliquee.
--
-- Enseignement collateral, non anticipe : Snowflake applique les contraintes de
-- TYPE, longueur comprise, en plus de NOT NULL. Ce n'est donc pas
-- "seul NOT NULL est applique", formule qu'employait CLAUDE.md, mais plutot
-- "les contraintes portees par la colonne elle-meme sont appliquees, celles qui
-- portent sur une RELATION entre lignes ou entre tables ne le sont pas".
--
-- ----------------------------------------------------------------------------
-- CONSEQUENCE D'ARCHITECTURE, confirmee et non plus supposee
--
-- Le TEST 6 en donne la demonstration la plus parlante : deux lignes en doublon
-- sur ce qui est declare comme clef primaire traversent le schema sans
-- resistance et se retrouvent telles quelles dans la vue de restitution servie
-- aux tableaux de bord. Un analyste verrait deux mesures contradictoires pour le
-- meme jeu et le meme jour, sans qu'aucune alerte ne se declenche.
--
-- L'integrite doit donc etre reportee sur des tests executes a chaque run du
-- pipeline (dbt : not_null, unique, relationships, expression_is_true), qui font
-- ECHOUER le run plutot que de laisser passer. C'est le principe deja applique
-- cote PostgreSQL par la tache controler_qualite_gold du DAG de promotion.
-- ============================================================================
