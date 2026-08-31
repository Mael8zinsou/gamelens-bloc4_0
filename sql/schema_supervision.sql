-- ============================================================================
-- GameLens - Couche de supervision, Bloc 4 - C4.3.1
-- ----------------------------------------------------------------------------
-- Le critere d'evaluation demande que la presentation du systeme de supervision
-- permette d'identifier quatre choses : les elements et indicateurs a
-- surveiller, les choix et la configuration des outils, la visualisation des
-- indicateurs, et le systeme d'alertes.
--
-- Ce fichier couvre le premier point. Les indicateurs sont definis en SQL, au
-- plus pres de la donnee, plutot que dans l'outil de visualisation : ils
-- restent ainsi versionnes, testables, et interrogeables par n'importe quel
-- client, y compris quand Grafana n'est pas demarre. L'outil affiche les
-- indicateurs, il ne les definit pas.
--
-- Deux angles morts vecus pendant la construction ont dicte ces choix :
--   - INC-004 : trois indicateurs au vert sur un service inatteignable, parce
--     que le healthcheck ne traversait pas le chemin reseau reel ;
--   - INC-007 : quatre collectes reelles, une seule tracee, la supervision
--     etant muette plutot qu'en erreur.
-- D'ou le principe retenu : surveiller aussi les ABSENCES, pas seulement les
-- erreurs. Un composant qui ne dit rien n'est pas un composant qui va bien.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Indicateur 1 : fraicheur de la donnee collectee.
-- L'indicateur le plus important de la plateforme : il repond a la seule
-- question que se pose un utilisateur d'un tableau de bord, « ce que je vois,
-- de quand date-t-il ? ».
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_indicateur_fraicheur AS
SELECT
    'frequentation'::text                                                   AS flux,
    max(collected_at)                                                       AS derniere_collecte,
    ROUND(EXTRACT(EPOCH FROM (now() - max(collected_at))) / 60.0, 1)        AS age_minutes,
    count(*) FILTER (WHERE collected_at > now() - INTERVAL '24 hours')      AS evenements_24h
FROM speed.player_count_events
UNION ALL
SELECT
    'tarification',
    max(collected_at),
    ROUND(EXTRACT(EPOCH FROM (now() - max(collected_at))) / 60.0, 1),
    count(*) FILTER (WHERE collected_at > now() - INTERVAL '24 hours')
FROM speed.price_snapshots;

COMMENT ON VIEW speed.v_indicateur_fraicheur IS
    'Age de la donnee la plus recente par flux. Indicateur principal de la plateforme.';

-- ----------------------------------------------------------------------------
-- Indicateur 2 : completude de la collecte.
-- Compare le nombre de titres reellement collectes au nombre de titres actifs
-- attendus. Detecte une source partiellement muette, cas qu'un simple
-- comptage de lignes ne revele pas.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_indicateur_completude AS
WITH attendus AS (
    SELECT count(*) AS n FROM speed.game_mapping WHERE is_active
),
collectes AS (
    SELECT count(DISTINCT steam_appid) AS n
    FROM speed.player_count_events
    WHERE collected_at > now() - INTERVAL '24 hours'
)
SELECT
    attendus.n                                                        AS titres_attendus,
    collectes.n                                                       AS titres_collectes_24h,
    attendus.n - collectes.n                                          AS titres_manquants,
    CASE WHEN attendus.n = 0 THEN NULL
         ELSE ROUND(100.0 * collectes.n / attendus.n, 1) END          AS taux_completude_pct
FROM attendus, collectes;

COMMENT ON VIEW speed.v_indicateur_completude IS
    'Titres distincts collectes sur 24h rapportes aux titres actifs. Detecte une source partiellement muette.';

-- ----------------------------------------------------------------------------
-- Indicateur 3 : latence du pipeline temps reel.
-- Ecart entre l'instant de collecte et l'instant d'ecriture en base. Mesure le
-- temps passe dans Kafka et dans le consumer, donc la sante de la chaine
-- elle-meme, independamment du volume.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_indicateur_latence AS
SELECT
    count(*)                                                                       AS echantillon_24h,
    ROUND(AVG(EXTRACT(EPOCH FROM (ingested_at - collected_at)))::numeric, 2)       AS latence_moyenne_s,
    ROUND(MAX(EXTRACT(EPOCH FROM (ingested_at - collected_at)))::numeric, 2)       AS latence_max_s,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (ingested_at - collected_at)))::numeric, 2)    AS latence_p95_s
