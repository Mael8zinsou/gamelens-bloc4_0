"""Rendu du schema de donnees en image, SVG et PNG.

Un bloc Mermaid n'est pas un schema : c'est la source d'un schema, et elle ne se
compile ni sur la plateforme de depot, ni dans un PPTX, ni sur le papier. Ce
module dessine donc directement, a partir du meme modele que le reste du
generateur : pas de dependance a un moteur de rendu externe, et un resultat
identique sur n'importe quel poste.

Deux sorties depuis une seule passe de geometrie : le SVG, qui est la source
vectorielle, et le PNG, que python-pptx sait inserer sans discuter.

Parti pris de lecture : les relations sont dessinees en TIRETS, parce que
Snowflake les declare sans les appliquer. Le trait dit la meme chose que la
section 4 du document, et un jury le voit avant de le lire.
"""

from __future__ import annotations

from pathlib import Path

# Geometrie, en pixels du SVG. Le PNG est rendu au double pour rester net.
LIGNE_H = 23
ENTETE_H = 34
COL_LARGE = 340
MARGE = 40
ECHELLE_PNG = 2

# Palette sobre, lisible en projection comme a l'impression.
ENCRE = "#1c2530"
ENCRE_PALE = "#5b6875"
TRAIT = "#94a3b8"
FOND = "#ffffff"
DIM_ENTETE = "#dbe4ef"
DIM_BORD = "#8ba3c0"
FAIT_ENTETE = "#e6ded2"
FAIT_BORD = "#bda98c"
MARQUEUR = "#7c5cff"


