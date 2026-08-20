# ============================================================================
# Image Airflow GameLens
# ----------------------------------------------------------------------------
# L'image officielle apache/airflow n'embarque qu'un jeu restreint de
# providers. Le provider PostgreSQL, necessaire pour que les taches passent par
# une Connection Airflow plutot que par une chaine de connexion codee en dur,
# n'en fait pas partie : il est ajoute ici.
#
# Etendre l'image plutot que d'utiliser _PIP_ADDITIONAL_REQUIREMENTS est le
# choix recommande par la documentation Airflow hors prototypage rapide : les
# dependances sont figees dans une image versionnee et reconstruite par la CI,
# au lieu d'etre reinstallees a chaque demarrage de conteneur.
# ============================================================================
FROM apache/airflow:3.1.8

# Le fichier de contraintes officiel evite qu'un provider ne tire une version
# de dependance incompatible avec le coeur d'Airflow.
ARG AIRFLOW_VERSION=3.1.8
ARG PYTHON_VERSION=3.12
ARG CONSTRAINTS="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

USER airflow

RUN pip install --no-cache-dir --constraint "${CONSTRAINTS}" \
        apache-airflow-providers-postgres \
        requests
