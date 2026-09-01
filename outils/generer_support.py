"""Generation du support de soutenance : docs/support_soutenance.md vers .pptx.

Le document Markdown est la SOURCE, le PPTX en est une sortie. Une retouche
faite dans PowerPoint est perdue a la regeneration suivante : corriger le .md.

Ce sens unique est voulu. Le support cite des chiffres qui bougent, 55 cas de
recette, 29 contrats, des credits mesures, des volumes ; un deck ecrit a la main
les fige au moment ou on l'ecrit. Ici, une correction dans le .md se propage.

    python outils/generer_support.py

Trois comportements a connaitre :

- `visuel: capture:<id>` pose l'image `docs/captures/<id>.png` si elle existe, et
  sinon un cadre marque decrivant la capture attendue. Deposer l'image et
  relancer suffit a la placer.
- `visuel: direct:<id>` marque une demonstration en direct, et le generateur
  AJOUTE derriere une diapositive de repli portant la preuve textuelle deja
  capturee. Le PPTX compte donc trois diapositives de plus que le .md.
- `densite: sobre` ou `dense` change la taille du texte et le nombre de puces
  attendu, selon que la diapositive se commente ou se relit.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "docs" / "support_soutenance.md"
SORTIE = RACINE / "docs" / "support_soutenance.pptx"
CAPTURES = RACINE / "docs" / "captures"
PREUVES = RACINE / "docs" / "preuves"

LARGEUR = Inches(13.333)
HAUTEUR = Inches(7.5)
MARGE = Inches(0.62)

ENCRE = RGBColor(0x1C, 0x25, 0x30)
ENCRE_PALE = RGBColor(0x5B, 0x68, 0x75)
ACCENT = RGBColor(0x7C, 0x5C, 0xFF)
ELIMINATOIRE = RGBColor(0xB0, 0x3A, 0x2B)
FILET = RGBColor(0x94, 0xA3, 0xB8)
FOND_CADRE = RGBColor(0xF1, 0xF4, 0xF8)
FOND_DIRECT = RGBColor(0xEC, 0xE6, 0xFF)
BLANC = RGBColor(0xFF, 0xFF, 0xFF)

ELIMINATOIRES = {"C4.2.1", "C4.2.2", "C4.2.3"}

REPLIS = {
    "cloisonnement_roles": ("c11_cloisonnement_roles.txt",
                            "Repli : le cloisonnement des roles, capture du 01/09"),
    "airflow": ("c14_airflow_dags.txt",
                "Repli : les 4 DAG et leurs runs, capture du 01/09"),
    "grafana": ("c19_supervision_indicateurs.txt",
                "Repli : les indicateurs lus en SQL, capture du 01/09"),
}


def analyser(texte: str) -> list[dict]:
    """Decoupe le Markdown en diapositives. Le format est decrit dans l'en-tete."""
    diapos: list[dict] = []
    motif = re.compile(
        r"^## (D\d+)\. ([^\n]+)$\n\n((?:    \w+: [^\n]*\n)+)(.*?)(?=^## D\d+\.|^# |\Z)",
        re.M | re.S,
    )
    for ident, titre, bloc, corps in motif.findall(texte):
        champs = dict(l.strip().split(": ", 1) for l in bloc.strip().splitlines())
        puces = re.search(r"### Puces\n(.*?)(?=\n### |\Z)", corps, re.S)
        notes = re.search(r"### Notes\n(.*?)(?=\n### |\Z)", corps, re.S)
        diapos.append({
            "ident": ident,
            "titre": titre.strip(),
            "minute": champs.get("minute", ""),
            "duree": champs.get("duree", ""),
            "competence": champs.get("competence", "-"),
            "criteres": champs.get("criteres", "-"),
            "densite": champs.get("densite", "sobre"),
            "visuel": champs.get("visuel", "-"),
            "puces": [
                re.sub(r"\*\*(.+?)\*\*", r"\1", l.strip()[2:]).strip()
                for l in (puces.group(1).splitlines() if puces else [])
                if l.strip().startswith("- ")
            ],
            "notes": (notes.group(1).strip() if notes else ""),
        })
    return diapos


