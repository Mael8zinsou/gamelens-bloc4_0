"""Canal de notification Telegram de la plateforme GameLens.

Comble V-02, le plus gros ecart entre cette plateforme et une plateforme
reellement exploitee. Les alertes etaient persistees, refermees
automatiquement, mesurables, et personne n'etait prevenu. Mesure sur aout
2026 : une rupture de fraicheur detectee en 90 minutes, restee ouverte
6 jours et 20 heures. La detection n'a jamais ete le probleme.

POURQUOI TELEGRAM ET PAS UN COURRIEL

Un envoi SMTP demande un serveur, des identifiants, une reputation
d'expediteur, et finit dans les indesirables au premier message automatique.
L'API Telegram est un POST HTTPS sortant : aucun port entrant a ouvrir, aucune
infrastructure a tenir, et le message arrive sur un telephone. Pour une
plateforme qui tourne sur un poste derriere une box, c'est la seule des deux
qui fonctionne sans rien construire de plus.

DEUX PROPRIETES A NE PAS CASSER

1. **Absent n'est pas casse.** Sans jeton ni destination configures, tout ce
   module est un no-op silencieux qui rend un succes. Un depot fraichement
   clone, la CI, un poste de passage doivent fonctionner sans compte Telegram.
   Un canal d'alerte qui empeche la plateforme de demarrer serait une panne de
   plus, pas une surveillance.

2. **Configure mais injoignable EST casse.** Si le jeton existe et que l'envoi
   echoue, l'execution est tracee en echec dans speed.pipeline_runs, ce qui
   declenche la regle critique `echecs_composants`. Un canal declare qui ne
   delivre pas est une panne, et le taire reproduirait exactement le defaut que
   ce module corrige.

POURQUOI L'ETAT DE NOTIFICATION VIT EN BASE ET PAS EN MEMOIRE

Les colonnes `notifiee_le` et `resolution_notifiee_le` de speed.alertes
retiennent ce qui a deja ete annonce. Passer la liste des nouveautes d'une
tache a l'autre aurait ete plus court, et aurait perdu definitivement toute
notification ratee : un envoi echoue serait reste echoue. Avec l'etat en base,
le cycle suivant reprend ce qui n'est pas parti. C'est le meme raisonnement que
l'idempotence du puits d'ingestion : on ne cherche pas a garantir l'envoi, on
rend le reessai inoffensif et automatique.

Effet de bord assume : une alerte ouverte ET refermee entre deux cycles de
15 minutes n'est jamais annoncee. C'est voulu. Un transitoire qui se resout
seul n'est pas un evenement dont il faut reveiller quelqu'un.
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))

from common import configurer_logs, connexion_pg, execution  # noqa: E402

logger = configurer_logs("notifications")

API = "https://api.telegram.org"
DELAI_S = 10

# La supervision tourne toutes les 15 minutes. Trois cycles manques sans
# nouvelle, c'est une supervision muette et non un retard de planification.
SEUIL_SUPERVISION_MUETTE_MIN = 45

CRITIQUE = "critique"

# La plateforme STOCKE en UTC, ce qui est juste et ne doit pas changer : un
# horodatage sans fuseau est un horodatage faux des qu'il franchit une
# frontiere ou un changement d'heure. Mais un message destine a un humain
# doit porter SON heure. La conversion se fait donc au plus tard possible, a
# la composition, et jamais a l'ecriture.
FUSEAU_AFFICHAGE = os.getenv("GAMELENS_TIMEZONE", "Europe/Paris")


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


def config() -> dict:
    return {
        "jeton": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "destination": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
    }


def configure() -> bool:
    """Le canal est-il utilisable ? Sinon tout ce module ne fait rien."""
    c = config()
    return bool(c["jeton"]) and bool(c["destination"])


def envoyer(texte: str, *, discret: bool = False) -> bool:
    """Envoie un message. Ne leve jamais : rend True si le message est parti.

    `discret` supprime la notification sonore du telephone, pour ce qui merite
    d'etre lu sans merite d'etre reveille.
    """
    c = config()
    if not configure():
        logger.debug("canal Telegram non configure, message non envoye")
        return False

    try:
        reponse = requests.post(
            f"{API}/bot{c['jeton']}/sendMessage",
            json={
                "chat_id": c["destination"],
                "text": texte,
                "parse_mode": "HTML",
                "disable_notification": discret,
                "link_preview_options": {"is_disabled": True},
            },
            timeout=DELAI_S,
        )
    except requests.RequestException as exc:
        # Le jeton ne doit apparaitre dans aucun journal : requests le met dans
        # l'URL, donc on ne journalise que le type et le message de l'exception.
        logger.error("envoi Telegram impossible : %s: %s", type(exc).__name__, exc)
        return False

    if reponse.status_code != 200:
        logger.error(
            "Telegram a refuse le message : HTTP %s %s",
            reponse.status_code,
            _sans_jeton(reponse.text, c["jeton"]),
        )
        return False

    return True


def _sans_jeton(texte: str, jeton: str) -> str:
    """Retire le jeton d'un texte avant journalisation."""
    return texte.replace(jeton, "[JETON]") if jeton else texte


