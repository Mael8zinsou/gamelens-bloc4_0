"""Connexion a Snowflake, frontiere de configuration de la couche Gold.

Ce module est la seule chose a changer pour basculer la couche Gold de
PostgreSQL vers Snowflake. C'est la contrainte de conception posee dans
CLAUDE.md pendant que le compte d'essai n'existait pas : tout ce qui vise
l'entrepot devait l'etre derriere une frontiere de configuration, de sorte que
le basculement soit un changement de connexion et non une reecriture.

Deux modes d'authentification, dans cet ordre de preference.

**Paire de cles RSA (recommande).** Snowflake impose desormais l'authentification
multifacteur aux utilisateurs humains sur les comptes recents, ce qui rend
l'authentification par mot de passe inutilisable pour un acces programmatique :
la connexion reste bloquee en attente d'une validation qu'un pipeline ne peut
pas donner. Une paire de cles attachee a un utilisateur de service contourne ce
mur sans l'affaiblir, et c'est de toute facon la pratique attendue en
production.

**Mot de passe.** Conserve pour la mise au point immediate apres creation du
compte, tant qu'aucune politique d'authentification n'est appliquee.
"""

from __future__ import annotations

import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(RACINE / ".env")
except ImportError:  # l'image d'outillage n'embarque pas python-dotenv
    pass


class ConfigurationManquante(RuntimeError):
    """Levee quand la configuration Snowflake est incomplete.

    Message deliberement explicite : cette erreur surviendra typiquement juste
    apres la creation du compte d'essai, au moment ou l'on ne sait pas encore
    quel identifiant Snowflake attend exactement.
    """


def _charger_cle_privee(chemin: str, phrase: str | None):
    """Charge une cle privee RSA au format attendu par le connecteur."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

    donnees = Path(chemin).read_bytes()
    cle = serialization.load_pem_private_key(
        donnees,
        password=phrase.encode() if phrase else None,
        backend=default_backend(),
    )
    return cle.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def parametres() -> dict:
    """Assemble les parametres de connexion depuis l'environnement."""
    compte = os.getenv("SNOWFLAKE_ACCOUNT")
    utilisateur = os.getenv("SNOWFLAKE_USER")
    if not compte or not utilisateur:
        raise ConfigurationManquante(
            "SNOWFLAKE_ACCOUNT et SNOWFLAKE_USER doivent etre definis dans .env. "
            "L'identifiant de compte est de la forme ORGANISATION-COMPTE, "
            "visible dans Snowsight sous Account details."
        )

    params = {
        "account": compte,
        "user": utilisateur,
        "role": os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "gamelens_wh"),
        "database": os.getenv("SNOWFLAKE_DATABASE", "gamelens"),
        "schema": os.getenv("SNOWFLAKE_SCHEMA", "mart"),
        "client_session_keep_alive": False,
        "application": "GameLens_RNCP39586",
    }

    chemin_cle = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    mot_de_passe = os.getenv("SNOWFLAKE_PASSWORD")

    if chemin_cle:
        params["private_key"] = _charger_cle_privee(
            chemin_cle, os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
        )
    elif mot_de_passe:
        params["password"] = mot_de_passe
    else:
        raise ConfigurationManquante(
            "Aucun moyen d'authentification : definir SNOWFLAKE_PRIVATE_KEY_PATH "
            "(recommande) ou SNOWFLAKE_PASSWORD dans .env."
        )

    return params


def mode_authentification() -> str:
    return "paire de cles RSA" if os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH") else "mot de passe"


def connexion():
    """Ouvre une connexion via le connecteur Python."""
    import snowflake.connector

    return snowflake.connector.connect(**parametres())


def session_snowpark():
    """Ouvre une session Snowpark, utilisee pour le calcul distribue (C4.2.2)."""
    from snowflake.snowpark import Session

    config = {k: v for k, v in parametres().items() if k not in ("application",)}
    return Session.builder.configs(config).create()
