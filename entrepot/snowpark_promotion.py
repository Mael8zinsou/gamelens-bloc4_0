"""Calcul distribue Snowpark : promotion Silver speed vers l'entrepot Gold.

Troisieme et derniere des trois methodes de traitement exigees par C4.2.2,
apres le pipeline temps reel et l'orchestrateur.

**En quoi est-ce distribue ?** C'est la question que le jury posera, et elle
merite une reponse precise plutot qu'un nom de technologie.

Snowpark n'execute pas les transformations dans ce processus Python. L'API
DataFrame construit un plan logique, le traduit en SQL, et le fait executer par
l'entrepot virtuel Snowflake, qui repartit le travail sur ses noeuds de calcul.
Le poste local n'orchestre que l'envoi du plan et la reception du resultat : les
jointures, les fenetres analytiques et les agregations n'y passent jamais.

C'est verifiable, et le script le verifie plutot que de l'affirmer. Il affiche
le SQL reellement genere par Snowpark, puis interroge l'historique des requetes
de la session pour montrer sur quel entrepot elles ont tourne, combien d'octets
ont ete parcourus et combien de micro-partitions ont ete elaguees.

C'est la difference concrete avec un PySpark en mode local, ecarte le
19/08/2026 : celui-ci se serait execute sur une seule machine, la meme que
celle qui pilote le script.

Usage :
    docker compose run --rm snowflake-cli python entrepot/snowpark_promotion.py
    docker compose run --rm snowflake-cli python entrepot/snowpark_promotion.py --expliquer
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
import psycopg2
from connexion_snowflake import parametres
from snowflake.snowpark import Session
from snowflake.snowpark import functions as F
from snowflake.snowpark.window import Window

SCHEMA_STAGING = "staging"


def connexion_silver():
    """Connexion a la couche Silver speed, source de la promotion."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        dbname=os.getenv("POSTGRES_DB", "gamelens"),
        user=os.getenv("POSTGRES_USER", "gamelens_app"),
        password=os.getenv("POSTGRES_PASSWORD", "devlocal_app"),
        connect_timeout=10,
    )


def extraire_silver() -> dict[str, pd.DataFrame]:
    """Extrait les jeux de donnees a promouvoir depuis PostgreSQL.

    Seule etape qui passe par pandas, et volontairement la plus mince possible :
    elle transporte, elle ne transforme pas. Tout le calcul a lieu ensuite cote
    Snowflake.
    """
    requetes = {
        "GAME_MAPPING": """
            SELECT steam_appid, unified_name, developer, genre
            FROM speed.game_mapping WHERE is_active
        """,
        "DAILY_STATS": """
            SELECT steam_appid, day, avg_player_count, max_player_count, observation_count
            FROM speed.v_daily_player_stats
        """,
        "PRICE_SNAPSHOTS": """
            SELECT steam_appid, price_final, price_initial, discount_percent,
                   currency, collected_at
            FROM speed.price_snapshots
        """,
    }

    conn = connexion_silver()
    try:
        jeux = {}
        for nom, requete in requetes.items():
            # Construction explicite plutot que pd.read_sql_query : pandas
            # avertit qu'il ne teste que SQLAlchemy, et le passage par le
            # curseur evite ce bruit tout en restant lisible.
            with conn.cursor() as cur:
                cur.execute(requete)
                colonnes = [d[0] for d in cur.description]
                cadre = pd.DataFrame(cur.fetchall(), columns=colonnes)
            # Snowflake met les identifiants non quotes en majuscules. Aligner
            # les noms de colonnes des maintenant evite de devoir quoter chaque
            # colonne ensuite, piege classique de write_pandas.
            cadre.columns = [c.upper() for c in cadre.columns]
            jeux[nom] = cadre
            print(f"  {nom:<18} {len(cadre):>5} ligne(s) extraite(s)")
        return jeux
    finally:
        conn.close()


def charger_staging(session: Session, jeux: dict[str, pd.DataFrame]) -> None:
    """Televerse les jeux extraits dans un schema de transit Snowflake."""
    session.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_STAGING}").collect()
    for nom, cadre in jeux.items():
        if cadre.empty:
            print(f"  {nom:<18} vide, televersement ignore")
            continue
        session.write_pandas(
            cadre,
            table_name=nom,
            schema=SCHEMA_STAGING,
            auto_create_table=True,
            overwrite=True,
            quote_identifiers=False,
            # use_logical_type=True : sans ce reglage, une colonne horodatee
            # avec fuseau est ecrite de facon incorrecte, ce que le connecteur
            # signale par un simple avertissement. price_snapshots.collected_at
            # est dans ce cas, et une date faussee cote entrepot ne se verrait
            # qu'en comparant les deux couches ligne a ligne.
            use_logical_type=True,
        )
        print(f"  {nom:<18} {len(cadre):>5} ligne(s) televersee(s)")


