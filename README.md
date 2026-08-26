# GameLens, infrastructure data

Plateforme de donnees interne de **Kestrel Interactive**, editeur de jeux video
independant. Elle unifie catalogue, popularite jouee, popularite diffusee et
tarification des titres du portefeuille et d'un panel concurrent suivi.

Ce depot porte le **Bloc 4** de la certification RNCP39586 (Concevoir et operer
une infrastructure data). Les Blocs 1 a 3 ont pose l'architecture, l'analyse et
le pilotage ; ce depot en est la realisation executable.

## Architecture

Medallion croisee avec une architecture Lambda, reprise du Bloc 1.

```
                       Steam Web API (temps reel, sans authentification)
                                    |
                                    v
                        ingestion/steam_producer.py
                                    |
                             Apache Kafka (KRaft)
                        gamelens.steam.player_count
                                    |
                        ingestion/kafka_to_postgres.py
                                    |
                                    v
              PostgreSQL, couche Silver speed (schema speed)
                                    |
                        Airflow, promotion journaliere
                                    |
                                    v
                  Snowflake, couche Gold (schema mart)
                        dim_games, dim_stores,
                  fact_prices, fact_popularity_history
```

## Demarrage

Prerequis : Docker Desktop demarre, Python 3.12.

```powershell
docker compose up -d                 # PostgreSQL + Kafka
Copy-Item .env.example .env          # puis ajuster si besoin
python -m pip install -r requirements.txt

python ingestion/create_topics.py       # declaration explicite des topics
python ingestion/seed_game_mapping.py  # referentiel des titres suivis
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 30 --depuis-le-debut
```

**Point de configuration important.** PostgreSQL est publie sur le port hote
**5433**, pas 5432. Un service PostgreSQL natif occupe frequemment 5432 sur un
poste Windows et Docker publie alors le port sans effet reel ni message
d'erreur. Voir INC-004 dans `docs/journal_incidents.md`.

**Depuis Git Bash**, prefixer les commandes Docker montant un volume par
`MSYS_NO_PATHCONV=1` et utiliser `pwd -W`. Depuis PowerShell, aucune adaptation
n'est necessaire.

## Organisation du depot

| Chemin | Contenu |
|---|---|
| `config/watchlist.json` | Titres suivis, source du referentiel `game_mapping` |
| `docker-compose.yml` | Composants d'infrastructure locaux |
| `ingestion/` | Pipeline temps reel (producer, consumer, referentiel, topics) |
| `sql/schema_silver_speed.sql` | Couche Silver speed, PostgreSQL |
| `sql/schema_gold_snowflake.sql` | Couche Gold, cible Snowflake |
| `sql/schema_gold.sql` | Prototype PostgreSQL du Gold, conserve comme reference |
| `sql/verify_snowflake_constraints.sql` | Verification empirique des contraintes Snowflake |
| `dags/` | DAG Airflow : promotion vers Gold, supervision |
| `entrepot/` | Connexion Snowflake, promotion Snowpark, controles et recette de CI |
| `supervision/` | Moteur d'alertes et verification du tableau de bord |
| `sql/schema_supervision.sql` | Indicateurs de supervision et journal d'alertes |
| `docker/grafana/` | Source de donnees et tableau de bord provisionnes comme code |
| `docs/journal_incidents.md` | Journal d'incidents, format impose par la grille C4.4.2 |
| `docs/cahier_recettes.md` | Cahier de recettes et de tests (C4.4.1) |
| `docs/observations.md` | Observations de session : surprises, fausses pistes, arbitrages |
| `docs/commandes_successives.md` | Trace chronologique des commandes reellement executees |
| `tests/` | Tests automatises, executes par la CI |

## Supervision

Les indicateurs sont definis en SQL dans `sql/schema_supervision.sql` : fraicheur
de la donnee, completude de la collecte, latence du pipeline, fiabilite par
composant, fraicheur de l'entrepot. Grafana les affiche, il ne les calcule pas,
ce qui les garde interrogeables par n'importe quel client meme si l'outil est
arrete.

Le moteur d'alertes (`supervision/regles_alertes.py`) evalue six regles, ouvre
une alerte au plus par regle, et la referme automatiquement quand la condition
disparait. Le DAG `gamelens_supervision` l'execute toutes les 15 minutes et fait
echouer son run en presence d'une alerte critique.

```powershell
docker compose up -d grafana
python supervision/regles_alertes.py           # evaluation ponctuelle
python supervision/verifier_tableau_bord.py    # controle des 7 panneaux
```

Interfaces : Airflow sur http://localhost:8080, Grafana sur http://localhost:3000,
compte `admin` / `admin` pour les deux.

## Integration continue

Depot : `Mael8zinsou/gamelens-bloc4_0` (prive). Le workflow `.github/workflows/ci.yml`
s'execute a chaque push et chaque pull request, en six etages : qualite du code,
tests unitaires, integrite du DAG Airflow, integration sur infrastructure jetable,
recette de l'entrepot Snowflake, puis publication de l'image Airflow sur
`ghcr.io` depuis la branche principale uniquement.

L'etage Snowflake applique le meme principe que l'etage d'integration : une base
est creee pour la duree du run, eprouvee, puis supprimee. Il verifie que le
schema livre s'applique, que le calcul distribue rend les valeurs attendues, que
le moteur applique toujours les memes contraintes et pas d'autres, et que les
controles d'integrite savent echouer quand les donnees sont invalides. La couche
de demonstration n'est jamais visee : `entrepot/recette_ci.py` refuse de demarrer
si elle l'etait.

Trois secrets sont attendus sur le depot : `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`
et `SNOWFLAKE_PRIVATE_KEY`, ce dernier portant le contenu PEM de la clef plutot
qu'un chemin, pour qu'elle ne soit jamais ecrite sur le disque du runner.

    gh secret set SNOWFLAKE_PRIVATE_KEY < secrets/snowflake_key.p8

Image publiee : `ghcr.io/mael8zinsou/gamelens-bloc4_0/airflow`, etiquetee `latest`
et par le SHA du commit.

## Etat d'avancement

Voir le tableau de suivi dans `CLAUDE.md`.