FROM speed.player_count_events
WHERE collected_at > now() - INTERVAL '24 hours';

COMMENT ON VIEW speed.v_indicateur_latence IS
    'Temps ecoule entre collecte et ecriture en base. Le p95 est preferable a la moyenne, qu un seul pic suffit a rendre illisible.';

-- ----------------------------------------------------------------------------
-- Indicateur 4 : fiabilite des composants.
-- Taux de succes et duree par composant sur 24h, depuis le journal d'execution
-- alimente par tous les composants du pipeline.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_indicateur_fiabilite AS
SELECT
    component                                                             AS composant,
    count(*)                                                              AS executions_24h,
    count(*) FILTER (WHERE status = 'success')                            AS succes,
    count(*) FILTER (WHERE status = 'failed')                             AS echecs,
    count(*) FILTER (WHERE status = 'started')                            AS inachevees,
    ROUND(100.0 * count(*) FILTER (WHERE status = 'success')
          / NULLIF(count(*), 0), 1)                                       AS taux_succes_pct,
    ROUND(AVG(EXTRACT(EPOCH FROM (ended_at - started_at)))::numeric, 2)   AS duree_moyenne_s,
    max(started_at)                                                       AS derniere_execution
FROM speed.pipeline_runs
WHERE started_at > now() - INTERVAL '24 hours'
GROUP BY component;

COMMENT ON VIEW speed.v_indicateur_fiabilite IS
    'Taux de succes et duree par composant. Le compteur inachevees repere un composant interrompu avant sa fin, cas qui ne produit ni succes ni echec.';

-- ----------------------------------------------------------------------------
-- Indicateur 5 : fraicheur de l'entrepot Gold.
-- Distinct de l'indicateur 1 : la collecte peut tres bien fonctionner pendant
-- que la promotion journaliere est en panne. Surveiller seulement l'entree du
-- pipeline laisserait ce cas invisible.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_indicateur_gold AS
SELECT
    (SELECT max(day) FROM mart.fact_popularity_history)                    AS derniere_journee_promue,
    (SELECT count(*) FROM mart.fact_popularity_history
      WHERE day = (SELECT max(day) FROM mart.fact_popularity_history))     AS lignes_derniere_journee,
    (SELECT count(*) FROM mart.dim_games)                                  AS dimensions_jeux,
    CURRENT_DATE - (SELECT max(day) FROM mart.fact_popularity_history)     AS retard_jours;

COMMENT ON VIEW speed.v_indicateur_gold IS
    'Fraicheur de la couche Gold POSTGRESQL, et d elle seule : la couche Snowflake n a aucun indicateur (V-13). La collecte peut fonctionner alors que la promotion est en panne, les deux se surveillent separement.';

-- ----------------------------------------------------------------------------
-- Journal des alertes.
--
-- Les alertes sont persistees plutot que seulement notifiees. Une alerte qui
-- n'existe que le temps d'une notification ne permet ni de constater qu'un
-- probleme dure, ni de mesurer combien de temps il a dure. La colonne
-- resolue_le sert exactement a cela.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS speed.alertes (
    alerte_id     BIGSERIAL PRIMARY KEY,
    regle         TEXT        NOT NULL,
    severite      TEXT        NOT NULL CHECK (severite IN ('critique', 'avertissement')),
    message       TEXT        NOT NULL,
    valeur        NUMERIC,
    seuil         NUMERIC,
    declenchee_le TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolue_le    TIMESTAMPTZ
);

COMMENT ON TABLE speed.alertes IS
    'Historique des alertes declenchees. Persistees pour pouvoir mesurer la duree d un incident, pas seulement son occurrence.';

CREATE INDEX IF NOT EXISTS idx_alertes_ouvertes
    ON speed.alertes (regle) WHERE resolue_le IS NULL;

-- ----------------------------------------------------------------------------
-- Vue de synthese, destinee au bandeau superieur du tableau de bord Grafana.
-- Une seule ligne par element surveille, avec un etat lisible sans connaitre
-- les seuils.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_supervision_synthese AS
SELECT
    'Fraicheur frequentation'::text AS element,
    f.age_minutes                   AS valeur,
    'minutes'::text                 AS unite,
    CASE WHEN f.age_minutes IS NULL THEN 'inconnu'
         WHEN f.age_minutes > 90    THEN 'critique'
         WHEN f.age_minutes > 45    THEN 'avertissement'
         ELSE 'nominal' END         AS etat
