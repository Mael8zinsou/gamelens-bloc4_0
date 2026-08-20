"""Moteur d'alertes de la plateforme GameLens.

Livrable C4.3.1, volet « systeme d'alertes ». Les regles sont declarees comme
des donnees et non comme du code : chacune porte une requete, un seuil, un
comparateur et un message. Ajouter une regle ne demande pas d'ecrire de la
logique, ce qui evite que le moteur d'alertes devienne lui-meme une source de
panne.

Trois principes tires des incidents rencontres pendant la construction.

1. **Surveiller les absences.** INC-007 a montre qu'un composant peut tourner
   sans laisser de trace, et qu'une supervision muette se confond avec un
   systeme au repos. La regle `composant_muet` verifie donc qu'un composant
   attendu s'est bien manifeste, independamment de son resultat.

2. **Ne pas repeter une alerte deja ouverte.** Une alerte est ouverte une fois
   et reste ouverte tant que la condition persiste. Sans cela, une regle
   evaluee toutes les 15 minutes produirait 96 lignes par jour pour un seul
   probleme, et le journal deviendrait illisible au moment ou l'on en a besoin.

3. **Refermer automatiquement.** Quand la condition disparait, l'alerte est
   resolue et horodatee. C'est ce qui permet de mesurer la DUREE d'un incident,
   pas seulement son occurrence.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))

from common import configurer_logs, connexion_pg, execution  # noqa: E402

logger = configurer_logs("alertes")

CRITIQUE = "critique"
AVERTISSEMENT = "avertissement"


@dataclass(frozen=True)
class Regle:
    nom: str
    severite: str
    requete: str
    seuil: float
    comparateur: str  # "sup" declenche si valeur > seuil, "inf" si valeur < seuil
    message: str  # accepte {valeur} et {seuil}

    def declenche(self, valeur: float | None) -> bool:
        # Une valeur absente n'est jamais traitee comme nominale : elle signale
        # une source vide, cas que INC-007 a rendu suspect par principe.
        if valeur is None:
            return True
        return valeur > self.seuil if self.comparateur == "sup" else valeur < self.seuil


REGLES: list[Regle] = [
    Regle(
        nom="fraicheur_frequentation",
        severite=CRITIQUE,
        requete="SELECT age_minutes FROM speed.v_indicateur_fraicheur WHERE flux = 'frequentation'",
        seuil=90,
        comparateur="sup",
        message="Aucune donnee de frequentation depuis {valeur} minutes (seuil {seuil}).",
    ),
    Regle(
        nom="completude_collecte",
        severite=AVERTISSEMENT,
        requete="SELECT taux_completude_pct FROM speed.v_indicateur_completude",
        seuil=100,
        comparateur="inf",
        message="Seuls {valeur} % des titres actifs ont ete collectes sur 24h (attendu {seuil} %).",
    ),
    Regle(
        nom="latence_pipeline",
        severite=AVERTISSEMENT,
        requete="SELECT latence_p95_s FROM speed.v_indicateur_latence",
        seuil=300,
        comparateur="sup",
        message="Latence p95 de {valeur} s entre collecte et ecriture (seuil {seuil} s). Consumer ralenti ou arrete.",
    ),
    Regle(
        nom="retard_entrepot_gold",
        severite=CRITIQUE,
        requete="SELECT retard_jours FROM speed.v_indicateur_gold",
        seuil=1,
        comparateur="sup",
        message="L entrepot Gold accuse {valeur} jour(s) de retard (seuil {seuil}). Le DAG de promotion a-t-il tourne ?",
    ),
    Regle(
        nom="echecs_composants",
        severite=CRITIQUE,
        requete="""SELECT count(*) FROM speed.pipeline_runs
                   WHERE status = 'failed' AND started_at > now() - INTERVAL '24 hours'""",
        seuil=0,
        comparateur="sup",
        message="{valeur} execution(s) en echec sur les 24 dernieres heures.",
    ),
    Regle(
        nom="composant_muet",
        severite=AVERTISSEMENT,
        # Surveille une ABSENCE : un composant attendu qui n'a produit aucune
        # execution, ni reussie ni echouee. Voir INC-007.
        requete="""SELECT count(*) FROM (VALUES ('steam_producer'), ('kafka_to_postgres'),
                                                ('steam_prices')) AS attendus(composant)
                   WHERE NOT EXISTS (
                       SELECT 1 FROM speed.pipeline_runs r
                       WHERE r.component = attendus.composant
                         AND r.started_at > now() - INTERVAL '24 hours')""",
        seuil=0,
        comparateur="sup",
        message="{valeur} composant(s) attendu(s) n ont produit aucune execution depuis 24h.",
    ),
]


def evaluer_regle(cur, regle: Regle) -> tuple[bool, float | None]:
    """Execute la requete d'une regle et indique si elle declenche."""
    cur.execute(regle.requete)
    ligne = cur.fetchone()
    valeur = None if ligne is None or ligne[0] is None else float(ligne[0])
    return regle.declenche(valeur), valeur


