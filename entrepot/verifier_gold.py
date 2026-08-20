"""Controle du contenu de la couche Gold sur Snowflake.

Pendant du controle de qualite execute par le DAG PostgreSQL, transpose sur
Snowflake. Il compte d'autant plus ici que Snowflake n'applique ni les
contraintes CHECK, ni les clefs etrangeres, ni les clefs primaires declarees :
sur cette plateforme, ces controles ne doublent pas le moteur, ils le
remplacent. Voir les resultats consignes dans
sql/verify_snowflake_constraints.sql.

Usage :
    docker compose run --rm snowflake-cli python entrepot/verifier_gold.py
"""

from __future__ import annotations

import sys

from connexion import connexion

VOLUMETRIE = [
    "mart.dim_games",
    "mart.dim_stores",
    "mart.fact_popularity_history",
    "mart.fact_prices",
]

# Chaque controle attend zero ligne : la requete cherche les VIOLATIONS.
CONTROLES = [
    ("dim_games sans nom unifie", "SELECT count(*) FROM mart.dim_games WHERE unified_name IS NULL"),
    (
        "dim_games en doublon sur steam_appid",
        """SELECT count(*) FROM (SELECT steam_appid FROM mart.dim_games
        GROUP BY steam_appid HAVING count(*) > 1)""",
    ),
    (
        "fact_prices avec un prix negatif ou nul",
        "SELECT count(*) FROM mart.fact_prices WHERE price <= 0",
    ),
    (
        "fact_popularity_history orpheline de dim_games",
        """SELECT count(*) FROM mart.fact_popularity_history f
        LEFT JOIN mart.dim_games g ON g.game_id = f.game_id
        WHERE g.game_id IS NULL""",
    ),
    (
        "fact_prices orpheline de dim_games",
        """SELECT count(*) FROM mart.fact_prices p
        LEFT JOIN mart.dim_games g ON g.game_id = p.game_id
        WHERE g.game_id IS NULL""",
    ),
    (
        "doublons sur le grain (game_id, day)",
        """SELECT count(*) FROM (SELECT game_id, day FROM mart.fact_popularity_history
        GROUP BY game_id, day HAVING count(*) > 1)""",
    ),
    (
        "popularite moyenne negative",
        "SELECT count(*) FROM mart.fact_popularity_history WHERE avg_player_count < 0",
    ),
    (
        "metacritic_score hors bornes 0-100",
        """SELECT count(*) FROM mart.dim_games
        WHERE metacritic_score IS NOT NULL
          AND (metacritic_score < 0 OR metacritic_score > 100)""",
    ),
]


def main() -> int:
    conn = connexion()
    echecs = []
    try:
        with conn.cursor() as cur:
            print("Volumetrie de la couche Gold\n")
            for table in VOLUMETRIE:
                cur.execute(f"SELECT count(*) FROM {table}")
                print(f"  {table:<32} {cur.fetchone()[0]:>5} ligne(s)")

            print("\nControles d'integrite, attendu 0 pour chacun\n")
            for libelle, requete in CONTROLES:
                cur.execute(requete)
                observe = cur.fetchone()[0]
                statut = "PASS" if observe == 0 else "FAIL"
                print(f"  [{statut}] {libelle:<46} {observe}")
                if observe:
                    echecs.append(f"{libelle} ({observe})")

            print("\nExtrait de la vue de restitution\n")
            cur.execute(
                """SELECT unified_name, day, avg_player_count
                   FROM mart.v_popularity_dashboard
                   ORDER BY avg_player_count DESC LIMIT 3"""
            )
            for nom, jour, moyenne in cur.fetchall():
                print(f"  {nom:<20} {jour}  {moyenne}")

            cur.execute(
                """SELECT g.unified_name, p.price, p.currency
                   FROM mart.fact_prices p
                   JOIN mart.dim_games g ON g.game_id = p.game_id
                   WHERE p.promotion_flag LIMIT 3"""
            )
            promotions = cur.fetchall()
            print(f"\n  {len(promotions)} titre(s) en promotion parmi les extraits :")
            for nom, prix, devise in promotions:
                print(f"    {nom:<20} {prix} {devise}")
    finally:
        conn.close()

    if echecs:
        print("\nControles en echec : " + " ; ".join(echecs))
        return 1
    print(f"\n{len(CONTROLES)} controles d'integrite au vert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
