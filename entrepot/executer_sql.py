"""Execute un script SQL sur Snowflake, instruction par instruction.

Le connecteur Python n'execute qu'une instruction a la fois. Ce module decoupe
le fichier avec le decoupeur du connecteur lui-meme, qui gere correctement les
commentaires et les points-virgules a l'interieur des chaines, puis rend compte
de chaque instruction separement.

Deux modes, et le second n'est pas un confort :

- **arret a la premiere erreur** (defaut), pour l'application d'un schema, ou
  une erreur signifie que la suite n'a plus de sens ;
- **poursuite sur erreur** (`--continuer`), pour les scripts de verification
  dont certaines instructions DOIVENT echouer. C'est le cas de
  `sql/verify_snowflake_constraints.sql`, qui cherche a etablir empiriquement
  quelles contraintes Snowflake applique reellement a l'ecriture. Un mode
  strict s'y arreterait au premier resultat interessant.

Usage :
    docker compose run --rm snowflake-cli python entrepot/executer_sql.py sql/schema_gold_snowflake.sql
    docker compose run --rm snowflake-cli python entrepot/executer_sql.py sql/verify_snowflake_constraints.sql --continuer
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from connexion import connexion


def est_significative(instruction: str) -> bool:
    """Vrai si l'instruction contient autre chose que des commentaires.

    Le decoupeur du connecteur restitue les blocs de commentaires de fin de
    fichier comme s'il s'agissait d'instructions. Les envoyer a Snowflake
    produit une erreur de compilation SQL parfaitement legitime mais denuee de
    sens, qui masquerait un vrai echec dans le compte rendu.
    """
    for ligne in instruction.splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("--"):
            return True
    return False


def resume(instruction: str, largeur: int = 74) -> str:
    """Premiere ligne significative de l'instruction, pour l'affichage."""
    for ligne in instruction.strip().splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("--"):
            return ligne[:largeur] + ("..." if len(ligne) > largeur else "")
    return instruction.strip()[:largeur]


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Execution d'un script SQL sur Snowflake")
    parseur.add_argument("fichier", help="chemin du script .sql")
    parseur.add_argument(
        "--continuer", action="store_true", help="poursuivre malgre les erreurs et les recenser"
    )
    parseur.add_argument(
        "--sans-contexte",
        action="store_true",
        help="ne pas se positionner sur l'entrepot et la base au moment de la connexion",
    )
    args = parseur.parse_args(argv)

    from snowflake.connector.util_text import split_statements

    contenu = Path(args.fichier).read_text(encoding="utf-8")
    instructions = [i for i, _ in split_statements(io.StringIO(contenu)) if est_significative(i)]

    print(f"Script   : {args.fichier}")
    print(
        f"Mode     : {'poursuite sur erreur' if args.continuer else 'arret a la premiere erreur'}"
    )
    print(f"Contenu  : {len(instructions)} instruction(s)\n")

    conn = connexion(avec_contexte=not args.sans_contexte)
    reussies, echouees = 0, []

    try:
        for numero, instruction in enumerate(instructions, start=1):
            etiquette = resume(instruction)
            try:
                with conn.cursor() as cur:
                    cur.execute(instruction)
                    lignes = cur.fetchall() if cur.description else []
                detail = f"{len(lignes)} ligne(s)" if lignes else "ok"
                print(f"  [{numero:>2}] OK      {etiquette}")
                if lignes and len(lignes) <= 8:
                    for ligne in lignes:
                        print(f"           -> {ligne}")
                elif lignes:
                    print(f"           -> {detail}")
                reussies += 1
            except Exception as exc:
                message = str(exc).splitlines()[0][:150]
                print(f"  [{numero:>2}] ERREUR  {etiquette}")
                print(f"           -> {message}")
                echouees.append((numero, etiquette, message))
                if not args.continuer:
                    print(f"\nArret a l'instruction {numero}.")
                    return 1
    finally:
        conn.close()

    print(f"\n{reussies} reussie(s), {len(echouees)} en erreur")
    if echouees and args.continuer:
        print("\nInstructions en erreur, a confronter aux resultats attendus du script :")
        for numero, etiquette, message in echouees:
            print(f"  [{numero:>2}] {etiquette}")
            print(f"       {message}")
    return 0 if not echouees or args.continuer else 1


if __name__ == "__main__":
    sys.exit(main())
