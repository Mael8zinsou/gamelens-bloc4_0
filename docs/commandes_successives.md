# Journal des commandes et requêtes, GameLens Bloc 4

Trace chronologique de ce qui a été réellement exécuté, session par session.
Objectif double : pouvoir rejouer la construction à l'identique, et disposer
d'une matière factuelle pour le cahier de recettes (C4.4.1) et la documentation
technique (C4.3.3).

Conventions de lecture :

- **[PS]** commande PowerShell, **[BASH]** commande Git Bash, **[PY]** script
  Python, **[SQL]** requête exécutée dans PostgreSQL, **[KAFKA]** outil en ligne
  de commande du broker.
- Les commandes marquées **(diagnostic)** ont servi une fois, à comprendre un
  problème. Elles ne font pas partie de la procédure de mise en route.
- Les commandes marquées **(procédure)** font partie de la mise en route
  reproductible et sont reprises dans `README.md`.

---

# Session 1, 19 août 2026

## Phase 0. Reconnaissance du projet et de l'environnement

Aucune modification, uniquement de la lecture. But : savoir ce qui existe avant
de décider quoi construire.

```bash
# [BASH] Contenu réel du dossier de travail
pwd ; ls -la ; find . -type f -not -path "./.git/*"

# [BASH] Périmètre du dépôt git : révèle que la racine est C:/Users/maelz
# (le dossier personnel entier est versionné) et qu'aucun fichier du projet
# n'y est suivi.
git rev-parse --show-toplevel ; git branch --show-current ; git ls-files .

# [BASH] Inventaire de l'outillage disponible
python --version
python -m pip list | grep -iE "snowflake|pandas|airflow|kafka|dbt|requests|duckdb"
docker --version ; docker compose version ; gh --version ; node --version

# [BASH] Test décisif sur Airflow : l'import réussit mais avertit que seul
# POSIX est supporté. Voir OBS-10.
python -c "import airflow; print(airflow.__version__)"

# [BASH] Recherche d'une configuration Snowflake existante : aucune.
ls -la ~/.snowflake/ ; ls -la ~/.snowsql/ ; env | grep -i snow

# [BASH] État des environnements Linux disponibles
wsl.exe -l -v
docker info --format "{{.ServerVersion}} {{.OSType}}"
```

Résultats notables : tout l'outillage est déjà installé, Docker Desktop est
présent mais son moteur est arrêté, WSL2 avec Ubuntu existe, et aucune trace de
configuration Snowflake.

## Phase 1. Lecture du référentiel officiel et des blocs précédents

```bash
# [BASH] Aucune bibliothèque d'extraction PDF n'était présente
python -m pip install pypdf

# [PY] Localisation puis extraction des pages Bloc 4 du référentiel
#      (pages 12 à 14 sur 19)
python -c "import pypdf; ..."   # recherche des pages contenant C4. / A4. / Bloc 4

# [PY] Confirmation des compétences éliminatoires dans le règlement spécial
#      (page 4) : C4.2.1, C4.2.2, C4.2.3
python -c "import pypdf; ..."

# [PY] Lecture de la grille d'évaluation officielle, onglet Bloc 4
python -c "import openpyxl; ..."   # 24 10 10 - Grille évaluation ....xlsx

# [BASH] Recherche de l'incident GOG dans le dossier du Bloc 3, pour vérifier
# la cohérence avec le schéma Gold. Voir OBS-07.
grep -n -iE "GOG|anti-bot|scraping" "Bloc 3/dossier_bloc3_gamelens.md"

# [BASH] Vérification du cadrage du panel de titres au Bloc 1. Voir OBS-08.
grep -n -iE "panel concurrent|portefeuille|appid" "Bloc 1/dossier_bloc1_gamelens.md"
```

## Phase 2. Mise en place du dépôt

```bash
# [BASH] (procédure) Dépôt dédié, distinct de celui du dossier personnel
git init
git config core.autocrlf false     # évite la réécriture des fins de ligne
git config core.quotepath false    # affiche correctement les chemins accentués

# [BASH] (procédure) Arborescence
mkdir -p sql ingestion dags docker/airflow docs tests .github/workflows dbt

# [BASH] Les trois fichiers SQL préexistants étaient à la racine alors que
# CLAUDE.md les référençait sous sql/. Écart corrigé.
mv schema_gold.sql schema_gold_snowflake.sql verify_snowflake_constraints.sql sql/
```

