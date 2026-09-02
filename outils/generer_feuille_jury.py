"""Feuille A4 remise a chaque membre du jury.

Deux exemplaires imprimes, poses en debut de seance. Elle met les 31
sous-criteres de la grille en regard du numero de diapositive qui les traite,
ce qui rend la notation triviale et signale la rigueur avant la premiere phrase.

Elle existe pour une raison precise : le marquage de conformite a ete retire du
support projete, ou il donnait a voir la mecanique de la notation au lieu du
propos. L'information n'est pas perdue, elle change de support et de
destinataire.

Trois sources, aucune saisie manuelle :

- les libelles des criteres viennent de docs/plan_soutenance.md, tables de
  tracabilite, ou ils sont deja recopies mot pour mot depuis la grille ;
- l'association critere vers diapositive vient des champs `criteres` de
  docs/support_soutenance.md ;
- les numeros de diapositive viennent de docs/annexes/plan_diapos.json, ecrit
  par le generateur du support, pour qu'ils ne puissent pas diverger.

    python outils/generer_feuille_jury.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

RACINE = Path(__file__).resolve().parent.parent
PLAN = RACINE / "docs" / "plan_soutenance.md"
SUPPORT = RACINE / "docs" / "support_soutenance.md"
NUMEROS = RACINE / "docs" / "annexes" / "plan_diapos.json"
SORTIE = RACINE / "docs" / "feuille_jury.pdf"

ENCRE = HexColor("#0b0b0b")
ENCRE_2 = HexColor("#52514e")
BLEU = HexColor("#2a78d6")
ORANGE = HexColor("#eb6834")
FILET = HexColor("#c9ced5")
PANNEAU = HexColor("#f1f2f4")

ELIMINATOIRES = {"C4.2.1", "C4.2.2", "C4.2.3"}

LARGEUR, HAUTEUR = A4
MARGE = 16 * mm


def lire_criteres() -> list[tuple[str, str, int, str]]:
    """(competence, livrable, numero, libelle) pour les 31 sous-criteres."""
    texte = PLAN.read_text(encoding="utf-8")
    sortie: list[tuple[str, str, int, str]] = []
    for entete, corps in re.findall(
        r"^### (C4\.\d\.\d, [^\n]+)$\n(.*?)(?=^### |^## |\Z)", texte, re.M | re.S
    ):
        competence = entete.split(",", 1)[0]
        livrable = entete.split(",", 1)[1].split("(")[0].strip()
        for numero, libelle in re.findall(r"^\| (\d+) \| ([^|]+) \|", corps, re.M):
            propre = libelle.replace("**", "").strip()
            sortie.append((competence, livrable, int(numero), propre))
    return sorted(sortie, key=lambda x: x[2])


def lire_diapos() -> dict[int, list[int]]:
    """critere -> numeros de diapositive, dans l'ordre de passage."""
    texte = SUPPORT.read_text(encoding="utf-8")
    numeros = json.loads(NUMEROS.read_text(encoding="utf-8"))["diapos"]
    par_critere: dict[int, list[int]] = {}
    motif = re.compile(
        r"^## (D\d+)\. [^\n]+$\n\n((?:    \w+: [^\n]*\n)+)", re.M
    )
    for ident, bloc in motif.findall(texte):
        champs = dict(l.strip().split(": ", 1) for l in bloc.strip().splitlines())
        brut = champs.get("criteres", "-")
        if brut == "-":
            continue
        for n in re.findall(r"\d+", brut):
            par_critere.setdefault(int(n), []).append(numeros[ident])
    return par_critere


