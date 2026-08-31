"""Promotion journaliere de la couche Silver speed vers l'entrepot Snowflake.

Ce DAG comble V-12, constate le 31/08/2026 : la couche Gold Snowflake, que
l'architecture designe comme la CIBLE, n'etait alimentee par aucun
ordonnanceur. Elle etait chargee a la main et accusait onze jours de retard,
pendant que le prototype PostgreSQL, lui, etait promu chaque nuit. Le systeme
faisait l'inverse de ce que l'architecture decrivait.

POURQUOI UN DAG SEPARE, ET NON DES TACHES DE PLUS DANS gamelens_promotion_gold

Les deux promotions lisent la meme source et ecrivent des donnees equivalentes,
ce qui plaide pour les reunir. Trois raisons de ne pas le faire.

1. Domaines de panne distincts. Snowflake est un service tiers, facture, dont
   le compte expire (V-01) et dont les credits s'epuisent. PostgreSQL est un
   conteneur local. Reunir les deux ferait qu'une indisponibilite de Snowflake
   emporterait la promotion PostgreSQL, qui n'a aucune raison d'en dependre.

2. Cadences potentiellement differentes. La promotion locale peut etre rejouee
   sans cout ; celle-ci consomme des credits a chaque execution.

3. Lisibilite de la supervision. Deux composants distincts dans
   speed.pipeline_runs donnent deux verdicts distincts. Fondus en un seul DAG,
   un echec cote Snowflake se lirait comme un echec de la promotion tout court.

CE QUE CE DAG NE FAIT PAS

Il n'ecrit pas une ligne de logique metier. La promotion vit dans
entrepot/snowpark_promotion.py et ce DAG l'appelle, exactement comme
gamelens_promotion_gold appelle ingestion/steam_prices.py. Le module reste
donc utilisable en ligne de commande, testable sans Airflow, et il n'existe
qu'une seule version du code de promotion.

VERIFIE AVANT D'ETRE ECRIT

L'obstacle suppose a ce DAG etait l'isolation des jeux de dependances (DA-08) :
Snowpark ne pouvait pas cohabiter avec le reste, donc pas dans l'image Airflow.
C'etait faux, et deduit plutot que constate (OBS-69). L'image
apache/airflow:3.1.8 embarque deja snowflake-snowpark-python 1.47.0,
snowflake-connector-python 4.0.0, le fournisseur Snowflake, pandas et pyarrow.
La promotion a ete executee a la main dans le conteneur AVANT l'ecriture de ce
fichier, pour separer un probleme d'execution d'un probleme d'orchestration.

Note de version assumee : l'image Airflow porte Snowpark 1.47.0 quand
requirements-snowflake.txt epingle 1.54.0. Le meme code tourne donc sur deux
versions. C'est une divergence a surveiller, et c'est aussi ce qui la rend
visible : la CI eprouve la 1.54, cet ordonnanceur eprouve la 1.47.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task

CONNEXION = "gamelens_postgres"

# Nom sous lequel les executions sont tracees dans speed.pipeline_runs. Il
# compte : les regles composant_muet et echecs_composants de la supervision
# raisonnent sur ce nom, et c'est par lui que cette promotion devient visible
# du dispositif d'alerte. Sans trace, son arret serait indiscernable de son
# bon fonctionnement, ce qui est exactement le defaut d'INC-007.
COMPOSANT = "snowpark_promotion"


@dag(
    dag_id="gamelens_promotion_snowflake",
    description="Promotion journaliere de la couche Silver speed vers l'entrepot Snowflake",
    doc_md=__doc__,
    # 03h00 UTC, une demi-heure apres gamelens_promotion_gold. Les deux couches
    # portent ainsi la meme journee, ce qui rend leur comparaison possible : un
    # ecart entre elles designe alors un defaut, et non un decalage d'horaire.
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2026, 8, 31, tz="UTC"),
    catchup=False,
    # Deux promotions concurrentes sur la meme journee se battraient sur le
    # schema de transit, que charger_staging ecrase a chaque passage.
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": pendulum.duration(minutes=5)},
    params={"jour": ""},
    tags=["gamelens", "gold", "snowflake", "c4.2.2"],
)
def promotion_snowflake():
    @task
    def verifier_fraicheur_silver(**context) -> str:
        """Porte d'entree : refuse de promouvoir une journee sans donnee.

        Meme raisonnement que dans gamelens_promotion_gold, et il vaut ici
        davantage : la promotion Snowpark procede par MERGE, donc une source
        vide ne produit aucune erreur, aucune ligne, et un run vert. Le
        pipeline aurait alors reussi a ne rien faire, ce qui est le mode de
        defaillance le plus couteux parce qu'il est silencieux.
        """
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        # logical_date vaut None sur un run manuel en Airflow 3 (INC-006).
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
                "Le pipeline temps reel a-t-il tourne ? Promotion Snowflake interrompue."
            )
        print(f"{total} evenements sur {titres} titres pour le {jour}.")
        return jour

    @task
    def promouvoir_vers_snowflake(jour: str) -> str:
        """Appelle la promotion Snowpark, tracee dans speed.pipeline_runs.

        L'appel passe par main(), le point d'entree reel du module, et non par
        ses fonctions internes : c'est ce qui garantit qu'il n'existe pas deux
        facons de promouvoir, une pour la ligne de commande et une pour
        l'ordonnanceur.

        La trace utilise le meme gestionnaire de contexte que l'ingestion. Il
        ouvre sa PROPRE connexion PostgreSQL, distincte du traitement, pour que
        la trace d'un echec survive a l'annulation de la transaction metier.
        """
        import logging

        from common import execution
        from snowpark_promotion import main

        logger = logging.getLogger("gamelens.promotion_snowflake")

        with execution(COMPOSANT, logger) as compteurs:
            code = main([])
            if code != 0:
                raise RuntimeError(f"snowpark_promotion a rendu le code {code}.")
            # Le detail des volumes est confronte a Snowflake par la tache
            # suivante, qui lit la cible plutot que de croire l'appelant.
            compteurs["records_written"] = 1

        return jour

    @task
    def controler_entrepot_snowflake(jour: str) -> None:
        """Verifie la cible en la LISANT, plutot qu'en croyant l'etape d'avant.

        Deux controles de nature differente.

        Le premier est propre a ce DAG : la journee promue est-elle bien
        arrivee ? Une promotion peut reussir sans rien ecrire, et c'est
        precisement ce que la porte d'entree ne peut pas garantir a elle seule,
        puisqu'elle regarde la source et non la destination.

        Le second delegue les huit controles d'integrite a
        entrepot/verifier_gold.py, qui reste l'autorite applicative sur ce
        sujet. Sur Snowflake ils ne doublent pas le moteur, ils le remplacent :
        ni CHECK, ni cle etrangere, ni cle primaire, ni UNIQUE ne sont
        appliques a l'ecriture (DA-04). Les contrats dbt en sont le pendant
        declaratif, rejoues par la CI a chaque push (DA-10) ; les executer ici
        supposerait d'ajouter dbt a l'image Airflow, ce qui n'est pas fait.
        """
        from connexion_snowflake import connexion
        from verifier_gold import main as verifier

        conn = connexion()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM mart.fact_popularity_history WHERE day = %s",
                    (jour,),
                )
                lignes_du_jour = cur.fetchone()[0]

                cur.execute("SELECT max(day) FROM mart.fact_popularity_history")
                derniere = cur.fetchone()[0]

                cur.execute("SELECT count(*) FROM mart.dim_games")
                jeux = cur.fetchone()[0]
        finally:
            conn.close()

        if lignes_du_jour == 0:
            raise ValueError(
                f"La promotion s'est terminee sans erreur mais l'entrepot ne contient "
                f"aucune ligne pour le {jour}. Derniere journee presente : {derniere}. "
                "Un pipeline qui reussit a ne rien faire est un pipeline qui ment."
            )
        print(
            f"[PASS] {lignes_du_jour} faits de popularite pour le {jour}, "
            f"{jeux} jeux au referentiel, derniere journee {derniere}."
        )

        if verifier() != 0:
            raise ValueError(
                "Les controles d'integrite de la couche Gold Snowflake sont en echec. "
                "Voir le detail ci-dessus : sur Snowflake, ces controles ne doublent "
                "pas le moteur, ils le remplacent."
            )

    jour = verifier_fraicheur_silver()
    controler_entrepot_snowflake(promouvoir_vers_snowflake(jour))


promotion_snowflake()
