"""Controles structurels sur le referentiel des titres suivis.

Ces tests ne touchent ni le reseau ni la base : ils verifient que le fichier de
configuration qui pilote toute la collecte reste coherent. Une watchlist
corrompue casserait le pipeline temps reel et la promotion Gold d'un seul coup,
d'ou l'interet de la controler en amont, dans la CI.
"""

import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CHAMPS_OBLIGATOIRES = {"steam_appid", "unified_name"}


def charger() -> list[dict]:
    with open(RACINE / "config" / "watchlist.json", encoding="utf-8") as f:
        return json.load(f)["titres"]


def test_watchlist_non_vide():
    assert len(charger()) > 0


def test_champs_obligatoires_presents():
    for titre in charger():
        manquants = CHAMPS_OBLIGATOIRES - set(titre)
        assert not manquants, f"champs manquants pour {titre} : {manquants}"


def test_appid_uniques():
    appids = [t["steam_appid"] for t in charger()]
    doublons = {a for a in appids if appids.count(a) > 1}
    assert not doublons, f"appid en double dans la watchlist : {doublons}"


def test_appid_sont_des_entiers_positifs():
    for titre in charger():
        appid = titre["steam_appid"]
        assert isinstance(appid, int), f"{appid} n'est pas un entier"
        assert appid > 0, f"{appid} n'est pas un identifiant Steam plausible"


def test_noms_unifies_uniques():
    noms = [t["unified_name"] for t in charger()]
    doublons = {n for n in noms if noms.count(n) > 1}
    assert not doublons, f"nom unifie en double : {doublons}"