def _zone(diapo_pptx, gauche, haut, largeur, hauteur):
    zone = diapo_pptx.shapes.add_textbox(gauche, haut, largeur, hauteur)
    cadre = zone.text_frame
    cadre.word_wrap = True
    cadre.margin_left = cadre.margin_right = 0
    cadre.margin_top = cadre.margin_bottom = 0
    return cadre


def _ecrire(cadre, contenu, taille, couleur=ENCRE, gras=False, espace_avant=0,
            aligne=PP_ALIGN.LEFT, premier=False, police=None):
    p = cadre.paragraphs[0] if premier else cadre.add_paragraph()
    p.alignment = aligne
    p.space_before = Pt(espace_avant)
    r = p.add_run()
    r.text = contenu
    r.font.size = Pt(taille)
    r.font.bold = gras
    r.font.color.rgb = couleur
    r.font.name = police or "Segoe UI"
    return p


def entete(diapo_pptx, diapo):
    """Titre, et pastille de competence a droite."""
    cadre = _zone(diapo_pptx, MARGE, Inches(0.42), Inches(9.5), Inches(1.0))
    _ecrire(cadre, diapo["titre"], 27, ENCRE, gras=True, premier=True)

    competence = diapo["competence"]
    if competence and competence != "-":
        eliminatoire = competence in ELIMINATOIRES
        largeur = Inches(2.35)
        pastille = diapo_pptx.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            LARGEUR - MARGE - largeur, Inches(0.45), largeur, Inches(0.46),
        )
        pastille.fill.solid()
        pastille.fill.fore_color.rgb = ELIMINATOIRE if eliminatoire else ENCRE_PALE
        pastille.line.fill.background()
        pastille.shadow.inherit = False
        tf = pastille.text_frame
        tf.margin_left = tf.margin_right = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        libelle = competence + ("  eliminatoire" if eliminatoire else "")
        _ecrire(tf, libelle, 12, BLANC, gras=True, aligne=PP_ALIGN.CENTER, premier=True)

    trait = diapo_pptx.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, MARGE, Inches(1.42), LARGEUR - 2 * MARGE, Emu(9525)
    )
    trait.fill.solid()
    trait.fill.fore_color.rgb = FILET
    trait.line.fill.background()
    trait.shadow.inherit = False


def pied(diapo_pptx, diapo, numero, total):
    gauche = _zone(diapo_pptx, MARGE, HAUTEUR - Inches(0.62), Inches(8.0), Inches(0.35))
    morceaux = [f"{diapo['ident']}", diapo["minute"]]
    if diapo["criteres"] and diapo["criteres"] != "-":
        morceaux.append(f"criteres {diapo['criteres']}")
    _ecrire(gauche, "     ".join(morceaux), 10, ENCRE_PALE, premier=True)

    droite = _zone(diapo_pptx, LARGEUR - MARGE - Inches(2.0),
                   HAUTEUR - Inches(0.62), Inches(2.0), Inches(0.35))
    _ecrire(droite, f"{numero} / {total}", 10, ENCRE_PALE,
            aligne=PP_ALIGN.RIGHT, premier=True)


def cadre_reserve(diapo_pptx, gauche, haut, largeur, hauteur, titre, detail,
                  couleur_fond=FOND_CADRE, couleur_bord=FILET):
    forme = diapo_pptx.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, gauche, haut, largeur, hauteur
    )
    forme.fill.solid()
    forme.fill.fore_color.rgb = couleur_fond
    forme.line.color.rgb = couleur_bord
    forme.line.width = Pt(1.25)
    forme.shadow.inherit = False
    tf = forme.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.3)
    _ecrire(tf, titre, 15, ACCENT, gras=True, aligne=PP_ALIGN.CENTER, premier=True)
    for ligne in detail:
        _ecrire(tf, ligne, 12, ENCRE_PALE, aligne=PP_ALIGN.CENTER, espace_avant=5)


