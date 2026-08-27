"""Tests de la lecture des reponses de frequentation Steam.

Aucun appel reseau. Ces tests n'existaient pas avant la couche Bronze : la
fonction rendait un `int | None`, et il n'y avait pour ainsi dire rien a
verifier. Depuis, elle rend aussi la reponse telle que recue et la raison d'un
rejet, ce qui est exactement ce que Bronze archive.

Les cas couverts sont ceux que Steam produit reellement : une reponse
exploitable, une reponse HTTP 200 portant `result` different de 1 pour un appid
inconnu, et une reponse annoncant un succes sans le champ attendu.
"""

from steam_producer import interroger_steam


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

    def get(self, *_args, **_kwargs):
        return ReponseSimulee(self._charge)


def test_reponse_exploitable_porte_le_compte_et_la_charge():
    charge = {"response": {"player_count": 18342, "result": 1}}
    releve = interroger_steam(SessionSimulee(charge), 413150)

    assert releve.joueurs == 18342
    assert releve.motif_rejet is None
    assert releve.statut_http == 200
    # La reponse complete est conservee, y compris le champ result dont la
    # valeur exploitee ne depend pas. C'est l'objet de la couche Bronze.
    assert releve.charge == charge


def test_appid_inconnu_est_rejete_avec_son_motif():
    """Steam repond 200 avec result=42 pour un appid qu'il ne connait pas.

    Avant la couche Bronze, ce cas ne produisait qu'un avertissement dans les
    journaux puis disparaissait, alors qu'il signale un jeu retire du catalogue.
    """
    charge = {"response": {"result": 42}}
    releve = interroger_steam(SessionSimulee(charge), 999999999)

    assert releve.joueurs is None
    assert releve.motif_rejet == "result=42"
    assert releve.charge == charge


def test_succes_annonce_sans_le_champ_attendu():
    """result=1 mais pas de player_count : le motif doit distinguer ce cas."""
    releve = interroger_steam(SessionSimulee({"response": {"result": 1}}), 413150)

    assert releve.joueurs is None
    assert releve.motif_rejet == "player_count absent de la reponse"


def test_zero_joueur_reste_une_valeur_exploitable():
    """Piege classique : 0 est faux en Python mais c'est une mesure valide.

    Un jeu sans joueur connecte a cet instant n'est pas une reponse manquante.
    Un test de verite au lieu d'un test de presence aurait perdu la donnee.
    """
    releve = interroger_steam(SessionSimulee({"response": {"player_count": 0, "result": 1}}), 1)

    assert releve.joueurs == 0
    assert releve.motif_rejet is None
