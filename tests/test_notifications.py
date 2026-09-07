"""Tests du canal de notification externe.

Aucun de ces tests ne joint le reseau : le transport est remplace par un double
qui enregistre ce qu'on lui donne. Ce qui est verifie ici n'est pas que Telegram
repond, c'est que les deux proprietes de conception tiennent.

1. **Absent n'est pas casse.** Sans configuration, rien ne part et rien
   n'echoue. Un depot fraichement clone et l'etage `tests` de la CI, qui n'ont
   aucun compte de messagerie, doivent passer.
2. **Ce qui part est lisible et ne fuit pas.** Le jeton ne doit apparaitre dans
   aucun journal, et le contenu des alertes est echappe avant d'entrer dans du
   HTML.

Le troisieme point teste ici est le plus facile a casser en refactorisant : une
fermeture ne s'annonce QUE si l'ouverture a ete annoncee. Sans cette condition,
un avertissement jamais annonce produirait un message de fermeture sortant de
nulle part.
"""

from __future__ import annotations

import datetime as dt

import pytest

import notifications


@pytest.fixture
def sans_canal(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


@pytest.fixture
def avec_canal(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:JETON-DE-TEST")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567890")


# ---------------------------------------------------------------------------
# 1. Absent n'est pas casse
# ---------------------------------------------------------------------------


def test_canal_absent_nest_pas_configure(sans_canal):
    assert notifications.configure() is False


def test_canal_absent_nenvoie_rien_et_ne_leve_pas(sans_canal, monkeypatch):
    """Sans configuration, aucun appel reseau ne doit meme etre tente."""

    def interdit(*a, **k):  # pragma: no cover
        raise AssertionError("un appel reseau a ete tente sans configuration")

    monkeypatch.setattr(notifications.requests, "post", interdit)
    assert notifications.envoyer("peu importe") is False


def test_variables_vides_valent_absentes(monkeypatch):
    """Une variable presente mais vide est le cas courant d'un .env recopie."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "   ")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")
    assert notifications.configure() is False


# ---------------------------------------------------------------------------
# 2. Ce qui part est lisible et ne fuit pas
# ---------------------------------------------------------------------------


def test_le_jeton_est_retire_des_journaux():
    brut = "erreur sur https://api.telegram.org/bot123456:SECRET/sendMessage"
    assert "SECRET" not in notifications._sans_jeton(brut, "123456:SECRET")
    assert "[JETON]" in notifications._sans_jeton(brut, "123456:SECRET")


def test_le_contenu_dune_alerte_est_echappe():
    """Un message d'alerte contenant < ou & casserait le rendu HTML de Telegram."""
    msg = notifications.composer_ouverture(
        "regle_<test>",
        "critique",
        "latence > 300 s & montante",
        dt.datetime(2026, 9, 7, 14, 30),
    )
    assert "&lt;test&gt;" in msg
    assert "&amp;" in msg
    assert "<b>" in msg  # le balisage voulu, lui, survit


def test_envoi_reussi_transmet_les_bons_champs(avec_canal, monkeypatch):
    captures = {}

    class Reponse:
        status_code = 200
        text = "ok"

    def faux_post(url, json, timeout):
        captures["url"] = url
        captures["json"] = json
        return Reponse()

    monkeypatch.setattr(notifications.requests, "post", faux_post)
    assert notifications.envoyer("bonjour", discret=True) is True
    assert captures["json"]["chat_id"] == "-1001234567890"
    assert captures["json"]["disable_notification"] is True
    assert captures["json"]["parse_mode"] == "HTML"


def test_un_refus_de_telegram_nest_pas_une_exception(avec_canal, monkeypatch):
    """Le transport rend False. C'est l'appelant qui decide d'en faire un echec."""

    class Reponse:
        status_code = 400
        text = "Bad Request: chat not found"

    monkeypatch.setattr(notifications.requests, "post", lambda *a, **k: Reponse())
    assert notifications.envoyer("bonjour") is False


def test_une_panne_reseau_nest_pas_une_exception(avec_canal, monkeypatch):
    def tombe(*a, **k):
        raise notifications.requests.ConnectionError("injoignable")

    monkeypatch.setattr(notifications.requests, "post", tombe)
    assert notifications.envoyer("bonjour") is False


# ---------------------------------------------------------------------------
# 3. Composition des messages
# ---------------------------------------------------------------------------


def test_duree_courte_en_minutes():
    debut = dt.datetime(2026, 9, 7, 14, 0)
    msg = notifications.composer_fermeture("fraicheur", debut, debut + dt.timedelta(minutes=42))
    assert "42 min" in msg


def test_duree_longue_en_heures():
    debut = dt.datetime(2026, 9, 1, 8, 0)
    msg = notifications.composer_fermeture("fraicheur", debut, debut + dt.timedelta(hours=6, minutes=20))
    assert "6 h 20" in msg


def _etat(**surcharges) -> dict:
    base = {
        "horodatage": dt.datetime(2026, 9, 7, 8, 0),
        "supervision_age_min": 7,
        "supervision_muette": False,
        "indicateurs": [("Fraicheur frequentation", "9.0", "minutes", "nominal")],
        "alertes_ouvertes": [],
        "composants_muets": [],
    }
    base.update(surcharges)
    return base


def test_battement_nominal_dit_quil_ny_a_rien():
    msg = notifications.composer_battement(_etat())
    assert "Aucune alerte ouverte" in msg
    assert "MUETTE" not in msg


def test_battement_denonce_une_supervision_muette():
    """Le coeur de V-07 : le temoin doit nommer l'absence du surveille."""
    msg = notifications.composer_battement(
        _etat(supervision_muette=True, supervision_age_min=310)
    )
    assert "LA SUPERVISION EST MUETTE" in msg
    assert "310" in msg


def test_battement_liste_les_alertes_ouvertes():
    msg = notifications.composer_battement(
        _etat(alertes_ouvertes=[("retard_entrepot_gold", "critique", dt.datetime(2026, 9, 6, 3, 0))])
    )
    assert "1 alerte(s) ouverte(s)" in msg
    assert "retard_entrepot_gold" in msg


def test_battement_signale_les_composants_muets():
    msg = notifications.composer_battement(
        _etat(composants_muets=[("snowpark_promotion", "05/09 03:00")])
    )
    assert "snowpark_promotion" in msg
