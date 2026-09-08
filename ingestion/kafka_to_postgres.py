"""Consumer temps reel : Kafka vers la couche Silver speed (PostgreSQL).

Seconde moitie de la branche speed. Consomme les DEUX topics de la plateforme
et ecrit chacun dans sa table : la frequentation jouee venue de Steam vers
speed.player_count_events, l'audience diffusee venue de Twitch vers
speed.viewer_count_events.

Un seul consumer et non deux, et c'est le choix a defendre. Dupliquer le module
aurait ete plus rapide, mais aurait fige deux exemplaires de la garantie de
livraison decrite ci-dessous, donc deux endroits ou la corriger le jour ou elle
se revele fausse. La boucle, l'ordre des validations et le tracage restent
uniques ; seuls la requete d'ecriture et l'extraction des parametres varient
selon le topic d'origine du message.

Les topics restent SEPARES en amont, eux : deux sources n'ont ni la meme
cadence de panne ni le meme puits, et rejouer les offsets de l'une ne doit pas
rejouer ceux de l'autre.

Garantie de livraison, point central a defendre a l'oral :

Kafka offre un at-least-once, pas un exactly-once, des lors que l'on ecrit vers
un systeme externe : entre l'ecriture en base et la validation de l'offset, un
arret brutal fait rejouer les memes messages au redemarrage. Plutot que de
chercher une transaction distribuee entre Kafka et PostgreSQL, le puits est
rendu idempotent :

  1. la table porte une contrainte UNIQUE (steam_appid, collected_at) ;
  2. l'ecriture se fait en ON CONFLICT DO NOTHING ;
  3. l'offset n'est valide qu'APRES le commit PostgreSQL.

Un doublon rejoue est donc absorbe silencieusement, et l'ordre des deux
validations garantit qu'aucun message n'est perdu. Le resultat est un
effectively-once, obtenu avec une contrainte d'unicite plutot qu'avec un
protocole distribue.

Usage :
    python kafka_to_postgres.py --timeout 30      s'arrete apres 30s sans message
    python kafka_to_postgres.py                   consommation continue
"""

from __future__ import annotations

import argparse
import json
import sys

from common import config, configurer_logs, connexion_pg, execution
from kafka import KafkaConsumer

logger = configurer_logs("kafka_to_pg")

GROUPE = "gamelens-silver-speed"

INSERTION_FREQUENTATION = """
INSERT INTO speed.player_count_events
    (steam_appid, player_count, collected_at, kafka_partition, kafka_offset)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_player_count_event DO NOTHING
"""

INSERTION_AUDIENCE = """
INSERT INTO speed.viewer_count_events
    (steam_appid, twitch_game_id, viewer_count, stream_count, collected_at,
     kafka_partition, kafka_offset)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_viewer_count_event DO NOTHING
"""


def _parametres_frequentation(evenement: dict, message) -> tuple:
    return (
        evenement["steam_appid"],
        evenement["player_count"],
        evenement["collected_at"],
        message.partition,
        message.offset,
    )


def _parametres_audience(evenement: dict, message) -> tuple:
    return (
        evenement["steam_appid"],
        evenement["twitch_game_id"],
        evenement["viewer_count"],
        evenement["stream_count"],
        evenement["collected_at"],
        message.partition,
        message.offset,
    )


def puits(cfg: dict) -> dict:
    """Associe chaque topic a sa requete d'ecriture et a son extracteur.

    Construit depuis la configuration plutot qu'en constante : les noms de
    topic sont surchargeables par l'environnement, et une table figee ici
    divergerait silencieusement de ce que le consumer ecoute reellement.
    """
    return {
        cfg["topic_players"]: (INSERTION_FREQUENTATION, _parametres_frequentation),
        cfg["topic_viewers"]: (INSERTION_AUDIENCE, _parametres_audience),
    }


def traiter_lot(conn, messages: list, compteurs: dict, tables: dict) -> int:
    """Ecrit un lot de messages et retourne le nombre de lignes reellement inserees.

    L'ecart entre le nombre de messages recus et le nombre de lignes inserees
    n'est pas une anomalie : il mesure les doublons absorbes par l'idempotence.

    Un lot peut melanger les deux sources : le puits est choisi message par
    message sur son topic d'origine, et un topic inconnu leve plutot que d'etre
    ignore. Ecrire une audience dans la table de frequentation serait pire
    qu'une panne, puisque personne ne le verrait.
    """
    inseres = 0
    with conn, conn.cursor() as cur:
        for message in messages:
            if message.topic not in tables:
                raise KeyError(f"topic inattendu : {message.topic}")
            requete, extraire = tables[message.topic]
            cur.execute(requete, extraire(message.value, message))
            inseres += cur.rowcount
    compteurs["records_written"] += inseres
    return inseres


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Consumer Kafka vers PostgreSQL")
    parseur.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="arret apres N secondes sans nouveau message (0 = jamais)",
    )
    parseur.add_argument(
        "--depuis-le-debut",
        action="store_true",
        help="repartir du debut du topic plutot que du dernier offset valide",
    )
    args = parseur.parse_args(argv)

    cfg = config()
    tables = puits(cfg)
    logger.info("groupe=%s topics=%s broker=%s", GROUPE, sorted(tables), cfg["kafka_servers"])

    # Consommateur et connexion construits A L'INTERIEUR du contexte de tracage.
    # Meme correction que dans steam_producer.py, pour la meme raison constatee
    # le 27/08/2026 : construits avant, un broker injoignable ou une base
    # indisponible levaient leur exception avant l'ouverture de la ligne de
    # journal, et la panne ne laissait aucune trace en echec.
    consommateur = None
    conn = None
    try:
        with execution("kafka_to_postgres", logger) as compteurs:
            consommateur = KafkaConsumer(
                *sorted(tables),
                bootstrap_servers=cfg["kafka_servers"].split(","),
                group_id=GROUPE,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="earliest" if args.depuis_le_debut else "latest",
                enable_auto_commit=False,  # la validation suit l'ecriture en base
                consumer_timeout_ms=args.timeout * 1000 if args.timeout else float("inf"),
                max_poll_records=200,
            )
            conn = connexion_pg()
            lot: list = []
            for message in consommateur:
                compteurs["records_in"] += 1
                lot.append(message)
                if len(lot) >= 50:
                    inseres = traiter_lot(conn, lot, compteurs, tables)
                    consommateur.commit()
                    logger.info(
                        "lot de %s messages : %s inseres, %s doublons absorbes",
                        len(lot),
                        inseres,
                        len(lot) - inseres,
                    )
                    lot = []
            if lot:
                inseres = traiter_lot(conn, lot, compteurs, tables)
                consommateur.commit()
                logger.info(
                    "lot final de %s messages : %s inseres, %s doublons absorbes",
                    len(lot),
                    inseres,
                    len(lot) - inseres,
                )
    except KeyboardInterrupt:
        logger.info("arret demande par l'operateur")
    finally:
        # L'un ou l'autre peut valoir None si sa construction a echoue.
        if consommateur is not None:
            consommateur.close()
        if conn is not None:
            conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