Fichiers créés à cette étape : `.gitignore`, `requirements.txt`,
`requirements-snowflake.txt` (isolé car Snowflake est indisponible),
`.env.example`, `docs/journal_incidents.md`.

## Phase 3. Vérification des hypothèses d'environnement

Deux hypothèses testées avant de construire dessus, plutôt que contournées par
précaution.

```powershell
# [PS] Démarrage du moteur Docker
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# [PS] (diagnostic) Le chemin accentué pose-t-il problème à Docker ?
#      Réponse : non. Le contenu du dépôt est lu depuis le conteneur.
$p = (Get-Location).Path
docker run --rm -v "${p}:/mnt" alpine:3.20 sh -c "ls /mnt; cat /mnt/.gitignore"
```

```bash
# [BASH] (diagnostic) Le même montage depuis Git Bash échoue :
#        ls: C:/Program Files/Git/mnt: No such file or directory
docker run --rm -v "$(pwd):/mnt" alpine:3.20 ls /mnt

# [BASH] (procédure) Forme correcte depuis Git Bash. Cause : la traduction de
#        chemins MSYS2, pas les accents. Voir INC-002 et OBS-02.
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/mnt" alpine:3.20 ls /mnt
```

## Phase 4. Vérification des sources de données

```python
# [PY] (diagnostic) L'endpoint temps réel répond-il, et sans authentification ?
#      Testé sur trois appid : 200, player_count exploitable.
requests.get("https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
             params={"appid": 1145360})

# [PY] (diagnostic) Existe-t-il une source tarifaire hors scraping GOG ?
#      Réponse : oui, price_overview donne currency, initial, final,
#      discount_percent. Résout l'incohérence avec le Bloc 3, voir OBS-07.
requests.get("https://store.steampowered.com/api/appdetails",
             params={"appids": 1145360, "cc": "fr", "filters": "price_overview"})

# [PY] (diagnostic) Vérification des 15 appid de la watchlist un par un contre
#      l'API Steam, plutôt que recopiés de mémoire. 15 sur 15 résolus, un seul
#      écart de libellé, Disco Elysium. Voir OBS-09.
for titre in watchlist: requests.get(".../appdetails", params={"appids": appid,
                                                              "filters": "basic"})
```

Fichier créé à cette étape : `config/watchlist.json`, 15 titres.

## Phase 5. Socle d'infrastructure

Fichiers créés : `sql/schema_silver_speed.sql`, `docker-compose.yml`.

```powershell
# [PS] (procédure) Validation de la syntaxe compose avant tout démarrage
docker compose config --quiet

# [PS] (procédure) Démarrage du socle : PostgreSQL 16 et Apache Kafka 3.9 KRaft
docker compose up -d
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# [PS] (procédure) Vérification que le schéma Silver s'est bien initialisé tout
#      seul depuis le fichier monté dans /docker-entrypoint-initdb.d
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "\dt speed.*"
```

Résultat : 4 tables créées (`game_mapping`, `player_count_events`,
`price_snapshots`, `pipeline_runs`), broker Kafka *healthy*.

## Phase 6. Incident INC-004, investigation de la collision de ports

Séquence complète conservée telle quelle : c'est la matière du C4.4.2.

```bash
# [BASH] Symptôme initial, à la première écriture applicative en base
python ingestion/seed_game_mapping.py
# -> UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 103
```

```powershell
# [PS] (diagnostic) Hypothèse : quelqu'un d'autre tient déjà le port 5432 ?
Get-NetTCPConnection -LocalPort 5432 -State Listen |
    ForEach-Object { Get-Process -Id $_.OwningProcess }
# -> PID 6284, processus postgres

# [PS] (diagnostic) Confirmation par le service Windows
Get-Service -Name "*postgres*"
# -> postgresql-x64-18, Running

# [PS] (diagnostic) Docker croit pourtant avoir publié le port
docker compose ps --format "table {{.Name}}\t{{.Ports}}"
# -> 0.0.0.0:5432->5432/tcp

# [PS] (diagnostic) ÉTAPE DÉCISIVE. Qui répond réellement sur l'hôte ?
docker exec -e PGPASSWORD=devlocal_app gamelens-postgres `
    psql -h host.docker.internal -p 5432 -U gamelens_app -d gamelens -c "select version()"