def poser_visuel(diapo_pptx, diapo, gauche, haut, largeur, hauteur) -> None:
    visuel = diapo["visuel"]

    if visuel.startswith("capture:"):
        identifiant = visuel.split(":", 1)[1]
        fichier = CAPTURES / f"{identifiant}.png"
        if fichier.exists():
            _image_ajustee(diapo_pptx, fichier, gauche, haut, largeur, hauteur)
        else:
            cadre_reserve(
                diapo_pptx, gauche, haut, largeur, hauteur,
                "Capture attendue",
                [f"docs/captures/{identifiant}.png",
                 "Deposer l'image et relancer le generateur"],
            )
        return

    if visuel.startswith("direct:"):
        identifiant = visuel.split(":", 1)[1]
        cadre_reserve(
            diapo_pptx, gauche, haut, largeur, hauteur,
            "DEMONSTRATION EN DIRECT",
            [identifiant.replace("_", " "),
             "Repli capture a la diapositive suivante",
             "Si pas de reponse en 10 secondes, passer au repli"],
            couleur_fond=FOND_DIRECT, couleur_bord=ACCENT,
        )
        return

    chemin = RACINE / "docs" / visuel
    if chemin.exists():
        _image_ajustee(diapo_pptx, chemin, gauche, haut, largeur, hauteur)


def _image_ajustee(diapo_pptx, fichier, gauche, haut, largeur, hauteur):
    """Insere l'image en preservant ses proportions, centree dans la zone."""
    from PIL import Image

    with Image.open(fichier) as im:
        rapport = im.width / im.height
    if largeur / hauteur > rapport:
        h = hauteur
        w = int(hauteur * rapport)
    else:
        w = largeur
        h = int(largeur / rapport)
    diapo_pptx.shapes.add_picture(
        str(fichier), gauche + (largeur - w) // 2, haut + (hauteur - h) // 2,
        width=w, height=h,
    )