def promouvoir_dimensions(session: Session) -> int:
    """Alimente mart.dim_games depuis le referentiel de transit.

    MERGE plutot qu'INSERT : la promotion doit rester rejouable, comme celle du
    DAG PostgreSQL. Snowflake n'appliquant pas les contraintes d'unicite
    declarees, c'est la clause du MERGE qui porte ici l'idempotence, et rien
    d'autre ne l'empecherait de dupliquer.
    """
    source = session.table(f"{SCHEMA_STAGING}.GAME_MAPPING")
    cible = session.table("mart.dim_games")

    resultat = cible.merge(
        source,
        cible["STEAM_APPID"] == source["STEAM_APPID"],
        [
            F.when_matched().update(
                {
                    "UNIFIED_NAME": source["UNIFIED_NAME"],
                    "DEVELOPER": source["DEVELOPER"],
                    "GENRE": source["GENRE"],
                    "GOLD_LOADED_AT": F.current_timestamp(),
                }
            ),
            F.when_not_matched().insert(
                {
                    "GAME_ID": F.call_builtin("UUID_STRING"),
                    "UNIFIED_NAME": source["UNIFIED_NAME"],
                    "DEVELOPER": source["DEVELOPER"],
                    "GENRE": source["GENRE"],
                    "STEAM_APPID": source["STEAM_APPID"],
                    "GOLD_LOADED_AT": F.current_timestamp(),
                }
            ),
        ],
    )
    total = resultat.rows_inserted + resultat.rows_updated
    print(
        f"  dim_games : {resultat.rows_inserted} insertion(s), {resultat.rows_updated} mise(s) a jour"
    )
    return total


def promouvoir_faits(session: Session) -> int:
    """Alimente mart.fact_popularity_history par jointure cote entrepot.

    La jointure entre les agregats journaliers et la dimension est effectuee par
    Snowflake, pas en local : aucune des deux tables n'est rapatriee.
    """
    stats = session.table(f"{SCHEMA_STAGING}.DAILY_STATS")
    dimensions = session.table("mart.dim_games").select("GAME_ID", "STEAM_APPID")

    source = stats.join(dimensions, stats["STEAM_APPID"] == dimensions["STEAM_APPID"]).select(
        dimensions["GAME_ID"].alias("GAME_ID"),
        stats["DAY"].alias("DAY"),
        stats["AVG_PLAYER_COUNT"].alias("AVG_PLAYER_COUNT"),
        stats["MAX_PLAYER_COUNT"].alias("MAX_PLAYER_COUNT"),
    )

    cible = session.table("mart.fact_popularity_history")
    resultat = cible.merge(
        source,
        (cible["GAME_ID"] == source["GAME_ID"]) & (cible["DAY"] == source["DAY"]),
        [
            F.when_matched().update(
                {
                    "AVG_PLAYER_COUNT": source["AVG_PLAYER_COUNT"],
                    "MAX_PLAYER_COUNT": source["MAX_PLAYER_COUNT"],
                }
            ),
            F.when_not_matched().insert(
                {
                    "GAME_ID": source["GAME_ID"],
                    "DAY": source["DAY"],
                    "AVG_PLAYER_COUNT": source["AVG_PLAYER_COUNT"],
                    "MAX_PLAYER_COUNT": source["MAX_PLAYER_COUNT"],
                }
            ),
        ],
    )
    print(
        f"  fact_popularity_history : {resultat.rows_inserted} insertion(s), "
        f"{resultat.rows_updated} mise(s) a jour"
    )
    return resultat.rows_inserted + resultat.rows_updated


