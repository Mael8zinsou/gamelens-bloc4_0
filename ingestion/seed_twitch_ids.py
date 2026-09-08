"""Resout les identifiants Twitch du panel et les ecrit dans speed.game_mapping.

C'est ce script qui fait enfin travailler game_mapping. La table porte depuis
le Bloc 1 un nom qui annonce la resolution d'identifiants entre plateformes ;
jusqu'ici elle ne resolvait que des identifiants Steam, sa colonne
twitch_game_id restant nulle sur la totalite du panel. Le schema promettait un
monde multi-sources que les sources ne livraient pas.

## Pourquoi deux tentatives et non une

Helix expose deux points d'appel, et aucun ne suffit seul.

`/helix/games?name=` exige une correspondance EXACTE. Il resout Hades sans
broncher et echoue sur tout titre dont Twitch retient un libelle different de
celui de Steam, ce qui est frequent : les deux plateformes ne cataloguent pas
le meme objet, l'une vend un produit, l'autre nomme une categorie de
diffusion.

`/helix/search/categories?query=` cherche de maniere approchante. Utilise seul
il resoudrait n'importe quoi vers n'importe quoi, un titre absent de Twitch
etant rattache au premier resultat plausible.

D'ou l'enchainement : correspondance exacte d'abord, recherche approchante
ensuite, mais **la recherche approchante n'est acceptee que si le nom rendu
est egal au nom cherche une fois normalise**. C'est une recherche floue dont on
refuse le flou : elle sert a retrouver un libelle, pas a deviner un titre.

Les trois libelles connus d'un titre sont essayes dans l'ordre : le nom unifie
de GameLens, puis le libelle exact cote Steam quand il differe. Un titre non
resolu reste nul et n'est pas collecte, ce qui est le comportement voulu :
mieux vaut une absence declaree qu'un rattachement invente.

Usage :
    python seed_twitch_ids.py           resout ce qui ne l'est pas encore
    python seed_twitch_ids.py --tout    reprend aussi les titres deja resolus
"""

from __future__ import annotations

import argparse
import re
import sys
import time

import requests
from common import config, configurer_logs, connexion_pg, execution

logger = configurer_logs("seed_twitch_ids")

URL_JETON = "https://id.twitch.tv/oauth2/token"
URL_GAMES = "https://api.twitch.tv/helix/games"
URL_RECHERCHE = "https://api.twitch.tv/helix/search/categories"
DELAI_ENTRE_APPELS = 0.15
TIMEOUT_HTTP = 10


def normaliser(s: str) -> str:
    """Reduit un libelle a ses lettres et chiffres, minuscules.

    Sert a comparer deux libelles sans se faire pieger par la ponctuation
    editoriale, qui differe systematiquement entre catalogues.
    """
    return re.sub(r"[^a-z0-9]", "", s.lower())


def obtenir_jeton(session: requests.Session, identifiant: str, secret: str) -> str:
    """Jeton d'application, flux client_credentials."""
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


def par_nom_exact(session: requests.Session, entetes: dict, libelle: str) -> tuple[str, str] | None:
    """Correspondance exacte. Rend (identifiant, libelle Twitch) ou None."""
    reponse = session.get(
        URL_GAMES, params={"name": libelle}, headers=entetes, timeout=TIMEOUT_HTTP
    )
    if reponse.status_code != 200:
        return None
    for jeu in reponse.json().get("data", []):
        return jeu["id"], jeu["name"]
    return None


def par_recherche(session: requests.Session, entetes: dict, libelle: str) -> tuple[str, str] | None:
    """Recherche approchante, dont on REFUSE le flou.

    Seul un resultat dont le nom normalise egale le nom cherche est accepte.
    Sans cette condition, un titre absent de Twitch serait rattache au premier
    resultat plausible, ce qui produirait une donnee fausse plutot qu'un trou
    declare. Un trou se voit, une donnee fausse ne se voit pas.
    """
    reponse = session.get(
        URL_RECHERCHE,
        params={"query": libelle, "first": 20},
        headers=entetes,
        timeout=TIMEOUT_HTTP,
    )
    if reponse.status_code != 200:
        return None
    cible = normaliser(libelle)
    for jeu in reponse.json().get("data", []):
        if normaliser(jeu["name"]) == cible:
            return jeu["id"], jeu["name"]
    return None


def resoudre(
    session: requests.Session, entetes: dict, libelles: list[str]
) -> tuple[str, str, str] | None:
    """Essaie chaque libelle connu, exact puis approchant."""
    for libelle in libelles:
        if not libelle:
            continue
        for methode in (par_nom_exact, par_recherche):
            trouve = methode(session, entetes, libelle)
            time.sleep(DELAI_ENTRE_APPELS)
            if trouve:
                return trouve[0], trouve[1], libelle
    return None


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Resolution des identifiants Twitch")
    parseur.add_argument(
        "--tout", action="store_true", help="reprend aussi les titres deja resolus"
    )
    args = parseur.parse_args(argv)

    cfg = config()
    if not cfg["twitch_client_id"] or not cfg["twitch_client_secret"]:
        logger.warning("identifiants Twitch absents, resolution ignoree")
        return 0

    filtre = "" if args.tout else "AND twitch_game_id IS NULL"
    conn = connexion_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT steam_appid, unified_name, steam_name
                  FROM speed.game_mapping
                 WHERE is_active {filtre}
                 ORDER BY unified_name
                """  # noqa: S608 - filtre construit ici, pas une entree externe
            )
            titres = cur.fetchall()
    finally:
        conn.close()

    if not titres:
        logger.info("aucun titre a resoudre")
        return 0

    session = requests.Session()
    non_resolus: list[str] = []

    with execution("seed_twitch_ids", logger) as compteurs:
        jeton = obtenir_jeton(session, cfg["twitch_client_id"], cfg["twitch_client_secret"])
        entetes = {"Client-Id": cfg["twitch_client_id"], "Authorization": f"Bearer {jeton}"}
        compteurs["records_in"] = len(titres)

        conn = connexion_pg()
        try:
            for appid, nom_unifie, nom_steam in titres:
                trouve = resoudre(session, entetes, [nom_unifie, nom_steam])
                if not trouve:
                    non_resolus.append(nom_unifie)
                    logger.warning("%-30s non resolu cote Twitch", nom_unifie[:30])
                    continue
                game_id, libelle_twitch, via = trouve
                with conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE speed.game_mapping
                           SET twitch_game_id = %s, updated_at = now()
                         WHERE steam_appid = %s
                        """,
                        (game_id, appid),
                    )
                compteurs["records_written"] += 1
                ecart = "" if normaliser(libelle_twitch) == normaliser(via) else f" (via {via!r})"
                logger.info("%-30s -> %-9s %r%s", nom_unifie[:30], game_id, libelle_twitch, ecart)
        finally:
            conn.close()

    logger.info(
        "%s/%s titres resolus, %s sans categorie Twitch",
        compteurs["records_written"],
        len(titres),
        len(non_resolus),
    )
    if non_resolus:
        logger.info("non resolus : %s", ", ".join(sorted(non_resolus)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