# -> "authentification par mot de passe échouée", en français accentué.
#    Le conteneur est une Alpine en locale C : il répondrait en anglais ASCII.
#    L'interlocuteur n'est donc pas le conteneur. Voir OBS-03.

# [PS] (diagnostic) Contre-épreuve, version vue depuis l'intérieur du conteneur
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -tAc "select version()"
# -> PostgreSQL 16.15 Alpine, alors que l'hôte expose une version 18
```

Correction appliquée : port hôte basculé de 5432 vers **5433** dans
`docker-compose.yml`, port interne inchangé, `.env` et `.env.example` alignés.

```powershell
# [PS] (procédure) Recréation du conteneur sur le nouveau port
docker compose up -d
```

## Phase 7. Pipeline temps réel, exécution de bout en bout

Fichiers créés : `ingestion/common.py`, `ingestion/seed_game_mapping.py`,
`ingestion/create_topics.py`, `ingestion/steam_producer.py`,
`ingestion/kafka_to_postgres.py`.

```bash
# [BASH] (procédure) Déclaration explicite des topics. Kafka les crée sinon à la
#        volée, en laissant partitionnement et rétention aux valeurs par défaut.
python ingestion/create_topics.py

# [BASH] (procédure) Référentiel de résolution des identifiants
python ingestion/seed_game_mapping.py
# -> 15 titres écrits dans speed.game_mapping

# [BASH] (procédure) Un cycle de collecte : 15 appels Steam, 15 publications Kafka
python ingestion/steam_producer.py --once
# -> 15 titres collectés, de 1 862 joueurs (Disco Elysium) à 86 069 (Stardew Valley)

# [BASH] (procédure) Consommation et écriture en couche Silver speed
python ingestion/kafka_to_postgres.py --timeout 15 --depuis-le-debut
# -> lot final de 15 messages : 15 insérés, 0 doublon absorbé
```

```powershell
# [KAFKA] (diagnostic) Contrôle du topic et relecture des messages bruts
docker exec gamelens-kafka /opt/kafka/bin/kafka-topics.sh `
    --bootstrap-server localhost:9092 --describe --topic gamelens.steam.player_count

docker exec gamelens-kafka /opt/kafka/bin/kafka-console-consumer.sh `
    --bootstrap-server localhost:9092 --topic gamelens.steam.player_count `
    --from-beginning --max-messages 3 --property print.key=true
# -> clé = appid, valeur = JSON horodaté en UTC
```

## Phase 8. Test d'idempotence (recette C4.4.1)

Le test le plus important de la session : il vérifie une garantie revendiquée
plutôt qu'une simple absence d'erreur.

```powershell
# [KAFKA] Provoque le scénario réel d'un redémarrage après incident : le groupe
#         de consommation repart du début et relit des messages déjà traités.
docker exec gamelens-kafka /opt/kafka/bin/kafka-consumer-groups.sh `
    --bootstrap-server localhost:9092 --group gamelens-silver-speed `
    --reset-offsets --to-earliest --topic gamelens.steam.player_count --execute
```

```bash
# [BASH] Relance du consumer sur des messages déjà écrits
python ingestion/kafka_to_postgres.py --timeout 15
# -> lot final de 15 messages : 0 inséré, 15 doublons absorbés
```

```sql
-- [SQL] Résultat attendu : 15, et non 30
SELECT count(*) FROM speed.player_count_events;
-- Observé : 15. Idempotence du puits confirmée.
```

## Phase 9. Contrôles finaux et versionnement

```sql
-- [SQL] Journal d'exécution, socle de la supervision C4.3.1
SELECT component, status, records_in, records_written,
       ended_at - started_at AS duree
FROM speed.pipeline_runs ORDER BY run_id;

-- [SQL] Agrégat journalier, ce qui sera promu vers fact_popularity_history
SELECT unified_name, day, avg_player_count, max_player_count, observation_count
FROM speed.v_daily_player_stats ORDER BY avg_player_count DESC LIMIT 5;
```

```bash
# [BASH] Deux commits : le socle, puis la mise à jour du suivi
git add -A && git commit -m "Socle d'infrastructure et pipeline temps reel ..."
git add -A && git commit -m "Mise a jour du suivi apres session 1"
```

