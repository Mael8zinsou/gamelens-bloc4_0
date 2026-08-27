"""Genere le dictionnaire de donnees depuis le catalogue, jamais a la main.

Annexe de la documentation technique (C4.3.3).

## Pourquoi generer plutot qu'ecrire

Un dictionnaire recopie a la main diverge du schema en quelques semaines. Le
scenario est ordinaire : quelqu'un ajoute une colonne, oublie la documentation,
et le fichier reste plausible tout en etant faux. C'est le pire etat pour une
documentation, parce qu'un lecteur lui fait confiance a tort.

Ici, la description vit dans le catalogue de la base, ecrite par les
`COMMENT ON COLUMN` des fichiers de `sql/`. Ce module la lit et la met en
forme. Il n'existe donc qu'un seul endroit ou ecrire, et une colonne ajoutee
sans commentaire apparait avec une description VIDE : un manque declare, pas un
mensonge silencieux.

La chaine d'integration continue regenere ce fichier a chaque push et echoue
s'il differe de celui du depot. La garantie est donc verifiee et non promise.

## Usage

    python outils/generer_dictionnaire.py                      # PostgreSQL
    python outils/generer_dictionnaire.py --cible snowflake    # couche Gold
    python outils/generer_dictionnaire.py --verifier           # sans ecrire
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "ingestion"))
sys.path.insert(0, str(RACINE / "entrepot"))

SCHEMAS_PG = ["bronze", "speed", "mart"]

ROLE_DES_SCHEMAS = {
    "bronze": "Archive des reponses d'API telles que recues. Source de recalcul.",
    "speed": "Couche Silver speed : donnee recente, nettoyee, servie en continu.",
    "mart": "Couche Gold prototype sur PostgreSQL. La cible de production est Snowflake.",
}

REQUETE_OBJETS = """
    SELECT n.nspname AS schema,
           c.relname AS objet,
           CASE c.relkind WHEN 'r' THEN 'table' WHEN 'v' THEN 'vue' END AS nature,
           obj_description(c.oid) AS description
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v')
    ORDER BY n.nspname, c.relkind DESC, c.relname
"""

REQUETE_COLONNES = """
    SELECT c.column_name,
           format_type(a.atttypid, a.atttypmod) AS type,
           c.is_nullable,
           c.column_default,
           d.description
    FROM information_schema.columns c
    JOIN pg_class pc ON pc.relname = c.table_name
    JOIN pg_namespace n ON n.oid = pc.relnamespace AND n.nspname = c.table_schema
    JOIN pg_attribute a ON a.attrelid = pc.oid AND a.attname = c.column_name
    LEFT JOIN pg_description d ON d.objoid = pc.oid AND d.objsubid = c.ordinal_position
    WHERE c.table_schema = %s AND c.table_name = %s
    ORDER BY c.ordinal_position
"""

REQUETE_CONTRAINTES = """
    SELECT conname, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE conrelid = (quote_ident(%s) || '.' || quote_ident(%s))::regclass
    ORDER BY contype, conname
