"""Generation du schema de donnees de la couche Gold : modele, image, document.

Livrable du critere C4.2.1 de la grille Bloc 4, qui demande un schema permettant
d'identifier le type des donnees, les modalites d'acces et leur organisation.

Comme les dictionnaires, ce schema est GENERE et non dessine a la main, pour
qu'il ne puisse pas mentir sur l'etat reel de l'entrepot. Trois sources, et un
recoupement entre elles :

- les colonnes et leurs types viennent du catalogue vivant ;
- les contraintes declarees viennent du catalogue vivant, table par table ;
- les CIBLES des clefs etrangeres et les colonnes des clefs viennent du DDL,
  parce que le catalogue Snowflake n'expose pas de quoi les reconstruire :
  `SHOW IMPORTED KEYS` est refuse dans ce contexte, et
  `information_schema.key_column_usage` n'existe pas chez ce moteur.

Le recoupement rend la troisieme source acceptable : le generateur compte les
contraintes de chaque type dans le DDL et dans le catalogue, et s'arrete si les
deux ne disent pas la meme chose.

## Deux passes, parce que deux environnements

La lecture du catalogue exige la connexion Snowflake, qui vit dans le conteneur
d'outillage. Le dessin exige Pillow et des polices, qui vivent sur le poste. Les
deux passes se parlent par un modele intermediaire versionne, schema_donnees.json.

    docker compose --profile outillage run --rm --no-deps snowflake-cli \\
        python /projet/outils/generer_schema.py        # 1. catalogue -> modele + document
    python outils/generer_schema.py --dessiner         # 2. modele -> SVG + PNG

La seconde passe ne touche pas au reseau : elle est rejouable hors ligne, ce qui
compte le jour d'une soutenance ou aucun acces n'est garanti.

    python outils/generer_schema.py --verifier         # echoue si le document a derive
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "entrepot"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

DDL = RACINE / "sql" / "schema_gold_snowflake.sql"
ANNEXES = RACINE / "docs" / "annexes"
SORTIE = ANNEXES / "schema_donnees.md"
MODELE = ANNEXES / "schema_donnees.json"
IMAGE_SVG = ANNEXES / "schema_donnees.svg"
IMAGE_PNG = ANNEXES / "schema_donnees.png"

TITRE_DIAGRAMME = "GameLens, couche Gold Snowflake : schema en etoile"

# Mermaid ne digerait pas les parentheses ; le diagramme dessine non plus n'en a
# pas besoin. La precision figure dans le dictionnaire de donnees, qui est
# l'annexe faite pour cela.
TYPE_NU = re.compile(r"\(.*\)")


def sans_commentaires(texte: str) -> str:
    """Retire les commentaires de fin de ligne, qui parlent des contraintes.

    Le DDL explique en commentaire que Snowflake accepte PRIMARY KEY et UNIQUE
    sans les appliquer. Compter les occurrences brutes revenait a compter ces
    phrases comme des contraintes, et le recoupement echouait sur un ecart qui
    n'existait pas.
    """
    return "\n".join(ligne.split("--", 1)[0] for ligne in texte.splitlines())


def aretes_du_ddl() -> list[list[str]]:
    """Les clefs etrangeres declarees : table source, colonne, table cible, colonne."""
    texte = sans_commentaires(DDL.read_text(encoding="utf-8"))
    aretes: list[list[str]] = []
    table = None
    for ligne in texte.splitlines():
        creation = re.search(r"CREATE OR REPLACE TABLE\s+\S*?(\w+)\s*\(", ligne, re.I)
        if creation:
            table = creation.group(1).lower()
            continue
        if table is None:
            continue
        reference = re.search(
            r"^\s*(\w+)\s+.*?REFERENCES\s+\S*?\.?(\w+)\s*\(\s*(\w+)\s*\)", ligne, re.I
        )
        if reference:
            aretes.append([table, reference.group(1).lower(),
                           reference.group(2).lower(), reference.group(3).lower()])
    return aretes


def cles_du_ddl() -> dict[str, list[str]]:
    """Les colonnes de clef primaire et d'unicite, indexees par 'table.colonne'.

    Le catalogue sait combien de contraintes portent sur une table, mais pas
    quelles colonnes elles couvrent. Le DDL le dit, et le recoupement des
    comptes garantit qu'il decrit bien l'etat en place.
    """
    texte = sans_commentaires(DDL.read_text(encoding="utf-8"))
    marques: dict[str, set[str]] = {}
    table = None
    for ligne in texte.splitlines():
        creation = re.search(r"CREATE OR REPLACE TABLE\s+\S*?(\w+)\s*\(", ligne, re.I)
        if creation:
            table = creation.group(1).lower()
            continue
        if table is None:
            continue

        groupee = re.search(r"^\s*PRIMARY KEY\s*\(([^)]+)\)", ligne, re.I)
        if groupee:
            for col in groupee.group(1).split(","):
                marques.setdefault(f"{table}.{col.strip().lower()}", set()).add("PK")
            continue

        unicite = re.search(r"^\s*CONSTRAINT\s+\w+\s+UNIQUE\s*\(([^)]+)\)", ligne, re.I)
        if unicite:
            for col in unicite.group(1).split(","):
                marques.setdefault(f"{table}.{col.strip().lower()}", set()).add("UK")
            continue

        colonne = re.match(r"^\s*(\w+)\s+[A-Z]", ligne)
        if colonne:
            nom = colonne.group(1).lower()
            if re.search(r"\bPRIMARY KEY\b", ligne, re.I):
                marques.setdefault(f"{table}.{nom}", set()).add("PK")
            if re.search(r"\bUNIQUE\b", ligne, re.I):
                marques.setdefault(f"{table}.{nom}", set()).add("UK")
    return {cle: sorted(valeurs) for cle, valeurs in marques.items()}


def compter_ddl() -> dict[str, int]:
    """Les contraintes declarees dans le DDL, par type, pour le recoupement."""
    texte = sans_commentaires(DDL.read_text(encoding="utf-8"))
    return {
        "PRIMARY KEY": len(re.findall(r"\bPRIMARY KEY\b", texte, re.I)),
        "FOREIGN KEY": len(re.findall(r"\bREFERENCES\b", texte, re.I)),
        "UNIQUE": len(re.findall(r"\bUNIQUE\b", texte, re.I)),
    }


def lire_catalogue() -> dict:
    """Interroge Snowflake et rend le modele complet du schema."""
    from connexion_snowflake import connexion

    conn = connexion()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, table_type
                  FROM information_schema.tables
                 WHERE table_schema = 'MART'
                 ORDER BY table_type DESC, table_name
                """
            )
            objets = [(n.lower(), t) for n, t in cur.fetchall()]

            colonnes: dict[str, list[list[str]]] = {}
            for nom, _ in objets:
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                      FROM information_schema.columns
                     WHERE table_schema = 'MART' AND table_name = %s
                     ORDER BY ordinal_position
                    """,
                    (nom.upper(),),
                )
                colonnes[nom] = [
                    [c.lower(), TYPE_NU.sub("", t), n] for c, t, n in cur.fetchall()
                ]

            cur.execute(
                """
                SELECT table_name, constraint_type, count(*)
                  FROM information_schema.table_constraints
                 WHERE table_schema = 'MART'
                 GROUP BY 1, 2 ORDER BY 1, 2
                """
            )
            contraintes = [[t.lower(), k, n] for t, k, n in cur.fetchall()]

            droits: list[list[str]] = []
            for nom, nature in objets:
                mot = "VIEW" if nature != "BASE TABLE" else "TABLE"
                try:
                    cur.execute(f"SHOW GRANTS ON {mot} mart.{nom}")
                    for ligne in cur.fetchall():
                        privilege, beneficiaire = ligne[1], str(ligne[5])
                        if beneficiaire.lower().startswith("gamelens_"):
                            droits.append([nom, beneficiaire.lower(), privilege])
                except Exception:  # noqa: BLE001 - une absence de droit n'est pas fatale
                    continue
    finally:
        conn.close()

    aretes = aretes_du_ddl()
    marques = cles_du_ddl()
    for src, col_src, _cible, _col in aretes:
        marques.setdefault(f"{src}.{col_src}", []).append("FK")

    attendu = compter_ddl()
    constate = {"PRIMARY KEY": 0, "FOREIGN KEY": 0, "UNIQUE": 0}
    for _, genre, nombre in contraintes:
        if genre in constate:
            constate[genre] += nombre
    ecarts = [
        f"{genre} : {attendu[genre]} dans le DDL, {constate[genre]} dans le catalogue"
        for genre in attendu
        if attendu[genre] != constate[genre]
    ]
    if ecarts:
        raise SystemExit(
            "Le DDL et le catalogue ne comptent pas les memes contraintes.\n  "
            + "\n  ".join(ecarts)
            + "\nLe schema livre a peut-etre ete modifie sans etre rejoue."
        )

    return {
        "objets": objets,
        "colonnes": colonnes,
        "contraintes": contraintes,
        "droits": sorted({tuple(d) for d in droits}),
        "aretes": aretes,
        "marques": marques,
    }


def rendre_document(modele: dict) -> str:
    objets = [(n, t) for n, t in modele["objets"]]
    colonnes = modele["colonnes"]

    lignes = [
        "# Schema de donnees, couche Gold\n",
        "\n> **Fichier genere. Ne pas modifier a la main.**\n",
        "> Colonnes, types, contraintes et droits lus dans le catalogue Snowflake ;\n",
        "> colonnes des clefs et cibles des clefs etrangeres lues dans\n",
        "> `sql/schema_gold_snowflake.sql`, les deux sources etant recoupees a\n",
        "> chaque generation. Regenerer par `outils/generer_schema.py`.\n",
        "\nLivrable du critere **C4.2.1**, qui demande un schema permettant\n",
        "d'identifier le type des donnees, les modalites d'acces et l'organisation\n",
        "des donnees. Les trois premieres sections repondent dans cet ordre.\n",
        "\n## 1. Organisation des donnees\n",
        "\n![Schema en etoile de la couche Gold](schema_donnees.png)\n",
        "\n*Source vectorielle : [`schema_donnees.svg`](schema_donnees.svg).*\n",
        "\nModele en etoile : deux dimensions, deux tables de faits, une vue de\n",
        "restitution. Le grain de `fact_popularity_history` est le couple\n",
        "(jeu, jour) ; celui de `fact_prices` est (jeu, boutique, instant de\n",
        "collecte). Colonnes larges plutot qu'un modele entite-attribut-valeur :\n",
        "les indicateurs suivis sont connus et peu nombreux.\n",
        "\nLes relations sont dessinees **en tirets**, et ce n'est pas une\n",
        "convention graphique : elles sont declarees dans le schema mais le moteur\n",
        "ne les applique pas. Voir la section 4.\n",
    ]

    vues = [n for n, t in objets if t != "BASE TABLE"]
    if vues:
        lignes.append(
            f"\nS'y ajoute la vue `mart.{vues[0]}`, seul objet visible du role de\n"
            "restitution. Elle joint la dimension des jeux et les faits de\n"
            "popularite, sans exposer les tables sous-jacentes.\n"
        )

    lignes.append("\n## 2. Type des donnees\n")
    lignes.append(
        "\nTypes tels que le catalogue les porte. Le dimensionnement exact\n"
        "(longueurs, precisions) figure dans `dictionnaire_gold_snowflake.md`,\n"
        "qui est l'annexe faite pour cela.\n"
    )
    for nom, nature in objets:
        etiquette = "table" if nature == "BASE TABLE" else "vue"
        lignes.append(f"\n### `mart.{nom}` ({etiquette})\n")
        lignes.append("\n| Colonne | Type | Nul | Clef |")
        lignes.append("\n|---|---|---|---|")
        for col, type_sql, nullable in colonnes[nom]:
            marques = modele["marques"].get(f"{nom}.{col}", [])
            lignes.append(
                f"\n| `{col}` | `{type_sql}` | "
                f"{'oui' if nullable == 'YES' else 'non'} | "
                f"{' '.join(sorted(marques)) if marques else ''} |"
            )
        lignes.append("\n")

    lignes.append("\n## 3. Modalites d'acces\n")
    droits = [tuple(d) for d in modele["droits"]]
    if droits:
        lignes.append(
            "\nLu en direct par `SHOW GRANTS`, et non recopie depuis le schema :\n"
            "c'est l'etat effectif des droits sur la couche de demonstration.\n"
        )
        lignes.append("\n| Objet | Role | Privilege |")
        lignes.append("\n|---|---|---|")
        for objet, role, privilege in sorted(droits):
            lignes.append(f"\n| `mart.{objet}` | `{role}` | `{privilege}` |")
        lignes.append("\n")
        lignes.append(
            "\nLe cloisonnement se lit dans ce tableau : `gamelens_etl_service`\n"
            "ecrit, `gamelens_analyst` lit les tables, et\n"
            "`gamelens_dashboard_viewer` ne voit que la vue. La verification par\n"
            "l'echec est dans `docs/preuves/c11_cloisonnement_roles.txt`.\n"
        )
    else:
        lignes.append(
            "\nLes droits n'ont pas pu etre lus : le role courant ne voit pas les\n"
            "attributions. Voir la matrice de droits de la documentation technique.\n"
        )

    lignes.append(
        "\n## 4. Ce que le moteur applique, et ce qu'il n'applique pas\n"
        "\nLe catalogue declare les contraintes ci-dessous. **Snowflake ne les\n"
        "applique pas a l'ecriture**, a l'exception de celles portees par la\n"
        "colonne elle-meme (`NOT NULL`, type, longueur). `CHECK`, `FOREIGN KEY`,\n"
        "`PRIMARY KEY` et `UNIQUE` sont des metadonnees, verifiees empiriquement\n"
        "par `sql/verify_snowflake_constraints.sql`.\n"
        "\n| Table | Contrainte declaree | Nombre |"
        "\n|---|---|---|"
    )
    for table, genre, nombre in modele["contraintes"]:
        lignes.append(f"\n| `mart.{table}` | {genre} | {nombre} |")
    lignes.append(
        "\n\nLe diagramme montre donc des relations **voulues**, pas des relations\n"
        "garanties par le moteur. Ce que le moteur ne garantit pas est porte par\n"
        "deux filets rejoues a chaque push : les contrats declaratifs de\n"
        "`dbt/models/gold/`, ou chaque `relationships` est exactement une des\n"
        "fleches du diagramme, et les controles applicatifs de\n"
        "`entrepot/verifier_gold.py`.\n"
    )
    return "".join(lignes)


def dessiner(modele: dict) -> None:
    """Deuxieme passe : le modele devient une image. Aucun reseau requis."""
    import diagramme

    colonnes = {
        nom: [tuple(c) for c in cols]
        for nom, cols in modele["colonnes"].items()
        if any(nom == t for t, nature in modele["objets"] if nature == "BASE TABLE")
    }
    marques = {
        (cle.split(".", 1)[0], cle.split(".", 1)[1]): set(valeurs)
        for cle, valeurs in modele["marques"].items()
    }
    aretes = [tuple(a) for a in modele["aretes"]]

    boites, aretes, largeur, hauteur = diagramme.disposer(colonnes, marques, aretes)
    IMAGE_SVG.write_text(
        diagramme.rendre_svg(boites, aretes, largeur, hauteur, TITRE_DIAGRAMME),
        encoding="utf-8", newline="\n",
    )
    diagramme.rendre_png(boites, aretes, largeur, hauteur, TITRE_DIAGRAMME, IMAGE_PNG)
    print(f"Ecrit : {IMAGE_SVG.relative_to(RACINE)} et {IMAGE_PNG.relative_to(RACINE)} "
          f"({largeur}x{hauteur})")


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Generation du schema de donnees")
    parseur.add_argument(
        "--dessiner",
        action="store_true",
        help="deuxieme passe : rendre le modele en SVG et PNG, sans reseau",
    )
    parseur.add_argument(
        "--verifier",
        action="store_true",
        help="ne rien ecrire, echouer si le document versionne n'est plus a jour",
    )
    args = parseur.parse_args(argv)

    if args.dessiner:
        if not MODELE.exists():
            print(f"{MODELE.relative_to(RACINE)} est absent : lancer d'abord la "
                  "premiere passe, dans le conteneur d'outillage.")
            return 1
        dessiner(json.loads(MODELE.read_text(encoding="utf-8")))
        return 0

    modele = lire_catalogue()
    rendu = rendre_document(modele)

    if args.verifier:
        if not SORTIE.exists():
            print(f"{SORTIE.relative_to(RACINE)} est absent.")
            return 1
        if SORTIE.read_text(encoding="utf-8") != rendu:
            print(
                f"{SORTIE.relative_to(RACINE)} ne correspond plus au catalogue.\n"
                "Corriger par : python outils/generer_schema.py"
            )
            return 1
        print(f"OK : {SORTIE.relative_to(RACINE)} est a jour.")
        return 0

    ANNEXES.mkdir(parents=True, exist_ok=True)
    MODELE.write_text(
        json.dumps(modele, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    SORTIE.write_text(rendu, encoding="utf-8", newline="\n")
    print(f"Ecrit : {MODELE.relative_to(RACINE)} et {SORTIE.relative_to(RACINE)}")
    print("Passe suivante, sur le poste : python outils/generer_schema.py --dessiner")
    return 0


if __name__ == "__main__":
    sys.exit(main())