## Récapitulatif des états vérifiés en fin de session 1

| Vérification | Commande | Résultat observé |
|---|---|---|
| Conteneurs démarrés | `docker compose ps` | 2 conteneurs *Up*, Kafka *healthy* |
| Schéma Silver initialisé | `\dt speed.*` | 4 tables |
| Résolution des identifiants | script de vérification Steam | 15 sur 15 |
| Collecte temps réel | `steam_producer.py --once` | 15 événements publiés |
| Écriture Silver speed | `kafka_to_postgres.py` | 15 lignes écrites |
| Idempotence après rejeu | rejeu offsets à zéro | 0 inséré, 15 absorbés, table à 15 |
| Journal de supervision | `SELECT ... FROM speed.pipeline_runs` | 4 exécutions tracées, 0 échec |

## Commandes de mise en route, version courte

Pour rejouer l'ensemble depuis un poste propre, Docker Desktop démarré :

```powershell
docker compose up -d
Copy-Item .env.example .env
python -m pip install -r requirements.txt
python ingestion/create_topics.py
python ingestion/seed_game_mapping.py
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 30 --depuis-le-debut
```

---

# Session 2, 20 août 2026

## Phase 1. Reprise de l'environnement

```powershell
# [PS] Le moteur Docker s'etait arrete entre les deux sessions.
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"

# [PS] (diagnostic) Verification des ressources avant d'ajouter 4 conteneurs
docker info --format "CPU={{.NCPU}} / RAM_octets={{.MemTotal}}"
# -> 8 CPU, 15,5 Go alloues a Docker : marge suffisante

# [PS] (diagnostic) L'image existe-t-elle avant d'ecrire le compose ?
#      Interroge le registre, ne necessite pas le moteur local.
docker manifest inspect apache/airflow:3.1.8
```

## Phase 2. Recuperation de la configuration officielle Airflow 3

Les noms de variables ont beaucoup change entre Airflow 2 et 3. Ils ont ete
releves sur le fichier officiel de la version exacte plutot que reconstitues.

```
Source : https://airflow.apache.org/docs/apache-airflow/3.1.8/docker-compose.yaml
Variables retenues, inexistantes en Airflow 2 :
  AIRFLOW__API_AUTH__JWT_SECRET
  AIRFLOW__CORE__EXECUTION_API_SERVER_URL
Services : api-server (ex webserver), scheduler, dag-processor, triggerer, init
```

## Phase 3. Base de metadonnees Airflow

```powershell
# [PS] (diagnostic) Le script d'init ne rejoue pas sur un volume existant :
#      la base est creee a la main, et le script sql/00_create_airflow_db.sql
#      est ajoute au depot pour la reproductibilite depuis zero.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -v ON_ERROR_STOP=1 `
  -c "CREATE ROLE airflow WITH LOGIN PASSWORD 'devlocal_airflow';" `
  -c "CREATE DATABASE airflow OWNER airflow;"
```

## Phase 4. Construction et demarrage d'Airflow

Fichiers crees : `docker/airflow/Dockerfile`, bloc `x-airflow-commun` et cinq
services ajoutes a `docker-compose.yml`.

```powershell
# [PS] (procédure) Image etendue : le provider PostgreSQL n'est pas dans
#      l'image officielle.
docker compose build airflow-init

# [PS] (procédure) Migration du schema et creation du compte admin
docker compose up airflow-init
# -> "Database migrating done!", "User admin created with role Admin", code 0

# [PS] (procédure) Demarrage des quatre composants
docker compose up -d airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer

# [PS] (procédure) Application du schema Gold sur PostgreSQL
docker cp "sql/schema_gold.sql" gamelens-postgres:/tmp/schema_gold.sql
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -v ON_ERROR_STOP=1 -f /tmp/schema_gold.sql

# [PS] (diagnostic) Verification des chemins d'import reels avant d'ecrire le DAG
docker exec gamelens-airflow-scheduler python -c "from airflow.sdk import dag, task"
docker exec gamelens-airflow-scheduler python -c "from airflow.providers.postgres.hooks.postgres import PostgresHook"
docker exec gamelens-airflow-scheduler python -c "import sys; sys.path.insert(0,'/opt/gamelens/ingestion'); import common; print(common.config())"
# -> resout postgres:5432 depuis le conteneur : la frontiere de configuration fonctionne
```