def ouvrir_alerte(cur, regle: Regle, valeur: float | None) -> bool:
    """Ouvre l'alerte si elle ne l'est pas deja. Retourne True si elle est nouvelle."""
    cur.execute(
        "SELECT alerte_id FROM speed.alertes WHERE regle = %s AND resolue_le IS NULL",
        (regle.nom,),
    )
    if cur.fetchone() is not None:
        return False

    affichage = "inconnue" if valeur is None else f"{valeur:g}"
    cur.execute(
        """INSERT INTO speed.alertes (regle, severite, message, valeur, seuil)
           VALUES (%s, %s, %s, %s, %s)""",
        (
            regle.nom,
            regle.severite,
            regle.message.format(valeur=affichage, seuil=f"{regle.seuil:g}"),
            valeur,
            regle.seuil,
        ),
    )
    return True


def resoudre_alerte(cur, regle: Regle) -> bool:
    """Referme l'alerte si elle etait ouverte. Retourne True si quelque chose a ete referme."""
    cur.execute(
        """UPDATE speed.alertes SET resolue_le = now()
           WHERE regle = %s AND resolue_le IS NULL""",
        (regle.nom,),
    )
    return cur.rowcount > 0


def evaluer_toutes(compteurs: dict | None = None) -> dict:
    """Evalue l'ensemble des regles et met a jour le journal d'alertes.

    Retourne un etat detaille, exploitable aussi bien par le DAG de supervision
    que par un appel en ligne de commande.
    """
    compteurs = compteurs if compteurs is not None else {"records_in": 0, "records_written": 0}
    resultat = {"declenchees": [], "nouvelles": [], "resolues": [], "nominales": []}

    conn = connexion_pg()
    try:
        with conn, conn.cursor() as cur:
            for regle in REGLES:
                compteurs["records_in"] += 1
                declenche, valeur = evaluer_regle(cur, regle)

                if declenche:
                    nouvelle = ouvrir_alerte(cur, regle, valeur)
                    resultat["declenchees"].append(regle.nom)
                    if nouvelle:
                        resultat["nouvelles"].append(regle.nom)
                        compteurs["records_written"] += 1
                    niveau = logger.error if regle.severite == CRITIQUE else logger.warning
                    niveau(
                        "[%s] %s : %s%s",
                        regle.severite.upper(),
                        regle.nom,
                        regle.message.format(
                            valeur="inconnue" if valeur is None else f"{valeur:g}",
                            seuil=f"{regle.seuil:g}",
                        ),
                        "" if nouvelle else "  (deja ouverte)",
                    )
                else:
                    if resoudre_alerte(cur, regle):
                        resultat["resolues"].append(regle.nom)
                        logger.info("[RESOLUE] %s revenue sous le seuil", regle.nom)
                    resultat["nominales"].append(regle.nom)
                    logger.info(
                        "[NOMINAL] %s : %s",
                        regle.nom,
                        f"{valeur:g}" if valeur is not None else "n/a",
                    )
    finally:
        conn.close()

    return resultat


def evaluer_et_tracer() -> dict:
    """Point d'entree pour les appelants automatises : trace l'execution.

    Meme distinction que pour la collecte tarifaire (INC-007) : le moteur
    d'alertes est lui aussi un composant, et il doit apparaitre dans le journal
    d'execution. Une supervision qui ne se supervise pas est un angle mort de plus.
    """
    with execution("moteur_alertes", logger) as compteurs:
        return evaluer_toutes(compteurs)


def main() -> int:
    resultat = evaluer_et_tracer()
    logger.info(
        "bilan : %s declenchee(s) dont %s nouvelle(s), %s resolue(s), %s nominale(s)",
        len(resultat["declenchees"]),
        len(resultat["nouvelles"]),
        len(resultat["resolues"]),
        len(resultat["nominales"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
