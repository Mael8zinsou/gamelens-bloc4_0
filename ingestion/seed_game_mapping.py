"""Alimente speed.game_mapping depuis config/watchlist.json.

Table de resolution des identifiants cross-plateformes posee au Bloc 1. Le
script est idempotent (UPSERT) : il peut etre rejoue a chaque ajout de titre
dans la watchlist sans dupliquer ni perdre les identifiants deja resolus.
"""

from __future__ import annotations

import sys

from common import charger_watchlist, configurer_logs, connexion_pg, execution

logger = configurer_logs("seed_mapping")


def main() -> int:
    titres = charger_watchlist()
    with execution("seed_game_mapping", logger) as compteurs:
        compteurs["records_in"] = len(titres)
        conn = connexion_pg()
        try:
            with conn, conn.cursor() as cur:
                for t in titres:
                    cur.execute(
                        """
                        INSERT INTO speed.game_mapping
                            (steam_appid, unified_name, developer, genre, steam_name, updated_at)
                        VALUES (%s, %s, %s, %s, %s, now())
                        ON CONFLICT (steam_appid) DO UPDATE
                           SET unified_name = EXCLUDED.unified_name,
                               developer    = EXCLUDED.developer,
                               genre        = EXCLUDED.genre,
                               steam_name   = COALESCE(EXCLUDED.steam_name, speed.game_mapping.steam_name),
                               updated_at   = now()
                        """,
                        (
                            t["steam_appid"],
                            t["unified_name"],
                            t.get("developer"),
                            t.get("genre"),
                            t.get("_nom_steam"),
                        ),
                    )
                    compteurs["records_written"] += 1
        finally:
            conn.close()

    logger.info("%s titres presents dans speed.game_mapping", compteurs["records_written"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
