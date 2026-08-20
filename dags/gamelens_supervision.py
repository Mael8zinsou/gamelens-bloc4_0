"""DAG de supervision de la plateforme GameLens.

Livrable C4.3.1. Evalue les regles d'alerte a intervalle court et fait remonter
les alertes critiques a l'orchestrateur.

Pourquoi passer par Airflow plutot que par une tache planifiee independante :
l'orchestrateur est deja le composant qui sait executer quelque chose a
intervalle regulier, en conserver la trace, reessayer, et notifier. Ajouter un
second mecanisme de planification a cote aurait cree un composant de plus a
surveiller, sans rien apporter.

Choix de conception a defendre : la tache d'evaluation reussit toujours, y
compris quand des alertes se declenchent, parce qu'evaluer des regles et
constater un probleme sont deux choses differentes. C'est une seconde tache qui
echoue en presence d'une alerte critique. Sans cette separation, un run en
echec ne permettrait pas de distinguer « la plateforme va mal » de « le moteur
d'alertes est casse », qui appellent des reactions opposees.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id="gamelens_supervision",
    description="Evaluation des regles d'alerte et remontee des alertes critiques",
    doc_md=__doc__,
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 8, 20, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    # Pas de reprise : une alerte qui persiste sera de toute facon revue au
    # cycle suivant, dans un quart d'heure. Reessayer ne ferait que multiplier
    # les executions sans changer le diagnostic.
    default_args={"retries": 0},
    tags=["gamelens", "supervision", "c4.3.1"],
)
def supervision():
    @task
    def evaluer_regles() -> dict:
        """Evalue les six regles et met a jour le journal d'alertes.

        Reussit meme si des alertes se declenchent : c'est le role de cette
        tache de les detecter, pas de s'en emouvoir.
        """
        import sys

        sys.path.insert(0, "/opt/gamelens/supervision")
        from regles_alertes import evaluer_et_tracer

        resultat = evaluer_et_tracer()
        print(
            f"{len(resultat['declenchees'])} regle(s) declenchee(s), "
            f"dont {len(resultat['nouvelles'])} nouvelle(s) ; "
            f"{len(resultat['resolues'])} resolue(s) ; "
            f"{len(resultat['nominales'])} nominale(s)"
        )
        return resultat

    @task
    def remonter_alertes_critiques(resultat: dict) -> None:
        """Echoue si une alerte critique est ouverte, afin qu'Airflow la notifie.

        Cette tache n'ecrit rien dans speed.pipeline_runs : son echec signale
        l'etat de la plateforme, pas une defaillance d'un composant. Les
        confondre fausserait la regle echecs_composants, qui compterait alors
        la supervision elle-meme parmi les pannes.
        """
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        hook = PostgresHook(postgres_conn_id="gamelens_postgres")
        ouvertes = hook.get_records(
            """SELECT regle, severite, message, declenchee_le
               FROM speed.alertes
               WHERE resolue_le IS NULL
               ORDER BY CASE severite WHEN 'critique' THEN 0 ELSE 1 END, declenchee_le"""
        )

        if not ouvertes:
            print("Aucune alerte ouverte. Plateforme nominale.")
            return

        critiques = []
        for regle, severite, message, depuis in ouvertes:
            print(
                f"[{severite.upper()}] {regle} (ouverte depuis {depuis:%Y-%m-%d %H:%M}) : {message}"
            )
            if severite == "critique":
                critiques.append(regle)

        if critiques:
            raise ValueError(
                f"{len(critiques)} alerte(s) critique(s) ouverte(s) : {', '.join(critiques)}"
            )
        print(f"{len(ouvertes)} avertissement(s) ouvert(s), aucune alerte critique.")

    remonter_alertes_critiques(evaluer_regles())


supervision()