"""


def echapper(texte: str | None) -> str:
    """Neutralise les caracteres qui casseraient un tableau Markdown."""
    if not texte:
        return ""
    return texte.replace("|", "\\|").replace(chr(10), " ").strip()


def rendre_postgres() -> str:
    """Interroge le catalogue PostgreSQL et rend le dictionnaire en Markdown."""
    from common import connexion_pg

    lignes: list[str] = []
    manquantes = 0

    conn = connexion_pg()
    try:
        with conn.cursor() as cur:
            cur.execute(REQUETE_OBJETS, (SCHEMAS_PG,))
            objets = cur.fetchall()

            schema_courant = None
            for schema, objet, nature, description in objets:
                if schema != schema_courant:
                    schema_courant = schema
                    lignes.append(f"\n## Schema `{schema}`\n")
                    lignes.append(ROLE_DES_SCHEMAS.get(schema, "") + "\n")

                lignes.append(f"\n### `{schema}.{objet}` ({nature})\n")
                if description:
                    lignes.append(f"{description}\n")

                cur.execute(REQUETE_COLONNES, (schema, objet))
                colonnes = cur.fetchall()

                lignes.append("\n| Colonne | Type | Nul | Defaut | Description |")
                lignes.append("\n|---|---|---|---|---|")
                for nom, type_sql, nullable, defaut, desc in colonnes:
                    if not desc and nature == "table":
                        manquantes += 1
                    defaut_court = echapper(defaut)[:40] if defaut else ""
                    lignes.append(
                        f"\n| `{nom}` | `{type_sql}` | {'oui' if nullable == 'YES' else 'non'} "
                        f"| {('`' + defaut_court + '`') if defaut_court else ''} | {echapper(desc)} |"
                    )
                lignes.append("\n")

                if nature == "table":
                    cur.execute(REQUETE_CONTRAINTES, (schema, objet))
                    contraintes = cur.fetchall()
                    if contraintes:
                        lignes.append("\nContraintes :\n")
                        for nom, definition in contraintes:
                            lignes.append(f"\n- `{nom}` : `{definition}`")
                        lignes.append("\n")
    finally:
        conn.close()

    entete = [
        "# Dictionnaire de donnees, couches PostgreSQL\n",
        "\n> **Fichier genere. Ne pas modifier a la main.**\n",
        "> Source : les `COMMENT ON` des fichiers de `sql/`, lus dans le catalogue\n",
        "> de la base. Regenerer par `python outils/generer_dictionnaire.py`.\n",
        "> La chaine d'integration continue echoue si ce fichier n'est pas a jour.\n",
    ]
    corps = "".join(lignes)
    bilan = (
        f"\n---\n\nColonnes de tables sans description : **{manquantes}**. "
        "Une case vide est un manque declare, pas un oubli invisible.\n"
    )
    return "".join(entete) + corps + bilan


def rendre_snowflake() -> str:
    """Interroge le catalogue Snowflake et rend le dictionnaire de la couche Gold.

    Cible de production de la couche Gold. Le schema mart de PostgreSQL en est
    le prototype, conserve comme repli et comme reference de comparaison.

    Snowflake porte les commentaires en ligne dans la definition des colonnes,
    et non par des instructions COMMENT ON separees : la source est donc
    sql/schema_gold_snowflake.sql lui-meme.
    """
    from connexion import connexion

    lignes: list[str] = []
    manquantes = 0

    conn = connexion()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name, table_type, comment
                FROM information_schema.tables
                WHERE table_schema = 'MART'
                ORDER BY table_type DESC, table_name
                """
            )
            objets = cur.fetchall()

            for nom, nature, commentaire in objets:
                etiquette = "table" if nature == "BASE TABLE" else "vue"
                lignes.append(f"\n### `mart.{nom.lower()}` ({etiquette})\n")
                if commentaire:
                    lignes.append(f"{echapper(commentaire)}\n")

                cur.execute(
                    """
                    SELECT column_name, data_type, character_maximum_length,
                           numeric_precision, numeric_scale, is_nullable, comment
                    FROM information_schema.columns
                    WHERE table_schema = 'MART' AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (nom,),
                )
                lignes.append("\n| Colonne | Type | Nul | Description |")
                lignes.append("\n|---|---|---|---|")
                for col, type_sql, longueur, precision, echelle, nullable, desc in cur.fetchall():
                    if longueur:
                        rendu = f"{type_sql}({longueur})"
                    elif precision is not None and type_sql == "NUMBER":
                        rendu = f"NUMBER({precision},{echelle})"
                    else:
                        rendu = type_sql
                    if not desc and etiquette == "table":
                        manquantes += 1
                    lignes.append(
                        f"\n| `{col.lower()}` | `{rendu}` | "
                        f"{'oui' if nullable == 'YES' else 'non'} | {echapper(desc)} |"
                    )
                lignes.append("\n")
    finally:
        conn.close()

    entete = [
        "# Dictionnaire de donnees, couche Gold Snowflake\n",
        "\n> **Fichier genere. Ne pas modifier a la main.**\n",
        "> Source : les commentaires en ligne de `sql/schema_gold_snowflake.sql`,\n",
        "> lus dans `information_schema` du compte Snowflake.\n",
        "> Regenerer par `python outils/generer_dictionnaire.py --cible snowflake`.\n",
        "\n**Avertissement d'architecture.** Snowflake declare les contraintes\n",
        "relationnelles mais ne les applique pas a l'ecriture : `CHECK`,\n",
        "`FOREIGN KEY`, `PRIMARY KEY` et `UNIQUE` sont des metadonnees. Seuls\n",
        "`NOT NULL`, le type et la longueur sont opposables. Les contraintes ne\n",
        "figurent donc pas dans ce dictionnaire : elles y seraient trompeuses.\n",
        "L'integrite reelle est portee par deux filets, tous deux rejoues a chaque\n",
        "push : les contrats declaratifs du projet dbt (`dbt/models/gold/`), ou\n",
        "chaque `relationships` est une clef etrangere que le moteur ignore, et les\n",
        "controles applicatifs de `entrepot/verifier_gold.py`. Le comportement du\n",
        "moteur est lui-meme verifie a chaque push, et les deux filets sont\n",
        "confrontes au meme jeu de donnees fautif pour verifier qu'ils restent\n",
        "d'accord (voir `entrepot/recette_ci.py`).\n",
    ]
    corps = "".join(lignes)
    bilan = f"\n---\n\nColonnes de tables sans description : **{manquantes}**.\n"
    return "".join(entete) + corps + bilan


SORTIES = {
    "postgres": RACINE / "docs" / "annexes" / "dictionnaire_donnees.md",
    "snowflake": RACINE / "docs" / "annexes" / "dictionnaire_gold_snowflake.md",
}


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Generation du dictionnaire de donnees")
    parseur.add_argument(
        "--cible",
        choices=sorted(SORTIES),
        default="postgres",
        help="catalogue a interroger (defaut : postgres)",
    )
    parseur.add_argument(
        "--verifier",
        action="store_true",
        help=(
            "ne rien ecrire, comparer au fichier du depot et sortir en code 1 s'il differe. "
            "Mode utilise par la chaine d'integration continue."
        ),
    )
    args = parseur.parse_args(argv)

    contenu = rendre_postgres() if args.cible == "postgres" else rendre_snowflake()
    sortie = SORTIES[args.cible]

    # La date de generation est volontairement EXCLUE du fichier : elle
    # changerait a chaque execution et ferait echouer la comparaison sans
    # qu'aucun schema n'ait bouge. Un controle qui echoue pour une raison sans
    # rapport avec ce qu'il verifie finit par etre desactive.
    if args.verifier:
        if not sortie.exists():
            print(f"ECHEC : {sortie.relative_to(RACINE)} est absent.")
            return 1
        actuel = sortie.read_text(encoding="utf-8")
        if actuel != contenu:
            print(
                f"ECHEC : {sortie.relative_to(RACINE)} ne correspond plus au catalogue.\n"
                "Le schema a change sans que le dictionnaire soit regenere.\n"
                f"Corriger par : python outils/generer_dictionnaire.py --cible {args.cible}"
            )
            attendues = len(contenu.splitlines())
            trouvees = len(actuel.splitlines())
            print(f"  {trouvees} ligne(s) dans le depot, {attendues} attendue(s).")
            return 1
        print(f"OK : {sortie.relative_to(RACINE)} est a jour ({len(contenu.splitlines())} lignes).")
        return 0

    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(contenu, encoding="utf-8")
    horodatage = datetime.now(UTC).strftime("%d/%m/%Y %H:%M UTC")
    print(
        f"{sortie.relative_to(RACINE)} genere ({len(contenu.splitlines())} lignes, {horodatage})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