def _fuseau():
    """Le fuseau d'affichage, ou None si indisponible."""
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(FUSEAU_AFFICHAGE)
    except Exception as exc:  # nom de fuseau invalide, base tzdata absente
        logger.warning(
            "fuseau %s inutilisable (%s), les heures resteront en UTC",
            FUSEAU_AFFICHAGE, type(exc).__name__,
        )
        return None


def _local(moment):
    """Convertit un horodatage AVERTI vers le fuseau d'affichage.

    Un horodatage naif est rendu tel quel : il ne porte pas l'information
    necessaire a une conversion, et deviner son fuseau produirait un decalage
    silencieux, ce qui est pire que le decalage visible qu'on corrige ici.
    """
    zone = _fuseau()
    if moment is None or zone is None or moment.tzinfo is None:
        return moment
    return moment.astimezone(zone)


def _e(valeur) -> str:
    """Echappe pour le mode HTML de Telegram."""
    return html.escape(str(valeur), quote=False)


# --------------------------------------------------------------------------
# Composition des messages
# --------------------------------------------------------------------------

PASTILLES = {CRITIQUE: "\U0001f534", "avertissement": "\U0001f7e0"}

# Les vues d'indicateurs portent une echelle a TROIS niveaux et non deux :
# v_supervision_synthese classe la latence en avertissement des 60 s alors
# que la regle ne se declenche qu'a 300 s. Cette bande intermediaire est
# deliberee, c'est une pre-alerte destinee au tableau de bord. Rendre tout
# ce qui n'est pas nominal par une croix la ferait passer pour une panne, et
# annoncer une panne qui n'en est pas une coute la credibilite du canal
# aussi surement que de taire une vraie.
MARQUES = {"nominal": "✓", "avertissement": "!", CRITIQUE: "✗", "inconnu": "?"}


def composer_ouverture(regle: str, severite: str, message: str, depuis) -> str:
    depuis = _local(depuis)
    pastille = PASTILLES.get(severite, "⚪")
    return (
        f"{pastille} <b>{_e(severite.upper())}</b>  {_e(regle)}\n"
        f"{_e(message)}\n"
        f"<i>Ouverte a {depuis:%H:%M} le {depuis:%d/%m}.</i>"
    )


