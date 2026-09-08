"""Verifie un panel de candidats contre l'API Steam appdetails.

Principe : je fournis le nom ATTENDU et l'appid presume. Steam rend le nom
reel. Tout ecart franc entre les deux fait rejeter le candidat, ce qui corrige
ma memoire des identifiants au lieu de lui faire confiance.

Trois filtres, dans cet ordre :
  1. la reponse aboutit et type == "game" (pas un DLC, pas une demo)
  2. le nom rendu ressemble au nom attendu
  3. le genre "Indie" est present, coherent avec le positionnement de Kestrel

Sortie : un JSON de candidats retenus, avec nom, developpeur et genre LUS A LA
SOURCE et non saisis a la main.
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import requests

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "config" / "watchlist.json"
URL = "https://store.steampowered.com/api/appdetails"
UA = {"User-Agent": "Mozilla/5.0 (GameLens certification RNCP39586)"}
DELAI = 1.5  # appdetails limite plus severement que l'API Web
TIMEOUT = 30

# Genres Steam a ne pas retenir comme genre principal : trop larges ou
# descriptifs d'un mode de distribution plutot que d'un type de jeu.
GENRES_ECARTES = {"Indie", "Early Access", "Free To Play", "Casual"}

# Un filtre automatique ne tranche pas tout, et le dire vaut mieux que de
# maquiller la regle pour qu'elle produise le resultat voulu.
#
# CONSERVES malgre l'absence du genre Indie : les titres du panel initial,
# verifies en session 1 et deja documentes. Le filtre est une regle
# d'ADMISSION pour les candidats nouveaux, pas un motif d'exclusion
# retroactive. Disco Elysium porte en outre le cas de divergence de nom cite
# par la documentation, que le rejeter ferait disparaitre.
PANEL_INITIAL = {
    1145360,
    1145350,
    367520,
    413150,
    105600,
    588650,
    646570,
    1794680,
    294100,
    427520,
    1313140,
    2379780,
    504230,
    632470,
    391540,
}

# EXCLUS bien qu'ils passent tous les filtres : Steam les classe type=game
# sans que ce soit des jeux video. Critere metier, hors de portee de l'API.
HORS_PANEL = {431960}  # Wallpaper Engine

CANDIDATS: dict[str, int] = {
    # --- Les 15 du panel initial, revus pour uniformiser la provenance ---
    "Hades": 1145360,
    "Hades II": 1145350,
    "Hollow Knight": 367520,
    "Stardew Valley": 413150,
    "Terraria": 105600,
    "Dead Cells": 588650,
    "Slay the Spire": 646570,
    "Vampire Survivors": 1794680,
    "RimWorld": 294100,
    "Factorio": 427520,
    "Cult of the Lamb": 1313140,
    "Balatro": 2379780,
    "Celeste": 504230,
    "Disco Elysium": 632470,
    "Undertale": 391540,
    # --- Ajouts ---
    "Cuphead": 268910,
    "The Binding of Isaac: Rebirth": 250900,
    "Don't Starve Together": 322330,
    "Don't Starve": 219740,
    "Darkest Dungeon": 262060,
    "Enter the Gungeon": 311690,
    "Katana ZERO": 460950,
    "ULTRAKILL": 1229490,
    "SUPERHOT": 322500,
    "SUPERHOT: MIND CONTROL DELETE": 617830,
    "Risk of Rain 2": 632360,
    "Risk of Rain": 248820,
    "Project Zomboid": 108600,
    "7 Days to Die": 251570,
    "Geometry Dash": 322170,
    "Prison Architect": 233450,
    "Space Engineers": 244850,
    "No Man's Sky": 275850,
    "Valheim": 892970,
    "Phasmophobia": 739630,
    "Among Us": 945360,
    "Palworld": 1623730,
    "Lethal Company": 1966720,
    "DAVE THE DIVER": 1868140,
    "Stray": 1332010,
    "The Forest": 242760,
    "Sons Of The Forest": 1326470,
    "Cities: Skylines": 255710,
    "Cities: Skylines II": 949230,
    "Euro Truck Simulator 2": 227300,
    "American Truck Simulator": 270880,
    "Europa Universalis IV": 236850,
    "Stellaris": 281990,
    "Hearts of Iron IV": 394360,
    "Crusader Kings III": 1158310,
    "Bastion": 107100,
    "Torchlight II": 200710,
    "Machinarium": 40700,
    "Antichamber": 219890,
    "FEZ": 224760,
    "Castle Crashers": 204360,
    "Mark of the Ninja": 214560,
    "Little Nightmares": 424840,
    "Ori and the Will of the Wisps": 1057090,
    "Ori and the Blind Forest": 261570,
    "Hotline Miami": 219150,
    "Hotline Miami 2: Wrong Number": 274170,
    "Divinity: Original Sin 2": 435150,
    "Beat Saber": 620980,
    "Garry's Mod": 4000,
    "Unturned": 304930,
    "Rust": 252490,
    "ARK: Survival Evolved": 346110,
    "Goat Simulator": 265930,
    "Kerbal Space Program": 220200,
    "Firewatch": 383870,
    "The Talos Principle": 257510,
    "Fall Guys": 1097150,
    "It Takes Two": 1426210,
    "Enshrouded": 1203620,
    "DREDGE": 1562430,
    "Wallpaper Engine": 431960,
    "Slime Rancher": 433340,
    "Subnautica": 264710,
    "Subnautica: Below Zero": 848450,
    "Oxygen Not Included": 457140,
    "Graveyard Keeper": 599140,
    "My Time at Portia": 666140,
    "Human: Fall Flat": 477160,
    "Untitled Goose Game": 837470,
    "A Hat in Time": 253230,
    "Shovel Knight": 250760,
    "Owlboy": 115800,
    "Axiom Verge": 332200,
    "Dust: An Elysian Tail": 236090,
    "Transistor": 237930,
    "Pyre": 462770,
    "Braid": 26800,
    "LIMBO": 48000,
    "INSIDE": 304430,
    "Little Inferno": 221260,
    "World of Goo": 22000,
    "Papers, Please": 239030,
    "The Stanley Parable": 221910,
    "Gone Home": 232430,
    "Oxenfree": 388880,
    "Night in the Woods": 481510,
    "Return of the Obra Dinn": 653530,
    "Outer Wilds": 753640,
    "The Witness": 210970,
    "Superliminal": 1049410,
    "Baba Is You": 736260,
    "Opus Magnum": 558990,
    "SpaceChem": 92800,
    "Infinifactory": 300570,
    "TIS-100": 370360,
    "SHENZHEN I/O": 504210,
    "EXAPUNKS": 716490,
    "Human Resource Machine": 375820,
    "7 Billion Humans": 792070,
    "Manifold Garden": 473950,
    "Deep Rock Galactic": 548430,
    "Barotrauma": 602960,
    "Noita": 881100,
    "Nuclear Throne": 242680,
    "Spelunky 2": 418530,
    "Spelunky": 239350,
    "Downwell": 360740,
    "Hyper Light Drifter": 257850,
    "Blasphemous": 774361,
    "Blasphemous 2": 2114740,
    "Salt and Sanctuary": 283640,
    "Sundered": 561600,
    "Guacamelee! 2": 534550,
    "Rogue Legacy": 241600,
    "Rogue Legacy 2": 1253920,
    "Wizard of Legend": 445980,
    "Moonlighter": 606150,
    "Children of Morta": 330020,
    "TUNIC": 553420,
    "Death's Door": 894020,
    "Neon White": 1533420,
    "Ghostrunner": 1139900,
    "Loop Hero": 1282730,
    "Inscryption": 1092790,
    "Cultist Simulator": 718670,
    "Sunless Sea": 304650,
    "Darkest Dungeon II": 1940340,
    "Monster Train": 1102190,
    "Griftlands": 601840,
    "Dicey Dungeons": 861540,
    "Void Bastards": 673880,
    "Streets of Rogue": 512900,
    "Crypt of the NecroDancer": 247080,
    "Curse of the Dead Gods": 1123770,
    "Neon Abyss": 1245820,
    "Skul: The Hero Slayer": 1147560,
    "20 Minutes Till Dawn": 1966900,
    "Brotato": 1942280,
    "Halls of Torment": 2218750,
    "Nova Drift": 858210,
    "Hardspace: Shipbreaker": 1161580,
    "ASTRONEER": 361420,
    "Raft": 648800,
    "Green Hell": 815370,
    "The Long Dark": 305620,
    "Frostpunk": 323190,
    "This War of Mine": 282070,
    "Banished": 242920,
    "Kenshi": 233860,
    "Dwarf Fortress": 975370,
    "Timberborn": 1062090,
    "Satisfactory": 526870,
    "Dyson Sphere Program": 1366540,
    "shapez": 1318690,
    "Mindustry": 1127400,
    "Terra Nil": 1593030,
    "Against the Storm": 1336490,
    "Northgard": 466560,
    "Bad North": 688420,
    "Into the Breach": 590380,
    "FTL: Faster Than Light": 212680,
    "Battle Brothers": 365360,
    "Wartales": 1527950,
    "Songs of Conquest": 867210,
    "Shadow Tactics": 418240,
    "Desperados III": 610370,
    "Invisible, Inc.": 243970,
    "Gunpoint": 206190,
    "Heat Signature": 268130,
    "Hacknet": 365450,
    "Duskers": 254320,
}


COMMENTAIRE = (
    "Panel de titres suivis par GameLens. Le portefeuille de Kestrel Interactive est "
    "fictif ; les titres listes ici constituent le panel concurrent reel, seul observable "
    "publiquement. Chaque appid est VERIFIE contre l'API Steam appdetails : le nom, le "
    "developpeur et le genre sont lus a la source, jamais saisis a la main, et tout "
    "candidat dont le nom rendu par Steam divergeait du nom attendu a ete rejete. Filtres "
    "appliques : type=game et genre Indie present, coherent avec le positionnement "
    "d'editeur independant de Kestrel Interactive. Deux exceptions assumees a cette regle, "
    "parce qu'un filtre automatique ne tranche pas tout : Disco Elysium est CONSERVE "
    "bien que Steam ne lui declare pas le genre Indie, car il appartient au panel "
    "initial verifie en session 1 et porte le cas documente de divergence de nom ; "
    "Wallpaper Engine est EXCLU bien qu'il passe tous les filtres, parce que Steam le "
    "classe type=game sans que ce soit un jeu video. Le Bloc 1 citait 570/730/1091500 a "
    "titre d'exemple : ces trois titres AAA sont hors panel."
)

NOTES = {
    632470: "Nom commercial Steam different du nom unifie : cas reel de resolution "
    "d identifiants traite par game_mapping (Bloc 1)."
}


def echapper(v: str) -> str:
    return json.dumps(v, ensure_ascii=False)


def ecrire_watchlist(retenus: list[dict]) -> None:
    """Ecrit config/watchlist.json, aligne en colonnes et en CRLF.

    Le fichier reste relu par un humain : les colonnes sont alignees sur la
    valeur la plus longue plutot que serrees, et la fin de ligne est celle que
    le depot porte pour ce fichier.
    """
    retenus = sorted(retenus, key=lambda t: t["unified_name"].lower())
    l_id = max(len(str(t["steam_appid"])) for t in retenus)
    l_nom = max(len(echapper(t["unified_name"])) for t in retenus)
    l_dev = max(len(echapper(t["developer"])) for t in retenus)

    lignes = []
    for t in retenus:
        bloc = (
            f'    {{"steam_appid": {str(t["steam_appid"]):>{l_id}}, '
            f'"unified_name": {echapper(t["unified_name"]):<{l_nom}}, '
            f'"developer": {echapper(t["developer"]):<{l_dev}}, '
            f'"genre": {echapper(t["genre"])}'
        )
        if t.get("_nom_steam"):
            bloc += f', "_nom_steam": {echapper(t["_nom_steam"])}'
        if t["steam_appid"] in NOTES:
            bloc += f', "_note": {echapper(NOTES[t["steam_appid"]])}'
        lignes.append(bloc + "}")

    texte = (
        "{\n"
        f'  "_commentaire": {echapper(COMMENTAIRE)},\n'
        '  "titres": [\n' + ",\n".join(lignes) + "\n  ]\n}\n"
    )

    # Le fichier produit doit etre du JSON valide, sans perte ni doublon.
    d = json.loads(texte)
    ids = [x["steam_appid"] for x in d["titres"]]
    if len(d["titres"]) != len(retenus) or len(set(ids)) != len(ids):
        raise SystemExit("ecriture incoherente : perte de titres ou appid en double")

    SORTIE.write_bytes(texte.replace("\n", "\r\n").encode("utf-8"))


def normaliser(s: str) -> str:
    """Reduit un titre a ses lettres et chiffres, minuscules."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def concordent(attendu: str, rendu: str) -> bool:
    """Le nom rendu par Steam correspond-il au nom attendu ?

    Tolerant sur les suffixes editoriaux ("- The Final Cut", "Deluxe
    Edition"), strict sur la racine : l'un doit contenir l'autre.
    """
    a, r = normaliser(attendu), normaliser(rendu)
    return a in r or r in a


