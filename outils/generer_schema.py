"""Generation du schema de donnees de la couche Gold, en diagramme.

Livrable du critere C4.2.1 de la grille Bloc 4, qui demande un schema permettant
d'identifier le type des donnees, les modalites d'acces et leur organisation.

Meme principe que le dictionnaire de donnees : le fichier est GENERE et non
ecrit a la main, pour qu'il ne puisse pas mentir sur l'etat reel de l'entrepot.
Trois sources, et un recoupement entre elles :

- les colonnes et leurs types viennent du catalogue vivant ;
- les contraintes declarees viennent du catalogue vivant, table par table ;
- les CIBLES des clefs etrangeres viennent du DDL, parce que le catalogue
  Snowflake n'expose pas de quoi les reconstruire : `SHOW IMPORTED KEYS` est
  refuse dans ce contexte, et `information_schema.key_column_usage`, qui
  porterait les colonnes de chaque contrainte, n'existe pas chez ce moteur.

Le recoupement est ce qui rend la troisieme source acceptable : le generateur
compte les contraintes de chaque type dans le DDL et dans le catalogue, et
s'arrete si les deux ne disent pas la meme chose. Un DDL modifie sans etre
rejoue, ou une table recreee sans ses contraintes, sont donc detectes.

    python outils/generer_schema.py              # ecrit le fichier
    python outils/generer_schema.py --verifier   # echoue s'il n'est plus a jour
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "entrepot"))

DDL = RACINE / "sql" / "schema_gold_snowflake.sql"
SORTIE = RACINE / "docs" / "annexes" / "schema_donnees.md"

# Mermaid ne digere pas les parentheses dans le type d'un attribut. La precision
# figure de toute facon dans le dictionnaire de donnees, qui est l'endroit fait
# pour elle ; le diagramme porte la nature du type, pas son dimensionnement.
TYPE_NU = re.compile(r"\(.*\)")


def aretes_du_ddl() -> list[tuple[str, str, str, str]]:
    """Les clefs etrangeres declarees, lues dans le DDL : source puis cible."""
    texte = sans_commentaires(DDL.read_text(encoding="utf-8"))
    aretes: list[tuple[str, str, str, str]] = []
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
            aretes.append(
                (table, reference.group(1).lower(),
                 reference.group(2).lower(), reference.group(3).lower())
            )
    return aretes


def sans_commentaires(texte: str) -> str:
    """Retire les commentaires de fin de ligne, qui parlent des contraintes.

    Le DDL explique en commentaire que Snowflake accepte PRIMARY KEY et UNIQUE
    sans les appliquer. Compter les occurrences brutes revenait a compter ces
    phrases comme des contraintes, et le recoupement echouait sur un ecart qui
    n'existait pas.
    """
    return "\n".join(ligne.split("--", 1)[0] for ligne in texte.splitlines())


def cles_du_ddl() -> dict[tuple[str, str], set[str]]:
    """Les colonnes de clef primaire et d'unicite, table par table.

    Le catalogue Snowflake sait combien de contraintes portent sur une table,
    mais pas quelles colonnes elles couvrent : ni `SHOW IMPORTED KEYS` ni
    `information_schema.key_column_usage` ne repondent ici. Le DDL, lui, le dit,
    et le recoupement des comptes garantit qu'il decrit bien l'etat en place.
    """
    texte = sans_commentaires(DDL.read_text(encoding="utf-8"))
    marques: dict[tuple[str, str], set[str]] = {}
    table = None
    for ligne in texte.splitlines():
        creation = re.search(r"CREATE OR REPLACE TABLE\s+\S*?(\w+)\s*\(", ligne, re.I)
        if creation:
            table = creation.group(1).lower()
            continue
        if table is None:
            continue

        # Clef posee en fin de table : PRIMARY KEY (a, b)
        groupee = re.search(r"^\s*PRIMARY KEY\s*\(([^)]+)\)", ligne, re.I)
        if groupee:
            for col in groupee.group(1).split(","):
                marques.setdefault((table, col.strip().lower()), set()).add("PK")
            continue

        # Unicite nommee : CONSTRAINT uq_x UNIQUE (a, b)
        unicite = re.search(r"^\s*CONSTRAINT\s+\w+\s+UNIQUE\s*\(([^)]+)\)", ligne, re.I)
        if unicite:
            for col in unicite.group(1).split(","):
                marques.setdefault((table, col.strip().lower()), set()).add("UK")
            continue

        # Contrainte portee par la colonne elle-meme.
        colonne = re.match(r"^\s*(\w+)\s+[A-Z]", ligne)
        if colonne:
            nom = colonne.group(1).lower()
            if re.search(r"\bPRIMARY KEY\b", ligne, re.I):
                marques.setdefault((table, nom), set()).add("PK")
            if re.search(r"\bUNIQUE\b", ligne, re.I):
                marques.setdefault((table, nom), set()).add("UK")
    return marques


def compter_ddl() -> dict[str, int]:
    """Les contraintes declarees dans le DDL, par type, pour le recoupement."""
    texte = sans_commentaires(DDL.read_text(encoding="utf-8"))
    # Une PRIMARY KEY posee sur la colonne compte autant qu'une posee en fin de
    # table : le catalogue ne fait pas la difference, le comptage non plus.
    return {
        "PRIMARY KEY": len(re.findall(r"\bPRIMARY KEY\b", texte, re.I)),
        "FOREIGN KEY": len(re.findall(r"\bREFERENCES\b", texte, re.I)),
        "UNIQUE": len(re.findall(r"\bUNIQUE\b", texte, re.I)),
    }


def rendre() -> str:
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
            objets = cur.fetchall()

            colonnes: dict[str, list[tuple[str, str, str]]] = {}
            for nom, _ in objets:
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable
                      FROM information_schema.columns
                     WHERE table_schema = 'MART' AND table_name = %s
                     ORDER BY ordinal_position
                    """,
                    (nom,),
                )
                colonnes[nom.lower()] = [
                    (c.lower(), TYPE_NU.sub("", t), n) for c, t, n in cur.fetchall()
                ]

            cur.execute(
                """
                SELECT table_name, constraint_type, count(*)
                  FROM information_schema.table_constraints
                 WHERE table_schema = 'MART'
                 GROUP BY 1, 2 ORDER BY 1, 2
                """
            )
            contraintes = [(t.lower(), k, n) for t, k, n in cur.fetchall()]

            droits: list[tuple[str, str, str]] = []
            for nom, nature in objets:
                mot = "VIEW" if nature != "BASE TABLE" else "TABLE"
                try:
                    cur.execute(f"SHOW GRANTS ON {mot} mart.{nom}")
                    for ligne in cur.fetchall():
                        # SHOW GRANTS rend privilege en 2e colonne et grantee en
                        # 6e ; on ne garde que les roles du projet.
                        privilege, beneficiaire = ligne[1], ligne[5]
                        if str(beneficiaire).lower().startswith("gamelens_"):
                            droits.append(
                                (nom.lower(), str(beneficiaire).lower(), privilege)
                            )
                except Exception:  # noqa: BLE001 - une absence de droit n'est pas fatale
                    continue
    finally:
        conn.close()

    aretes = aretes_du_ddl()

    # Recoupement : le DDL et le catalogue doivent compter pareil.
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

    marques = cles_du_ddl()
    for src, col_src, _cible, _col_cible in aretes:
        marques.setdefault((src, col_src), set()).add("FK")

    lignes = [
        "# Schema de donnees, couche Gold\n",
        "\n> **Fichier genere. Ne pas modifier a la main.**\n",
        "> Colonnes, types et contraintes lus dans le catalogue Snowflake ;\n",
        "> cibles des clefs etrangeres lues dans `sql/schema_gold_snowflake.sql`,\n",
        "> les deux sources etant recoupees a chaque generation.\n",
        "> Regenerer par `python outils/generer_schema.py`.\n",
        "\nLivrable du critere **C4.2.1**, qui demande un schema permettant\n",
        "d'identifier le type des donnees, les modalites d'acces et l'organisation\n",
        "des donnees. Les trois sections ci-dessous repondent dans cet ordre.\n",
        "\n## 1. Organisation des donnees\n",
        "\nModele en etoile : deux dimensions, deux tables de faits, une vue de\n",
        "restitution. Le grain de `fact_popularity_history` est le couple\n",
        "(jeu, jour) ; celui de `fact_prices` est (jeu, boutique, instant de\n",
        "collecte). Colonnes larges plutot qu'un modele entite-attribut-valeur :\n",
        "les indicateurs suivis sont connus et peu nombreux.\n",
        "\n```mermaid\nerDiagram\n",
    ]

    for src, col_src, cible, _ in aretes:
        lignes.append(f"    {cible} ||--o{{ {src} : {col_src}\n")

    for nom, nature in objets:
        cle = nom.lower()
        if nature != "BASE TABLE":
            continue
        lignes.append(f"    {cle} {{\n")
        for col, type_sql, nullable in colonnes[cle]:
            portees = marques.get((cle, col), set())
            # Mermaid n'accepte qu'un marqueur par attribut : on garde le plus
            # structurant. Une colonne a la fois clef etrangere et partie d'un
            # grain unique est d'abord une clef etrangere, l'unicite du grain
            # etant dite en toutes lettres au-dessus du diagramme.
            suffixe = ""
            for candidat in ("PK", "FK", "UK"):
                if candidat in portees:
                    suffixe = f" {candidat}"
                    break
            lignes.append(f"        {type_sql} {col}{suffixe}\n")
        lignes.append("    }\n")
    lignes.append("```\n")

    vues = [n for n, t in objets if t != "BASE TABLE"]
    if vues:
        lignes.append(
            f"\nS'y ajoute la vue `mart.{vues[0].lower()}`, seul objet visible du\n"
            "role de restitution. Elle joint la dimension des jeux et les faits de\n"
            "popularite, sans exposer les tables sous-jacentes.\n"
        )

    lignes.append("\n## 2. Type des donnees\n")
    lignes.append(
        "\nTypes tels que le catalogue les porte. Le dimensionnement exact\n"
        "(longueurs, precisions) figure dans `dictionnaire_gold_snowflake.md`,\n"
        "qui est l'annexe faite pour cela.\n"
    )
    for nom, nature in objets:
        cle = nom.lower()
        etiquette = "table" if nature == "BASE TABLE" else "vue"
        lignes.append(f"\n### `mart.{cle}` ({etiquette})\n")
        lignes.append("\n| Colonne | Type | Nul |")
        lignes.append("\n|---|---|---|")
        for col, type_sql, nullable in colonnes[cle]:
            lignes.append(
                f"\n| `{col}` | `{type_sql}` | {'oui' if nullable == 'YES' else 'non'} |"
            )
        lignes.append("\n")

    lignes.append("\n## 3. Modalites d'acces\n")
    if droits:
        lignes.append("\n| Objet | Role | Privilege |")
        lignes.append("\n|---|---|---|")
        for objet, role, privilege in sorted(set(droits)):
            lignes.append(f"\n| `mart.{objet}` | `{role}` | `{privilege}` |")
        lignes.append("\n")
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
    for table, genre, nombre in contraintes:
        lignes.append(f"\n| `mart.{table}` | {genre} | {nombre} |")
    lignes.append(
        "\n\nLe diagramme ci-dessus montre donc des relations **voulues**, pas des\n"
        "relations garanties par le moteur. Ce que le moteur ne garantit pas est\n"
        "porte par deux filets rejoues a chaque push : les contrats declaratifs de\n"
        "`dbt/models/gold/`, ou chaque `relationships` est exactement une des\n"
        "fleches de ce diagramme, et les controles applicatifs de\n"
        "`entrepot/verifier_gold.py`.\n"
    )
    return "".join(lignes)


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Generation du schema de donnees")
    parseur.add_argument(
        "--verifier",
        action="store_true",
        help="ne rien ecrire, echouer si le fichier versionne n'est plus a jour",
    )
    args = parseur.parse_args(argv)

    rendu = rendre()

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

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(rendu, encoding="utf-8", newline="\n")
    print(f"Ecrit : {SORTIE.relative_to(RACINE)} ({len(rendu.splitlines())} lignes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
