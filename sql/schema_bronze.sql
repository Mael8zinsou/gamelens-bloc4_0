-- ============================================================================
-- Couche Bronze : archive des reponses d'API telles que recues
-- ----------------------------------------------------------------------------
-- L'architecture Medallion du Bloc 1 declare une couche Bronze sur S3. Elle
-- n'avait jamais ete construite : la chaine allait de l'API a Silver
-- directement, et la reponse d'origine etait jetee dans la ligne meme qui en
-- extrayait la valeur utile.
--
-- Ecart assume avec la declaration du Bloc 1 : cette couche est ici une table
-- PostgreSQL et non un stockage objet. Le support change, la PROPRIETE
-- RECHERCHEE est la meme, et c'est elle qui compte : disposer de la matiere
-- premiere pour recalculer si une transformation se revele fausse. Un stockage
-- objet apporterait le cout au repos et la duree de conservation longue ; a
-- l'echelle de ce projet il n'apporterait rien d'autre, et il ferait dependre
-- la demonstration d'un service tiers de plus.
--
-- Pourquoi cette couche compte particulierement ici : les sources ne sont pas
-- rejouables. Personne ne dira jamais combien de joueurs etaient connectes
-- mardi dernier, ni a quel prix un jeu etait vendu ce jour-la. Un defaut de
-- transformation decouvert dans trois mois aurait donc corrompu trois mois
-- d'historique DEFINITIVEMENT, sans aucun chemin de reparation. C'est le seul
-- endroit du projet ou une erreur serait irrattrapable.
--
-- Ce que Kafka n'apporte pas, malgre sa retention de 168 heures : il transporte
-- le message DEJA TRANSFORME, pas la reponse d'origine, et sept jours est une
-- fenetre de retention, pas un archivage.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS bronze;

COMMENT ON SCHEMA bronze IS
    'Reponses d''API telles que recues, jamais modifiees. Source de recalcul.';

-- ----------------------------------------------------------------------------
-- reponses_brutes
--
-- Grain : une ligne par appel d'API, qu'il ait abouti ou non.
--
-- Le "ou non" n'est pas une precaution de style. Avant cette table, une reponse
-- inexploitable (result != 1, absence de price_overview, erreur reseau) ne
-- produisait qu'un avertissement dans les journaux, puis disparaissait.
-- L'observation "Steam a repondu pour cet identifiant a cet instant, mais sans
-- donnee utilisable" est pourtant une information : un jeu retire du catalogue
-- ou une API qui se degrade ressemblent exactement a cela. La conserver rend
-- ces phenomenes analysables au lieu de les laisser au fil des logs.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bronze.reponses_brutes (
    reponse_id    BIGSERIAL PRIMARY KEY,
    source        TEXT        NOT NULL,
    identifiant   TEXT        NOT NULL,
    collecte_le   TIMESTAMPTZ NOT NULL,
    statut_http   INTEGER,
    exploitable   BOOLEAN     NOT NULL,
    motif_rejet   TEXT,
    charge        JSONB,
    archivee_le   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Meme discipline que le puits temps reel : le rejeu doit etre inoffensif.
    -- Une reprise Airflow apres echec partiel ne doit pas empiler deux fois la
    -- meme reponse. Le triplet suffit, collecte_le etant fixe une fois par
    -- cycle et non par titre.
    CONSTRAINT uq_reponses_brutes_grain UNIQUE (source, identifiant, collecte_le),

    -- Une reponse declaree inexploitable doit dire pourquoi. Sans cette
    -- contrainte, le cas le plus interessant serait aussi le moins documente.
    CONSTRAINT ck_reponses_brutes_motif
        CHECK (exploitable OR motif_rejet IS NOT NULL)
);

COMMENT ON TABLE bronze.reponses_brutes IS
    'Une ligne par appel d''API, abouti ou non. Jamais modifiee apres ecriture.';
COMMENT ON COLUMN bronze.reponses_brutes.source IS
    'Point d''appel interroge, ex. steam_player_count ou steam_appdetails.';
COMMENT ON COLUMN bronze.reponses_brutes.identifiant IS
    'Identifiant interroge cote source, en texte pour rester agnostique.';
COMMENT ON COLUMN bronze.reponses_brutes.collecte_le IS
    'Instant de l''appel, fourni par l''appelant, et non instant d''ecriture.';
COMMENT ON COLUMN bronze.reponses_brutes.charge IS
    'Corps de la reponse tel quel. NULL si la reponse n''a jamais ete obtenue.';
COMMENT ON COLUMN bronze.reponses_brutes.motif_rejet IS
    'Pourquoi la reponse est inexploitable. Obligatoire dans ce cas.';

CREATE INDEX IF NOT EXISTS idx_reponses_brutes_source_temps
    ON bronze.reponses_brutes (source, collecte_le DESC);

-- Retrouver rapidement les appels en echec est le premier usage analytique de
-- cette table. Index partiel : il ne porte que sur la minorite qui compte.
CREATE INDEX IF NOT EXISTS idx_reponses_brutes_inexploitables
    ON bronze.reponses_brutes (source, collecte_le DESC)
    WHERE NOT exploitable;

-- ----------------------------------------------------------------------------
-- Vue de suivi : taux d'exploitabilite par source sur 24 heures.
-- Alimente la supervision sans lui imposer de connaitre la structure de la
-- table, et donne un indicateur qui n'existait pas : la sante des SOURCES,
-- distincte de la sante des composants.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW bronze.v_sante_sources AS
SELECT
    source,
    count(*)                                            AS appels_24h,
    count(*) FILTER (WHERE exploitable)                 AS exploitables,
    count(*) FILTER (WHERE NOT exploitable)             AS rejets,
    round(
        100.0 * count(*) FILTER (WHERE exploitable) / NULLIF(count(*), 0),
        1
    )                                                   AS taux_exploitable_pct,
    max(collecte_le)                                    AS dernier_appel
FROM bronze.reponses_brutes
WHERE collecte_le >= now() - interval '24 hours'
GROUP BY source;

COMMENT ON VIEW bronze.v_sante_sources IS
    'Taux de reponses exploitables par source sur 24h. Sante des sources, pas des composants.';

-- ----------------------------------------------------------------------------
-- Droits, sur le meme modele que la couche Silver (Bloc 1).
--
-- Point important : aucun UPDATE n'est accorde, contrairement au schema speed.
-- Une archive qui peut etre modifiee n'est plus une archive. Le seul droit
-- d'ecriture est l'ajout.
-- ----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA bronze TO etl_service, analyst;

GRANT INSERT, SELECT ON bronze.reponses_brutes TO etl_service;
GRANT USAGE, SELECT ON SEQUENCE bronze.reponses_brutes_reponse_id_seq TO etl_service;

GRANT SELECT ON bronze.reponses_brutes TO analyst;
GRANT SELECT ON bronze.v_sante_sources TO analyst;

-- dashboard_viewer n'obtient rien : la donnee brute n'a pas vocation a etre
-- restituee, et l'exposer contournerait le cloisonnement pose au Bloc 1.

ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT INSERT, SELECT ON TABLES TO etl_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA bronze GRANT SELECT ON TABLES TO analyst;