def rendre() -> None:
    criteres = lire_criteres()
    diapos = lire_diapos()

    c = canvas.Canvas(str(SORTIE), pagesize=A4)
    c.setTitle("GameLens, Bloc 4 : les criteres et leurs diapositives")

    y = HAUTEUR - MARGE

    c.setFillColor(ENCRE)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGE, y - 4, "GameLens, infrastructure data")
    c.setFont("Helvetica", 9.5)
    c.setFillColor(ENCRE_2)
    c.drawRightString(LARGEUR - MARGE, y - 4,
                      "Bloc 4, RNCP39586  ·  soutenance du 11/09/2026")
    y -= 16
    c.setFont("Helvetica", 10)
    c.drawString(MARGE, y - 4,
                 "Où chaque sous-critère de la grille est traité, "
                 "et sur quelle diapositive.")
    y -= 12
    c.setStrokeColor(BLEU)
    c.setLineWidth(1.6)
    c.line(MARGE, y, MARGE + 34, y)
    y -= 16

    competence_courante = None
    for competence, livrable, numero, libelle in criteres:
        if y < MARGE + 40:
            c.showPage()
            y = HAUTEUR - MARGE
            competence_courante = None

        if competence != competence_courante:
            competence_courante = competence
            eliminatoire = competence in ELIMINATOIRES
            y -= 4
            c.setFillColor(PANNEAU)
            c.rect(MARGE, y - 4, LARGEUR - 2 * MARGE, 15, stroke=0, fill=1)
            c.setFillColor(ORANGE if eliminatoire else BLEU)
            c.setFont("Helvetica-Bold", 9.5)
            c.drawString(MARGE + 5, y, competence)
            c.setFillColor(ENCRE)
            c.setFont("Helvetica", 9.5)
            c.drawString(MARGE + 40, y, livrable)
            if eliminatoire:
                c.setFillColor(ORANGE)
                c.setFont("Helvetica-Bold", 8)
                c.drawRightString(LARGEUR - MARGE - 5, y, "ELIMINATOIRE")
            y -= 15

        pages = diapos.get(numero, [])
        etiquette = ", ".join(str(n) for n in sorted(set(pages))) or "-"

        c.setFillColor(ENCRE_2)
        c.setFont("Helvetica", 8)
        c.drawString(MARGE + 5, y, f"{numero:02d}")
        c.setFillColor(ENCRE)
        c.setFont("Helvetica", 9.5)
        texte = libelle if len(libelle) < 104 else libelle[:101] + "..."
        c.drawString(MARGE + 22, y, texte)

        c.setFillColor(BLEU)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawRightString(LARGEUR - MARGE - 5, y, etiquette)

        y -= 4
        c.setStrokeColor(FILET)
        c.setLineWidth(0.3)
        c.line(MARGE + 5, y, LARGEUR - MARGE - 5, y)
        y -= 9

    y -= 6
    c.setFillColor(ENCRE_2)
    c.setFont("Helvetica-Oblique", 8.5)
    for ligne in (
        "Les numéros renvoient au pied de page du support projeté.",
        "Trois diapositives de repli, non numérotées ici, ne s'affichent "
        "qu'en cas de panne d'une démonstration.",
        "Feuille générée depuis le plan de soutenance et le support : elle ne "
        "peut pas diverger de ce qui sera projeté.",
    ):
        c.drawString(MARGE, y, ligne)
        y -= 11

    c.showPage()
    c.save()

    manquants = [n for n, *_ in [(x[2],) for x in criteres] if n not in diapos]
    print(f"Ecrit : {SORTIE.relative_to(RACINE)}")
    print(f"  {len(criteres)} sous-criteres, "
          f"{len(diapos)} associes a au moins une diapositive")
    if manquants:
        print(f"  SANS DIAPOSITIVE : {manquants}")
    print("  imprimer en deux exemplaires, un par membre du jury")


def main(argv: list[str] | None = None) -> int:
    for fichier in (PLAN, SUPPORT, NUMEROS):
        if not fichier.exists():
            print(f"{fichier.relative_to(RACINE)} est absent : lancer d'abord "
                  "outils/generer_support.py.")
            return 1
    rendre()
    return 0


if __name__ == "__main__":
    sys.exit(main())