## Phase 5. Contraintes d'unicite manquantes (INC-005)

```sql
-- [SQL] Sans ces deux contraintes, aucun ON CONFLICT n'etait ancrable et un
-- rejeu du DAG aurait duplique les lignes en silence.
ALTER TABLE mart.dim_games   ADD CONSTRAINT uq_dim_games_steam_appid UNIQUE (steam_appid);
ALTER TABLE mart.fact_prices ADD CONSTRAINT uq_fact_prices_grain     UNIQUE (game_id, store_id, collected_at);

-- [SQL] Amorcage de la boutique Steam
INSERT INTO mart.dim_stores (name, base_url, source_type)
VALUES ('Steam', 'https://store.steampowered.com', 'api')
ON CONFLICT (name) DO NOTHING;
```

## Phase 6. Enregistrement et execution du DAG

Fichier cree : `dags/gamelens_promotion_gold.py`.

```powershell
# [PS] (diagnostic) Le DAG n'apparaissait pas apres 5 minutes. Ni erreur
#      d'import, ni fichier manquant : l'analyseur rescanne le dossier toutes
#      les 5 minutes par defaut.
docker exec gamelens-airflow-dag-processor ls -la /opt/airflow/dags
docker exec gamelens-airflow-scheduler airflow dags list-import-errors

# [PS] (procédure) Force l'analyse immediate, utile apres chaque modification
docker exec gamelens-airflow-scheduler airflow dags reserialize
docker exec gamelens-airflow-scheduler airflow dags list
```

### Test negatif de la porte de fraicheur (recette C4.4.1)

```sql
-- [SQL] Etat de depart : aucune donnee pour la journee en cours
SELECT (collected_at AT TIME ZONE 'UTC')::date AS jour, count(*)
FROM speed.player_count_events GROUP BY 1 ORDER BY 1;
-- Observe : uniquement 2026-08-19, rien pour 2026-08-20
```

```powershell
# [PS] Le run planifie de 02h30 s'est declenche seul. Resultat attendu : echec.
docker exec gamelens-airflow-scheduler airflow tasks states-for-dag-run `
    gamelens_promotion_gold "scheduled__2026-08-20T02:30:00+00:00"
```

```bash
# [BASH] Verification que l'echec est bien celui voulu, et non un plantage
grep -iE "ValueError|Aucun evenement" docker/airflow/logs/dag_id=*/run_id=scheduled*/task_id=verifier_fraicheur_silver/attempt=1.log
# -> ValueError: "Aucun evenement de frequentation pour le 2026-08-20.
#    Le pipeline temps reel a-t-il tourne ? Promotion interrompue."
# PASS : la porte bloque la promotion avec un message actionnable.
```

### Reprise automatique (observee, non provoquee)

```bash
# [BASH] Alimentation de la journee en cours
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 12
# -> 30 messages inseres (15 du jour, 15 restes dans Kafka depuis la session 1)
```

```powershell
# [PS] La seconde tentative, declenchee seule 5 minutes apres l'echec, passe.
docker exec gamelens-airflow-scheduler airflow tasks states-for-dag-run `
    gamelens_promotion_gold "scheduled__2026-08-20T02:30:00+00:00"
# -> les 6 taches en success. Echec a 07:52:17, succes a 07:57:17, sans intervention.
```

### Blocage des runs manuels, explique et non contourne

```powershell
# [PS] (diagnostic) Deux runs manuels restaient en "queued" sans demarrer.
docker exec gamelens-airflow-scheduler airflow dags list-runs gamelens_promotion_gold
# -> le run planifie est "running", les deux manuels "queued" :
#    max_active_runs=1 les fait attendre. Comportement voulu, pas une panne.
#    Ils se sont executes seuls, et en succes, des la place liberee.
```

## Phase 7. Verification de la couche Gold

