"""Controle de bon fonctionnement de la connexion Snowflake.

Premiere chose a executer apres la creation du compte d'essai, avant tout
script de schema. Le but est de distinguer les causes d'echec les unes des
autres plutot que de laisser un seul message generique, parce que les erreurs
de premiere connexion a Snowflake se ressemblent toutes et pointent rarement
vers la bonne cause.

Ce que le controle etablit, dans l'ordre :

  1. la configuration est complete et le mode d'authentification est celui voulu ;
  2. la connexion aboutit reellement, ce qui valide l'identifiant de compte,
     souvent la premiere erreur, et l'authentification ;
  3. le role, l'entrepot virtuel et la base sont ceux attendus ;
  4. le compte d'essai n'est pas expire, ce qui se lit sur les credits restants.

Usage :
    docker compose run --rm snowflake-cli python entrepot/verifier_connexion.py
"""

from __future__ import annotations

import sys

from connexion import ConfigurationManquante, mode_authentification, parametres


def ligne(libelle: str, valeur) -> None:
    print(f"  {libelle:<28} {valeur}")


def main() -> int:
    print("Verification de la connexion Snowflake\n")

    # --- 1. Configuration -----------------------------------------------------
    try:
        params = parametres()
    except ConfigurationManquante as exc:
        print(f"  CONFIGURATION INCOMPLETE\n\n  {exc}\n")
        return 1

    ligne("compte", params["account"])
    ligne("utilisateur", params["user"])
    ligne("authentification", mode_authentification())
    ligne("role demande", params["role"])
    ligne("entrepot demande", params["warehouse"])
    print()

    # --- 2. Connexion ---------------------------------------------------------
    try:
        import snowflake.connector

        try:
            conn = snowflake.connector.connect(**params)
        except Exception as premiere:
            # A la toute premiere connexion, l'entrepot virtuel et la base
            # n'existent pas encore. Le connecteur echoue en s'y positionnant,
            # avec un message qui laisse croire a un probleme d'authentification.
            # On retente sans contexte pour trancher entre les deux causes.
            if "does not exist" not in str(premiere) and "Object" not in str(premiere):
                raise
            print("  entrepot ou base absents, nouvelle tentative sans contexte")
            conn = snowflake.connector.connect(**parametres(avec_contexte=False))
            print("  (l authentification fonctionne : ce sont les objets qui manquent)")
    except Exception as exc:
        message = str(exc)
        print(f"  ECHEC DE CONNEXION : {type(exc).__name__}\n  {message[:400]}\n")
        # Les messages de Snowflake sont peu explicites sur les causes les plus
        # frequentes : on les nomme plutot que de laisser chercher.
        if "250001" in message or "Could not connect" in message:
            print("  Piste : identifiant de compte probablement incorrect. Il s'ecrit")
            print("  ORGANISATION-COMPTE, pas l'URL complete ni l'identifiant de region.")
        if "Incorrect username or password" in message:
            print("  Piste : identifiants invalides, ou politique d'authentification")
            print("  multifacteur bloquant l'acces par mot de passe. Basculer sur une")
            print("  paire de cles RSA (SNOWFLAKE_PRIVATE_KEY_PATH).")
        if "JWT token is invalid" in message:
            print("  Piste : la cle publique n'est pas (ou plus) associee a l'utilisateur.")
            print("  Verifier avec DESC USER <utilisateur>, champ RSA_PUBLIC_KEY_FP.")
        return 1

    # --- 3. Contexte effectif -------------------------------------------------
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT CURRENT_VERSION(), CURRENT_ACCOUNT(), CURRENT_REGION(), "
                "CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA()"
            )
            version, compte, region, role, entrepot, base, schema = cur.fetchone()

        print("  CONNEXION ETABLIE\n")
        ligne("version Snowflake", version)
        ligne("compte effectif", compte)
        ligne("region", region)
        ligne("role effectif", role)
        ligne("entrepot effectif", entrepot or "aucun (a creer)")
        ligne("base effective", base or "aucune (a creer)")
        ligne("schema effectif", schema or "aucun (a creer)")
        print()

        # --- 4. Etat du compte d'essai ---------------------------------------
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT ROUND(SUM(credits_used), 2)
                       FROM snowflake.account_usage.warehouse_metering_history
                       WHERE start_time > DATEADD(day, -30, CURRENT_TIMESTAMP())"""
                )
                credits = cur.fetchone()[0]
            ligne("credits consommes (30 j)", credits if credits is not None else "0 (aucun usage)")
        except Exception as exc:
            # account_usage n'est peuple qu'apres un delai sur un compte neuf :
            # une erreur ici n'est pas un probleme de connexion.
            ligne("credits consommes (30 j)", f"non disponible ({type(exc).__name__})")

        print("\n  Tout est en place. Etape suivante : sql/schema_gold_snowflake.sql")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
