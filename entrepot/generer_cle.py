"""Genere une paire de cles RSA pour l'authentification Snowflake.

Snowflake impose l'authentification multifacteur aux utilisateurs humains sur
les comptes recents. Un pipeline ne pouvant pas valider une notification, la
paire de cles est le moyen d'acces programmatique attendu.

Le script produit deux fichiers dans secrets/, repertoire ignore par git :

  - `snowflake_key.p8`      cle privee, a garder sur le poste ;
  - `snowflake_key.pub`     cle publique, a coller dans Snowflake.

Il affiche ensuite la commande SQL exacte a executer dans Snowsight, la cle
publique devant y etre fournie sans ses lignes d'en-tete et sans retours a la
ligne, ce qui est la source d'erreur la plus frequente de cette etape.

Usage :
    python entrepot/generer_cle.py
    python entrepot/generer_cle.py --utilisateur GAMELENS_SERVICE --phrase secret
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

RACINE = Path(__file__).resolve().parent.parent
DOSSIER = RACINE / "secrets"


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description="Generation d'une paire de cles Snowflake")
    parseur.add_argument(
        "--utilisateur",
        default="GAMELENS_SERVICE",
        help="nom de l'utilisateur Snowflake destinataire",
    )
    parseur.add_argument(
        "--phrase", default=None, help="phrase secrete chiffrant la cle privee (optionnelle)"
    )
    parseur.add_argument("--force", action="store_true", help="ecrase une paire existante")
    args = parseur.parse_args(argv)

    DOSSIER.mkdir(exist_ok=True)
    chemin_prive = DOSSIER / "snowflake_key.p8"
    chemin_public = DOSSIER / "snowflake_key.pub"

    if chemin_prive.exists() and not args.force:
        print(f"Une cle existe deja : {chemin_prive}")
        print("Utiliser --force pour la remplacer. Attention, l'ancienne cle publique")
        print("resterait alors associee a l'utilisateur cote Snowflake.")
        return 1

    cle = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    chiffrement = (
        serialization.BestAvailableEncryption(args.phrase.encode())
        if args.phrase
        else serialization.NoEncryption()
    )
    chemin_prive.write_bytes(
        cle.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=chiffrement,
        )
    )
    chemin_public.write_bytes(
        cle.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    # Snowflake attend le corps base64 seul, sans les lignes BEGIN/END et sans
    # retours a la ligne. Le fournir tel quel depuis le fichier PEM est l'erreur
    # classique de cette etape.
    corps = "".join(
        ligne for ligne in chemin_public.read_text().splitlines() if not ligne.startswith("-----")
    )

    print(f"Cle privee  : {chemin_prive}")
    print(f"Cle publique: {chemin_public}\n")
    print("1. Executer ceci dans Snowsight, avec le role ACCOUNTADMIN :\n")
    print(f"   ALTER USER {args.utilisateur} SET RSA_PUBLIC_KEY='{corps}';\n")
    print("2. Ajouter ceci dans .env :\n")
    print("   SNOWFLAKE_PRIVATE_KEY_PATH=secrets/snowflake_key.p8")
    if args.phrase:
        print(f"   SNOWFLAKE_PRIVATE_KEY_PASSPHRASE={args.phrase}")
    print("\n3. Verifier :\n")
    print("   python entrepot/verifier_connexion.py\n")
    print("Controle cote Snowflake apres l'etape 1 :")
    print(f"   DESC USER {args.utilisateur};   -- le champ RSA_PUBLIC_KEY_FP doit etre renseigne")
    return 0


if __name__ == "__main__":
    sys.exit(main())
