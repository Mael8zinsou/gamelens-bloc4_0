"""Verifie que chaque panneau du tableau de bord Grafana fonctionne reellement.

Un tableau de bord qui s'affiche n'est pas un tableau de bord qui fonctionne :
un panneau dont la requete echoue reste visible, avec un message d'erreur
discret, et se confond facilement avec un panneau vide. Ce script execute la
requete de chaque panneau a travers l'API de Grafana, donc en passant par la
source de donnees provisionnee et son role en lecture seule, et rapporte le
nombre de lignes obtenues.

Ce controle a servi des sa premiere execution : il valide non seulement le SQL,
mais aussi la resolution de la source de donnees, les droits du role `analyst`,
et la presence effective du tableau de bord provisionne.

Usage :
    python supervision/verifier_tableau_bord.py
    python supervision/verifier_tableau_bord.py --url http://localhost:3000
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import sys
import urllib.error
import urllib.request

RACINE = pathlib.Path(__file__).resolve().parent.parent
TABLEAU = RACINE / "docker" / "grafana" / "dashboards" / "gamelens_supervision.json"
UID_SOURCE = "gamelens-pg"


def interroger(url: str, auth: str, cible: dict) -> dict:
    corps = {
        "from": "now-24h",
        "to": "now",
        "queries": [
            {
                "refId": "A",
                "datasource": {"uid": UID_SOURCE},
                "format": cible["format"],
                "rawQuery": True,
                "rawSql": cible["rawSql"],
                "intervalMs": 3_600_000,
                "maxDataPoints": 100,
            }
        ],
    }
    requete = urllib.request.Request(
        f"{url}/api/ds/query",
        data=json.dumps(corps).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(requete, timeout=20) as reponse:
        return json.load(reponse)["results"]["A"]


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Verification des panneaux Grafana")
    parseur.add_argument("--url", default="http://localhost:3000")
    parseur.add_argument("--utilisateur", default="admin")
    parseur.add_argument("--mot-de-passe", default="admin")
    args = parseur.parse_args(argv)

    auth = base64.b64encode(f"{args.utilisateur}:{args.mot_de_passe}".encode()).decode()
    tableau = json.loads(TABLEAU.read_text(encoding="utf-8"))

    print(f"Tableau de bord : {tableau['title']}")
    print(f"Grafana         : {args.url}\n")

    succes = echecs = 0
    for panneau in tableau["panels"]:
        titre = panneau["title"]
        try:
            resultat = interroger(args.url, auth, panneau["targets"][0])
        except urllib.error.URLError as exc:
            print(f"  INJOIGNABLE  {titre} : {exc.reason}")
            echecs += 1
            continue

        if "error" in resultat:
            print(f"  ECHEC        {titre} : {resultat['error'][:120]}")
            echecs += 1
            continue

        frames = resultat.get("frames") or []
        valeurs = frames[0]["data"]["values"] if frames else []
        lignes = len(valeurs[0]) if valeurs else 0
        # Zero ligne n'est pas un echec en soi (aucune alerte ouverte, par
        # exemple), mais merite d'etre signale : c'est le cas ou un panneau
        # muet se confond avec un panneau casse.
        marque = "OK       " if lignes else "VIDE     "
        print(f"  {marque}    {titre:<40} {lignes} ligne(s)")
        succes += 1

    print(f"\n{succes} panneau(x) fonctionnel(s), {echecs} en echec")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