def genre_principal(genres: list[dict]) -> str | None:
    noms = [g["description"] for g in genres]
    for n in noms:
        if n not in GENRES_ECARTES:
            return n
    return "Indie" if "Indie" in noms else None


def main() -> int:
    session = requests.Session()
    retenus, rejets = [], []

    for i, (attendu, appid) in enumerate(CANDIDATS.items(), 1):
        motif = None
        try:
            r = session.get(
                URL,
                params={"appids": appid, "l": "english", "cc": "fr"},
                headers=UA,
                timeout=TIMEOUT,
            )
            if r.status_code == 429:
                time.sleep(30)
                r = session.get(
                    URL,
                    params={"appids": appid, "l": "english", "cc": "fr"},
                    headers=UA,
                    timeout=TIMEOUT,
                )
            bloc = (r.json() or {}).get(str(appid)) or {}
            if not bloc.get("success"):
                motif = f"HTTP {r.status_code}, success=false"
            else:
                d = bloc["data"]
                nom, typ = d.get("name", ""), d.get("type")
                genres = [g["description"] for g in d.get("genres", [])]
                if typ != "game":
                    motif = f"type={typ}"
                elif not concordent(attendu, nom):
                    motif = f"NOM DIVERGENT, Steam rend {nom!r}"
                elif appid in HORS_PANEL:
                    motif = "hors panel : classe type=game mais n'est pas un jeu"
                elif "Indie" not in genres and appid not in PANEL_INITIAL:
                    motif = f"pas Indie, genres={genres}"
                else:
                    retenus.append(
                        {
                            "steam_appid": appid,
                            "unified_name": attendu,
                            "developer": (d.get("developers") or ["inconnu"])[0],
                            "genre": genre_principal(d.get("genres", [])),
                            "_nom_steam": nom if normaliser(nom) != normaliser(attendu) else None,
                        }
                    )
        except Exception as e:
            motif = f"{type(e).__name__}: {e}"

        if motif:
            rejets.append({"attendu": attendu, "appid": appid, "motif": motif})
        if i % 25 == 0:
            print(f"  {i}/{len(CANDIDATS)} traites, {len(retenus)} retenus", flush=True)
        time.sleep(DELAI)

    print(f"\nRETENUS {len(retenus)}   REJETES {len(rejets)}")
    for r in rejets:
        print(f"  rejete  {r['attendu']!r} ({r['appid']}) : {r['motif']}")

    ecrire_watchlist(retenus)
    genres = Counter(t["genre"] for t in retenus)
    devs = len({t["developer"] for t in retenus})
    print(f"\n{SORTIE} : {len(retenus)} titres, {devs} developpeurs distincts")
    print("  genres : " + ", ".join(f"{g} {n}" for g, n in genres.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
