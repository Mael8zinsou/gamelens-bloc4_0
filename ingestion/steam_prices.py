"""Collecte tarifaire Steam vers la couche Silver speed.

Alimente `speed.price_snapshots` depuis l'endpoint `appdetails` de la boutique
Steam (`price_overview`). Cette source remplace le scraping GOG, sorti du
perimetre par l'arbitrage du Bloc 3 (section 3.3) : la table de faits
`mart.fact_prices` reste donc alimentee, sans scraping et sans contredire cet
arbitrage.

Le module est appelable de deux facons, volontairement : en ligne de commande
pour la mise au point, et comme fonction depuis une tache Airflow. La logique
metier n'est pas ecrite dans le DAG, ce qui la rend testable par la CI sans
qu'Airflow soit demarre.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

import requests
from common import charger_watchlist, configurer_logs, connexion_pg, execution

logger = configurer_logs("steam_prices")

URL_APPDETAILS = "https://store.steampowered.com/api/appdetails"
DELAI_ENTRE_APPELS = 1.5  # endpoint de boutique, plus severement limite que l'API Web
TIMEOUT_HTTP = 15

INSERTION = """
INSERT INTO speed.price_snapshots
    (steam_appid, price_final, price_initial, discount_percent, currency, collected_at)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_price_snapshot DO NOTHING
"""


def lire_prix(session: requests.Session, appid: int) -> dict | None:
    """Retourne le tarif d'un titre, ou None si Steam n'en expose pas.

    Un None n'est pas une erreur : un jeu gratuit, retire de la vente ou
    indisponible dans la region interrogee ne porte pas de `price_overview`.
    """
    reponse = session.get(
        URL_APPDETAILS,
        params={"appids": appid, "cc": "fr", "l": "fr", "filters": "price_overview"},
        timeout=TIMEOUT_HTTP,
    )
    reponse.raise_for_status()
    bloc = reponse.json().get(str(appid), {})
    if not bloc.get("success"):
        return None
    apercu = (bloc.get("data") or {}).get("price_overview")
    if not apercu:
        return None
    # Steam exprime les montants en centimes.
    return {
        "price_final": apercu["final"] / 100,
        "price_initial": apercu.get("initial", apercu["final"]) / 100,
        "discount_percent": apercu.get("discount_percent", 0),
        "currency": apercu.get("currency", "EUR"),
    }


def collecter(compteurs: dict | None = None) -> dict:
    """Collecte les tarifs de toute la watchlist et les ecrit en Silver speed."""
    compteurs = compteurs if compteurs is not None else {"records_in": 0, "records_written": 0}
    titres = charger_watchlist()
    collecte_le = datetime.now(UTC).replace(microsecond=0)

    session = requests.Session()
    session.headers["User-Agent"] = "GameLens/1.0 (projet de certification RNCP39586)"

    sans_tarif: list[int] = []
    conn = connexion_pg()
    try:
        with conn, conn.cursor() as cur:
            for titre in titres:
                appid = titre["steam_appid"]
                compteurs["records_in"] += 1
                try:
                    tarif = lire_prix(session, appid)
                except requests.RequestException as exc:
                    logger.warning("appid=%s injoignable (%s)", appid, type(exc).__name__)
                    continue

                if tarif is None:
                    sans_tarif.append(appid)
                    logger.info("appid=%-8s %-18s aucun tarif expose", appid, titre["unified_name"])
                    time.sleep(DELAI_ENTRE_APPELS)
                    continue

                cur.execute(
                    INSERTION,
                    (
                        appid,
                        tarif["price_final"],
                        tarif["price_initial"],
                        tarif["discount_percent"],
                        tarif["currency"],
                        collecte_le,
                    ),
                )
                compteurs["records_written"] += cur.rowcount
                logger.info(
                    "appid=%-8s %-18s %6.2f %s%s",
                    appid,
                    titre["unified_name"],
                    tarif["price_final"],
                    tarif["currency"],
                    f"  (remise {tarif['discount_percent']}%)" if tarif["discount_percent"] else "",
                )
                time.sleep(DELAI_ENTRE_APPELS)
    finally:
        conn.close()

    if sans_tarif:
        logger.info("%s titre(s) sans tarif expose : %s", len(sans_tarif), sans_tarif)
    return compteurs


def collecter_et_tracer() -> dict:
    """Collecte en enregistrant l'execution dans speed.pipeline_runs.

    C'est ce point d'entree, et non `collecter`, que doivent utiliser les
    appelants automatises. La distinction n'est pas cosmetique : lors de la
    premiere execution orchestree du 20/08/2026, le DAG appelait directement
    `collecter`, si bien que quatre collectes reelles n'apparaissaient que sous
    la forme d'une seule ligne de journal. Une execution non tracee est une
    execution invisible pour la supervision (C4.3.1).
    """
    with execution("steam_prices", logger) as compteurs:
        collecter(compteurs)
    return compteurs


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Collecte tarifaire Steam").parse_args(argv)
    collecter_et_tracer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