class Boite:
    """Une table dessinee : son cadre, son entete et ses lignes de colonnes."""

    def __init__(self, nom, colonnes, marques, x, y):
        self.nom = nom
        self.colonnes = colonnes
        self.marques = marques
        self.x = x
        self.y = y
        self.largeur = COL_LARGE
        self.hauteur = ENTETE_H + LIGNE_H * len(colonnes)
        self.est_fait = nom.startswith("fact_")

    def ancre_ligne(self, colonne: str) -> tuple[int, int]:
        """Le point d'attache d'une arete, au milieu de la ligne visee."""
        for i, (col, _t, _n) in enumerate(self.colonnes):
            if col == colonne:
                return (self.x, self.y + ENTETE_H + LIGNE_H * i + LIGNE_H // 2)
        return (self.x, self.y + self.hauteur // 2)

    def marqueur(self, colonne: str) -> str:
        portees = self.marques.get((self.nom, colonne), set())
        for candidat in ("PK", "FK", "UK"):
            if candidat in portees:
                return candidat
        return ""


def disposer(colonnes_par_table, marques, aretes):
    """Place les tables en etoile : dimensions a gauche, faits a droite.

    Une seule arete diagonale au lieu de trois croisements, ce qui reste lisible
    une fois projete au fond d'une salle.
    """
    dims = sorted(t for t in colonnes_par_table if t.startswith("dim_"))
    faits = sorted(t for t in colonnes_par_table if t.startswith("fact_"))

    colonne_gauche = MARGE
    colonne_droite = MARGE + COL_LARGE + 260

    boites: dict[str, Boite] = {}
    y = MARGE + 30
    for nom in dims:
        boites[nom] = Boite(nom, colonnes_par_table[nom], marques, colonne_gauche, y)
        y += boites[nom].hauteur + 55

    y = MARGE + 30
    for nom in faits:
        boites[nom] = Boite(nom, colonnes_par_table[nom], marques, colonne_droite, y)
        y += boites[nom].hauteur + 55

    largeur = colonne_droite + COL_LARGE + MARGE
    hauteur = max(b.y + b.hauteur for b in boites.values()) + MARGE + 78
    return boites, aretes, largeur, hauteur


def _chemin(boites, arete):
    """Trace orthogonal entre la colonne source et la colonne cible."""
    src, col_src, cible, col_cible = arete
    b_src, b_cible = boites[src], boites[cible]
    # La source est un fait (a droite), la cible une dimension (a gauche).
    x1, y1 = b_cible.x + b_cible.largeur, b_cible.ancre_ligne(col_cible)[1]
    x2, y2 = b_src.x, b_src.ancre_ligne(col_src)[1]
    milieu = (x1 + x2) // 2
    return [(x1, y1), (milieu, y1), (milieu, y2), (x2, y2)]


def rendre_svg(boites, aretes, largeur, hauteur, titre) -> str:
    p: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" '
        f'height="{hauteur}" viewBox="0 0 {largeur} {hauteur}" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        f'<rect width="{largeur}" height="{hauteur}" fill="{FOND}"/>',
        f'<text x="{MARGE}" y="30" font-size="17" font-weight="600" '
        f'fill="{ENCRE}">{titre}</text>',
    ]

    for arete in aretes:
        points = _chemin(boites, arete)
        trace = " ".join(f"{x},{y}" for x, y in points)
        p.append(
            f'<polyline points="{trace}" fill="none" stroke="{TRAIT}" '
            f'stroke-width="1.6" stroke-dasharray="6 4"/>'
        )
        # Patte d'oie du cote du fait : cardinalite plusieurs.
        xf, yf = points[-1]
        p.append(
            f'<path d="M{xf},{yf} l-11,-6 M{xf},{yf} l-11,0 M{xf},{yf} l-11,6" '
            f'stroke="{TRAIT}" stroke-width="1.6" fill="none"/>'
        )
        xd, yd = points[0]
        p.append(
            f'<circle cx="{xd + 6}" cy="{yd}" r="3.4" fill="none" '
            f'stroke="{TRAIT}" stroke-width="1.6"/>'
        )

    for boite in boites.values():
        fond_entete = FAIT_ENTETE if boite.est_fait else DIM_ENTETE
        bord = FAIT_BORD if boite.est_fait else DIM_BORD
        p.append(
            f'<rect x="{boite.x}" y="{boite.y}" width="{boite.largeur}" '
            f'height="{boite.hauteur}" rx="7" fill="{FOND}" stroke="{bord}" '
            f'stroke-width="1.4"/>'
        )
        p.append(
            f'<path d="M{boite.x},{boite.y + ENTETE_H} v-{ENTETE_H - 7} '
            f'a7,7 0 0 1 7,-7 h{boite.largeur - 14} a7,7 0 0 1 7,7 '
            f'v{ENTETE_H - 7} z" fill="{fond_entete}" stroke="{bord}" '
            f'stroke-width="1.4"/>'
        )
        p.append(
            f'<text x="{boite.x + 13}" y="{boite.y + 23}" font-size="14.5" '
            f'font-weight="600" fill="{ENCRE}">{boite.nom}</text>'
        )
        etiquette = "faits" if boite.est_fait else "dimension"
        p.append(
            f'<text x="{boite.x + boite.largeur - 13}" y="{boite.y + 23}" '
            f'font-size="11" text-anchor="end" fill="{ENCRE_PALE}">{etiquette}</text>'
        )

        for i, (col, type_sql, nullable) in enumerate(boite.colonnes):
            y = boite.y + ENTETE_H + LIGNE_H * i + 16
            if i:
                p.append(
                    f'<line x1="{boite.x + 1}" y1="{y - 16}" '
                    f'x2="{boite.x + boite.largeur - 1}" y2="{y - 16}" '
                    f'stroke="{TRAIT}" stroke-width="0.5" opacity="0.45"/>'
                )
            marque = boite.marqueur(col)
            if marque:
                p.append(
                    f'<text x="{boite.x + 13}" y="{y}" font-size="9.5" '
                    f'font-weight="700" fill="{MARQUEUR}">{marque}</text>'
                )
            p.append(
                f'<text x="{boite.x + 42}" y="{y}" font-size="12.5" '
                f'fill="{ENCRE}" font-family="Consolas, monospace">{col}</text>'
            )
            p.append(
                f'<text x="{boite.x + boite.largeur - 13}" y="{y}" font-size="11" '
                f'text-anchor="end" fill="{ENCRE_PALE}">{type_sql}</text>'
            )

    legende = hauteur - 46
    p.append(
        f'<line x1="{MARGE}" y1="{legende - 16}" x2="{largeur - MARGE}" '
        f'y2="{legende - 16}" stroke="{TRAIT}" stroke-width="0.8"/>'
    )
    p.append(
        f'<text x="{MARGE}" y="{legende + 2}" font-size="11.5" fill="{ENCRE_PALE}">'
        f'PK clef primaire, FK clef etrangere, UK unicite. '
        f'Traits en tirets : relations DECLAREES, que Snowflake n applique pas a '
        f'l ecriture.</text>'
    )
    p.append(
        f'<text x="{MARGE}" y="{legende + 20}" font-size="11.5" fill="{ENCRE_PALE}">'
        f'L integrite est portee hors du moteur, par les contrats dbt et les '
        f'controles de entrepot/verifier_gold.py, rejoues a chaque push.</text>'
    )
    p.append("</svg>")
    return "\n".join(p)


def _police(taille, gras=False, mono=False):
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


def rendre_png(boites, aretes, largeur, hauteur, titre, destination: Path) -> None:
    from PIL import Image, ImageDraw

    e = ECHELLE_PNG
    image = Image.new("RGB", (largeur * e, hauteur * e), FOND)
    d = ImageDraw.Draw(image)

    def texte(x, y, contenu, taille, couleur=ENCRE, gras=False, mono=False, ancre="ls"):
        d.text((x * e, y * e), contenu, font=_police(int(taille * e), gras, mono),
               fill=couleur, anchor=ancre)

    texte(MARGE, 30, titre, 17, ENCRE, gras=True)

    for arete in aretes:
        points = _chemin(boites, arete)
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            # Tirets manuels : Pillow ne sait pas pointiller une ligne.
            longueur = max(abs(x2 - x1), abs(y2 - y1))
            if not longueur:
                continue
            pas = 10
            for debut in range(0, longueur, pas):
                fin = min(debut + 6, longueur)
                fx = 1 if x2 > x1 else (-1 if x2 < x1 else 0)
                fy = 1 if y2 > y1 else (-1 if y2 < y1 else 0)
                d.line(
                    [((x1 + fx * debut) * e, (y1 + fy * debut) * e),
                     ((x1 + fx * fin) * e, (y1 + fy * fin) * e)],
                    fill=TRAIT, width=max(1, int(1.6 * e)),
                )
        xf, yf = points[-1]
        for dy in (-6, 0, 6):
            d.line([(xf * e, yf * e), ((xf - 11) * e, (yf + dy) * e)],
                   fill=TRAIT, width=max(1, int(1.6 * e)))
        xd, yd = points[0]
        r = 3.4
        d.ellipse([((xd + 6 - r) * e, (yd - r) * e), ((xd + 6 + r) * e, (yd + r) * e)],
                  outline=TRAIT, width=max(1, int(1.6 * e)))

    for boite in boites.values():
        fond_entete = FAIT_ENTETE if boite.est_fait else DIM_ENTETE
        bord = FAIT_BORD if boite.est_fait else DIM_BORD
        d.rounded_rectangle(
            [(boite.x * e, boite.y * e),
             ((boite.x + boite.largeur) * e, (boite.y + boite.hauteur) * e)],
            radius=7 * e, fill=FOND, outline=bord, width=max(1, int(1.4 * e)),
        )
        d.rounded_rectangle(
            [(boite.x * e, boite.y * e),
             ((boite.x + boite.largeur) * e, (boite.y + ENTETE_H) * e)],
            radius=7 * e, fill=fond_entete, outline=bord, width=max(1, int(1.4 * e)),
        )
        d.rectangle(
            [(boite.x * e, (boite.y + ENTETE_H - 8) * e),
             ((boite.x + boite.largeur) * e, (boite.y + ENTETE_H) * e)],
            fill=fond_entete,
        )
        d.line([(boite.x * e, (boite.y + ENTETE_H) * e),
                ((boite.x + boite.largeur) * e, (boite.y + ENTETE_H) * e)],
               fill=bord, width=max(1, int(1.4 * e)))
        texte(boite.x + 13, boite.y + 23, boite.nom, 14.5, ENCRE, gras=True)
        etiquette = "faits" if boite.est_fait else "dimension"
        texte(boite.x + boite.largeur - 13, boite.y + 23, etiquette, 11,
              ENCRE_PALE, ancre="rs")

        for i, (col, type_sql, _n) in enumerate(boite.colonnes):
            y = boite.y + ENTETE_H + LIGNE_H * i + 16
            if i:
                d.line([((boite.x + 1) * e, (y - 16) * e),
                        ((boite.x + boite.largeur - 1) * e, (y - 16) * e)],
                       fill="#dfe5ec", width=1)
            marque = boite.marqueur(col)
            if marque:
                texte(boite.x + 13, y, marque, 9.5, MARQUEUR, gras=True)
            texte(boite.x + 42, y, col, 12.5, ENCRE, mono=True)
            texte(boite.x + boite.largeur - 13, y, type_sql, 11, ENCRE_PALE, ancre="rs")

    legende = hauteur - 46
    d.line([(MARGE * e, (legende - 16) * e), ((largeur - MARGE) * e, (legende - 16) * e)],
           fill=TRAIT, width=1)
    texte(MARGE, legende + 2,
          "PK clef primaire, FK clef etrangere, UK unicite. Traits en tirets : "
          "relations DECLAREES, que Snowflake n applique pas a l ecriture.",
          11.5, ENCRE_PALE)
    texte(MARGE, legende + 20,
          "L integrite est portee hors du moteur, par les contrats dbt et les "
          "controles de entrepot/verifier_gold.py, rejoues a chaque push.",
          11.5, ENCRE_PALE)

    image.save(destination, "PNG")
