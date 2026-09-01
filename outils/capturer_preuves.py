"""Capture les preuves textuelles de la soutenance dans docs/preuves/.

Le depot ne conservait aucune trace montrable : tout etait transcrit dans les
documents de docs/, rien n'existait sous forme de sortie reelle datee. Cet outil
comble ce manque de facon reproductible, et non par des commandes jetables dont
personne ne saurait dire quand elles ont tourne.

Chaque capture porte en en-tete la date, la commande exacte, et le ou les
criteres de la grille qu'elle sert. Les identifiants numerotes renvoient au
tableau de tracabilite de docs/plan_soutenance.md.

    python outils/capturer_preuves.py                 # tout
    python outils/capturer_preuves.py --sans-reseau   # seulement le local
    python outils/capturer_preuves.py --seulement c11 # une capture

Les captures marquees reseau visent Snowflake, l'API Steam ou github.com. Elles
doivent etre produites avant le jour de la soutenance : le reglement ne garantit
aucun acces reseau dans la salle d'examen.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "docs" / "preuves"

# Le shell lance par subprocess ne retrouve pas toujours gh sur un poste
# Windows, alors que Python le voit. On resout le chemin absolu une fois.
GH = (shutil.which("gh") or "gh").replace("\\", "/")


@dataclass(frozen=True)
class Capture:
    """Une preuve a produire, et ce qu'elle sert a cocher."""

    identifiant: str
    fichier: str
    criteres: str
    intitule: str
    # Une capture est soit une commande a lancer, soit une fonction Python qui
    # rend (sortie, code). La seconde forme sert quand le detour par un shell
    # pose plus de problemes qu'il n'en resout, ce qui est le cas de gh.EXE.
    commande: list[str] | None = None
    fonction: object = None
    reseau: bool = False
    # Certaines commandes rendent un code non nul sans que ce soit un echec :
    # un refus de droits en fait partie, et c'est justement la preuve.
    codes_admis: tuple[int, ...] = field(default=(0,))


