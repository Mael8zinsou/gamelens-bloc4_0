"""Consumer temps reel : Kafka vers la couche Silver speed (PostgreSQL).

Seconde moitie de la branche speed. Consomme le topic des relevés de
frequentation et ecrit dans speed.player_count_events.

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

INSERTION = """
INSERT INTO speed.player_count_events
    (steam_appid, player_count, collected_at, kafka_partition, kafka_offset)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_player_count_event DO NOTHING
"""


def traiter_lot(conn, messages: list, compteurs: dict) -> int:
    """Ecrit un lot de messages et retourne le nombre de lignes reellement inserees.

    L'ecart entre le nombre de messages recus et le nombre de lignes inserees
    n'est pas une anomalie : il mesure les doublons absorbes par l'idempotence.
    """
    inseres = 0
    with conn, conn.cursor() as cur:
        for message in messages:
            evenement = message.value
            cur.execute(
                INSERTION,
                (
                    evenement["steam_appid"],
                    evenement["player_count"],
                    evenement["collected_at"],
                    message.partition,
                    message.offset,
                ),
            )
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
    consommateur = KafkaConsumer(
        cfg["topic_players"],
        bootstrap_servers=cfg["kafka_servers"].split(","),
        group_id=GROUPE,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest" if args.depuis_le_debut else "latest",
        enable_auto_commit=False,  # la validation suit l'ecriture en base
        consumer_timeout_ms=args.timeout * 1000 if args.timeout else float("inf"),
        max_poll_records=200,
    )

    logger.info("groupe=%s topic=%s broker=%s", GROUPE, cfg["topic_players"], cfg["kafka_servers"])
    conn = connexion_pg()

    try:
        with execution("kafka_to_postgres", logger) as compteurs:
            lot: list = []
            for message in consommateur:
                compteurs["records_in"] += 1
                lot.append(message)
                if len(lot) >= 50:
                    inseres = traiter_lot(conn, lot, compteurs)
                    consommateur.commit()
                    logger.info(
                        "lot de %s messages : %s inseres, %s doublons absorbes",
                        len(lot),
                        inseres,
                        len(lot) - inseres,
                    )
                    lot = []
            if lot:
                inseres = traiter_lot(conn, lot, compteurs)
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
        consommateur.close()
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
