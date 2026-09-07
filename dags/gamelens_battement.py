"""DAG de battement : le contrat de presence de la plateforme GameLens.

Comble V-07, la supervision qui ne se surveille pas elle-meme. Ce DAG est
volontairement SEPARE de `gamelens_supervision`, et cette separation est tout
le raisonnement.

POURQUOI UN SECOND DAG PLUTOT QU'UNE TACHE DE PLUS

Une notification evenementielle ne dit rien quand rien ne part. Si le moteur
d'alertes s'arrete, aucune regle n'est evaluee, aucune alerte n'est ouverte,
donc aucun message n'est envoye, et le silence devient indiscernable d'une
plateforme saine. C'est le defaut d'origine, deplace d'un cran.

Le battement inverse la charge de la preuve : il part que tout aille bien ou
non. Son ABSENCE est le signal. Et parce qu'il vit dans un DAG distinct, il
survit a une panne de la supervision et peut la denoncer : il lit quand
`moteur_alertes` a tourne pour la derniere fois et le dit en tete du message.

On ne demande jamais a un dispositif de temoigner de sa propre existence. On
lui adjoint un temoin.

OU S'ARRETE LA CHAINE, ET POURQUOI LA

Le temoin demande a son tour un temoin : si l'ordonnanceur Airflow meurt, les
deux DAG meurent ensemble et plus rien ne part. Ce dernier maillon est humain,
c'est le lecteur qui ne recoit pas son message de 8h. Ce n'est pas une elegance,
c'est un arbitrage assume : chaque niveau supplementaire coute un composant a
tenir, et un cran au-dessus suffit a transformer une panne silencieuse en
silence remarquable. Un service externe de type sonde de presence serait le
niveau suivant, au prix d'une dependance tierce de plus.

CADENCE

8h et 20h. Une panne nocturne est vue au reveil, une panne de journee avant la
nuit. La cadence n'est pas plus serree a dessein : un message trop frequent
cesse d'etre lu, et son absence cesse alors d'etre remarquee, ce qui detruit
la seule propriete qui justifie ce DAG.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id="gamelens_battement",
    description="Bilan periodique sur le canal externe, et surveillance de la supervision",
    doc_md=__doc__,
    schedule="0 8,20 * * *",
    start_date=pendulum.datetime(2026, 9, 7, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    # Un reessai, contrairement au DAG de supervision : ici l'echec probable
    # est une indisponibilite reseau passagere du service de messagerie, pas un
    # diagnostic sur la plateforme. Le reessayer a du sens.
    default_args={"retries": 1, "retry_delay": pendulum.duration(minutes=2)},
    tags=["gamelens", "supervision", "c4.3.1"],
)
def battement():
    @task
    def envoyer_bilan() -> dict:
        """Compose et envoie le bilan. Echoue si le canal est configure et muet.

        Sans configuration, la tache reussit sans rien envoyer : un depot
        fraichement clone ne doit pas voir son ordonnanceur virer au rouge
        parce qu'aucun compte de messagerie n'a ete cree.
        """
        from notifications import battement_et_tracer

        resultat = battement_et_tracer()
        etat = resultat["etat"]

        if not resultat["configure"]:
            print(
                "Canal non configure : bilan compose mais non envoye. "
                "Renseigner TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID, voir .env.example."
            )
        else:
            print(f"Bilan envoye a {etat['horodatage']:%d/%m %H:%M}.")

        if etat["supervision_muette"]:
            print(
                f"ATTENTION : supervision muette depuis {etat['supervision_age_min']} minutes."
            )
        print(f"{len(etat['alertes_ouvertes'])} alerte(s) ouverte(s), "
              f"{len(etat['composants_muets'])} composant(s) sans execution recente.")

        return {
            "envoye": resultat["envoye"],
            "alertes_ouvertes": len(etat["alertes_ouvertes"]),
            "supervision_muette": etat["supervision_muette"],
        }

    envoyer_bilan()


battement()
