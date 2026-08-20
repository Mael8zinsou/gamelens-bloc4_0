"""Tests de la lecture des reponses tarifaires Steam.

Aucun appel reseau : les reponses de l'API sont simulees. La CI doit pouvoir
verifier la logique de conversion sans dependre de la disponibilite de Steam,
ni imposer un delai de 1,5 seconde par titre.

Les cas couverts sont ceux reellement rencontres pendant la collecte du
20/08/2026 : un tarif plein, un tarif remise (Cult of the Lamb a -60 %), et
l'absence de tarif, qui n'est pas une erreur.
"""

import pytest
from steam_prices import lire_prix


class ReponseSimulee:
    def __init__(self, charge):
        self._charge = charge

    def raise_for_status(self):
        return None

    def json(self):
        return self._charge


class SessionSimulee:
    def __init__(self, charge):
        self._charge = charge
        self.appels = 0

    def get(self, *_args, **_kwargs):
        self.appels += 1
        return ReponseSimulee(self._charge)


def test_tarif_plein_converti_en_euros():
    session = SessionSimulee(
        {
            "1145360": {
                "success": True,
                "data": {
                    "price_overview": {
                        "currency": "EUR",
                        "initial": 2450,
                        "final": 2450,
                        "discount_percent": 0,
                    }
                },
            }
        }
    )
    tarif = lire_prix(session, 1145360)
    assert tarif["price_final"] == 24.50
    assert tarif["price_initial"] == 24.50
    assert tarif["discount_percent"] == 0
    assert tarif["currency"] == "EUR"


def test_tarif_en_promotion():
    session = SessionSimulee(
        {
            "1313140": {
                "success": True,
                "data": {
                    "price_overview": {
                        "currency": "EUR",
                        "initial": 2299,
                        "final": 919,
                        "discount_percent": 60,
                    }
                },
            }
        }
    )
    tarif = lire_prix(session, 1313140)
    assert tarif["price_final"] == 9.19
    assert tarif["price_initial"] == 22.99
    assert tarif["discount_percent"] == 60
    # Le drapeau de promotion cote Gold derive de ce champ.
    assert tarif["discount_percent"] > 0


def test_jeu_sans_tarif_expose_retourne_none():
    """Jeu gratuit ou retire de la vente : absence de tarif, pas une erreur."""
    session = SessionSimulee({"570": {"success": True, "data": {}}})
    assert lire_prix(session, 570) is None


def test_reponse_en_echec_retourne_none():
    """Steam repond 200 avec success=false pour un appid inconnu."""
    session = SessionSimulee({"999999999": {"success": False}})
    assert lire_prix(session, 999999999) is None


def test_prix_initial_absent_retombe_sur_le_prix_final():
    session = SessionSimulee(
        {
            "413150": {
                "success": True,
                "data": {
                    "price_overview": {"currency": "EUR", "final": 1399, "discount_percent": 0}
                },
            }
        }
    )
    tarif = lire_prix(session, 413150)
    assert tarif["price_initial"] == 13.99


@pytest.mark.parametrize("centimes,attendu", [(0, 0.0), (99, 0.99), (100, 1.0), (123456, 1234.56)])
def test_conversion_centimes_vers_euros(centimes, attendu):
    session = SessionSimulee(
        {
            "1": {
                "success": True,
                "data": {
                    "price_overview": {
                        "currency": "EUR",
                        "initial": centimes,
                        "final": centimes,
                        "discount_percent": 0,
                    }
                },
            }
        }
    )
    assert lire_prix(session, 1)["price_final"] == attendu
