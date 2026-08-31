"""Recette automatisee de la couche Gold Snowflake, executee par la CI (C4.2.3).

Comble le seul angle mort du pipeline d'integration continue : jusqu'ici,
`entrepot/` passait au controle de qualite mais rien ne l'EXECUTAIT, faute
d'identifiants sur le runner. C'etait la partie de la plateforme la moins
couverte alors qu'elle est la plus exposee, puisque Snowflake n'applique
aucune contrainte relationnelle et que l'integrite y repose entierement sur
des controles applicatifs.

Principe : meme logique d'infrastructure jetable que l'etage d'integration
PostgreSQL. Une base Snowflake est creee pour la duree du run, eprouvee, puis
supprimee. La couche de demonstration `gamelens` n'est jamais touchee, et un
garde-fou refuse de demarrer si la base visee porte un nom protege. La
precaution n'est pas theorique : `sql/schema_gold_snowflake.sql` contient des
CREATE OR REPLACE TABLE qui detruiraient les donnees de soutenance.

Dix etapes, dont trois tests negatifs :

  1. creation de la base jetable ;
  2. application du schema Gold, redirige vers cette base ;
  3. chargement d'un jeu de donnees deterministe ;
  4. controles d'integrite applicatifs, attendus tous au vert ;
  5. materialisation des modeles dbt sur cette base ;
  6. contrats dbt (29 tests), attendus tous au vert ;
  7. calcul distribue Snowpark, resultat compare a des valeurs calculees a la
     main, et non simplement "la requete passe" ;
  8. mise a l'epreuve des contraintes : on verifie que Snowflake laisse encore
     passer ce que l'on a documente comme non applique, et rejette ce qu'il
     applique reellement ;
  9. controles d'integrite a nouveau, cette fois attendus EN ECHEC : les
     violations que le moteur a laisse entrer doivent etre rattrapees par le
     filet applicatif. Un controle qui ne sait pas echouer ne prouve rien ;
 10. contrats dbt a nouveau, egalement attendus EN ECHEC, et sur les cinq
     tests nommes a l'avance et non sur n'importe lesquels.

Les etapes 9 et 10 eprouvent DEUX filets sur le meme jeu de donnees fautif.
C'est deliberé : la plateforme en garde deux, l'un applicatif et l'autre
declaratif, et leur coexistence n'a de valeur que si on verifie qu'ils
restent d'accord. Le jour ou l'un rattrape ce que l'autre laisse passer, la
recette s'arrete plutot que de laisser la divergence s'installer.

Usage :
    docker compose run --rm snowflake-cli python entrepot/recette_ci.py
    docker compose run --rm snowflake-cli python entrepot/recette_ci.py --conserver
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from connexion_snowflake import connexion, mode_authentification

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_DBT = RACINE / "dbt"

# Bases que la recette refuse de viser, quelle que soit la configuration.
# gamelens porte la couche de demonstration presentee a la soutenance.
BASES_PROTEGEES = {"gamelens", "snowflake", "snowflake_sample_data"}

JOURS = [f"2026-01-0{n}" for n in range(1, 9)]

# Jeu de donnees choisi pour que les resultats du calcul distribue soient
# calculables de tete, donc verifiables. Voir ATTENDU_CLASSEMENT.
JEUX = [
    ("rec-0000-0000-0000-000000000001", "Recette Alpha", "Roguelike", 900001),
    ("rec-0000-0000-0000-000000000002", "Recette Beta", "Roguelike", 900002),
    ("rec-0000-0000-0000-000000000003", "Recette Gamma", "Metroidvania", 900003),
]
BOUTIQUE = ("rec-store-0000-0000-000000000001", "Steam Recette", "api")

# Alpha croit de 100 en 100 sur huit jours, Beta et Gamma restent plats.
POPULARITE = {
    "rec-0000-0000-0000-000000000001": [100, 200, 300, 400, 500, 600, 700, 800],
    "rec-0000-0000-0000-000000000002": [50] * 8,
    "rec-0000-0000-0000-000000000003": [10] * 8,
}

# Valeurs attendues au dernier jour, calculees a la main :
#   moyenne glissante 7j d'Alpha = (200+...+800) / 7 = 500
#   part du genre Roguelike      = 800 / 850 = 94.1 %  et  50 / 850 = 5.9 %
#   Metroidvania ne contient que Gamma, donc 100 % et rang 1
ATTENDU_CLASSEMENT = {
    "Recette Alpha": {"moyenne_7j": 500.0, "rang": 1, "part": 94.1},
    "Recette Beta": {"moyenne_7j": 50.0, "rang": 2, "part": 5.9},
    "Recette Gamma": {"moyenne_7j": 10.0, "rang": 1, "part": 100.0},
}

# ----------------------------------------------------------------------------
# Comportement des contraintes, etabli empiriquement le 20/08/2026 et consigne
# dans sql/verify_snowflake_constraints.sql. Ce tableau en fait un test de
# non-regression : si Snowflake se mettait un jour a appliquer les clefs
# etrangeres, la CI virerait au rouge et le choix d'architecture consistant a
# reporter l'integrite sur des tests dbt devrait etre reexamine. Une hypothese
# d'architecture qui n'est verifiee qu'une fois est une hypothese qui perime.
# ----------------------------------------------------------------------------
GAME_A = JEUX[0][0]
STORE = BOUTIQUE[0]
TROP_LONG = "rec-identifiant-beaucoup-trop-long-pour-la-colonne"  # plus de 36

COMPORTEMENT_ATTENDU = [
    (
        "NOT NULL sur unified_name",
        "INSERT INTO mart.dim_games (game_id, unified_name) " "SELECT 'rec-viol-not-null', NULL",
        True,
    ),
    (
        "longueur VARCHAR(36) depassee",
        f"INSERT INTO mart.dim_games (game_id, unified_name) "
        f"SELECT '{TROP_LONG}', 'Identifiant trop long'",
        True,
    ),
    (
        "CHECK implicite : prix negatif",
        f"INSERT INTO mart.fact_prices (game_id, store_id, price, collected_at) "
        f"SELECT '{GAME_A}', '{STORE}', -5.00, '2026-01-08 12:00:00'::timestamp_ntz",
        False,
    ),
    (
        "clef etrangere : game_id inexistant",
        f"INSERT INTO mart.fact_prices (game_id, store_id, price, collected_at) "
        f"SELECT 'rec-jeu-inexistant', '{STORE}', 9.99, "
        f"'2026-01-08 13:00:00'::timestamp_ntz",
        False,
    ),
    (
        "clef primaire : (game_id, day) en doublon",
        f"INSERT INTO mart.fact_popularity_history (game_id, day, avg_player_count) "
        f"SELECT '{GAME_A}', '{JOURS[-1]}'::date, 999",
        False,
    ),
    (
        "contrainte UNIQUE : steam_appid en doublon",
        "INSERT INTO mart.dim_games (game_id, unified_name, steam_appid) "
        "SELECT 'rec-doublon-appid', 'Doublon Alpha', 900001",
        False,
    ),
]


# ----------------------------------------------------------------------------
# Les contrats dbt qui doivent tomber, et eux seuls, une fois les violations
# ci-dessus entrees dans la base. Deduits ligne a ligne du tableau precedent :
#
#   prix negatif             -> expression_is_true price > 0
#   game_id inexistant       -> relationships fact_prices.game_id
#   (game_id, day) doublon   -> unicite du grain, ET la vue qui les joint,
#                               car un doublon de fait duplique chaque journee
#                               au travers de la jointure
#   steam_appid doublon      -> unique dim_games.steam_appid
#
# Exiger un ensemble exact, et pas seulement un code de sortie non nul, est ce
# qui separe "la suite a echoue" de "la suite a echoue pour la bonne raison".
# Un test qui tomberait ici sans figurer dans cette liste serait un signal, pas
# un detail : il voudrait dire que le jeu de recette est devenu invalide sur un
# point que personne n'a voulu.
# ----------------------------------------------------------------------------
ATTENDU_ECHECS_DBT = {
    "dbt_utils_source_expression_is_true_gold_fact_prices_price___0",
    "source_relationships_gold_fact_prices_game_id__game_id__source_gold_dim_games_",
    "dbt_utils_source_unique_combination_of_columns_gold_fact_popularity_history_game_id__day",
    "dbt_utils_unique_combination_of_columns_v_popularity_dashboard_game_id__day",
    "source_unique_gold_dim_games_steam_appid",
}


def titre(numero: int, libelle: str) -> None:
    print(f"\n{numero}. {libelle}")
    print("   " + "-" * (len(libelle) + 2))


def nom_base() -> str:
    """Nom de la base jetable, distinct par run et par tentative.

    Rend la valeur demandee telle quelle, protegee ou non : c'est garde_fou
    qui tranche. La premiere version ecartait discretement les noms proteges
    en retombant sur un nom genere, si bien que le garde-fou n'etait jamais
    atteignable et que le test negatif passait au vert sans rien prouver. Un
    contournement muet vaut moins qu'un refus : l'appelant qui visait une
    base precise doit apprendre qu'il ne l'obtiendra pas.
    """
    explicite = os.getenv("SNOWFLAKE_DATABASE")
    if explicite:
        return explicite
    run = os.getenv("GITHUB_RUN_NUMBER", "local")
    tentative = os.getenv("GITHUB_RUN_ATTEMPT", str(int(time.time()) % 100000))
    return f"gamelens_ci_{run}_{tentative}"


def garde_fou(base: str) -> None:
    """Interdit de viser une base de production, y compris par accident."""
    if base.lower() in BASES_PROTEGEES:
        raise SystemExit(
            f"REFUS : la recette vise la base '{base}', qui est protegee.\n"
            "Le script de schema contient des CREATE OR REPLACE TABLE : "
            "l'executer ici detruirait la couche de demonstration. "
            "Laisser SNOWFLAKE_DATABASE vide pour obtenir une base jetable."
        )


def sql_hors_contexte(instructions: list[str]) -> None:
    """Execute des instructions sans se positionner sur une base.

    Necessaire pour creer ou supprimer la base elle-meme : le connecteur
    echouerait a se positionner sur une base qui n'existe pas encore, ou qui
    vient de disparaitre.
    """
    conn = connexion(avec_contexte=False)
    try:
        with conn.cursor() as cur:
            for instruction in instructions:
                cur.execute(instruction)
    finally:
        conn.close()


def lancer(script: str, *arguments: str, base: str) -> subprocess.CompletedProcess:
    """Invoque un script du depot avec la base jetable pour contexte.

    Passe par un sous-processus plutot que par un import : c'est le point
    d'entree reel qui est mis a l'epreuve, code de sortie compris, et non une
    fonction interne appelee dans des conditions arrangees.
    """
    environnement = dict(os.environ, SNOWFLAKE_DATABASE=base, SNOWFLAKE_SCHEMA="mart")
    return subprocess.run(
        [sys.executable, str(RACINE / "entrepot" / script), *arguments],
        env=environnement,
        cwd=str(RACINE),
        capture_output=True,
        text=True,
    )


def creer_base(base: str) -> None:
    sql_hors_contexte(
        [f"CREATE OR REPLACE DATABASE {base}", f"CREATE SCHEMA IF NOT EXISTS {base}.mart"]
    )
    print(f"   base jetable {base} creee")


def supprimer_base(base: str) -> None:
    garde_fou(base)
    sql_hors_contexte([f"DROP DATABASE IF EXISTS {base}"])
    print(f"   base jetable {base} supprimee")


def appliquer_schema(base: str) -> None:
    """Rejoue le script de schema livre, redirige vers la base jetable.

    C'est le script du depot qui est execute, pas une copie simplifiee : si
    quelqu'un y introduit une erreur de DDL, la CI le voit.
    """
    resultat = lancer(
        "executer_sql.py",
        str(RACINE / "sql" / "schema_gold_snowflake.sql"),
        "--base",
        base,
        "--sans-contexte",
        base=base,
    )
    print("   " + resultat.stdout.strip().replace("\n", "\n   "))
    if resultat.returncode != 0:
        print(resultat.stderr)
        raise SystemExit("Le schema Gold ne s'applique plus : recette interrompue.")


def charger_jeu_de_recette(base: str) -> None:
    conn = connexion()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO mart.dim_stores (store_id, name, source_type) SELECT %s, %s, %s",
                BOUTIQUE,
            )
            for game_id, nom, genre, appid in JEUX:
                cur.execute(
                    "INSERT INTO mart.dim_games (game_id, unified_name, genre, steam_appid) "
                    "SELECT %s, %s, %s, %s",
                    (game_id, nom, genre, appid),
                )
                for jour, valeur in zip(JOURS, POPULARITE[game_id], strict=False):
                    cur.execute(
                        "INSERT INTO mart.fact_popularity_history "
                        "(game_id, day, avg_player_count, max_player_count) "
                        "SELECT %s, %s::date, %s, %s",
                        (game_id, jour, valeur, valeur),
                    )
                cur.execute(
                    "INSERT INTO mart.fact_prices "
                    "(game_id, store_id, price, currency, promotion_flag, collected_at) "
                    "SELECT %s, %s, %s, 'EUR', %s, %s::timestamp_ntz",
                    (game_id, BOUTIQUE[0], 19.99, game_id == JEUX[0][0], f"{JOURS[-1]} 10:00:00"),
                )
        print(
            f"   {len(JEUX)} jeux, 1 boutique, {len(JEUX) * len(JOURS)} faits de popularite, "
            f"{len(JEUX)} tarifs"
        )
    finally:
        conn.close()


def controles_integrite(base: str, attendu_au_vert: bool) -> None:
    """Execute verifier_gold.py et confronte son code de sortie a l'attendu.

    Appele deux fois dans la recette, avec des attentes inverses. Le second
    appel est le plus utile : un controle qui ne sait pas echouer ne prouve
    rien sur les fois ou il reussit.
    """
    resultat = lancer("verifier_gold.py", base=base)
    lignes = [x for x in resultat.stdout.splitlines() if "[PASS]" in x or "[FAIL]" in x]
    for ligne in lignes:
        print("   " + ligne.strip())

    au_vert = resultat.returncode == 0
    if au_vert is not attendu_au_vert:
        print(resultat.stdout[-1500:])
        print(resultat.stderr[-800:])
        etat = "au vert" if au_vert else "en echec"
        veut = "au vert" if attendu_au_vert else "en echec"
        raise SystemExit(f"Controles {etat} alors qu'ils etaient attendus {veut}.")

    nombre = sum(1 for x in lignes if "[FAIL]" in x)
    if attendu_au_vert:
        print(f"   -> {len(lignes)} controles, 0 violation : conforme")
    else:
        print(f"   -> {nombre} violation(s) detectee(s) par le filet applicatif : conforme")


def calcul_distribue(base: str) -> None:
    """Rejoue le calcul analytique Snowpark et compare a des valeurs attendues.

    Le calcul distribue de C4.2.2 etait jusqu'ici prouve par une execution
    manuelle. Le verifier ici lui donne un filet : la fenetre glissante et le
    classement par genre sont confrontes a des nombres calcules a la main, pas
    seulement a l'absence d'erreur.
    """
    from connexion_snowflake import parametres
    from snowflake.snowpark import Session
    from snowpark_promotion import calculer_classement

    session = Session.builder.configs(
        {k: v for k, v in parametres().items() if k != "application"}
    ).create()
    try:
        contexte = session.sql("SELECT CURRENT_WAREHOUSE(), CURRENT_DATABASE()").collect()[0]
        print(f"   entrepot virtuel {contexte[0]} | base {contexte[1]}")

        lignes = calculer_classement(session).collect()
        ecarts = []
        for ligne in lignes:
            attendu = ATTENDU_CLASSEMENT.get(ligne["JEU"])
            if attendu is None:
                continue
            observe = {
                "moyenne_7j": float(ligne["MOYENNE_GLISSANTE_7J"]),
                "rang": int(ligne["RANG_DANS_LE_GENRE"]),
                "part": float(ligne["PART_DU_GENRE_PCT"]),
            }
            conforme = observe == attendu
            marque = "PASS" if conforme else "FAIL"
            print(
                f"   [{marque}] {ligne['JEU']:<16} moy.7j {observe['moyenne_7j']:>7} "
                f"rang {observe['rang']} part {observe['part']:>5} %"
            )
            if not conforme:
                ecarts.append(f"{ligne['JEU']} : attendu {attendu}, observe {observe}")

        if len(lignes) != len(ATTENDU_CLASSEMENT):
            ecarts.append(
                f"{len(lignes)} ligne(s) de classement, {len(ATTENDU_CLASSEMENT)} attendues"
            )
        if ecarts:
            raise SystemExit("Calcul distribue non conforme : " + " ; ".join(ecarts))
        print(f"   -> {len(lignes)} lignes conformes aux valeurs calculees a la main")
    finally:
        session.close()


def eprouver_contraintes(base: str) -> None:
    """Verifie que Snowflake applique toujours ce qu'il applique, et pas plus.

    Test de non-regression sur une hypothese d'architecture. Les insertions qui
    doivent reussir laissent volontairement des donnees invalides derriere
    elles : c'est ce que l'etape suivante doit rattraper.
    """
    conn = connexion()
    ecarts = []
    try:
        for libelle, instruction, doit_echouer in COMPORTEMENT_ATTENDU:
            try:
                with conn.cursor() as cur:
                    cur.execute(instruction)
                a_echoue, detail = False, "acceptee"
            except Exception as exc:
                a_echoue = True
                detail = str(exc).splitlines()[0][:60]

            conforme = a_echoue is doit_echouer
            marque = "PASS" if conforme else "FAIL"
            verdict = "rejetee par le moteur" if a_echoue else "acceptee par le moteur"
            print(f"   [{marque}] {libelle:<42} {verdict}")
            if not conforme:
                ecarts.append(
                    f"{libelle} : attendu "
                    f"{'un rejet' if doit_echouer else 'une acceptation'}, obtenu {detail}"
                )
    finally:
        conn.close()

    if ecarts:
        raise SystemExit(
            "Le comportement des contraintes Snowflake a change : "
            + " ; ".join(ecarts)
            + "\nLe choix de reporter l'integrite sur des tests applicatifs "
            "doit etre reexamine."
        )
    appliquees = sum(1 for _, _, e in COMPORTEMENT_ATTENDU if e)
    print(
        f"   -> {appliquees} contrainte(s) appliquee(s) par le moteur, "
        f"{len(COMPORTEMENT_ATTENDU) - appliquees} laissee(s) a la charge de l'applicatif"
    )


def _cible_dbt() -> str:
    """Deduit la cible dbt du mode d'authentification, plutot que la demander.

    dbt-snowflake refuse private_key et private_key_path renseignes ensemble,
    et un env_var() vide compte comme renseigne : les deux modes doivent donc
    vivre dans deux cibles distinctes de dbt/profiles.yml. Laisser l'appelant
    choisir aurait suffi a ce qu'un jour la CI vise la cible locale et echoue
    sur un fichier de cle absent, avec un message parlant de PEM.
    """
    return "local" if os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH") else "ci"


def _executable_dbt() -> list[str]:
    """Localise dbt, installe selon le contexte comme binaire ou comme module.

    Sur le runner, pip depose l'executable sur le PATH. Dans l'image
    d'outillage aussi, mais l'appel par module reste un repli utile si le
    PATH d'un futur environnement est plus avare.
    """
    binaire = shutil.which("dbt")
    return [binaire] if binaire else [sys.executable, "-m", "dbt.cli.main"]


def _lancer_dbt(commande: str, base: str, *arguments: str) -> subprocess.CompletedProcess:
    environnement = dict(
        os.environ,
        SNOWFLAKE_DATABASE=base,
        SNOWFLAKE_SCHEMA="mart",
        DBT_TARGET=_cible_dbt(),
    )
    return subprocess.run(
        [
            *_executable_dbt(),
            commande,
            "--project-dir",
            str(DOSSIER_DBT),
            "--profiles-dir",
            str(DOSSIER_DBT),
            *arguments,
        ],
        env=environnement,
        cwd=str(RACINE),
        capture_output=True,
        text=True,
    )


def _resultats_dbt() -> dict[str, str]:
    """Lit le verdict de chaque test dans run_results.json.

    Le fichier plutot que la sortie console : celle-ci est faite pour etre lue
    par un humain, tronque les noms longs par des points de suite et change de
    forme d'une version a l'autre. En tirer un jeu d'assertions serait le
    genre de test qui casse pour une raison sans rapport avec ce qu'il verifie.
    """
    chemin = DOSSIER_DBT / "target" / "run_results.json"
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    # unique_id a la forme test.<paquet>.<nom>.<empreinte>
    return {r["unique_id"].split(".")[2]: r["status"] for r in donnees["results"]}


def construire_modeles_dbt(base: str) -> None:
    """Installe les paquets dbt puis materialise la vue de tableau de bord.

    Le run vise la base jetable, donc la vue y est creee de zero : c'est aussi
    la seule facon d'eprouver que le modele est bien portable, la version SQL
    d'origine nommant gamelens.mart. en dur.
    """
    for commande, arguments in (("deps", ()), ("run", ())):
        resultat = _lancer_dbt(commande, base, *arguments)
        if resultat.returncode != 0:
            print(resultat.stdout[-2000:])
            print(resultat.stderr[-800:])
            raise SystemExit(f"dbt {commande} a echoue : recette interrompue.")

    etats = _resultats_dbt()
    for nom, etat in etats.items():
        print(f"   [{'PASS' if etat == 'success' else 'FAIL'}] modele {nom:<32} {etat}")
    print(f"   -> {len(etats)} modele(s) materialise(s) sur {base}")
    verifier_vue_dbt(base)


def verifier_vue_dbt(base: str) -> None:
    """Verifie ce que le remplacement d'une vue detruit en silence sur Snowflake.

    Deux proprietes que CREATE OR REPLACE VIEW emporte avec lui, et dont
    l'absence ne provoque aucune erreur :

    Les droits. Un dbt run sans la configuration grants retirerait au tableau
    de bord l'acces qu'il avait. Rien ne le signalerait : la vue existe, elle
    est correcte, elle est simplement devenue invisible pour le seul role qui
    la consultait. Le symptome arriverait plus tard, sous la forme d'un
    panneau Grafana vide.

    Le commentaire. outils/generer_dictionnaire.py le lit dans le catalogue
    pour produire docs/annexes/, et la CI compare le resultat au depot. Une
    vue recreee sans son commentaire ferait echouer la chaine sur un message
    parlant du dictionnaire, jamais de dbt.

    Les deux etaient des risques identifies avant d'ecrire le modele. Les
    verifier ici les transforme en proprietes tenues.
    """
    conn = connexion()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW GRANTS ON VIEW mart.v_popularity_dashboard")
            beneficiaires = {ligne[5].upper() for ligne in cur.fetchall()}

            cur.execute(
                "SELECT comment FROM information_schema.views "
                "WHERE table_schema = 'MART' AND table_name = 'V_POPULARITY_DASHBOARD'"
            )
            ligne = cur.fetchone()
            commentaire = ligne[0] if ligne else None
    finally:
        conn.close()

    attendu = "GAMELENS_DASHBOARD_VIEWER"
    if attendu not in beneficiaires:
        raise SystemExit(
            f"La vue reconstruite par dbt n'accorde plus rien a {attendu}. "
            f"Beneficiaires trouves : {', '.join(sorted(beneficiaires)) or 'aucun'}. "
            "Verifier la configuration grants du modele."
        )
    print(f"   [PASS] droits preserves          SELECT accorde a {attendu.lower()}")

    if not commentaire:
        raise SystemExit(
            "La vue reconstruite par dbt a perdu son COMMENT. Le dictionnaire "
            "genere divergerait du catalogue et la CI echouerait ailleurs, sur "
            "un message sans rapport. Verifier persist_docs et la description "
            "portee par dbt/models/gold/_models.yml."
        )
    print(f"   [PASS] commentaire preserve      {commentaire[:52]}...")


def contrats_dbt(base: str, attendu_au_vert: bool) -> set[str]:
    """Execute les tests dbt et confronte les ECHECS NOMMES a un attendu.

    Appele deux fois, comme controles_integrite, et pour la meme raison : une
    suite de tests qui n'a jamais echoue ne prouve rien sur les fois ou elle
    reussit. La difference est dans l'exigence. Au second appel, on ne se
    contente pas d'un code de sortie non nul : on verifie que ce sont
    exactement les cinq tests attendus qui tombent, ceux qui correspondent aux
    quatre violations que le moteur a laisse entrer a l'etape precedente. Un
    filet qui se declenche pour la mauvaise raison n'est pas un filet.
    """
    resultat = _lancer_dbt("test", base)
    etats = _resultats_dbt()
    echecs = {nom for nom, etat in etats.items() if etat != "pass"}

    au_vert = resultat.returncode == 0
    if au_vert is not attendu_au_vert:
        print(resultat.stdout[-2500:])
        raise SystemExit(
            f"Contrats dbt {'au vert' if au_vert else 'en echec'} alors qu'ils "
            f"etaient attendus {'au vert' if attendu_au_vert else 'en echec'}."
        )

    if attendu_au_vert:
        print(f"   -> {len(etats)} contrats dbt, 0 violation : conforme")
        return echecs

    for nom in sorted(echecs):
        print(f"   [PASS] violation rattrapee par {nom[:70]}")

    if echecs != ATTENDU_ECHECS_DBT:
        manquants = ATTENDU_ECHECS_DBT - echecs
        surnumeraires = echecs - ATTENDU_ECHECS_DBT
        detail = []
        if manquants:
            detail.append("violations NON detectees : " + ", ".join(sorted(manquants)))
        if surnumeraires:
            detail.append("echecs inattendus : " + ", ".join(sorted(surnumeraires)))
        raise SystemExit(
            "Les contrats dbt ne tombent pas sur les violations attendues. " + " ; ".join(detail)
        )

    print(f"   -> {len(echecs)} contrats en echec, exactement ceux attendus : conforme")
    return echecs


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Recette de la couche Gold Snowflake")
    parseur.add_argument(
        "--conserver",
        action="store_true",
        help="ne pas supprimer la base jetable, pour inspecter un echec",
    )
    parseur.add_argument(
        "--supprimer-seulement",
        action="store_true",
        help=(
            "supprimer la base jetable et sortir, sans rien eprouver. "
            "Filet de securite de la CI : un run interrompu par une annulation "
            "ou un delai depasse ne passe pas par le bloc finally et laisserait "
            "une base orpheline consommer du stockage sur le compte."
        ),
    )
    args = parseur.parse_args(argv)

    base = nom_base()
    garde_fou(base)

    if args.supprimer_seulement:
        supprimer_base(base)
        return 0
    # Toutes les etapes suivantes, sous-processus compris, visent cette base.
    os.environ["SNOWFLAKE_DATABASE"] = base
    os.environ["SNOWFLAKE_SCHEMA"] = "mart"

    print("Recette de la couche Gold sur Snowflake")
    print(f"  base jetable   : {base}")
    print(f"  authentification : {mode_authentification()}")
    depart = time.time()

    try:
        titre(1, "Creation de l'infrastructure jetable")
        creer_base(base)

        titre(2, "Application du schema Gold livre")
        appliquer_schema(base)

        titre(3, "Chargement du jeu de donnees de recette")
        charger_jeu_de_recette(base)

        titre(4, "Controles d'integrite sur donnees saines, attendus au vert")
        controles_integrite(base, attendu_au_vert=True)

        titre(5, "Materialisation des modeles dbt")
        construire_modeles_dbt(base)

        titre(6, "Contrats dbt sur donnees saines, attendus au vert")
        contrats_dbt(base, attendu_au_vert=True)

        titre(7, "Calcul distribue Snowpark, confronte aux valeurs attendues")
        calcul_distribue(base)

        titre(8, "Mise a l'epreuve des contraintes du moteur")
        eprouver_contraintes(base)

        titre(9, "Controles d'integrite apres violations, attendus EN ECHEC")
        controles_integrite(base, attendu_au_vert=False)

        titre(10, "Contrats dbt apres violations, attendus EN ECHEC")
        contrats_dbt(base, attendu_au_vert=False)
        # Les deux filets viennent d'etre eprouves sur EXACTEMENT le meme jeu
        # de donnees fautif, l'un apres l'autre. C'est la seule facon de garder
        # les deux sans que leur coexistence devienne un pari : le jour ou l'un
        # rattrape une violation que l'autre laisse passer, la recette s'arrete
        # ici plutot que de laisser la divergence s'installer en silence.
        print("\n   Concordance : le filet applicatif et les contrats dbt ont")
        print("   tous deux rattrape les violations laissees par le moteur.")

        print(f"\nRecette Snowflake au vert en {time.time() - depart:.0f} s.")
        return 0
    finally:
        if args.conserver:
            print(f"\nBase {base} conservee sur demande. Penser a la supprimer.")
        else:
            print()
            supprimer_base(base)


if __name__ == "__main__":
    sys.exit(main())