def composer_fermeture(regle: str, depuis, jusqu_a) -> str:
    # La duree se calcule AVANT conversion : elle est independante du fuseau,
    # et la convertir des deux cotes serait un calcul de plus pour rien.
    minutes = int((jusqu_a - depuis).total_seconds() // 60)
    depuis, jusqu_a = _local(depuis), _local(jusqu_a)
    duree = f"{minutes} min" if minutes < 120 else f"{minutes // 60} h {minutes % 60:02d}"
    return (
        f"\U0001f7e2 <b>REFERMEE</b>  {_e(regle)}\n"
        f"<i>Ouverte {duree}, refermee automatiquement a {jusqu_a:%H:%M}.</i>"
    )


def composer_battement(etat: dict) -> str:
    """Le bilan periodique. Il part que tout aille bien ou non.

    C'est ce qui le distingue d'une notification : son ABSENCE est un signal.
    Une alerte qui ne part pas est indiscernable d'une plateforme saine ; un
    battement qui ne part pas se remarque.
    """
    horodatage = _local(etat["horodatage"])
    lignes = [f"\U0001f4c5 <b>GameLens</b>  bilan du {horodatage:%d/%m a %H:%M}", ""]

    if etat["supervision_muette"]:
        lignes += [
            "\U0001f534 <b>LA SUPERVISION EST MUETTE</b>",
            f"Aucune evaluation depuis {etat['supervision_age_min']} minutes "
            f"(seuil {SEUIL_SUPERVISION_MUETTE_MIN}).",
            "Les alertes ci-dessous peuvent etre perimees.",
            "",
        ]

    for element, valeur, unite, niveau in etat["indicateurs"]:
        marque = MARQUES.get(niveau, "?")
        lignes.append(f"{marque} {_e(element)} : <b>{_e(valeur)}</b> {_e(unite)}")

    ouvertes = etat["alertes_ouvertes"]
    lignes.append("")
    if ouvertes:
        lignes.append(f"<b>{len(ouvertes)} alerte(s) ouverte(s)</b>")
        for regle, severite, depuis in ouvertes:
            pastille = PASTILLES.get(severite, "⚪")
            local = _local(depuis)
            lignes.append(f"{pastille} {_e(regle)}, depuis {local:%d/%m %H:%M}")
    else:
        lignes.append("Aucune alerte ouverte.")

    muets = etat["composants_muets"]
    if muets:
        lignes += ["", "<b>Composants sans execution recente</b>"]
        lignes += [f"✗ {_e(n)}, dernier passage {_e(q)}" for n, q in muets]

    return "\n".join(lignes)


# --------------------------------------------------------------------------
# Selection de ce qui doit partir
# --------------------------------------------------------------------------


def notifier_changements(compteurs: dict | None = None) -> dict:
    """Annonce les alertes critiques ouvertes et les fermetures deja annoncees.

    Les avertissements ne partent pas a l'unite : ils attendent le bilan. Ce
    qui demande une action et ce qui demande un regard n'appellent pas la meme
    interruption.

    Une fermeture n'est annoncee que si l'ouverture l'a ete. Sans cette
    condition, un avertissement jamais annonce produirait un message de
    fermeture sortant de nulle part.
    """
    compteurs = compteurs if compteurs is not None else {"records_in": 0, "records_written": 0}
    resultat = {"ouvertures": [], "fermetures": [], "echecs": 0, "configure": configure()}

    conn = connexion_pg()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """SELECT alerte_id, regle, severite, message, declenchee_le
                     FROM speed.alertes
                    WHERE resolue_le IS NULL
                      AND notifiee_le IS NULL
                      AND severite = %s
                    ORDER BY declenchee_le""",
                (CRITIQUE,),
            )
            for alerte_id, regle, severite, message, depuis in cur.fetchall():
                compteurs["records_in"] += 1
                if not resultat["configure"]:
                    continue
                if envoyer(composer_ouverture(regle, severite, message, depuis)):
                    cur.execute(
                        "UPDATE speed.alertes SET notifiee_le = now() WHERE alerte_id = %s",
                        (alerte_id,),
                    )
                    resultat["ouvertures"].append(regle)
                    compteurs["records_written"] += 1
                else:
                    resultat["echecs"] += 1

            cur.execute(
                """SELECT alerte_id, regle, declenchee_le, resolue_le
                     FROM speed.alertes
                    WHERE resolue_le IS NOT NULL
                      AND notifiee_le IS NOT NULL
                      AND resolution_notifiee_le IS NULL
                    ORDER BY resolue_le""",
            )
            for alerte_id, regle, depuis, jusqu_a in cur.fetchall():
                compteurs["records_in"] += 1
                if not resultat["configure"]:
                    continue
                if envoyer(composer_fermeture(regle, depuis, jusqu_a), discret=True):
                    cur.execute(
                        "UPDATE speed.alertes SET resolution_notifiee_le = now() WHERE alerte_id = %s",
                        (alerte_id,),
                    )
                    resultat["fermetures"].append(regle)
                    compteurs["records_written"] += 1
                else:
                    resultat["echecs"] += 1
    finally:
        conn.close()

    return resultat


