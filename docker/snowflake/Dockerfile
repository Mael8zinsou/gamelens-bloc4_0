# ============================================================================
# Outillage Snowflake GameLens : dbt et Snowpark.
# ----------------------------------------------------------------------------
# Image d'outillage, pas de service : elle ne tourne pas en permanence, elle
# s'invoque a la demande.
#
#   docker compose run --rm snowflake-cli dbt --version
#   docker compose run --rm snowflake-cli python entrepot/verifier_connexion.py
#
# L'isolation n'est pas de la precaution : elle repare un conflit reel. Voir
# requirements-snowflake.txt.
# ============================================================================
FROM python:3.12-slim

# git est requis par dbt pour les packages, ca ne coute qu'une poignee de Mo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /projet

COPY requirements-snowflake.txt /tmp/requirements-snowflake.txt
RUN pip install --no-cache-dir -r /tmp/requirements-snowflake.txt

# dbt cherche son profil dans ~/.dbt par defaut ; il est fourni par le depot.
ENV DBT_PROFILES_DIR=/projet/dbt
# Et son projet dans le repertoire courant, qui est /projet et non /projet/dbt.
# Sans cette ligne, tout appel a dbt depuis ce conteneur echoue sur
# "No dbt_project.yml found at expected path /projet/dbt_project.yml".
# Les appels programmes passent en plus --project-dir explicitement : la CI
# installe dbt sur le runner et non dans cette image, elle n'herite donc de
# rien d'ici.
ENV DBT_PROJECT_DIR=/projet/dbt
ENV PYTHONPATH=/projet/entrepot:/projet/ingestion
ENV PYTHONUNBUFFERED=1

CMD ["bash"]
