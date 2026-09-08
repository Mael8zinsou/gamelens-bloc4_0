"""Producer temps reel : Twitch Helix vers Kafka.

Seconde source de la plateforme, et la premiere qui mesure autre chose que
Steam. Steam dit qui JOUE, Twitch dit qui REGARDE : ce n'est pas une source de
plus sur le meme axe, c'est un second axe, et le seul indicateur avance du
dispositif. Une poussee d'audience precede generalement une poussee de ventes.

Ecrit sur le patron de steam_producer.py, deliberement : meme archivage Bronze
avant exploitation, meme tolerance a l'echec d'un titre, meme tracage par
execution(). Deux sources qui se ressemblent se supervisent et se diagnostiquent
de la meme facon.

## Ce que cette source change pour game_mapping

speed.game_mapping porte un nom qui annonce la resolution d'identifiants entre
plateformes. Jusqu'a cette source elle ne resolvait que des identifiants Steam,
sa colonne twitch_game_id restant nulle sur la totalite du panel. C'est
seed_twitch_ids.py qui la remplit, et ce producteur qui s'en sert.

## Trois choix a defendre

1. **Le jeton est demande a chaque execution.** Un jeton d'application Twitch
   vaut une soixantaine de jours ; le mettre en cache economiserait un appel
   sur 150. En echange il faudrait gerer sa peremption, son stockage et son
   invalidation, c'est-a-dire trois facons de tomber en panne pour un gain
   nul a cette echelle. Le renouvellement systematique est le comportement
   correct par construction.

2. **L'audience est la somme des 100 streams les plus regardes**, pas de tous.
   Helix rend les streams tries par audience decroissante ; au-dela du
   centieme, la queue longue est faite de diffusions a un ou deux
   spectateurs. Paginer jusqu'a l'epuisement multiplierait le cout d'appel
   pour une correction inferieure au pourcent. La troncature est constatee et
   archivee plutot que passee sous silence.

3. **Zero spectateur est une observation, pas une absence.** Un titre sans
   aucun stream en direct rend legitimement zero. C'est ce qui justifie une
   table distincte de player_count_events : fusionner les deux flux imposerait
   de distinguer le zero de l'absence dans une colonne nullable.

Usage :
    python twitch_producer.py --once          un seul cycle puis sortie
    python twitch_producer.py --cycles 3      trois cycles
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
from common import config, configurer_logs, connexion_pg, execution
from kafka import KafkaProducer
from kafka.errors import KafkaError

SOURCE_BRONZE = "twitch_viewers"

logger = configurer_logs("twitch_producer")

URL_JETON = "https://id.twitch.tv/oauth2/token"
URL_STREAMS = "https://api.twitch.tv/helix/streams"
DELAI_ENTRE_APPELS = 0.2  # Helix tolere 800 points par minute, un appel valant 1
LIMITE_STREAMS = 100  # maximum accepte par Helix sur un seul appel
TIMEOUT_HTTP = 10


@dataclass
class Releve:
    """Resultat d'un appel a Helix, exploitable ou non.

    Meme forme que le Releve de steam_producer.py, pour que les deux sources
    s'archivent et se diagnostiquent de la meme maniere.
    """

    spectateurs: int | None
    streams: int | None
    tronque: bool
    charge: dict | None
    statut_http: int | None
    motif_rejet: str | None


def obtenir_jeton(session: requests.Session, identifiant: str, secret: str) -> str:
    """Jeton d'application par le flux client_credentials.

    Ce flux n'engage aucun utilisateur : il authentifie l'application seule, ce
    qui est exactement ce qu'un pipeline peut satisfaire. Meme raisonnement que
    la paire de clefs RSA cote Snowflake, ou l'authentification multifacteur
    imposee aux humains est hors de portee d'un traitement automatique.
    """
    reponse = session.post(
        URL_JETON,
        params={
            "client_id": identifiant,
            "client_secret": secret,
            "grant_type": "client_credentials",
        },
        timeout=TIMEOUT_HTTP,
    )
    reponse.raise_for_status()
    jeton = reponse.json().get("access_token")
    if not jeton:
        raise RuntimeError("Twitch n'a pas rendu de jeton d'acces")
    return jeton


def interroger_twitch(session: requests.Session, entetes: dict, game_id: str) -> Releve:
    """Somme l'audience des streams en direct d'un titre."""
    reponse = session.get(
        URL_STREAMS,
        params={"game_id": game_id, "first": LIMITE_STREAMS, "type": "live"},
        headers=entetes,
        timeout=TIMEOUT_HTTP,
    )
    statut = reponse.status_code
    reponse.raise_for_status()

    corps = reponse.json()
    diffusions = corps.get("data")
    if diffusions is None:
        return Releve(None, None, False, corps, statut, "champ data absent de la reponse")

    spectateurs = sum(int(d.get("viewer_count", 0)) for d in diffusions)
    # Le curseur de pagination n'est present que s'il reste des streams au-dela
    # de la page demandee : c'est ainsi que la troncature se constate.
    tronque = bool(corps.get("pagination", {}).get("cursor")) and len(diffusions) >= LIMITE_STREAMS
    return Releve(spectateurs, len(diffusions), tronque, corps, statut, None)


def titres_resolus() -> list[dict]:
    """Titres du panel dont l'identifiant Twitch est resolu.

    Lus en base et non dans la watchlist : la resolution est le produit de
    seed_twitch_ids.py, elle vit dans le referentiel et pas dans un fichier de
    configuration ecrit a la main.
    """
    conn = connexion_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT steam_appid, unified_name, twitch_game_id
                  FROM speed.game_mapping
                 WHERE is_active AND twitch_game_id IS NOT NULL
                 ORDER BY steam_appid
                """
            )
            return [
                {"steam_appid": a, "unified_name": n, "twitch_game_id": t}
                for a, n, t in cur.fetchall()
            ]
    finally:
        conn.close()


