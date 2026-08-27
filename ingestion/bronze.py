"""Archivage des reponses d'API telles que recues (couche Bronze).

L'architecture Medallion du Bloc 1 declare une couche Bronze. Elle n'existait
pas : la chaine allait de l'API a Silver directement, et la reponse d'origine
etait jetee dans la ligne meme qui en extrayait la valeur utile.

Ce module comble ce manque. Voir `sql/schema_bronze.sql` pour le raisonnement
complet, dont l'ecart assume avec le stockage objet annonce au Bloc 1.

## Connexion dediee, et pourquoi

L'archivage ouvre sa PROPRE connexion, en autocommit, distincte de celle du
traitement metier. Meme raisonnement que `execution()` dans common.py : si la
transaction metier est annulee, la trace de ce qui a ete recu doit survivre.
Une archive qui disparait avec l'echec de ce qu'on en derivait ne sert a rien,
puisque c'est precisement ce cas qui justifie son existence.

## Ce qui est archive

Tout appel, abouti ou non. Le "ou non" n'est pas du zele : avant cette table,
une reponse inexploitable ne produisait qu'un avertissement dans les journaux,
puis disparaissait. L'observation "la source a repondu pour cet identifiant a
cet instant, mais sans donnee utilisable" est pourtant le signal d'un jeu
retire du catalogue ou d'une API qui se degrade.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime

import psycopg2.extras
from common import connexion_pg

INSERTION = """
    INSERT INTO bronze.reponses_brutes
        (source, identifiant, collecte_le, statut_http, exploitable, motif_rejet, charge)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT ON CONSTRAINT uq_reponses_brutes_grain DO NOTHING
"""


class Archive:
    """Ecrit dans bronze.reponses_brutes et compte ce qu'elle a vu.

    Les compteurs ne sont pas decoratifs : ils permettent a l'appelant de
    verifier que le nombre d'appels archives correspond au nombre d'appels
    emis. Un ecart signale un chemin de code qui interroge une source sans
    passer par l'archive, ce qui est exactement le defaut que ce module existe
    pour supprimer.
    """

    def __init__(self, conn, logger: logging.Logger) -> None:
        self._conn = conn
        self._logger = logger
        self.archivees = 0
        self.exploitables = 0
        self.rejets = 0

    def enregistrer(
        self,
        source: str,
        identifiant: str | int,
        collecte_le: datetime,
        charge: dict | list | None = None,
        statut_http: int | None = None,
        motif_rejet: str | None = None,
    ) -> None:
        """Archive une reponse. `motif_rejet` non nul la declare inexploitable.

        Ne rattrape pas les erreurs d'ecriture. Un archivage qui echoue en
        silence rendrait la couche Bronze inutile le jour ou elle servirait, et
        la base visee est de toute facon la meme que celle du journal
        d'executions : si elle est indisponible, le run est deja perdu.
        """
        exploitable = motif_rejet is None
        with self._conn.cursor() as cur:
            cur.execute(
                INSERTION,
                (
                    source,
                    str(identifiant),
                    collecte_le,
                    statut_http,
                    exploitable,
                    motif_rejet,
                    psycopg2.extras.Json(charge) if charge is not None else None,
                ),
            )
        self.archivees += 1
        if exploitable:
            self.exploitables += 1
        else:
            self.rejets += 1
            self._logger.warning(
                "bronze : %s/%s inexploitable (%s)", source, identifiant, motif_rejet
            )


@contextmanager
def archive(logger: logging.Logger):
    """Ouvre une archive Bronze le temps d'une collecte."""
    conn = connexion_pg()
    conn.autocommit = True
    depot = Archive(conn, logger)
    try:
        yield depot
    finally:
        conn.close()
        logger.info(
            "bronze : %s reponse(s) archivee(s), dont %s exploitable(s) et %s rejet(s)",
            depot.archivees,
            depot.exploitables,
            depot.rejets,
        )
