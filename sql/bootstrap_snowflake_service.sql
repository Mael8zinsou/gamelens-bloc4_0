-- ============================================================================
-- Amorcage du compte d'essai Snowflake : utilisateur de service GameLens.
--
-- A executer UNE SEULE FOIS dans Snowsight, immediatement apres la creation du
-- compte, avec le role ACCOUNTADMIN.
--
-- Pourquoi un utilisateur de service distinct du compte de connexion :
-- Snowflake impose l'authentification multifacteur aux utilisateurs humains sur
-- les comptes recents. Un pipeline ne peut pas valider une notification, donc
-- l'acces programmatique passe necessairement par un utilisateur non humain
-- authentifie par paire de cles. Ce n'est pas un contournement, c'est la
-- pratique attendue en production, et cela evite au passage que les
-- identifiants personnels du candidat circulent dans la configuration.
-- ============================================================================

USE ROLE ACCOUNTADMIN;

-- TYPE = SERVICE : utilisateur non humain, exempte de MFA et restreint aux
-- authentifications par paire de cles ou OAuth. Si votre compte ne connait pas
-- encore ce type, remplacer par TYPE = LEGACY_SERVICE, ou retirer la ligne.
CREATE USER IF NOT EXISTS GAMELENS_SERVICE
    TYPE = SERVICE
    DEFAULT_ROLE = ACCOUNTADMIN
    DEFAULT_WAREHOUSE = gamelens_wh
    COMMENT = 'Utilisateur de service GameLens, certification RNCP39586 Bloc 4.';

-- ACCOUNTADMIN est necessaire le temps de creer l'entrepot virtuel, la base et
-- les roles applicatifs (sql/schema_gold_snowflake.sql). A restreindre ensuite
-- vers gamelens_etl_service, une fois le schema en place.
GRANT ROLE ACCOUNTADMIN TO USER GAMELENS_SERVICE;

-- ----------------------------------------------------------------------------
-- Etape suivante : associer la cle publique generee par
-- `python entrepot/generer_cle.py`, qui affiche la commande exacte, de la forme
--
--     ALTER USER GAMELENS_SERVICE SET RSA_PUBLIC_KEY='MIIBIjANBgkq...';
--
-- La cle doit etre collee SANS les lignes -----BEGIN/END----- et SANS retour a
-- la ligne. C'est l'erreur la plus frequente de cette etape, et elle se
-- manifeste plus tard par un message parlant de jeton JWT invalide, qui
-- n'oriente pas vers la vraie cause.
-- ----------------------------------------------------------------------------

-- Controle apres association : le champ RSA_PUBLIC_KEY_FP doit etre renseigne.
DESC USER GAMELENS_SERVICE;

-- Identifiant de compte a reporter dans .env sous SNOWFLAKE_ACCOUNT.
-- Le resultat s'ecrit ORGANISATION.COMPTE : le reporter avec un TIRET,
-- ORGANISATION-COMPTE, qui est la forme attendue par le connecteur.
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS identifiant_compte;
