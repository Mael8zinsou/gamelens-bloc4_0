-- ============================================================================
-- Couche Silver speed : popularite DIFFUSEE (source Twitch)
-- ----------------------------------------------------------------------------
-- Fichier SEPARE de sql/schema_silver_speed.sql, pour la meme raison que
-- sql/schema_bronze.sql et sql/schema_supervision.sql le sont : les scripts de
-- sql/ ne rejouent pas sur une instance deja initialisee, docker-entrypoint
-- ne les executant que sur un volume vierge. Une brique ajoutee apres coup doit
-- donc etre applicable seule, a la main, sans rejouer un schema eprouve.
--
-- Tout ici est garde par IF NOT EXISTS ou OR REPLACE : ce fichier se rejoue
-- autant de fois qu'on veut.
--
-- ## Pourquoi une table distincte plutot que des colonnes de plus
--
-- La frequentation jouee et l'audience diffusee ont le meme grain apparent
-- (un titre, un instant) mais pas la meme disponibilite : un jeu sans aucun
-- stream en direct rend zero spectateur, ce qui est une observation valide,
-- alors qu'un titre retire du catalogue Steam ne rend RIEN. Les fusionner
-- imposerait de distinguer le zero de l'absence dans une colonne nullable,
-- exactement le genre d'ambiguite que la couche Bronze existe pour eviter.
--
-- Les deux flux se rejoignent plus loin, a la promotion Gold, ou
-- mart.fact_popularity_history porte les quatre colonnes cote a cote. C'est le
-- modele en colonnes larges pose au Bloc 2, sans EAV.
--
-- ## L'axe que cette source ajoute
--
-- Steam mesure qui JOUE, Twitch mesure qui REGARDE. Ce n'est pas une source de
-- plus sur le meme axe mais un second axe, et le seul indicateur avance du
-- dispositif : une poussee d'audience precede generalement une poussee de
-- ventes. C'est aussi ce qui fait enfin travailler speed.game_mapping, table
-- dont le nom annonce la resolution d'identifiants entre plateformes et qui,
-- jusqu'a cette source, ne resolvait que des identifiants Steam.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- viewer_count_events : evenements bruts de l'audience diffusee.
--
-- Meme strategie de livraison que speed.player_count_events, et c'est
-- deliberement le meme raisonnement : Kafka garantit un at-least-once, donc un
-- evenement peut etre reconsomme apres un redemarrage du consumer. La
-- contrainte UNIQUE (steam_appid, collected_at) plus un ON CONFLICT DO NOTHING
-- rendent le puits idempotent, ce qui produit un effectively-once sans
-- transaction distribuee.
--
-- La clef est steam_appid et non twitch_game_id : c'est l'identifiant pivot de
-- la plateforme, celui que porte game_mapping et sur lequel se fait la jointure
-- avec la frequentation jouee. twitch_game_id est conserve a cote, comme trace
-- de la resolution effectivement operee.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS speed.viewer_count_events (
    event_id        BIGSERIAL PRIMARY KEY,
    steam_appid     INTEGER     NOT NULL REFERENCES speed.game_mapping(steam_appid),
    twitch_game_id  TEXT        NOT NULL,
    viewer_count    INTEGER     NOT NULL CHECK (viewer_count >= 0),
    stream_count    INTEGER     NOT NULL CHECK (stream_count >= 0),
    collected_at    TIMESTAMPTZ NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    kafka_partition INTEGER,
    kafka_offset    BIGINT,
    CONSTRAINT uq_viewer_count_event UNIQUE (steam_appid, collected_at)
);

CREATE INDEX IF NOT EXISTS idx_viewer_count_events_collecte
    ON speed.viewer_count_events (collected_at DESC);

COMMENT ON TABLE speed.viewer_count_events IS
    'Releves d''audience diffusee sur Twitch, un enregistrement par titre et par instant de collecte. Puits idempotent du topic gamelens.twitch.viewer_count.';

COMMENT ON COLUMN speed.viewer_count_events.event_id IS 'Clef primaire technique.';
COMMENT ON COLUMN speed.viewer_count_events.steam_appid IS
    'Titre concerne, identifiant pivot de la plateforme. Reference speed.game_mapping.';
COMMENT ON COLUMN speed.viewer_count_events.twitch_game_id IS
    'Identifiant Twitch effectivement interroge. Conserve pour tracer la resolution operee par game_mapping.';
COMMENT ON COLUMN speed.viewer_count_events.viewer_count IS
    'Somme des spectateurs de tous les streams en direct du titre a cet instant. Zero est une observation valide, pas une absence.';
COMMENT ON COLUMN speed.viewer_count_events.stream_count IS
    'Nombre de streams en direct a cet instant. Distingue une forte audience concentree d''une audience diffuse.';
COMMENT ON COLUMN speed.viewer_count_events.collected_at IS
    'Instant du releve, cote GameLens. Avec steam_appid, definit le grain et porte l''idempotence.';
COMMENT ON COLUMN speed.viewer_count_events.ingested_at IS
    'Instant de l''ecriture en base. L''ecart avec collected_at est la latence supervisee.';
COMMENT ON COLUMN speed.viewer_count_events.kafka_partition IS 'Partition Kafka d''origine, conservee pour le diagnostic.';
COMMENT ON COLUMN speed.viewer_count_events.kafka_offset IS 'Offset Kafka d''origine, conserve pour le diagnostic.';

-- ----------------------------------------------------------------------------
-- v_daily_viewer_stats : agregat journalier, symetrique de
-- v_daily_player_stats. C'est la vue que consomme la promotion Gold.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW speed.v_daily_viewer_stats AS
SELECT
    e.steam_appid,
    m.unified_name,
    (e.collected_at AT TIME ZONE 'UTC')::date       AS day,
    ROUND(AVG(e.viewer_count), 2)                   AS avg_viewer_count,
    MAX(e.viewer_count)                             AS max_viewer_count,
    ROUND(AVG(e.stream_count), 2)                   AS avg_stream_count,
    COUNT(*)                                        AS observation_count
FROM speed.viewer_count_events e
JOIN speed.game_mapping m ON m.steam_appid = e.steam_appid
GROUP BY e.steam_appid, m.unified_name, (e.collected_at AT TIME ZONE 'UTC')::date;

COMMENT ON VIEW speed.v_daily_viewer_stats IS
    'Agregat journalier de l''audience diffusee, promu vers mart.fact_popularity_history par le DAG de promotion. observation_count sert de controle de completude.';

-- ----------------------------------------------------------------------------
-- Droits : strictement le meme modele que le reste de la couche Silver.
--
-- Les roles existent deja (sql/schema_silver_speed.sql les cree). On ne les
-- recree pas ici : un second endroit de creation produirait deux definitions
-- concurrentes du meme modele de securite, defaut deja rencontre et corrige
-- (OBS-25). On accorde seulement, sur les objets nouveaux.
--
-- etl_service ecrit sans jamais supprimer, analyst lit les evenements,
-- dashboard_viewer ne voit que l'agregat. Le role de restitution n'accede
-- jamais aux tables, seulement aux vues.
-- ----------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE ON speed.viewer_count_events TO etl_service;
GRANT USAGE, SELECT ON SEQUENCE speed.viewer_count_events_event_id_seq TO etl_service;
GRANT SELECT ON speed.viewer_count_events TO analyst;
GRANT SELECT ON speed.v_daily_viewer_stats TO analyst, dashboard_viewer;