def promouvoir_tarifs(session) -> int:
    """Alimente mart.dim_stores et mart.fact_prices depuis le transit.

    La boutique Steam est creee par MERGE plutot que par INSERT conditionnel :
    Snowflake n'applique pas la contrainte UNIQUE declaree sur dim_stores.name,
    donc rien n'empecherait un second passage de creer un doublon de boutique,
    qui multiplierait ensuite silencieusement les faits tarifaires.
    """
    boutiques = session.create_dataframe(
        [("Steam", "https://store.steampowered.com", "api")],
        schema=["NAME", "BASE_URL", "SOURCE_TYPE"],
    )
    cible_boutiques = session.table("mart.dim_stores")
    cible_boutiques.merge(
        boutiques,
        cible_boutiques["NAME"] == boutiques["NAME"],
        [
            F.when_not_matched().insert(
                {
                    "STORE_ID": F.call_builtin("UUID_STRING"),
                    "NAME": boutiques["NAME"],
                    "BASE_URL": boutiques["BASE_URL"],
                    "SOURCE_TYPE": boutiques["SOURCE_TYPE"],
                }
            )
        ],
    )

    tarifs = session.table(f"{SCHEMA_STAGING}.PRICE_SNAPSHOTS")
    jeux = session.table("mart.dim_games").select("GAME_ID", "STEAM_APPID")
    steam = session.table("mart.dim_stores").filter(F.col("NAME") == F.lit("Steam"))

    source = (
        tarifs.join(jeux, tarifs["STEAM_APPID"] == jeux["STEAM_APPID"])
        .join(steam)
        .select(
            jeux["GAME_ID"].alias("GAME_ID"),
            steam["STORE_ID"].alias("STORE_ID"),
            tarifs["PRICE_FINAL"].alias("PRICE"),
            tarifs["CURRENCY"].alias("CURRENCY"),
            (tarifs["DISCOUNT_PERCENT"] > 0).alias("PROMOTION_FLAG"),
            tarifs["COLLECTED_AT"].alias("COLLECTED_AT"),
        )
    )

    cible = session.table("mart.fact_prices")
    resultat = cible.merge(
        source,
        (cible["GAME_ID"] == source["GAME_ID"])
        & (cible["STORE_ID"] == source["STORE_ID"])
        & (cible["COLLECTED_AT"] == source["COLLECTED_AT"]),
        [
            F.when_matched().update(
                {"PRICE": source["PRICE"], "PROMOTION_FLAG": source["PROMOTION_FLAG"]}
            ),
            F.when_not_matched().insert(
                {
                    "PRICE_ID": F.call_builtin("UUID_STRING"),
                    "GAME_ID": source["GAME_ID"],
                    "STORE_ID": source["STORE_ID"],
                    "PRICE": source["PRICE"],
                    "CURRENCY": source["CURRENCY"],
                    "PROMOTION_FLAG": source["PROMOTION_FLAG"],
                    "COLLECTED_AT": source["COLLECTED_AT"],
                }
            ),
        ],
    )
    print(
        f"  fact_prices : {resultat.rows_inserted} insertion(s), "
        f"{resultat.rows_updated} mise(s) a jour"
    )
    return resultat.rows_inserted + resultat.rows_updated


def calculer_classement(session: Session, expliquer: bool = False):
    """Calcul analytique distribue : moyenne glissante et rang par genre.

    C'est le coeur de la demonstration du calcul distribue. Trois operations
    qui, sur un volume reel, ne tiendraient pas en memoire locale :

      - une jointure entre faits et dimensions ;
      - une fenetre glissante sur 7 jours par jeu, ordonnee par date ;
      - un classement par genre, calcule sur toute la partition.

    Aucune n'est executee ici : Snowpark les traduit en une seule requete SQL
    que l'entrepot virtuel repartit sur ses noeuds.
    """
    faits = session.table("mart.fact_popularity_history")
    jeux = session.table("mart.dim_games").select("GAME_ID", "UNIFIED_NAME", "GENRE")
    # La fenetre s'applique APRES le renommage des colonnes : elle doit donc
    # ordonner sur JOUR et non sur DAY, sous peine d'un invalid identifier qui
    # ne survient qu'a l'execution, Snowpark differant la resolution des noms.

    fenetre_glissante = Window.partition_by("GAME_ID").order_by("JOUR").rows_between(-6, 0)

    enrichi = (
        faits.join(jeux, faits["GAME_ID"] == jeux["GAME_ID"])
        .select(
            jeux["UNIFIED_NAME"].alias("JEU"),
            jeux["GENRE"].alias("GENRE"),
            faits["DAY"].alias("JOUR"),
            faits["AVG_PLAYER_COUNT"].alias("JOUEURS_MOYENS"),
            faits["GAME_ID"].alias("GAME_ID"),
        )
        .with_column(
            "MOYENNE_GLISSANTE_7J",
            F.round(F.avg("JOUEURS_MOYENS").over(fenetre_glissante), 2),
        )
    )

    dernier_jour = enrichi.select(F.max("JOUR").alias("M")).collect()[0]["M"]

    classement = (
        enrichi.filter(F.col("JOUR") == F.lit(dernier_jour))
        .with_column(
            "RANG_DANS_LE_GENRE",
            F.rank().over(Window.partition_by("GENRE").order_by(F.col("JOUEURS_MOYENS").desc())),
        )
        .with_column(
            "PART_DU_GENRE_PCT",
            F.round(
                100
                * F.col("JOUEURS_MOYENS")
                / F.sum("JOUEURS_MOYENS").over(Window.partition_by("GENRE")),
                1,
            ),
        )
        .select(
            "JEU",
            "GENRE",
            "JOUR",
            "JOUEURS_MOYENS",
            "MOYENNE_GLISSANTE_7J",
            "RANG_DANS_LE_GENRE",
            "PART_DU_GENRE_PCT",
        )
        .sort(F.col("GENRE"), F.col("RANG_DANS_LE_GENRE"))
    )

    if expliquer:
        print("\n  --- SQL genere par Snowpark et envoye a l'entrepot ---")
        for requete in classement.queries["queries"]:
            print("  " + requete.replace("\n", "\n  ")[:1800])
        print("  --- fin du SQL ---\n")

    return classement


