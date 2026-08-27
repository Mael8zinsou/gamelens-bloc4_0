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
    def __init__(self, charge, statut=200):
        self._charge = charge
        self.status_code = statut

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
    tarif = lire_prix(session, 1145360).tarif
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
    tarif = lire_prix(session, 1313140).tarif
    assert tarif["price_final"] == 9.19
    assert tarif["price_initial"] == 22.99
    assert tarif["discount_percent"] == 60
    # Le drapeau de promotion cote Gold derive de ce champ.
    assert tarif["discount_percent"] > 0


def test_jeu_sans_tarif_expose_est_archive_avec_son_motif():
    """Jeu gratuit ou retire de la vente : absence de tarif, pas une erreur.

    Le releve doit neanmoins porter la reponse recue et la raison du rejet :
    c'est ce que la couche Bronze conserve, la ou seule une ligne de journal
    subsistait auparavant.
    """
    session = SessionSimulee({"570": {"success": True, "data": {}}})
    releve = lire_prix(session, 570)
    assert releve.tarif is None
    assert releve.motif_rejet == "aucun price_overview expose"
    assert releve.charge == {"570": {"success": True, "data": {}}}
    assert releve.statut_http == 200


def test_reponse_en_echec_est_archivee_avec_son_motif():
    """Steam repond 200 avec success=false pour un appid inconnu."""
    session = SessionSimulee({"999999999": {"success": False}})
    releve = lire_prix(session, 999999999)
    assert releve.tarif is None
    assert releve.motif_rejet == "success=false cote Steam"
    # La reponse est conservee telle quelle, y compris quand elle ne sert a rien
    # aujourd'hui : c'est tout l'objet de la couche Bronze.
    assert releve.charge == {"999999999": {"success": False}}


def test_tarif_exploitable_porte_la_reponse_complete():
    """Un appel abouti archive aussi sa reponse, pas seulement le derive."""
    charge = {
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
    releve = lire_prix(SessionSimulee(charge), 1145360)
    assert releve.motif_rejet is None
    assert releve.charge == charge


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
    tarif = lire_prix(session, 413150).tarif
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
    assert lire_prix(session, 1).tarif["price_final"] == attendu