def _etages_ci() -> tuple[str, int]:
    """Les 6 etages du dernier run vert, et le detail de l'etage entrepot."""
    gh = shutil.which("gh") or "gh"

    def lancer(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [gh, *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=RACINE,
        )

    trouve = lancer(
        "run", "list", "--workflow=ci.yml", "--status=success", "--limit", "1",
        "--json", "databaseId,displayTitle,createdAt", "-q",
        r'.[0] | "\(.databaseId)|\(.createdAt)|\(.displayTitle)"',
    )
    if trouve.returncode != 0 or not trouve.stdout.strip():
        return (trouve.stdout + trouve.stderr, trouve.returncode or 1)

    identifiant, cree_le, titre = trouve.stdout.strip().split("|", 2)
    morceaux = [f"Run {identifiant}, {cree_le}\n  {titre}\n"]

    vue = lancer("run", "view", identifiant)
    morceaux.append(vue.stdout or vue.stderr)

    detail = lancer(
        "run", "view", identifiant, "--json", "jobs", "-q",
        r'.jobs[] | "\n=== \(.name) : \(.conclusion) ===", '
        r'(.steps[] | "  \(.conclusion)  \(.name)")',
    )
    morceaux.append("\n--- etapes de chaque etage ---")
    morceaux.append(detail.stdout or detail.stderr)

    code = max(trouve.returncode, vue.returncode, detail.returncode)
    return ("\n".join(morceaux), code)


CAPTURES: tuple[Capture, ...] = (
    Capture(
        "c11",
        "c11_cloisonnement_roles.txt",
        "11",
        "Modalites d'acces : dashboard_viewer refuse sur une table de faits, "
        "servi par la vue",
        ["bash", "-c", (
            "echo '--- 1. dashboard_viewer tente de lire une table de faits ---'; "
            "docker exec gamelens-postgres psql -U dashboard_viewer -d gamelens "
            "-c 'SELECT count(*) FROM mart.fact_prices;' 2>&1; "
            "echo; echo '--- 2. la vue de restitution lui repond ---'; "
            "docker exec gamelens-postgres psql -U dashboard_viewer -d gamelens "
            "-c 'SELECT unified_name, day, avg_player_count "
            "FROM mart.v_popularity_dashboard ORDER BY day DESC, "
            "avg_player_count DESC LIMIT 5;' 2>&1"
        )],
    ),
    Capture(
        "c14",
        "c14_airflow_dags.txt",
        "14",
        "Orchestrateur : les 4 DAG et leurs derniers runs",
        ["bash", "-c", (
            "echo '--- DAG declares ---'; "
            "docker exec gamelens-airflow-scheduler airflow dags list 2>/dev/null; "
            "echo; echo '--- derniers runs par DAG ---'; "
            "for d in gamelens_ingestion_temps_reel gamelens_promotion_gold "
            "gamelens_promotion_snowflake gamelens_supervision; do "
            "docker exec gamelens-airflow-scheduler airflow dags list-runs "
            "-d $d --no-backfill 2>/dev/null | head -6; echo; done"
        )],
    ),
    Capture(
        "c19",
        "c19_supervision_indicateurs.txt",
        "19, 20",
        "Supervision : les 5 vues d'indicateurs et le journal d'alertes",
        ["bash", "-c", (
            "docker exec gamelens-postgres psql -U gamelens_app -d gamelens -e "
            "-c 'SELECT * FROM speed.v_indicateur_fraicheur;' "
            "-c 'SELECT * FROM speed.v_indicateur_completude;' "
            "-c 'SELECT * FROM speed.v_indicateur_latence;' "
            "-c 'SELECT * FROM speed.v_indicateur_fiabilite;' "
            "-c 'SELECT * FROM speed.v_indicateur_gold;' "
            "-c 'SELECT regle, severite, declenchee_le, resolue_le, valeur, seuil "
            "FROM speed.alertes ORDER BY declenchee_le DESC LIMIT 10;' 2>&1"
        )],
    ),
    Capture(
        "c26",
        "c26_tests_unitaires.txt",
        "26, 27",
        "Cahier de recettes : les tests automatises, tels que la CI les lance",
        [sys.executable, "-m", "pytest", "tests", "-v"],
    ),
    Capture(
        "c15",
        "c15_snowpark_sql_genere.txt",
        "15",
        "Calcul distribue : le SQL que Snowpark genere et pousse sur le compute "
        "Snowflake",
        ["bash", "-c", (
            "MSYS_NO_PATHCONV=1 docker compose --profile outillage "
            "run --rm --no-deps snowflake-cli python "
            "/projet/entrepot/snowpark_promotion.py --expliquer 2>&1"
        )],
        reseau=True,
    ),
    Capture(
        "c10",
        "c10_contrats_dbt.txt",
        "10, 12",
        "Schema de donnees : les 29 contrats declaratifs dbt sur la couche Gold",
        ["bash", "-c", (
            "MSYS_NO_PATHCONV=1 docker compose --profile outillage "
            "run --rm snowflake-cli dbt test --project-dir /projet/dbt "
            "--profiles-dir /projet/dbt 2>&1"
        )],
        reseau=True,
    ),
    Capture(
        "c12",
        "c12_integrite_gold.txt",
        "10, 12",
        "Schema de donnees : les 8 controles applicatifs, second filet d'integrite",
        ["bash", "-c", (
            "MSYS_NO_PATHCONV=1 docker compose --profile outillage "
            "run --rm snowflake-cli python /projet/entrepot/verifier_gold.py 2>&1"
        )],
        reseau=True,
    ),
    Capture(
        "c16",
        "c16_ci_six_etages.txt",
        "16",
        "CI/CD : les 6 etages du dernier run, avec leur duree et leur conclusion",
        fonction=_etages_ci,
        reseau=True,
    ),
    Capture(
        "c09",
        "c09_couts_snowflake.txt",
        "9",
        "Estimation des couts : consommation de credits mesuree, par entrepot",
        ["bash", "-c", (
            "cd '%s' && cat > sql/_preuve_couts.sql <<'FIN'\n"
            "SELECT warehouse_name, round(sum(credits_used), 4) AS credits,\n"
            "       min(to_date(start_time)) AS depuis,\n"
            "       max(to_date(start_time)) AS jusqu_a\n"
            "  FROM snowflake.account_usage.warehouse_metering_history\n"
            " GROUP BY 1 ORDER BY 2 DESC;\n"
            "FIN\n"
            "MSYS_NO_PATHCONV=1 docker compose --profile outillage run --rm "
            "--no-deps snowflake-cli python /projet/entrepot/executer_sql.py "
            "/projet/sql/_preuve_couts.sql --sans-contexte 2>&1; "
            "rm -f sql/_preuve_couts.sql"
        )],
        reseau=True,
    ),
)


def ecrire(capture: Capture, sortie: str, code: int) -> Path:
    """Ecrit la capture avec son en-tete de provenance."""
    horodatage = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    if capture.commande is None:
        commande = f"fonction Python {capture.fonction.__name__}() de cet outil"
    elif capture.commande[0] == "bash":
        commande = capture.commande[-1]
    else:
        commande = " ".join(capture.commande)
    entete = (
        f"# Preuve {capture.identifiant} : {capture.intitule}\n"
        f"#\n"
        f"# Criteres de la grille : {capture.criteres} "
        f"(voir docs/plan_soutenance.md)\n"
        f"# Reseau requis        : {'oui' if capture.reseau else 'non'}\n"
        f"# Capture le           : {horodatage}\n"
        f"# Code de sortie       : {code}\n"
        f"#\n"
        f"# Commande :\n"
    )
    entete += "".join(f"#   {l}\n" for l in commande.splitlines())
    entete += "#\n" + "# " + "-" * 74 + "\n\n"

    chemin = DOSSIER / capture.fichier
    chemin.write_text(entete + sortie.rstrip() + "\n", encoding="utf-8", newline="\n")
    return chemin


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument(
        "--sans-reseau",
        action="store_true",
        help="ne produire que les captures qui tournent hors ligne",
    )
    parseur.add_argument(
        "--seulement",
        metavar="ID",
        help="ne produire qu'une capture, par son identifiant (ex : c11)",
    )
    args = parseur.parse_args(argv)

    DOSSIER.mkdir(parents=True, exist_ok=True)

    a_faire = [c for c in CAPTURES if not (args.sans_reseau and c.reseau)]
    if args.seulement:
        a_faire = [c for c in a_faire if c.identifiant == args.seulement]
        if not a_faire:
            print(f"Aucune capture ne porte l'identifiant {args.seulement}.")
            return 2

    echecs: list[str] = []
    for capture in a_faire:
        marque = "reseau" if capture.reseau else "local "
        print(f"[{marque}] {capture.identifiant:5} {capture.intitule[:58]}", flush=True)
        if capture.fonction is not None:
            sortie, code = capture.fonction()
        else:
            resultat = subprocess.run(
                capture.commande, capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=RACINE,
            )
            code = resultat.returncode
            sortie = resultat.stdout + (
                ("\n--- stderr ---\n" + resultat.stderr)
                if resultat.stderr.strip() else ""
            )
        chemin = ecrire(capture, sortie, code)
        lignes = len(sortie.splitlines())
        if code not in capture.codes_admis:
            echecs.append(f"{capture.identifiant} (code {code})")
            print(f"          ECHEC code {code}, {lignes} lignes gardees")
        else:
            print(f"          ok, {lignes} lignes -> {chemin.name}")

    print()
    if echecs:
        print(f"{len(a_faire) - len(echecs)}/{len(a_faire)} captures produites. "
              f"En echec : {', '.join(echecs)}")
        return 1
    print(f"{len(a_faire)}/{len(a_faire)} captures produites dans docs/preuves/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
