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


def _charger_cle_privee(donnees: bytes, phrase: str | None):
    """Convertit une cle privee RSA au format DER attendu par le connecteur.

    La cle arrive soit d'un fichier (usage local), soit directement du contenu
    PEM (usage en integration continue). Le second cas evite d'ecrire la cle
    sur le disque du runner : elle ne vit que dans la memoire du processus,
    le temps de la connexion.
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization

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


def parametres(avec_contexte: bool = True) -> dict:
    """Assemble les parametres de connexion depuis l'environnement.

    `avec_contexte=False` omet l'entrepot virtuel, la base et le schema. C'est
    necessaire a la toute premiere connexion : ces objets n'existent pas encore,
    et le connecteur echoue en tentant de s'y positionner. L'erreur obtenue
    parle alors d'objet inexistant, ce qui laisse croire a un probleme
    d'authentification alors que celle-ci a parfaitement fonctionne.
    """
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
        "client_session_keep_alive": False,
        "application": "GameLens_RNCP39586",
    }
    if avec_contexte:
        params["warehouse"] = os.getenv("SNOWFLAKE_WAREHOUSE", "gamelens_wh")
        params["database"] = os.getenv("SNOWFLAKE_DATABASE", "gamelens")
        params["schema"] = os.getenv("SNOWFLAKE_SCHEMA", "mart")

    chemin_cle = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    contenu_cle = os.getenv("SNOWFLAKE_PRIVATE_KEY")
    mot_de_passe = os.getenv("SNOWFLAKE_PASSWORD")
    phrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None

    if chemin_cle:
        params["private_key"] = _charger_cle_privee(Path(chemin_cle).read_bytes(), phrase)
    elif contenu_cle:
        # Voie de l'integration continue : le secret du dispositif de CI est une
        # chaine, pas un fichier. Les gestionnaires de secrets restituent parfois
        # les sauts de ligne echappes, ce qui casse le decodage PEM avec un
        # message trompeur sur le format de la cle ; on les retablit.
        params["private_key"] = _charger_cle_privee(
            contenu_cle.replace("\\n", "\n").encode(), phrase
        )
    elif mot_de_passe:
        params["password"] = mot_de_passe
    else:
        raise ConfigurationManquante(
            "Aucun moyen d'authentification : definir SNOWFLAKE_PRIVATE_KEY_PATH "
            "(local, recommande), SNOWFLAKE_PRIVATE_KEY (contenu PEM, integration "
            "continue) ou SNOWFLAKE_PASSWORD."
        )

    return params


def mode_authentification() -> str:
    if os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH"):
        return "paire de cles RSA (fichier)"
    if os.getenv("SNOWFLAKE_PRIVATE_KEY"):
        return "paire de cles RSA (contenu en environnement)"
    return "mot de passe"


def connexion(avec_contexte: bool = True):
    """Ouvre une connexion via le connecteur Python."""
    import snowflake.connector

    return snowflake.connector.connect(**parametres(avec_contexte))


def session_snowpark():
    """Ouvre une session Snowpark, utilisee pour le calcul distribue (C4.2.2)."""
    from snowflake.snowpark import Session

    config = {k: v for k, v in parametres().items() if k not in ("application",)}
    return Session.builder.configs(config).create()