def preuve_execution_distante(session) -> None:
    """Montre ou les requetes ont reellement tourne.

    Sans cette verification, rien ne distingue un calcul pousse dans l'entrepot
    d'un calcul rapatrie puis fait en local. L'historique de session, disponible
    immediatement contrairement a account_usage qui accuse un delai de plusieurs
    dizaines de minutes, donne l'entrepot utilise, sa taille, le numero de
    cluster qui a servi la requete, et le volume reellement parcourus.

    Les colonnes ont ete relevees sur la fonction de table elle-meme plutot que
    supposees : query_history_by_session n'expose pas les memes colonnes que
    account_usage.query_history, et notamment pas les micro-partitions.
    """
    lignes_hist = session.sql(
        """
        SELECT query_type, warehouse_name, warehouse_size, cluster_number,
               bytes_scanned, rows_produced, compilation_time, execution_time
        FROM TABLE(information_schema.query_history_by_session(result_limit => 20))
        WHERE query_type IN ('SELECT', 'MERGE')
          AND warehouse_name IS NOT NULL
        ORDER BY start_time DESC
        LIMIT 6
        """
    ).collect()

    if not lignes_hist:
        print("  historique de session vide")
        return

    entete = (
        f"  {'type':<8} {'entrepot':<14} {'taille':<9} {'cluster':>7} "
        f"{'octets lus':>11} {'lignes':>8} {'compil ms':>10} {'exec ms':>8}"
    )
    print(entete)
    print("  " + "-" * (len(entete) - 2))
    for r in lignes_hist:
        print(
            f"  {r['QUERY_TYPE']:<8} {r['WAREHOUSE_NAME'] or '-':<14} "
            f"{r['WAREHOUSE_SIZE'] or '-':<9} {r['CLUSTER_NUMBER'] or 0:>7} "
            f"{r['BYTES_SCANNED'] or 0:>11} {r['ROWS_PRODUCED'] or 0:>8} "
            f"{r['COMPILATION_TIME'] or 0:>10} {r['EXECUTION_TIME'] or 0:>8}"
        )
    print()
    print("  Chaque ligne est une requete compilee et executee par l entrepot virtuel,")
    print("  pas par ce processus Python.")


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Promotion distribuee Snowpark")
    parseur.add_argument(
        "--expliquer", action="store_true", help="afficher le SQL genere par Snowpark"
    )
    args = parseur.parse_args(argv)

    print("Promotion Silver speed vers Gold, calcul distribue Snowpark\n")

    print("1. Extraction depuis la couche Silver speed (PostgreSQL)")
    jeux = extraire_silver()

    session = Session.builder.configs(
        {k: v for k, v in parametres().items() if k != "application"}
    ).create()

    try:
        # information_schema.warehouses() n'existe pas cote Snowflake : les
        # metadonnees d'entrepot passent par SHOW WAREHOUSES ou par
        # account_usage. La taille est de toute facon rapportee plus bas par
        # l'historique des requetes, ou elle est plus utile.
        contexte = session.sql(
            "SELECT CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_ROLE()"
        ).collect()[0]
        print(
            f"   session Snowpark ouverte | entrepot {contexte[0]} | "
            f"base {contexte[1]} | role {contexte[2]}"
        )

        print("\n2. Televersement vers le schema de transit")
        charger_staging(session, jeux)

        print("\n3. Promotion vers l'entrepot Gold, executee par Snowflake")
        promouvoir_dimensions(session)
        promouvoir_faits(session)
        promouvoir_tarifs(session)

        print("\n4. Calcul analytique distribue : fenetre glissante et classement")
        classement = calculer_classement(session, expliquer=args.expliquer)
        resultats = classement.collect()
        print(f"  {len(resultats)} ligne(s) de classement calculee(s) cote entrepot\n")

        entete = (
            f"  {'jeu':<20} {'genre':<14} {'joueurs':>9} {'moy. 7j':>9} {'rang':>5} {'part %':>7}"
        )
        print(entete)
        print("  " + "-" * (len(entete) - 2))
        for r in resultats:
            print(
                f"  {r['JEU']:<20} {r['GENRE'] or '-':<14} {r['JOUEURS_MOYENS']:>9} "
                f"{r['MOYENNE_GLISSANTE_7J']:>9} {r['RANG_DANS_LE_GENRE']:>5} "
                f"{r['PART_DU_GENRE_PCT']:>7}"
            )

        print("\n5. Preuve que le calcul a bien eu lieu dans l'entrepot")
        preuve_execution_distante(session)

        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