def etat_plateforme() -> dict:
    """Lit l'etat courant pour le bilan periodique.

    Regarde AUSSI quand la supervision a tourne pour la derniere fois, ce que
    la supervision elle-meme ne fait pas. C'est le point de V-07 : on ne
    demande pas a un dispositif de temoigner de sa propre existence, on lui
    adjoint un temoin.
    """
    conn = connexion_pg()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT now()")
            horodatage = cur.fetchone()[0]

            cur.execute(
                """SELECT EXTRACT(epoch FROM (now() - max(started_at))) / 60
                     FROM speed.pipeline_runs WHERE component = 'moteur_alertes'"""
            )
            ligne = cur.fetchone()
            age = None if ligne is None or ligne[0] is None else int(ligne[0])

            cur.execute("SELECT element, valeur, unite, etat FROM speed.v_supervision_synthese")
            indicateurs = cur.fetchall()

            cur.execute(
                """SELECT regle, severite, declenchee_le FROM speed.alertes
                    WHERE resolue_le IS NULL
                    ORDER BY CASE severite WHEN 'critique' THEN 0 ELSE 1 END, declenchee_le"""
            )
            ouvertes = cur.fetchall()

            cur.execute(
                # Formate en SQL, donc dans le fuseau de la SESSION, qui est
                # UTC : _local() ne le verra jamais puisqu'il recoit deja du
                # texte. La conversion doit donc etre faite ici, sans quoi ce
                # seul champ resterait decale au milieu d'un message correct.
                """SELECT composant,
                          to_char(derniere_execution AT TIME ZONE %s, 'DD/MM HH24:MI')
                     FROM speed.v_indicateur_fiabilite
                    WHERE derniere_execution < now() - INTERVAL '26 hours'
                    ORDER BY derniere_execution""",
                (FUSEAU_AFFICHAGE,),
            )
            muets = cur.fetchall()
    finally:
        conn.close()

    return {
        "horodatage": horodatage,
        "supervision_age_min": age,
        "supervision_muette": age is None or age > SEUIL_SUPERVISION_MUETTE_MIN,
        "indicateurs": indicateurs,
        "alertes_ouvertes": ouvertes,
        "composants_muets": muets,
    }


# --------------------------------------------------------------------------
# Points d'entree traces
# --------------------------------------------------------------------------


def notifier_et_tracer() -> dict:
    with execution("notificateur", logger) as compteurs:
        resultat = notifier_changements(compteurs)
        if resultat["echecs"]:
            raise RuntimeError(
                f"{resultat['echecs']} message(s) non delivre(s) sur un canal configure"
            )
    return resultat


def battement_et_tracer() -> dict:
    with execution("battement", logger) as compteurs:
        etat = etat_plateforme()
        compteurs["records_in"] = len(etat["indicateurs"])
        if not configure():
            logger.warning("canal Telegram non configure : bilan non envoye")
            return {"envoye": False, "configure": False, "etat": etat}
        if not envoyer(composer_battement(etat)):
            raise RuntimeError("bilan non delivre sur un canal configure")
        compteurs["records_written"] = 1
    return {"envoye": True, "configure": True, "etat": etat}


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument(
        "--essai", action="store_true", help="envoie un message de verification et sort"
    )
    parseur.add_argument(
        "--battement", action="store_true", help="compose et envoie le bilan periodique"
    )
    args = parseur.parse_args(argv)

    if not configure():
        logger.error(
            "TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID absents de l'environnement. "
            "Les renseigner dans .env, voir .env.example."
        )
        return 1

    if args.essai:
        ok = envoyer(
            "✅ <b>GameLens</b>\nCanal de notification operationnel.\n"
            "<i>Message d'essai, aucune action requise.</i>"
        )
        logger.info("message d'essai %s", "delivre" if ok else "NON delivre")
        return 0 if ok else 1

    if args.battement:
        resultat = battement_et_tracer()
        logger.info("bilan %s", "envoye" if resultat["envoye"] else "non envoye")
        return 0

    resultat = notifier_et_tracer()
    logger.info(
        "%s ouverture(s) et %s fermeture(s) annoncees",
        len(resultat["ouvertures"]),
        len(resultat["fermetures"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