def taille_ajustee(puces, largeur_pouces, hauteur_pouces, depart, interligne):
    """Reduit la police jusqu'a ce que les puces tiennent dans la zone.

    Estimation volontairement prudente : on compte une largeur moyenne de 0,5 em
    par caractere, ce qui surestime pour du texte francais courant. Mieux vaut
    une diapositive un peu aeree qu'une diapositive tronquee en projection.
    """
    taille = depart
    while taille > 10:
        par_ligne = max(12, int(largeur_pouces * 72 / (taille * 0.5)))
        lignes = sum(max(1, -(-len(puce) // par_ligne)) for puce in puces)
        hauteur = (lignes * taille * 1.3 + (len(puces) - 1) * interligne) / 72
        if hauteur <= hauteur_pouces:
            return taille
        taille -= 0.5
    return taille


def construire_diapo(presentation, diapo, numero, total):
    d = presentation.slides.add_slide(presentation.slide_layouts[6])
    entete(d, diapo)

    haut = Inches(1.75)
    hauteur = HAUTEUR - haut - Inches(0.85)
    a_un_visuel = diapo["visuel"] != "-"

    if a_un_visuel and diapo["puces"]:
        largeur_texte = Inches(5.55)
        largeur_visuel = LARGEUR - 2 * MARGE - largeur_texte - Inches(0.4)
        poser_visuel(d, diapo, MARGE + largeur_texte + Inches(0.4), haut,
                     largeur_visuel, hauteur)
    elif a_un_visuel:
        largeur_texte = None
        poser_visuel(d, diapo, MARGE, haut, LARGEUR - 2 * MARGE, hauteur)
    else:
        largeur_texte = LARGEUR - 2 * MARGE

    if diapo["puces"]:
        depart = 19 if diapo["densite"] == "sobre" else 14.5
        interligne = 14 if diapo["densite"] == "sobre" else 9
        taille = taille_ajustee(
            diapo["puces"], largeur_texte / 914400, hauteur / 914400,
            depart, interligne,
        )
        cadre = _zone(d, MARGE, haut, largeur_texte, hauteur)
        for i, puce in enumerate(diapo["puces"]):
            p = _ecrire(cadre, puce, taille, ENCRE,
                        espace_avant=0 if not i else interligne, premier=(i == 0))
            p.level = 0
            pastille = p._p.get_or_add_pPr()
            pastille.set("marL", str(Emu(Inches(0.26))))
            pastille.set("indent", str(-Emu(Inches(0.26))))

    if diapo["notes"]:
        d.notes_slide.notes_text_frame.text = diapo["notes"]

    pied(d, diapo, numero, total)
    return d


def construire_repli(presentation, diapo, numero, total):
    """Diapositive de secours placee derriere chaque demonstration en direct."""
    identifiant = diapo["visuel"].split(":", 1)[1]
    fichier, titre = REPLIS[identifiant]
    chemin = PREUVES / fichier

    faux_diapo = dict(diapo)
    faux_diapo["titre"] = titre
    faux_diapo["ident"] = diapo["ident"] + "r"
    faux_diapo["puces"] = []

    d = presentation.slides.add_slide(presentation.slide_layouts[6])
    entete(d, faux_diapo)

    haut = Inches(1.75)
    hauteur = HAUTEUR - haut - Inches(0.85)
    capture = CAPTURES / f"{identifiant}.png"
    if capture.exists():
        _image_ajustee(d, capture, MARGE, haut, LARGEUR - 2 * MARGE, hauteur)
    elif chemin.exists():
        lignes = [
            l for l in chemin.read_text(encoding="utf-8").splitlines()
            if not l.startswith("#")
        ]
        extrait = [l for l in lignes if l.strip()][:16]
        cadre = _zone(d, MARGE, haut, LARGEUR - 2 * MARGE, hauteur)
        for i, ligne in enumerate(extrait):
            _ecrire(cadre, ligne[:118], 11, ENCRE, premier=(i == 0),
                    police="Consolas")
        d.notes_slide.notes_text_frame.text = (
            f"Repli de {diapo['ident']}. Source : docs/preuves/{fichier}.\n"
            "Ne pas commenter la panne : enchainer comme si c'etait prevu."
        )
    else:
        cadre_reserve(d, MARGE, haut, LARGEUR - 2 * MARGE, hauteur,
                      "Preuve absente",
                      [f"Attendue : docs/preuves/{fichier}",
                       "Lancer : python outils/capturer_preuves.py --sans-reseau"])

    pied(d, faux_diapo, numero, total)


def main(argv: list[str] | None = None) -> int:
    if not SOURCE.exists():
        print(f"{SOURCE.relative_to(RACINE)} est absent.")
        return 1

    diapos = analyser(SOURCE.read_text(encoding="utf-8"))
    if not diapos:
        print("Aucune diapositive reconnue : le format du Markdown a-t-il change ?")
        return 1

    total = len(diapos) + sum(1 for d in diapos if d["visuel"].startswith("direct:"))

    presentation = Presentation()
    presentation.slide_width = LARGEUR
    presentation.slide_height = HAUTEUR

    numero = 0
    requises: list[str] = []
    souhaitables: list[str] = []
    for diapo in diapos:
        numero += 1
        construire_diapo(presentation, diapo, numero, total)
        if diapo["visuel"].startswith("capture:"):
            identifiant = diapo["visuel"].split(":", 1)[1]
            if not (CAPTURES / f"{identifiant}.png").exists():
                requises.append(identifiant)
        if diapo["visuel"].startswith("direct:"):
            identifiant = diapo["visuel"].split(":", 1)[1]
            if not (CAPTURES / f"{identifiant}.png").exists():
                souhaitables.append(identifiant)
            numero += 1
            construire_repli(presentation, diapo, numero, total)

    presentation.save(SORTIE)

    duree = sum(
        int(d["duree"].split(":")[0]) * 60 + int(d["duree"].split(":")[1])
        for d in diapos
    )
    print(f"Ecrit : {SORTIE.relative_to(RACINE)}")
    print(f"  {len(diapos)} diapositives du Markdown, {total} dans le PPTX "
          f"(replis des demonstrations compris)")
    print(f"  duree annoncee : {duree // 60}:{duree % 60:02d} sur 30:00")
    if requises:
        print(f"  CADRES VIDES, capture requise dans docs/captures/ : "
              f"{', '.join(sorted(set(requises)))}")
    if souhaitables:
        print(f"  replis assures par le texte, une capture les rendrait "
              f"plus lisibles : {', '.join(sorted(set(souhaitables)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
