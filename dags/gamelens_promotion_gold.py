"""DAG de promotion de la couche Silver speed vers la couche Gold.

Deuxieme des trois methodes de traitement exigees par C4.2.2 : l'orchestrateur.

Ce DAG ne collecte pas le flux temps reel, qui est produit en continu par
`ingestion/steam_producer.py` et consomme par `ingestion/kafka_to_postgres.py`.
Il opere en aval, une fois par jour : il agrege les evenements de la journee,
alimente les dimensions et les tables de faits de l'entrepot, puis controle la
qualite du resultat.

Deux principes de conception, tous deux defendables a l'oral :

1. **Rejouabilite.** Chaque tache est idempotente. Un run relance sur une
   journee deja traitee met a jour au lieu de dupliquer, ce qui autorise le
   rattrapage d'un jour manque sans nettoyage prealable. C'est le meme principe
   que celui retenu pour le puits Kafka, applique au batch.

2. **La logique metier n'est pas dans le DAG.** La collecte tarifaire vit dans
   `ingestion/steam_prices.py` et le DAG ne fait que l'appeler. Le module est
   donc testable par la CI sans qu'Airflow soit demarre, et le meme code sert
   en ligne de commande et en orchestration.

Cible : le schema `mart` de PostgreSQL, et lui seul.

Precision necessaire depuis que le compte Snowflake existe (20/08/2026), sans
quoi ce DAG laisse croire qu'il alimente l'entrepot. Il ne l'alimente pas. La
couche Gold Snowflake est chargee par entrepot/snowpark_promotion.py, invoque
A LA MAIN depuis le conteneur d'outillage : aucun DAG ne la vise.

Les deux couches Gold divergent donc, et c'est visible : PostgreSQL suit la
collecte du jour, Snowflake porte l'etat du dernier chargement manuel. Ce
n'est pas un choix d'architecture, c'est une dette, suivie sous V-12 dans la
feuille de route d'exploitation.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task

CONNEXION = "gamelens_postgres"


@dag(
    dag_id="gamelens_promotion_gold",
    description="Promotion journaliere de la couche Silver speed vers l'entrepot Gold",
    doc_md=__doc__,
    schedule="30 2 * * *",  # 02h30 UTC, apres la fin de la journee collectee
    start_date=pendulum.datetime(2026, 8, 19, tz="UTC"),
    catchup=False,
    max_active_runs=1,  # evite deux promotions concurrentes sur le meme jour
    default_args={"retries": 2, "retry_delay": pendulum.duration(minutes=5)},
    # Permet de rejouer explicitement une journee passee depuis l'interface,
    # sans toucher au code ni desactiver catchup.
    params={"jour": ""},
    tags=["gamelens", "gold", "c4.2.2"],
)
def promotion_gold():
    @task
    def verifier_fraicheur_silver(**context) -> str:
        """Porte d'entree : refuse de promouvoir une journee sans donnee.

        Sans ce controle, un run sur une journee vide reussirait en ecrivant
        zero ligne, et la supervision verrait un succes la ou il y a en realite
        une rupture de collecte. Un pipeline qui reussit a ne rien faire est un
        pipeline qui ment.
        """
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        # Piege propre a Airflow 3 : logical_date vaut None pour un run
        # declenche manuellement, alors qu'Airflow 2 en fournissait toujours un.
        # Sans ce repli, la tache planterait sur un AttributeError au moment
        # meme ou l'on cherche a la tester a la main.
        date_logique = context.get("logical_date")
        jour = (
            context["params"].get("jour")
            or (date_logique.date().isoformat() if date_logique else None)
            or pendulum.now("UTC").date().isoformat()
        )
        hook = PostgresHook(postgres_conn_id=CONNEXION)
        total, titres = hook.get_first(
            """
            SELECT count(*), count(DISTINCT steam_appid)
            FROM speed.player_count_events
            WHERE (collected_at AT TIME ZONE 'UTC')::date = %s
            """,
            parameters=(jour,),
        )
        if total == 0:
            raise ValueError(
                f"Aucun evenement de frequentation pour le {jour}. "
                "Le pipeline temps reel a-t-il tourne ? Promotion interrompue."
            )
        print(f"{total} evenements sur {titres} titres pour le {jour}.")
        return jour

    @task
    def promouvoir_dimension_jeux(jour: str) -> int:
        """Aligne mart.dim_games sur le referentiel speed.game_mapping."""
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        hook = PostgresHook(postgres_conn_id=CONNEXION)
        conn = hook.get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mart.dim_games
                    (unified_name, genre, developer, steam_appid, twitch_game_id,
                     gold_loaded_at)
                SELECT m.unified_name, m.genre, m.developer, m.steam_appid,
                       m.twitch_game_id, now()
                FROM speed.game_mapping m
                WHERE m.is_active
                ON CONFLICT ON CONSTRAINT uq_dim_games_steam_appid DO UPDATE
                   SET unified_name   = EXCLUDED.unified_name,
                       genre          = EXCLUDED.genre,
                       developer      = EXCLUDED.developer,
                       twitch_game_id = EXCLUDED.twitch_game_id,
                       gold_loaded_at = now()
                """
            )
            lignes = cur.rowcount
        print(f"{lignes} dimension(s) jeu alignee(s) pour le {jour}.")
        return lignes

    @task
    def collecter_tarifs_steam() -> int:
        """Releve tarifaire du jour, ecrit en Silver speed.

        Delegue entierement a ingestion/steam_prices.py : le DAG orchestre, il
        n'implemente pas.
        """
        import sys

        sys.path.insert(0, "/opt/gamelens/ingestion")
        from steam_prices import collecter_et_tracer

        # collecter_et_tracer, et non collecter : la seconde n'alimente pas
        # speed.pipeline_runs et rendrait la collecte orchestree invisible
        # pour la supervision.
        compteurs = collecter_et_tracer()
        ecrits = compteurs["records_written"]
        lus = compteurs["records_in"]
        print(f"{ecrits} releve(s) tarifaire(s) sur {lus} titre(s) interroge(s).")
        return ecrits

    @task
    def promouvoir_faits_popularite(jour: str) -> int:
        """Agrege la journee et alimente mart.fact_popularity_history.

        Les colonnes de popularite diffusee restent nulles : la source Twitch
        n'est pas encore branchee. Le grain journalier et les colonnes larges
        sont ceux poses au Bloc 1, sans modele EAV.
        """
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        hook = PostgresHook(postgres_conn_id=CONNEXION)
        conn = hook.get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mart.fact_popularity_history
                    (game_id, day, avg_player_count, max_player_count,
                     avg_viewer_count, max_viewer_count)
                SELECT g.game_id, v.day, v.avg_player_count, v.max_player_count,
                       a.avg_viewer_count, a.max_viewer_count
                FROM speed.v_daily_player_stats v
                JOIN mart.dim_games g ON g.steam_appid = v.steam_appid
                -- Jointure EXTERNE : un titre sans identifiant Twitch resolu
                -- garde sa frequentation jouee, audience a NULL. Une jointure
                -- interne le ferait disparaitre de la table de faits, ce qui
                -- transformerait une source manquante en perte de donnee.
                LEFT JOIN speed.v_daily_viewer_stats a
                       ON a.steam_appid = v.steam_appid AND a.day = v.day
                WHERE v.day = %s
                ON CONFLICT (game_id, day) DO UPDATE
                   SET avg_player_count = EXCLUDED.avg_player_count,
                       max_player_count = EXCLUDED.max_player_count,
                       avg_viewer_count = EXCLUDED.avg_viewer_count,
                       max_viewer_count = EXCLUDED.max_viewer_count
                """,
                (jour,),
            )
            lignes = cur.rowcount
        print(f"{lignes} fait(s) de popularite promu(s) pour le {jour}.")
        return lignes

    @task
    def promouvoir_faits_tarifs(jour: str, _releves: int) -> int:
        """Alimente mart.fact_prices depuis les releves tarifaires du jour."""
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        hook = PostgresHook(postgres_conn_id=CONNEXION)
        conn = hook.get_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mart.fact_prices
                    (game_id, store_id, price, currency, promotion_flag, collected_at)
                SELECT g.game_id,
                       s.store_id,
                       p.price_final,
                       p.currency,
                       p.discount_percent > 0,
                       p.collected_at
                FROM speed.price_snapshots p
                JOIN mart.dim_games g ON g.steam_appid = p.steam_appid
                CROSS JOIN (SELECT store_id FROM mart.dim_stores WHERE name = 'Steam') s
                WHERE (p.collected_at AT TIME ZONE 'UTC')::date = %s
                ON CONFLICT ON CONSTRAINT uq_fact_prices_grain DO UPDATE
                   SET price          = EXCLUDED.price,
                       promotion_flag = EXCLUDED.promotion_flag
                """,
                (jour,),
            )
            lignes = cur.rowcount
        print(f"{lignes} fait(s) tarifaire(s) promu(s) pour le {jour}.")
        return lignes

    @task
    def controler_qualite_gold(jour: str, _pop: int, _prix: int) -> None:
        """Controles de qualite sur la couche Gold, en PASS/FAIL.

        Materialise le principe pose au cadrage : l'integrite ne repose pas
        seulement sur les contraintes declarees, elle est verifiee a chaque run
        et fait echouer le pipeline en cas de violation, plutot que d'etre
        constatee plus tard par un analyste devant un tableau de bord faux.

        Ce sont les memes assertions que celles portees, cote Snowflake, par
        les contrats de dbt/models/gold/ depuis le 27/08/2026. Deux ecritures
        de la meme regle sur deux moteurs : ici PostgreSQL les applique deja
        par ses contraintes, la-bas rien ne les applique et le controle est
        le seul filet. Voir DA-04 et DA-10.
        """
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        controles = [
            (
                "dim_games sans nom unifie",
                "SELECT count(*) FROM mart.dim_games WHERE unified_name IS NULL",
                0,
            ),
            (
                "fact_prices avec un prix negatif ou nul",
                "SELECT count(*) FROM mart.fact_prices WHERE price <= 0",
                0,
            ),
            (
                "fact_popularity_history orpheline de dim_games",
                """SELECT count(*) FROM mart.fact_popularity_history f
                LEFT JOIN mart.dim_games g ON g.game_id = f.game_id
                WHERE g.game_id IS NULL""",
                0,
            ),
            (
                "doublons sur le grain (game_id, day)",
                """SELECT count(*) FROM (
                    SELECT game_id, day FROM mart.fact_popularity_history
                    GROUP BY game_id, day HAVING count(*) > 1
                ) d""",
                0,
            ),
            (
                "popularite moyenne negative",
                "SELECT count(*) FROM mart.fact_popularity_history WHERE avg_player_count < 0",
                0,
            ),
        ]

        hook = PostgresHook(postgres_conn_id=CONNEXION)
        echecs = []
        for libelle, requete, attendu in controles:
            observe = hook.get_first(requete)[0]
            statut = "PASS" if observe == attendu else "FAIL"
            print(f"[{statut}] {libelle} : attendu {attendu}, observe {observe}")
            if statut == "FAIL":
                echecs.append(f"{libelle} (attendu {attendu}, observe {observe})")

        # Controle de completude, distinct des controles d'integrite : il verifie
        # que la promotion a bien produit quelque chose pour la journee visee.
        promus = hook.get_first(
            "SELECT count(*) FROM mart.fact_popularity_history WHERE day = %s",
            parameters=(jour,),
        )[0]
        statut = "PASS" if promus > 0 else "FAIL"
        print(f"[{statut}] faits de popularite presents pour le {jour} : {promus}")
        if promus == 0:
            echecs.append(f"aucun fait de popularite pour le {jour}")

        if echecs:
            raise ValueError("Controles de qualite en echec : " + " ; ".join(echecs))
        print(f"{len(controles) + 1} controles de qualite au vert.")

    jour = verifier_fraicheur_silver()
    dimensions = promouvoir_dimension_jeux(jour)
    releves = collecter_tarifs_steam()
    faits_popularite = promouvoir_faits_popularite(jour)
    faits_tarifs = promouvoir_faits_tarifs(jour, releves)

    dimensions >> [faits_popularite, faits_tarifs]
    controler_qualite_gold(jour, faits_popularite, faits_tarifs)


promotion_gold()
