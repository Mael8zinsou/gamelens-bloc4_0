"""Declaration explicite des topics Kafka.

Kafka cree un topic a la volee a la premiere ecriture, ce qui depanne en
developpement mais laisse le partitionnement et la retention au hasard des
valeurs par defaut du broker. Les topics sont donc declares ici, de maniere
idempotente, pour que ces deux parametres soient des decisions et non des
effets de bord.

Partitionnement : une seule partition. Le volume actuel est de 150 evenements
par cycle et par source, tres loin du seuil ou le parallelisme apporte quoi
que ce soit, et
une partition unique donne l'ordre total gratuitement. Le producer publie
malgre tout avec l'appid en cle : le jour ou le nombre de partitions augmente,
l'ordre reste garanti par titre, sans rien changer au code.
"""

from __future__ import annotations

import sys

from common import config, configurer_logs
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

logger = configurer_logs("create_topics")

RETENTION_7_JOURS_MS = str(7 * 24 * 60 * 60 * 1000)

TOPICS = [
    NewTopic(
        name="gamelens.steam.player_count",
        num_partitions=1,
        replication_factor=1,
        topic_configs={
            "retention.ms": RETENTION_7_JOURS_MS,
            "cleanup.policy": "delete",
        },
    ),
    # Audience diffusee. Topic SEPARE et non un type d'evenement de plus
    # sur le topic existant : les deux flux n'ont ni la meme cadence de
    # panne ni le meme puits, et un consumer qui rejoue les offsets d'une
    # source ne doit pas rejouer ceux de l'autre.
    NewTopic(
        name="gamelens.twitch.viewer_count",
        num_partitions=1,
        replication_factor=1,
        topic_configs={
            "retention.ms": RETENTION_7_JOURS_MS,
            "cleanup.policy": "delete",
        },
    ),
]


def main() -> int:
    cfg = config()
    admin = KafkaAdminClient(bootstrap_servers=cfg["kafka_servers"].split(","))
    try:
        for topic in TOPICS:
            try:
                admin.create_topics([topic])
                logger.info(
                    "topic %s cree (%s partition(s), retention 7 jours)",
                    topic.name,
                    topic.num_partitions,
                )
            except TopicAlreadyExistsError:
                logger.info("topic %s deja present, rien a faire", topic.name)
        logger.info(
            "topics du cluster : %s",
            sorted(t for t in admin.list_topics() if not t.startswith("__")),
        )
    finally:
        admin.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
