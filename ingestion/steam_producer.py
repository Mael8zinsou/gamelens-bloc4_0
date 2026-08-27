"""Producer temps reel : Steam Web API vers Kafka.

Interroge GetNumberOfCurrentPlayers pour chaque titre suivi et publie un
evenement par titre sur le topic Kafka. C'est la premiere moitie de la branche
speed de l'architecture Lambda (Bloc 1) et la premiere des trois methodes de
traitement exigees par C4.2.2.

Choix de conception notables :

- La cle Kafka est l'appid. Kafka garantit l'ordre a l'interieur d'une
  partition : cle constante par jeu, donc les releves d'un meme titre restent
  ordonnes meme si le topic est partitionne pour passer a l'echelle.
- Un titre en echec ne fait pas tomber le cycle. Une API tierce indisponible
  est un aleas nominal, pas une exception : le cycle se poursuit et l'echec est
  compte, ce que la supervision detectera via le ratio ecrits sur lus.
- acks="all" : l'accuse de reception n'est renvoye qu'une fois l'ecriture
  repliquee. Sur un broker a noeud unique l'effet est limite, mais le reglage
  est celui qui vaut en production et evite une mauvaise surprise a la montee
  en charge.

Usage :
    python steam_producer.py --once          un seul cycle puis sortie
    python steam_producer.py --cycles 3      trois cycles
    python steam_producer.py                 boucle continue
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import requests
from bronze import Archive, archive
from common import charger_watchlist, config, configurer_logs, execution
from kafka import KafkaProducer
from kafka.errors import KafkaError

# Nom du point d'appel dans bronze.reponses_brutes. Constante plutot que
# chaine libre : la vue bronze.v_sante_sources regroupe dessus.
SOURCE_BRONZE = "steam_player_count"

logger = configurer_logs("steam_producer")

URL_STEAM = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
DELAI_ENTRE_APPELS = 0.4  # respect des limites de frequence de l'API Steam
TIMEOUT_HTTP = 10


@dataclass
class Releve:
    """Resultat d'un appel a Steam, exploitable ou non.

    Renvoyer un objet plutot qu'un `int | None` n'est pas du confort : la
    couche Bronze a besoin de la reponse telle que recue et de la raison du
    rejet, or les deux etaient jetes dans la ligne meme qui en extrayait le
    nombre de joueurs.
    """

    joueurs: int | None
    charge: dict | None
    statut_http: int | None
    motif_rejet: str | None


def interroger_steam(session: requests.Session, appid: int) -> Releve:
    """Interroge Steam et rend la reponse complete, exploitable ou non."""
    reponse = session.get(URL_STEAM, params={"appid": appid}, timeout=TIMEOUT_HTTP)
    statut = reponse.status_code
    reponse.raise_for_status()

    corps = reponse.json()
    contenu = corps.get("response", {})
    # result == 1 signale une reponse exploitable cote Steam ; toute autre
    # valeur accompagne une reponse HTTP 200 sans donnee utile.
    if contenu.get("result") != 1:
        return Releve(None, corps, statut, f"result={contenu.get('result')!r}")
    if "player_count" not in contenu:
        return Releve(None, corps, statut, "player_count absent de la reponse")
    return Releve(int(contenu["player_count"]), corps, statut, None)


def cycle(
    producteur: KafkaProducer,
    topic: str,
    titres: list[dict],
    compteurs: dict,
    depot: Archive,
) -> None:
    """Un passage complet sur la watchlist.

    Chaque appel est archive en couche Bronze AVANT toute exploitation, y
    compris ceux qui echouent. C'est l'ordre qui compte : archiver apres avoir
    exploite reviendrait a ne conserver que ce qu'on a su lire.
    """
    session = requests.Session()
    session.headers["User-Agent"] = "GameLens/1.0 (projet de certification RNCP39586)"
    collecte_le = datetime.now(UTC).replace(microsecond=0)

    for titre in titres:
        appid = titre["steam_appid"]
        compteurs["records_in"] += 1
        try:
            releve = interroger_steam(session, appid)
        except requests.RequestException as exc:
            # Un appel qui n'aboutit pas est une observation, pas un neant :
            # la source etait injoignable a cet instant precis, et c'est
            # exactement ce qu'on voudra savoir en analysant un trou.
            depot.enregistrer(
                SOURCE_BRONZE,
                appid,
                collecte_le,
                motif_rejet=f"{type(exc).__name__}: {exc}"[:500],
            )
            logger.warning(
                "appid=%s injoignable (%s), titre ignore pour ce cycle", appid, type(exc).__name__
            )
            continue

        depot.enregistrer(
            SOURCE_BRONZE,
            appid,
            collecte_le,
            charge=releve.charge,
            statut_http=releve.statut_http,
            motif_rejet=releve.motif_rejet,
        )

        if releve.joueurs is None:
            continue

        joueurs = releve.joueurs
        evenement = {
            "steam_appid": appid,
            "unified_name": titre["unified_name"],
            "player_count": joueurs,
            "collected_at": collecte_le.isoformat(),
        }
        producteur.send(topic, key=str(appid).encode(), value=evenement)
        compteurs["records_written"] += 1
        logger.info("appid=%-8s %-18s %8s joueurs", appid, titre["unified_name"], joueurs)
        time.sleep(DELAI_ENTRE_APPELS)

    producteur.flush(timeout=30)


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Producer Steam vers Kafka")
    parseur.add_argument("--once", action="store_true", help="un seul cycle puis sortie")
    parseur.add_argument("--cycles", type=int, default=0, help="nombre de cycles (0 = infini)")
    args = parseur.parse_args(argv)

    cfg = config()
    titres = charger_watchlist()
    cycles_vises = 1 if args.once else args.cycles

    logger.info(
        "%s titres suivis, topic=%s, broker=%s, intervalle=%ss",
        len(titres),
        cfg["topic_players"],
        cfg["kafka_servers"],
        cfg["poll_interval"],
    )

    # Le producteur est construit A L'INTERIEUR du contexte de tracage, et non
    # avant lui. Corrige un angle mort constate le 27/08/2026 par un test
    # deliberé, broker arrete : KafkaProducer leve NoBrokersAvailable des sa
    # construction, donc AVANT que execution() n'ouvre la ligne de journal. Une
    # panne de broker ne laissait alors aucune trace en echec dans
    # speed.pipeline_runs. La supervision finissait par la voir, mais comme un
    # composant muet et non comme une execution echouee, ce qui est un
    # diagnostic moins precis pour la meme panne.
    producteur = None
    try:
        with execution("steam_producer", logger) as compteurs, archive(logger) as depot:
            producteur = KafkaProducer(
                bootstrap_servers=cfg["kafka_servers"].split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
                linger_ms=50,
            )
            numero = 0
            while True:
                numero += 1
                logger.info("--- cycle %s ---", numero)
                cycle(producteur, cfg["topic_players"], titres, compteurs, depot)
                if cycles_vises and numero >= cycles_vises:
                    break
                time.sleep(cfg["poll_interval"])
    except KeyboardInterrupt:
        logger.info("arret demande par l'operateur")
    except KafkaError as exc:
        logger.error("erreur Kafka : %s", exc)
        return 1
    finally:
        # Peut valoir None si la construction elle-meme a echoue.
        if producteur is not None:
            producteur.close(timeout=10)

    return 0


if __name__ == "__main__":
    sys.exit(main())
