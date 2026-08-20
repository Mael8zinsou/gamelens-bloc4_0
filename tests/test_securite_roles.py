"""Tests de securite : cloisonnement effectif des roles applicatifs.

Ces tests repondent a une lacune identifiee au cahier de recettes (TSEC-01) :
les droits etaient accordes et verifies, mais aucun **refus** n'avait ete teste.
Un droit accorde se verifie en l'exercant ; un droit refuse ne se constate qu'en
tentant l'operation interdite et en obtenant l'erreur attendue.

Le referentiel mentionne explicitement des tests de securite parmi les tests a
executer (C4.4.1).

Contrairement aux autres tests du dossier, ceux-ci ont besoin d'une base
accessible. Ils sont donc ignores automatiquement quand elle ne l'est pas :
l'etage `tests` de la CI les saute, l'etage `integration` les execute.

Propriete PostgreSQL demontree ici : les droits d'une vue sont evalues avec ceux
de son PROPRIETAIRE et non de l'appelant. C'est ce qui permet a
dashboard_viewer de lire mart.v_popularity_dashboard sans posseder le moindre
droit sur les tables sous-jacentes, et c'est ce qui rend le cloisonnement reel
plutot que declaratif.
"""

from __future__ import annotations

import os

import psycopg2
import pytest
from psycopg2 import errors

AUTORISE = "autorise"
REFUSE = "refuse"

MOTS_DE_PASSE = {
    "etl_service": "devlocal_etl",
    "analyst": "devlocal_analyst",
    "dashboard_viewer": "devlocal_dashboard",
}

LIRE_VUE_GOLD = "SELECT 1 FROM mart.v_popularity_dashboard LIMIT 1"
LIRE_FAITS_GOLD = "SELECT 1 FROM mart.fact_popularity_history LIMIT 1"
LIRE_DIM_GOLD = "SELECT 1 FROM mart.dim_games LIMIT 1"
LIRE_EVENEMENTS = "SELECT 1 FROM speed.player_count_events LIMIT 1"
LIRE_AGREGAT = "SELECT 1 FROM speed.v_daily_player_stats LIMIT 1"
ECRIRE_JOURNAL = (
    "INSERT INTO speed.pipeline_runs (component, status) VALUES ('test_securite', 'started')"
)
SUPPRIMER_EVENEMENTS = "DELETE FROM speed.player_count_events WHERE steam_appid = -1"

# Matrice de droits attendue, declinaison du modele de securite du Bloc 1.
CAS = [
    # dashboard_viewer ne voit que des agregats, jamais une table de faits.
    ("dashboard_viewer", "lire la vue de restitution Gold", LIRE_VUE_GOLD, AUTORISE),
    ("dashboard_viewer", "lire l agregat journalier Silver", LIRE_AGREGAT, AUTORISE),
    ("dashboard_viewer", "lire la table de faits Gold", LIRE_FAITS_GOLD, REFUSE),
    ("dashboard_viewer", "lire la dimension Gold", LIRE_DIM_GOLD, REFUSE),
    ("dashboard_viewer", "lire les evenements bruts Silver", LIRE_EVENEMENTS, REFUSE),
    ("dashboard_viewer", "ecrire dans le journal d execution", ECRIRE_JOURNAL, REFUSE),
    # analyst lit largement, mais n'ecrit rien.
    ("analyst", "lire la table de faits Gold", LIRE_FAITS_GOLD, AUTORISE),
    ("analyst", "lire les evenements bruts Silver", LIRE_EVENEMENTS, AUTORISE),
    ("analyst", "ecrire dans le journal d execution", ECRIRE_JOURNAL, REFUSE),
    ("analyst", "supprimer des evenements", SUPPRIMER_EVENEMENTS, REFUSE),
    # etl_service ecrit, mais ne supprime jamais.
    ("etl_service", "lire la table de faits Gold", LIRE_FAITS_GOLD, AUTORISE),
    ("etl_service", "ecrire dans le journal d execution", ECRIRE_JOURNAL, AUTORISE),
    ("etl_service", "supprimer des evenements", SUPPRIMER_EVENEMENTS, REFUSE),
]


def connexion(role: str):
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5433")),
        dbname=os.getenv("POSTGRES_DB", "gamelens"),
        user=role,
        password=MOTS_DE_PASSE[role],
        connect_timeout=5,
    )


@pytest.fixture(scope="module", autouse=True)
def base_disponible():
    """Ignore tout le module si la base n'est pas joignable."""
    try:
        connexion("analyst").close()
    except psycopg2.Error as exc:
        pytest.skip(f"base indisponible, tests de securite ignores : {type(exc).__name__}")


@pytest.mark.parametrize(
    "role,operation,requete,attendu",
    CAS,
    ids=[f"{r}-{o.replace(' ', '_')}-{a}" for r, o, _, a in CAS],
)
def test_cloisonnement_des_roles(role, operation, requete, attendu):
    """Verifie qu'une operation est bien autorisee, ou bien refusee.

    Tout est execute dans une transaction annulee : aucun test n'ecrit
    durablement, y compris ceux dont l'attendu est un succes d'ecriture.
    """
    conn = connexion(role)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(requete)
            except errors.InsufficientPrivilege:
                obtenu = REFUSE
            else:
                obtenu = AUTORISE
        conn.rollback()
    finally:
        conn.close()

    assert (
        obtenu == attendu
    ), f"role {role}, operation « {operation} » : attendu {attendu}, obtenu {obtenu}"
