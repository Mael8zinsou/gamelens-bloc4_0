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
| `dags/` | DAG Airflow |
| `docs/journal_incidents.md` | Journal d'incidents, format impose par la grille C4.4.2 |
| `docs/observations.md` | Observations de session : surprises, fausses pistes, arbitrages |
| `docs/commandes_successives.md` | Trace chronologique des commandes reellement executees |
| `tests/` | Tests automatises, executes par la CI |

## Etat d'avancement

Voir le tableau de suivi dans `CLAUDE.md`.