FROM speed.v_indicateur_fraicheur f WHERE f.flux = 'frequentation'
UNION ALL
SELECT
    'Completude de la collecte',
    c.taux_completude_pct,
    'pourcent',
    CASE WHEN c.taux_completude_pct IS NULL THEN 'inconnu'
         WHEN c.taux_completude_pct < 80    THEN 'critique'
         WHEN c.taux_completude_pct < 100   THEN 'avertissement'
         ELSE 'nominal' END
FROM speed.v_indicateur_completude c
UNION ALL
SELECT
    'Latence du pipeline (p95)',
    l.latence_p95_s,
    'secondes',
    CASE WHEN l.latence_p95_s IS NULL THEN 'inconnu'
         WHEN l.latence_p95_s > 300  THEN 'critique'
         WHEN l.latence_p95_s > 60   THEN 'avertissement'
         ELSE 'nominal' END
FROM speed.v_indicateur_latence l
UNION ALL
SELECT
    'Retard de l entrepot Gold',
    g.retard_jours,
    'jours',
    CASE WHEN g.retard_jours IS NULL THEN 'inconnu'
         WHEN g.retard_jours > 1     THEN 'critique'
         WHEN g.retard_jours = 1     THEN 'avertissement'
         ELSE 'nominal' END
FROM speed.v_indicateur_gold g
UNION ALL
SELECT
    'Alertes ouvertes',
    (SELECT count(*) FROM speed.alertes WHERE resolue_le IS NULL),
    'alertes',
    CASE WHEN (SELECT count(*) FROM speed.alertes
                WHERE resolue_le IS NULL AND severite = 'critique') > 0 THEN 'critique'
         WHEN (SELECT count(*) FROM speed.alertes WHERE resolue_le IS NULL) > 0 THEN 'avertissement'
         ELSE 'nominal' END;

COMMENT ON VIEW speed.v_supervision_synthese IS
    'Etat consolide de la plateforme, un element surveille par ligne. Alimente le bandeau superieur du tableau de bord.';

-- ----------------------------------------------------------------------------
-- Droits : analyst et dashboard_viewer consultent la supervision sans pouvoir
-- ecrire dans le journal d'alertes, reserve a etl_service.
-- ----------------------------------------------------------------------------
GRANT SELECT ON speed.v_indicateur_fraicheur, speed.v_indicateur_completude,
                speed.v_indicateur_latence, speed.v_indicateur_fiabilite,
                speed.v_indicateur_gold, speed.v_supervision_synthese
    TO analyst, dashboard_viewer;

GRANT SELECT, INSERT, UPDATE ON speed.alertes TO etl_service;
GRANT USAGE, SELECT ON SEQUENCE speed.alertes_alerte_id_seq TO etl_service;
GRANT SELECT ON speed.alertes TO analyst;

-- ============================================================================
-- Dictionnaire de donnees : description de chaque colonne
-- Source du dictionnaire genere par outils/generer_dictionnaire.py (C4.3.3).
-- ============================================================================

COMMENT ON COLUMN speed.alertes.alerte_id IS 'Clef technique de l''alerte.';
COMMENT ON COLUMN speed.alertes.regle IS
    'Nom de la regle declenchante, tel que defini dans supervision/regles_alertes.py.';
COMMENT ON COLUMN speed.alertes.severite IS 'critique ou avertissement. Contraint par CHECK.';
COMMENT ON COLUMN speed.alertes.message IS 'Message formate, valeur observee et seuil substitues.';
COMMENT ON COLUMN speed.alertes.valeur IS 'Valeur observee au declenchement.';
COMMENT ON COLUMN speed.alertes.seuil IS 'Seuil franchi. Defini en SQL, jamais dans l''outil de restitution.';
COMMENT ON COLUMN speed.alertes.declenchee_le IS 'Premiere evaluation ayant constate le franchissement.';
COMMENT ON COLUMN speed.alertes.resolue_le IS
    'Evaluation ayant constate le retour sous seuil. Nul tant que l''alerte est ouverte. '
    'L''ecart avec declenchee_le mesure la duree d''incident.';