```sql
-- [SQL] Contenu de l'entrepot apres promotion
SELECT (SELECT count(*) FROM mart.dim_games)               AS dim_games,
       (SELECT count(*) FROM mart.dim_stores)              AS dim_stores,
       (SELECT count(*) FROM mart.fact_popularity_history) AS faits_popularite,
       (SELECT count(*) FROM mart.fact_prices)             AS faits_prix;
-- Observe : 15, 1, 15, 45 (trois releves tarifaires horodates distincts)

-- [SQL] Le drapeau de promotion est reellement exerce par une remise reelle
SELECT g.unified_name, p.price, p.promotion_flag
FROM mart.fact_prices p JOIN mart.dim_games g USING (game_id)
WHERE p.promotion_flag;
-- Observe : Cult of the Lamb a 9,19 EUR, remise de 60 %
```

## Phase 8. Angle mort de la supervision (INC-007)

```sql
-- [SQL] Recoupement de deux comptages qui auraient du concorder.
--       C'est cet ecart qui a revele le defaut, aucune alerte ne l'a signale.
SELECT collected_at, count(*) FROM speed.price_snapshots GROUP BY 1 ORDER BY 1;
-- Observe : 4 collectes distinctes

SELECT component, status, records_in, records_written, started_at
FROM speed.pipeline_runs WHERE component='steam_prices' ORDER BY run_id;
-- Observe : 1 seule ligne. Les collectes orchestrees n'etaient pas tracees.
```

Correction : point d'entree `collecter_et_tracer()` distinct de `collecter()`,
appel corrige dans le DAG, puis nouveau run de verification.

```sql
-- [SQL] Apres correction : la collecte orchestree apparait bien
SELECT component, started_at FROM speed.pipeline_runs WHERE component='steam_prices';
-- Observe : 2 lignes, dont celle du run orchestre de 08:00:12. PASS.
```

## Phase 9. Pipeline CI/CD

Fichiers crees : `.github/workflows/ci.yml`, `ruff.toml`, `tests/conftest.py`,
`tests/test_watchlist.py`, `tests/test_steam_prices.py`.

```bash
# [BASH] (procédure) Etage qualite, memes commandes qu'en CI
python -m ruff check ingestion dags tests
python -m ruff format --check ingestion dags tests
# 11 anomalies relevees puis corrigees (--fix), aucune n'etait un bug

# [BASH] (procédure) Etage tests unitaires, sans reseau ni base
python -m pytest tests -q
# -> 14 passed
```

```powershell
# [PS] (diagnostic puis procédure) Etage d'integrite du DAG, teste localement
#      avant d'etre inscrit dans le workflow.
docker build -t gamelens/airflow:ci ./docker/airflow
$ws = (Get-Location).Path
docker run --rm -v "${ws}/dags:/opt/airflow/dags:ro" `
    -e AIRFLOW__CORE__LOAD_EXAMPLES=false gamelens/airflow:ci `
    bash -c "airflow db migrate && airflow dags list-import-errors && airflow dags list | grep gamelens_promotion_gold"
# -> ECHEC au premier essai : "Aucune erreur d import" mais DAG absent de la liste.
#    Cause : en Airflow 3, "dags list" lit la base de metadonnees, pas le dossier.
#    Correction : ajout de "airflow dags reserialize" avant la liste.
# -> PASS apres correction, sur les deux controles.
```

```bash
# [BASH] Validation du workflow avant commit
python -c "import yaml; print(list(yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']))"
# -> ['qualite', 'tests', 'dag', 'integration', 'publication']
```

## Recapitulatif des etats verifies en fin de session 2

| Verification | Commande | Resultat observe |
|---|---|---|
| Pile complete demarree | `docker compose ps` | 6 conteneurs *Up*, tous *healthy* |
| DAG enregistre | `airflow dags list` | `gamelens_promotion_gold`, actif |
| Porte de fraicheur bloque une journee vide | run planifie sans donnee | `ValueError` avec message actionnable |
| Reprise automatique | 2e tentative apres 5 min | run complet en succes, sans intervention |
| Promotion vers Gold | `SELECT count(*)` sur `mart.*` | 15 dimensions, 15 faits popularite, 45 faits prix |
| Controles de qualite Gold | tache `controler_qualite_gold` | 6 controles au vert |
| Idempotence du DAG | 3 runs sur la meme journee | `dim_games` et `fact_popularity_history` stables a 15 |
| Supervision des collectes | `speed.pipeline_runs` | defaut trouve puis corrige et verifie |
| Etage qualite de la CI | `ruff check` et `format --check` | tout passe |
| Etage tests de la CI | `pytest tests` | 14 tests verts |
| Etage integrite DAG de la CI | conteneur jetable | 2 controles PASS |
| Etages integration et publication | non executes | **necessitent un depot distant** |

