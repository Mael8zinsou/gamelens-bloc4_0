-- ============================================================================
-- Base de metadonnees d'Airflow.
--
-- Airflow est heberge sur la meme instance PostgreSQL que la couche Silver
-- speed, mais dans une base distincte. C'est un choix assume d'echelle de
-- developpement : il evite une seconde instance sur un poste de travail, tout
-- en gardant les metadonnees d'orchestration separees des donnees metier.
-- En production, les deux seraient sur des instances distinctes, l'une etant
-- un composant d'outillage et l'autre un actif de donnees.
--
-- Ce fichier s'execute avant 10_schema_silver_speed.sql (ordre alphabetique),
-- au tout premier demarrage du conteneur uniquement.
-- ============================================================================

CREATE ROLE airflow WITH LOGIN PASSWORD 'devlocal_airflow';
CREATE DATABASE airflow OWNER airflow;
