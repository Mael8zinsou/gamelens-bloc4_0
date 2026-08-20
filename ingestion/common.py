"""Briques partagees par les composants d'ingestion GameLens.

Regroupe ce que le producer et le consumer utilisent tous les deux :
chargement de la configuration, connexion PostgreSQL, journalisation, et
enregistrement des executions dans speed.pipeline_runs (socle de la
supervision, C4.3.1).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent

load_dotenv(RACINE / ".env")


def configurer_logs(nom: str) -> logging.Logger:
    """Journalisation sur la sortie standard, horodatee et prefixee du composant.

    Le format est volontairement identique pour tous les composants : les
    fichiers de log conserves servent de preuve d'execution reelle et doivent
    rester lisibles cote a cote.
    """
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    return logging.getLogger(nom)


def config() -> dict:
    """Configuration effective, valeurs par defaut alignees sur docker-compose.yml."""
    return {
        "pg_host": os.getenv("POSTGRES_HOST", "localhost"),
        "pg_port": int(os.getenv("POSTGRES_PORT", "5432")),
        "pg_db": os.getenv("POSTGRES_DB", "gamelens"),
        "pg_user": os.getenv("POSTGRES_USER", "gamelens_app"),
        "pg_password": os.getenv("POSTGRES_PASSWORD", "devlocal_app"),
        "kafka_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        "topic_players": os.getenv("KAFKA_TOPIC_PLAYERS", "gamelens.steam.player_count"),
        "poll_interval": int(os.getenv("STEAM_POLL_INTERVAL_SECONDS", "60")),
    }


def connexion_pg():
    """Ouvre une connexion PostgreSQL vers la couche Silver speed."""
    c = config()
    return psycopg2.connect(
        host=c["pg_host"],
        port=c["pg_port"],
        dbname=c["pg_db"],
        user=c["pg_user"],
        password=c["pg_password"],
        connect_timeout=10,
    )


def charger_watchlist() -> list[dict]:
    """Charge la liste des titres suivis depuis config/watchlist.json."""
    with open(RACINE / "config" / "watchlist.json", encoding="utf-8") as f:
        titres = json.load(f)["titres"]
    return [t for t in titres if not t.get("_desactive")]


@contextmanager
def execution(composant: str, logger: logging.Logger):
    """Enregistre une execution dans speed.pipeline_runs, succes comme echec.

    Utilise sa propre connexion, distincte de celle du traitement : si la
    transaction metier est annulee, la trace de l'echec doit malgre tout
    survivre. C'est precisement ce que l'on veut superviser.
    """
    conn = connexion_pg()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO speed.pipeline_runs (component, status) VALUES (%s, 'started') RETURNING run_id",
            (composant,),
        )
        run_id = cur.fetchone()[0]
    logger.info("execution %s demarree (run_id=%s)", composant, run_id)

    compteurs = {"records_in": 0, "records_written": 0}
    try:
        yield compteurs
    except BaseException as exc:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE speed.pipeline_runs
                      SET status = 'failed', ended_at = now(),
                          records_in = %s, records_written = %s, error_message = %s
                    WHERE run_id = %s""",
                (
                    compteurs["records_in"],
                    compteurs["records_written"],
                    f"{type(exc).__name__}: {exc}"[:2000],
                    run_id,
                ),
            )
        logger.error("execution %s en echec : %s: %s", composant, type(exc).__name__, exc)
        raise
    else:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE speed.pipeline_runs
                      SET status = 'success', ended_at = now(),
                          records_in = %s, records_written = %s
                    WHERE run_id = %s""",
                (compteurs["records_in"], compteurs["records_written"], run_id),
            )
        logger.info(
            "execution %s terminee (lus=%s, ecrits=%s)",
            composant,
            compteurs["records_in"],
            compteurs["records_written"],
        )
    finally:
        conn.close()