## Mise en route complete, version courte

Poste propre, Docker Desktop demarre :

```powershell
docker compose up -d postgres kafka
Copy-Item .env.example .env
python -m pip install -r requirements.txt
python ingestion/create_topics.py
python ingestion/seed_game_mapping.py
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 30 --depuis-le-debut

docker compose build airflow-init
docker compose up airflow-init
docker compose up -d airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer
# Interface : http://localhost:8080 (admin / admin)
```

## Phase 10. Dépôt distant et exécution réelle de la CI

```bash
# [BASH] (diagnostic) Verification prealable : aucun secret ne doit partir.
git ls-files | grep -E "^\.env$" || echo "non suivi, correct"
git ls-files | wc -l          # 29 fichiers, uniquement le projet

# [BASH] (diagnostic) Le compte dispose-t-il du scope workflow, indispensable
#        pour pousser un fichier .github/workflows/ ?
gh auth status
# -> compte Mael8zinsou, scopes 'gist', 'read:org', 'repo', 'workflow'

# [BASH] (procédure) Creation du depot prive et premier push
gh repo create gamelens-bloc4_0 --private --source=. --remote=origin --push
# -> https://github.com/Mael8zinsou/gamelens-bloc4_0
```

### Premiere execution du workflow : echec attendu de l'etage non testable en local

```bash
# [BASH] Suivi du run
gh run list --limit 3 --workflow=CI
gh run view <id> --json conclusion,jobs

# Resultat : qualite, tests, dag en success ; integration en failure ;
# publication ignoree par dependance.

# [BASH] Lecture ciblee de l'echec
gh run view <id> --log-failed
# -> echec sur "Verifier l'initialisation du schema Silver speed"
```

```sql
-- [SQL] Contre-verification locale AVANT de corriger quoi que ce soit :
-- l'infrastructure est-elle en cause, ou l'assertion ?
SELECT table_type, count(*) FROM information_schema.tables
WHERE table_schema='speed' GROUP BY 1;
-- Observe : BASE TABLE = 4, VIEW = 1.
-- L'attendu de 4 sur un comptage non filtre etait faux. Le defaut etait dans
-- le test, pas dans le systeme teste. Voir OBS-22.
```

Deux corrections dans le même commit : filtrage sur `table_type` avec
vérification séparée de la vue, et normalisation en minuscules du nom d'image
pour l'étage de publication, défaut repéré par relecture avant qu'il ne se
manifeste (OBS-23).

### Seconde execution : cinq etages verts

```bash
# [BASH] Attente de la fin du run, sans interrogation repetee inutile
until [ "$(gh run view <id> --json status --jq .status)" = "completed" ]; do sleep 20; done
gh run view <id> --json conclusion,jobs

# CONCLUSION: success
#   success  Qualite du code
#   success  Tests unitaires
#   success  Integrite du DAG Airflow
#   success  Integration sur infrastructure reelle
#   success  Publication de l'image

# [BASH] Verification que l'image existe reellement, plutot que de se fier au
#        seul statut du job
gh run view <id> --log | grep -iE "pushing manifest|naming to ghcr"
# -> ghcr.io/mael8zinsou/gamelens-bloc4_0/airflow:latest
# -> ghcr.io/mael8zinsou/gamelens-bloc4_0/airflow:95065aa3ac0c...
```

### Detail des etapes de l'etage d'integration, toutes en succes

| Etape | Ce qu'elle prouve |
|---|---|
| Demarrer le socle PostgreSQL et Kafka | Le `docker-compose.yml` fonctionne sur une machine vierge |
| Attendre que le socle soit sain | Les healthchecks repondent dans le delai imparti |
| Verifier l'initialisation du schema Silver | 4 tables et 1 vue creees automatiquement |
| Executer le pipeline temps reel | Steam, Kafka et PostgreSQL de bout en bout depuis un runner |
| Verifier le resultat en base | Le pipeline a reellement ecrit des lignes |
| Verifier l'idempotence du puits | Le rejeu des offsets ne duplique rien, test de la session 1 automatise |
