"""Schemas et graphiques du support de soutenance.

Un deck de data engineer sans un seul graphique se disqualifie tout seul. Ce
module produit les visuels qui manquaient : l'architecture de bout en bout, la
chaine d'integration continue, la consommation de credits et le cahier de
recettes.

Tout est dessine avec Pillow, comme le schema de donnees, pour que le support
n'ait qu'un seul langage visuel. Les couleurs viennent de la palette validee :
bleu, orange et aqua sont les trois premiers emplacements categoriels, valides
ensemble en mode clair (ecart CVD 9,2 au pire, plancher vision normale 27,6).
L'aqua passe sous 3:1 de contraste sur fond clair, ce qui impose des etiquettes
visibles : chaque bloc en porte une.

    python outils/visuels.py
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "docs" / "annexes"

ECHELLE = 2

# Palette validee, mode clair.
ENCRE = "#0b0b0b"
ENCRE_2 = "#52514e"
SURFACE = "#fcfcfb"
BLEU = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
GRIS = "#b8bcc2"
GRIS_PALE = "#e8eaed"
FILET = "#c9ced5"


def police(taille, gras=False, mono=False):
    from PIL import ImageFont

    candidats = (
        ["C:/Windows/Fonts/consola.ttf"] if mono
        else (["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"] if gras
              else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
    )
    for chemin in candidats:
        if Path(chemin).exists():
            return ImageFont.truetype(chemin, taille)
    return ImageFont.load_default()


class Toile:
    """Petit vocabulaire de dessin partage par tous les visuels."""

    def __init__(self, largeur, hauteur):
        from PIL import Image, ImageDraw

        self.l, self.h = largeur, hauteur
        self.img = Image.new("RGB", (largeur * ECHELLE, hauteur * ECHELLE), SURFACE)
        self.d = ImageDraw.Draw(self.img)

    def texte(self, x, y, contenu, taille=13, couleur=ENCRE, gras=False,
              mono=False, ancre="ls"):
        self.d.text((x * ECHELLE, y * ECHELLE), contenu,
                    font=police(int(taille * ECHELLE), gras, mono),
                    fill=couleur, anchor=ancre)

    def largeur_texte(self, contenu, taille=13, gras=False, mono=False):
        f = police(int(taille * ECHELLE), gras, mono)
        return self.d.textlength(contenu, font=f) / ECHELLE

    def bloc(self, x, y, l, h, fond=None, bord=FILET, rayon=6, epaisseur=1.3):
        self.d.rounded_rectangle(
            [(x * ECHELLE, y * ECHELLE), ((x + l) * ECHELLE, (y + h) * ECHELLE)],
            radius=int(rayon * ECHELLE), fill=fond, outline=bord,
            width=max(1, int(epaisseur * ECHELLE)),
        )

    def ligne(self, points, couleur=FILET, epaisseur=1.6):
        self.d.line([(x * ECHELLE, y * ECHELLE) for x, y in points],
                    fill=couleur, width=max(1, int(epaisseur * ECHELLE)))

    def fleche(self, x1, y1, x2, y2, couleur=GRIS, epaisseur=1.6):
        """Trait horizontal termine par une pointe."""
        self.ligne([(x1, y1), (x2, y2)], couleur, epaisseur)
        for dy in (-4, 4):
            self.ligne([(x2, y2), (x2 - 6, y2 + dy)], couleur, epaisseur)

    def enregistrer(self, nom):
        chemin = SORTIE / nom
        self.img.save(chemin, "PNG")
        print(f"  {chemin.relative_to(RACINE)}  ({self.l}x{self.h})")
        return chemin


def architecture():
    """Le flux de bout en bout : Medallion croisee Lambda, et qui orchestre quoi."""
    t = Toile(1180, 486)

    t.texte(40, 42, "De la source à l'entrepôt", 20, ENCRE, gras=True)
    t.texte(40, 66, "Architecture Medallion, croisée avec une architecture Lambda",
            12.5, ENCRE_2)

    colonnes = [
        (40, 210, "SOURCES", GRIS),
        (280, 200, "BRONZE", ORANGE),
        (520, 220, "SILVER speed", BLEU),
        (800, 340, "GOLD", AQUA),
    ]
    haut_bandeau = 100
    for x, l, titre, couleur in colonnes:
        t.d.rectangle(
            [(x * ECHELLE, haut_bandeau * ECHELLE),
             ((x + l) * ECHELLE, (haut_bandeau + 4) * ECHELLE)], fill=couleur
        )
        t.texte(x, haut_bandeau + 22, titre, 11.5, couleur, gras=True)

    def boite(x, y, l, h, titre, detail=None, couleur=FILET, fond=None):
        t.bloc(x, y, l, h, fond=fond, bord=couleur)
        t.texte(x + 12, y + 21, titre, 12.5, ENCRE, gras=True)
        if detail:
            t.texte(x + 12, y + 38, detail, 10.5, ENCRE_2)

    boite(40, 140, 210, 52, "Steam fréquentation", "GetNumberOfCurrentPlayers")
    boite(40, 204, 210, 52, "Steam tarifs", "appdetails / price_overview")
    boite(40, 268, 210, 52, "Twitch, RAWG", "OAuth, catalogue")

    boite(280, 140, 200, 74, "bronze.reponses_brutes", couleur=ORANGE)
    t.texte(292, 178, "archive de tout appel,", 10.5, ENCRE_2)
    t.texte(292, 192, "abouti ou non, sans UPDATE", 10.5, ENCRE_2)

    boite(280, 246, 200, 52, "Apache Kafka", "mode KRaft, tampon durable")

    boite(520, 190, 220, 74, "PostgreSQL", "schéma speed", couleur=BLEU)
    t.texte(532, 245, "la donnée récente, nettoyée", 10.5, ENCRE_2)

    boite(800, 140, 340, 62, "Snowflake, couche Gold", "cible de production",
          couleur=AQUA)
    t.texte(812, 187, "dim_games, dim_stores, fact_prices, fact_popularity_history",
            10, ENCRE_2)

    boite(800, 226, 340, 54, "PostgreSQL, couche Gold", "prototype et repli",
          couleur=AQUA)

    t.fleche(250, 166, 274, 166)
    t.fleche(250, 230, 274, 246 + 26)
    t.fleche(480, 177, 514, 205)
    t.fleche(480, 272, 514, 235)
    t.fleche(740, 214, 794, 171)
    t.fleche(740, 234, 794, 253)

    bas = 350
    t.bloc(40, bas, 1100, 108, fond=GRIS_PALE, bord=FILET)
    t.texte(60, bas + 26, "Apache Airflow orchestre les quatre chaînes", 13.5,
            ENCRE, gras=True)
    dags = [
        ("gamelens_ingestion_temps_reel", "toutes les 15 min"),
        ("gamelens_promotion_gold", "02h30 UTC, une journée par run"),
        ("gamelens_promotion_snowflake", "03h00 UTC, MERGE de tout l'historique"),
        ("gamelens_supervision", "toutes les 15 min"),
    ]
    for i, (nom, cadence) in enumerate(dags):
        x = 60 + (i % 2) * 545
        y = bas + 52 + (i // 2) * 30
        t.d.ellipse([((x) * ECHELLE, (y - 8) * ECHELLE),
                     ((x + 7) * ECHELLE, (y - 1) * ECHELLE)], fill=BLEU)
        t.texte(x + 16, y, nom, 11.5, ENCRE, mono=True)
        t.texte(x + 16 + t.largeur_texte(nom, 11.5, mono=True) + 12, y,
                cadence, 10.5, ENCRE_2)

    return t.enregistrer("visuel_architecture.png")


def ci_etages():
    """Les six étages, et ce que chacun detruit derriere lui."""
    t = Toile(1180, 384)

    t.texte(40, 42, "Six étages, à chaque push", 20, ENCRE, gras=True)
    t.texte(40, 66,
            "Les étages 4 et 5 montent une infrastructure neuve, l'éprouvent, "
            "puis la détruisent", 12.5, ENCRE_2)

    etages = [
        ("1", "Qualité", "ruff, format"),
        ("2", "Tests", "pytest"),
        ("3", "Intégrité DAG", "4 DAG chargés"),
        ("4", "Intégration", "socle jetable"),
        ("5", "Recette entrepôt", "base Snowflake jetable"),
        ("6", "Publication", "image sur ghcr.io"),
    ]
    x = 40
    largeur = 168
    ecart = 15
    for i, (numero, titre, detail) in enumerate(etages):
        jetable = numero in ("4", "5")
        couleur = ORANGE if jetable else BLEU
        t.bloc(x, 130, largeur, 96, fond=SURFACE, bord=couleur, epaisseur=1.5)
        t.d.rectangle([(x * ECHELLE, 130 * ECHELLE),
                       ((x + largeur) * ECHELLE, 134 * ECHELLE)], fill=couleur)
        t.texte(x + 14, 160, numero, 15, couleur, gras=True)
        t.texte(x + 36, 160, titre, 13, ENCRE, gras=True)
        t.texte(x + 14, 182, detail, 10.5, ENCRE_2)
        if jetable:
            t.texte(x + 14, 204, "créé puis détruit", 10, ORANGE, gras=True)
        if i < len(etages) - 1:
            t.fleche(x + largeur + 3, 178, x + largeur + ecart - 3, 178)
        x += largeur + ecart

    t.bloc(40, 268, 1100, 96, fond=GRIS_PALE, bord=FILET)
    t.texte(60, 296, "Ce que l'étage 5 vérifie sur une base créée pour le run",
            13, ENCRE, gras=True)
    points = [
        "le schéma livré s'applique",
        "le calcul distribué rend les valeurs calculées à la main",
        "le moteur applique toujours les mêmes contraintes, et pas d'autres",
        "les deux filets d'intégrité échouent sur des données fautives",
    ]
    for i, point in enumerate(points):
        x = 60 + (i % 2) * 545
        y = 322 + (i // 2) * 24
        t.d.ellipse([(x * ECHELLE, (y - 8) * ECHELLE),
                     ((x + 7) * ECHELLE, (y - 1) * ECHELLE)], fill=AQUA)
        t.texte(x + 16, y, point, 11, ENCRE_2)

    return t.enregistrer("visuel_ci.png")


def couts():
    """Part-a-tout sur deux parts, avec emphase sur celle qui pose probleme."""
    t = Toile(1180, 420)

    t.texte(40, 44, "Ce que l'entrepôt a réellement coûté", 20, ENCRE, gras=True)
    t.texte(40, 68, "Relevé dans l'historique de facturation Snowflake, "
                    "12 jours au 31/08/2026", 12.5, ENCRE_2)

    # Figure de tete : la mesure, pas une estimation.
    t.texte(40, 168, "2,1566", 62, ENCRE, gras=True)
    largeur_nombre = t.largeur_texte("2,1566", 62, gras=True)
    t.texte(46 + largeur_nombre, 168, "crédits", 20, ENCRE_2)
    t.texte(42, 194, "sur les 400 du compte, en 12 jours", 12.5, ENCRE_2)

    # Barre empilee horizontale, 2 px de fond entre les parts.
    total = 2.1566
    parts = [
        ("gamelens_wh", 1.4663, GRIS, "dimensionné XS, suspension à 60 s"),
        ("COMPUTE_WH", 0.6899, ORANGE, "entrepôt par défaut, jamais configuré"),
    ]
    x0, y0, largeur, hauteur = 430, 150, 710, 54
    x = x0
    for i, (nom, valeur, couleur, _) in enumerate(parts):
        l = largeur * valeur / total
        if i:
            x += 2
            l -= 2
        t.d.rounded_rectangle(
            [(x * ECHELLE, y0 * ECHELLE), ((x + l) * ECHELLE, (y0 + hauteur) * ECHELLE)],
            radius=int(4 * ECHELLE), fill=couleur,
        )
        pourcentage = 100 * valeur / total
        t.texte(x + 14, y0 + 33, f"{pourcentage:.0f} %", 17, SURFACE, gras=True)
        x += l

    # Etiquettes directes : la palette impose du relief, pas une legende seule.
    x = x0
    for i, (nom, valeur, couleur, detail) in enumerate(parts):
        l = largeur * valeur / total
        t.texte(x + (2 if i else 0), y0 - 14, nom, 12.5, couleur, gras=True)
        t.texte(x + (2 if i else 0), y0 + hauteur + 22, f"{valeur:.4f} crédit".replace(".", ","),
                11.5, ENCRE)
        t.texte(x + (2 if i else 0), y0 + hauteur + 40, detail, 10.5, ENCRE_2)
        x += l

    t.ligne([(40, 300), (1140, 300)], FILET, 1)
    t.texte(40, 330,
            "Au rythme mesuré, 0,18 crédit par jour, les 108 jours restants "
            "coûtent une vingtaine de crédits sur 400.", 13, ENCRE)
    t.texte(40, 356,
            "Ce n'est donc pas le budget qui contraint le projet, c'est la date "
            "d'expiration du compte.", 13, ENCRE, gras=True)

    return t.enregistrer("visuel_couts.png")


def recettes():
    """Magnitude comparee sur huit categories : barres, une seule teinte."""
    t = Toile(1180, 420)

    t.texte(40, 44, "Cahier de recettes", 20, ENCRE, gras=True)
    t.texte(40, 68, "55 cas, aucun partiel, aucun en attente. Les trois familles "
                    "exigées, plus celles du projet", 12.5, ENCRE_2)

    familles = [
        ("Structurels", 19, True),
        ("Supervision", 6, False),
        ("Ingestion orchestrée", 6, False),
        ("Couche Bronze", 6, False),
        ("Contrats dbt", 6, False),
        ("Fonctionnels", 5, True),
        ("Promotion Snowflake", 4, False),
        ("Sécurité", 3, True),
    ]
    maximum = max(v for _, v, _ in familles)
    x0, y0 = 300, 118
    largeur_max = 700
    hauteur = 24
    pas = 32

    for i, (nom, valeur, exigee) in enumerate(familles):
        y = y0 + i * pas
        couleur = BLEU if exigee else GRIS
        l = largeur_max * valeur / maximum
        t.d.rounded_rectangle(
            [(x0 * ECHELLE, y * ECHELLE),
             ((x0 + l) * ECHELLE, (y + hauteur) * ECHELLE)],
            radius=int(4 * ECHELLE), fill=couleur,
        )
        t.texte(x0 - 14, y + 17, nom, 12, ENCRE if exigee else ENCRE_2,
                gras=exigee, ancre="rs")
        t.texte(x0 + l + 12, y + 17, str(valeur), 12.5, ENCRE, gras=True)

    t.texte(x0 - 14, y0 - 16, "familles exigées par la grille en bleu", 10.5,
            BLEU, ancre="rs")

    t.ligne([(40, 384), (1140, 384)], FILET, 1)
    t.texte(40, 404,
            "Format retenu : PASS ou FAIL vérifié sur un résultat attendu, et non "
            "\u00ab la requête s'exécute sans erreur \u00bb.", 12, ENCRE_2)

    return t.enregistrer("visuel_recettes.png")


def investigation():
    """INC-004 : les cinq etapes, et celle qui a tranche.

    Comptes repris du journal d'incidents : deux hypotheses ecartees, une
    confirmee, deux verifications d'isolement. L'etape 4 est mise en avant
    parce que c'est elle qui a identifie le serveur, par la langue de son
    message d'erreur.
    """
    t = Toile(1180, 560)

    t.texte(40, 42, "INC-004 : ce qui a tranché", 20, ENCRE, gras=True)
    t.texte(40, 66,
            "Le message d'erreur désignait l'encodage. La cause était une "
            "collision de ports.", 12.5, ENCRE_2)

    etapes = [
        ("1", "Encodage du code, ou chemin accentué",
         "Scripts en UTF-8, et le même chemin monté sans problème (INC-002)",
         "écartée", GRIS),
        ("2", "Le conteneur n'est pas démarré",
         "docker compose ps : Up, healthcheck pg_isready au vert",
         "écartée", GRIS),
        ("3", "Le port 5432 n'est pas servi par le conteneur",
         "Get-NetTCPConnection : PID 6284, service postgresql-x64-18",
         "confirmée", BLEU),
        ("4", "Qui répond réellement sur ce port ?",
         "Connexion depuis le conteneur : réponse en FRANÇAIS ACCENTUÉ",
         "a tranché", ORANGE),
        ("5", "Isoler les deux serveurs",
         "select version() dans le conteneur : PostgreSQL 16.15 Alpine",
         "confirmé", BLEU),
    ]

    y = 112
    for numero, hypothese, verification, issue, couleur in etapes:
        decisive = issue == "a tranché"
        if decisive:
            t.bloc(34, y - 6, 1112, 52, fond="#fdf1ea", bord=ORANGE, epaisseur=1.5)
        t.d.ellipse([(40 * ECHELLE, (y + 6) * ECHELLE),
                     (64 * ECHELLE, (y + 30) * ECHELLE)], fill=couleur)
        t.texte(52, y + 23, numero, 12.5, SURFACE, gras=True, ancre="ms")
        t.texte(78, y + 16, hypothese, 12.5, ENCRE, gras=decisive)
        t.texte(78, y + 34, verification, 10.5, ENCRE_2)
        t.texte(1136, y + 24, issue.upper(), 11, couleur, gras=True, ancre="rs")
        if not decisive:
            t.ligne([(40, y + 46), (1140, y + 46)], "#e4e7ec", 1)
        y += 58

    bas = 410
    t.bloc(40, bas, 1100, 118, fond=GRIS_PALE, bord=FILET)
    t.texte(60, bas + 26, "Trois scénarios pesés, un retenu", 13.5, ENCRE, gras=True)
    scenarios = [
        ("Arrêter le service natif", "à refaire à chaque redémarrage", False),
        ("Désinstaller PostgreSQL", "destructif et disproportionné", False),
        ("Publier le conteneur sur 5433", "une variable à ajuster", True),
    ]
    x = 60
    for titre, effet, retenu in scenarios:
        couleur = AQUA if retenu else GRIS
        t.bloc(x, bas + 44, 340, 56, fond=SURFACE, bord=couleur,
               epaisseur=1.5 if retenu else 1.1)
        t.texte(x + 14, bas + 66, titre, 12, ENCRE, gras=retenu)
        t.texte(x + 14, bas + 86, effet, 10.5, ENCRE_2)
        if retenu:
            t.texte(x + 326, bas + 66, "RETENU", 9.5, AQUA, gras=True, ancre="rs")
        x += 360

    return t.enregistrer("visuel_investigation.png")


def main() -> int:
    SORTIE.mkdir(parents=True, exist_ok=True)
    print("Visuels du support :")
    architecture()
    ci_etages()
    couts()
    recettes()
    investigation()
    return 0


if __name__ == "__main__":
    sys.exit(main())