def cycle(
    producteur: KafkaProducer,
    topic: str,
    titres: list[dict],
    entetes: dict,
    compteurs: dict,
    depot: Archive,
) -> None:
    """Un passage complet sur les titres resolus.

    Comme cote Steam, chaque appel est archive en couche Bronze AVANT toute
    exploitation, y compris ceux qui echouent : archiver apres avoir exploite
    reviendrait a ne conserver que ce qu'on a su lire.
    """
    session = requests.Session()
    collecte_le = datetime.now(UTC).replace(microsecond=0)

    for titre in titres:
        appid, game_id = titre["steam_appid"], titre["twitch_game_id"]
        compteurs["records_in"] += 1
        try:
            releve = interroger_twitch(session, entetes, game_id)
        except requests.RequestException as exc:
            depot.enregistrer(
                SOURCE_BRONZE,
                game_id,
                collecte_le,
                motif_rejet=f"{type(exc).__name__}: {exc}"[:500],
            )
            logger.warning(
                "game_id=%s injoignable (%s), titre ignore pour ce cycle",
                game_id,
                type(exc).__name__,
            )
            continue

        depot.enregistrer(
            SOURCE_BRONZE,
            game_id,
            collecte_le,
            charge=releve.charge,
            statut_http=releve.statut_http,
            motif_rejet=releve.motif_rejet,
        )

        if releve.spectateurs is None:
            continue

        evenement = {
            "steam_appid": appid,
            "twitch_game_id": game_id,
            "unified_name": titre["unified_name"],
            "viewer_count": releve.spectateurs,
            "stream_count": releve.streams,
            "collected_at": collecte_le.isoformat(),
        }
        producteur.send(topic, key=str(appid).encode(), value=evenement)
        compteurs["records_written"] += 1
        logger.info(
            "game_id=%-8s %-24s %7s spectateurs sur %3s stream(s)%s",
            game_id,
            titre["unified_name"][:24],
            releve.spectateurs,
            releve.streams,
            " (tronque)" if releve.tronque else "",
        )
        time.sleep(DELAI_ENTRE_APPELS)

    producteur.flush(timeout=30)


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Producer Twitch vers Kafka")
    parseur.add_argument("--once", action="store_true", help="un seul cycle puis sortie")
    parseur.add_argument("--cycles", type=int, default=0, help="nombre de cycles (0 = infini)")
    args = parseur.parse_args(argv)

    cfg = config()
    if not cfg["twitch_client_id"] or not cfg["twitch_client_secret"]:
        # Absent n'est pas casse, meme asymetrie que le canal de notification :
        # un depot fraichement clone et l'etage tests de la CI n'ont pas
        # d'identifiants Twitch et doivent fonctionner. En revanche des
        # identifiants presents mais refuses SONT une panne, tracee plus bas.
        logger.warning("identifiants Twitch absents, collecte d'audience ignoree")
        return 0

    titres = titres_resolus()
    if not titres:
        logger.warning("aucun titre ne porte de twitch_game_id. Lancer seed_twitch_ids.py d'abord.")
        return 0

    cycles_vises = 1 if args.once else args.cycles
    logger.info(
        "%s titres resolus, topic=%s, broker=%s",
        len(titres),
        cfg["topic_viewers"],
        cfg["kafka_servers"],
    )

    producteur = None
    try:
        # Le producteur est construit A L'INTERIEUR du contexte de tracage,
        # comme cote Steam : KafkaProducer leve des sa construction si le
        # broker est absent, et une panne survenue avant l'ouverture de la
        # ligne de journal ne laisserait aucune trace en echec.
        with execution("twitch_producer", logger) as compteurs, archive(logger) as depot:
            session = requests.Session()
            jeton = obtenir_jeton(session, cfg["twitch_client_id"], cfg["twitch_client_secret"])
            entetes = {"Client-Id": cfg["twitch_client_id"], "Authorization": f"Bearer {jeton}"}

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
                cycle(producteur, cfg["topic_viewers"], titres, entetes, compteurs, depot)
                if cycles_vises and numero >= cycles_vises:
                    break
                time.sleep(cfg["poll_interval"])
    except KeyboardInterrupt:
        logger.info("arret demande par l'operateur")
    except KafkaError as exc:
        logger.error("erreur Kafka : %s", exc)
        return 1
    finally:
        if producteur is not None:
            producteur.close(timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(main())
