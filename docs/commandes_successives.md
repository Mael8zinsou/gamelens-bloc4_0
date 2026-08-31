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

---

# Session 3, 20 août 2026

## Phase 1. Alignement du modèle de rôles (OBS-25)

Découvert en préparant le test de sécurité : deux modèles concurrents.

```bash
# [BASH] (diagnostic) Comparaison des rôles déclarés par les deux couches
grep -n "CREATE ROLE\|GRANT" sql/schema_silver_speed.sql
grep -n "CREATE ROLE\|GRANT" sql/schema_gold.sql
# -> Silver : gamelens_etl, gamelens_reader
#    Gold   : etl_service, analyst, dashboard_viewer
```

```powershell
# [PS] (procédure) Application du schéma Silver corrigé, idempotent
docker cp "sql/schema_silver_speed.sql" gamelens-postgres:/tmp/silver.sql
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -v ON_ERROR_STOP=1 -f /tmp/silver.sql

# [PS] Suppression des deux rôles orphelins
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "DROP OWNED BY gamelens_etl, gamelens_reader; DROP ROLE IF EXISTS gamelens_etl; DROP ROLE IF EXISTS gamelens_reader;"
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg\_%';"
# -> airflow, analyst, dashboard_viewer, etl_service, gamelens_app
```

## Phase 2. Test de sécurité, et test du test

```bash
# [BASH] (procédure) 13 cas paramétrés, 3 rôles, refus compris
python -m pytest tests/test_securite_roles.py -v
# -> 13 passed
```

```powershell
# [PS] Le test détecte-t-il réellement une brèche ? Cassure volontaire.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "GRANT SELECT ON mart.fact_popularity_history TO dashboard_viewer;"
```

```bash
# [BASH] Le test DOIT maintenant échouer
python -m pytest tests/test_securite_roles.py -k "lire_la_table_de_faits_Gold-refuse"
# -> FAILED : "attendu refuse, obtenu autorise". Le test est donc réel.
```

```powershell
# [PS] Rétablissement, puis retour au vert
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "REVOKE SELECT ON mart.fact_popularity_history FROM dashboard_viewer;"
```

## Phase 3. Couche de supervision

Fichier créé : `sql/schema_supervision.sql`, cinq vues d'indicateurs, une table
d'alertes, une vue de synthèse.

```powershell
# [PS] (procédure) Application du schéma de supervision
docker cp "sql/schema_supervision.sql" gamelens-postgres:/tmp/supervision.sql
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -v ON_ERROR_STOP=1 -f /tmp/supervision.sql
```

```sql
-- [SQL] État consolidé de la plateforme, un élément surveillé par ligne
SELECT * FROM speed.v_supervision_synthese;
-- Observé : fraîcheur 209 min (critique), complétude 100 % (nominal),
-- latence p95 64 890 s (critique), retard Gold 0 jour (nominal).
-- Les deux états critiques sont exacts, voir OBS-29.
```

## Phase 4. Moteur d'alertes et cycle de vie

Fichier créé : `supervision/regles_alertes.py`, six règles déclarées comme données.

```bash
# [BASH] (procédure) Première évaluation
python supervision/regles_alertes.py
# -> 2 déclenchée(s) dont 2 nouvelle(s), 0 résolue(s), 4 nominale(s)

# [BASH] Seconde évaluation, condition inchangée : pas de doublon attendu
python supervision/regles_alertes.py
# -> 2 déclenchée(s) dont 0 nouvelle(s) ; mentions "(deja ouverte)"
```

```sql
-- [SQL] Le journal ne contient bien que deux lignes, pas quatre
SELECT alerte_id, regle, severite, valeur, seuil, resolue_le
FROM speed.alertes ORDER BY alerte_id;
```

```bash
# [BASH] Retour de la donnée, puis réévaluation : fermeture attendue
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 12
python supervision/regles_alertes.py
# -> [RESOLUE] fraicheur_frequentation revenue sous le seuil
#    L'alerte de latence reste ouverte, à juste titre : les événements en
#    retard de la session 1 sont encore dans la fenêtre de 24 heures.
```

## Phase 5. DAG de supervision

Fichier créé : `dags/gamelens_supervision.py`, cadence de 15 minutes.

```powershell
# [PS] (procédure) Recréation des conteneurs pour monter supervision/
docker compose up -d
docker exec gamelens-airflow-scheduler airflow dags reserialize
docker exec gamelens-airflow-scheduler airflow dags list
# -> gamelens_promotion_gold et gamelens_supervision

# [PS] Déclenchement, avec un avertissement ouvert et aucune alerte critique
docker exec gamelens-airflow-scheduler airflow dags trigger gamelens_supervision --run-id supervision-01
docker exec gamelens-airflow-scheduler airflow tasks states-for-dag-run gamelens_supervision supervision-01
# -> les deux tâches en success, comme attendu

# [PS] Lecture du journal DEPUIS le conteneur : le nom de dossier contient des
#      deux-points, illisibles par un client Windows.
docker exec gamelens-airflow-scheduler sh -c "cat '/opt/airflow/logs/dag_id=gamelens_supervision/run_id=supervision-01/task_id=remonter_alertes_critiques/attempt=1.log'"
# -> "1 avertissement(s) ouvert(s), aucune alerte critique."
```

## Phase 6. Visualisation Grafana, provisionnée comme code

Fichiers créés : `docker/grafana/provisioning/datasources/postgres.yml`,
`docker/grafana/provisioning/dashboards/gamelens.yml`,
`docker/grafana/dashboards/gamelens_supervision.json` (7 panneaux).

```powershell
# [PS] (procédure) Démarrage
docker compose up -d grafana
```

```bash
# [BASH] (procédure) Vérification par l'API, sans passer par le navigateur
curl -s http://localhost:3000/api/health
# -> {"database":"ok","version":"11.6.0"}

curl -s -u admin:admin http://localhost:3000/api/datasources
# -> GameLens PostgreSQL | uid=gamelens-pg | url=postgres:5432 | user=analyst
#    Le rôle est bien analyst, en lecture seule, pas le propriétaire.

curl -s -u admin:admin http://localhost:3000/api/datasources/uid/gamelens-pg/health
# -> {"message":"Database Connection OK","status":"OK"}

curl -s -u admin:admin "http://localhost:3000/api/search?query=GameLens"
# -> GameLens, supervision de la plateforme | uid=gamelens-supervision
```

```bash
# [BASH] (procédure) Contrôle des 7 panneaux, requêtes exécutées via l'API
python supervision/verifier_tableau_bord.py
# -> 7 panneau(x) fonctionnel(s), 0 en echec
```

## Phase 7. Extension de la chaîne d'intégration

Deux étapes ajoutées à l'étage `integration` : tests de sécurité sur les rôles,
et contrôle de fumée du moteur d'alertes avec assertion sur sa propre trace
dans `speed.pipeline_runs`, conséquence directe d'INC-007.

```bash
# [BASH] (procédure) Contrôles locaux avant de pousser, mêmes commandes qu'en CI
python -m ruff check ingestion dags tests supervision
python -m ruff format --check ingestion dags tests supervision
python -m pytest tests -q
# -> 27 passed (14 unitaires + 13 de sécurité)
```

## Récapitulatif des états vérifiés en fin de session 3

| Vérification | Commande | Résultat observé |
|---|---|---|
| Modèle de rôles unifié | `SELECT rolname FROM pg_roles` | 3 rôles applicatifs, plus le propriétaire |
| Cloisonnement effectif | `pytest tests/test_securite_roles.py` | 13 sur 13, dont 7 refus |
| Le test de refus détecte une brèche | GRANT puis REVOKE | échec attendu, puis retour au vert |
| Indicateurs de supervision | `SELECT * FROM speed.v_supervision_synthese` | 5 éléments, états exacts |
| Déclenchement d'alerte | `regles_alertes.py` | 2 déclenchées, 2 nouvelles |
| Absence de doublon | seconde évaluation | 2 déclenchées, 0 nouvelle |
| Fermeture automatique | après retour de la donnée | 1 résolue, horodatée |
| Remontée par Airflow | DAG `gamelens_supervision` | 2 tâches en succès, avertissement signalé |
| Tableau de bord Grafana | `verifier_tableau_bord.py` | 7 panneaux sur 7 |
| Qualité et tests | `ruff` et `pytest` | tout vert, 27 tests |

## Mise en route complète, version courte

Poste propre, Docker Desktop démarré :

```powershell
docker compose up -d postgres kafka grafana
Copy-Item .env.example .env
python -m pip install -r requirements.txt

python ingestion/create_topics.py
python ingestion/seed_game_mapping.py
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 30 --depuis-le-debut
python supervision/regles_alertes.py

docker compose build airflow-init
docker compose up airflow-init
docker compose up -d airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer

# Airflow  : http://localhost:8080  (admin / admin)
# Grafana  : http://localhost:3000  (admin / admin)
```

---

# Session 4, 20 août 2026

## Phase 1. Levée d'un risque avant d'engager le compte

```bash
# [BASH] (diagnostic) Snowpark est-il disponible pour Python 3.12 ?
#        Incertitude ouverte depuis la session 1, levée AVANT que le compte
#        ne soit créé.
python -m pip index versions snowflake-snowpark-python
# -> 1.54.0 disponible, résolution possible sur 3.12

# [BASH] L'installation a modifié l'environnement global. Constat de ce qui a
#        RÉELLEMENT changé, par date de modification, plutôt que de croire la
#        liste de conflits affichée par pip.
find "$SITE_PACKAGES" -maxdepth 1 -name "*.dist-info" -mmin -15 -printf "%TH:%TM  %f\n"
# -> snowflake-connector-python 4.7.2, requests 2.34.2, cryptography, pyopenssl
#    pydantic / starlette / uvicorn NON touchés : ces conflits préexistaient.

# [BASH] Restauration des versions épinglées
python -m pip uninstall -y snowflake-snowpark-python
python -m pip install "snowflake-connector-python==3.9.1" "requests==2.32.3"
python -m pytest tests -q            # -> 27 passed, projet intact
```

## Phase 2. Isolation de l'outillage Snowflake

```bash
# [BASH] (diagnostic) Tentative d'environnement virtuel : impossible.
python -m venv .venv-snowflake
# -> No module named venv.__main__
python -c "import venv; print(venv.__path__)"
ls "C:/Users/maelz/AppData/Local/Programs/Python/Python312/Lib/venv"
# -> le répertoire ne contient qu'un requirements.txt égaré, daté d'août 2024.
#    Le module venv de cette installation est vide. Voir OBS-34.
```

```powershell
# [PS] (diagnostic) Résolution des versions dans un conteneur jetable, pour ne
#      rien installer sur le poste.
docker run --rm python:3.12-slim sh -c "pip install snowflake-snowpark-python dbt-snowflake; pip list"
# -> dbt-core 1.12.2, dbt-snowflake 1.12.0, snowpark 1.54.0, connecteur 4.7.2

# [PS] (procédure) Construction de l'image d'outillage
docker compose --profile outillage build snowflake-cli
```

Deux conflits rencontrés à la construction, corrigés par lecture du message
plutôt que par tâtonnement : `pandas==2.2.3` trop ancien pour l'extra pandas du
connecteur, et `python-dotenv==1.0.1` recopié de `requirements.txt` alors que
dbt-core 1.12 exige `>=1.2`.

## Phase 3. Amorçage du compte et première connexion

Côté Maël, dans Snowsight : `sql/bootstrap_snowflake_service.sql`, puis
`python entrepot/generer_cle.py` et la commande `ALTER USER ... SET RSA_PUBLIC_KEY`
qu'il affiche.

```powershell
# [PS] (procédure) Contrôle préalable, avant tout script de schéma
docker compose run --rm snowflake-cli python entrepot/verifier_connexion.py
# -> CONNEXION ETABLIE
#    version 10.29.101 | compte TF82164 | région AWS_EU_WEST_3
#    role ACCOUNTADMIN | entrepôt, base et schéma : aucun (à créer)
```

Le repli sans contexte s'est avéré nécessaire : la base `gamelens` n'existant pas
encore, une connexion la réclamant échoue avec un message qui laisse croire à un
problème d'authentification.

## Phase 4. Application du schéma Gold

```powershell
# [PS] (procédure)
docker compose run --rm snowflake-cli python entrepot/executer_sql.py sql/schema_gold_snowflake.sql --sans-contexte
# -> 27 réussies, 0 en erreur
```

Premier passage : une 28e instruction en erreur, le découpeur traitant un bloc de
commentaires de fin de fichier comme une instruction. Défaut de l'exécuteur,
corrigé par un filtre sur les instructions ne contenant que des commentaires.

## Phase 5. Vérification empirique des contraintes Snowflake

```powershell
# [PS] Mode poursuite sur erreur : certaines instructions DOIVENT échouer.
docker compose run --rm snowflake-cli python entrepot/executer_sql.py sql/verify_snowflake_constraints.sql --continuer
```

Première exécution, 2 erreurs :

```
[10] ERREUR  INSERT INTO dim_games (game_id, unified_name) VALUES (..., NULL)
     -> 100072 (22000): NULL result in a non-nullable column        <- ATTENDU
[12] ERREUR  INSERT INTO fact_prices ... game_id inexistant
     -> 100078 (22000): String 'inexistant-0000-...' is too long    <- PAS attendu
```

La seconde erreur ne portait pas sur la clé étrangère mais sur la **longueur** :
38 caractères pour une colonne `VARCHAR(36)`. Le test n'avait jamais mis la
contrainte à l'épreuve. Identifiant raccourci à 35 caractères, réexécution :

```
[12] OK      INSERT INTO fact_prices ... game_id inexistant
```

**Matrice établie** : `NOT NULL` et les contraintes de type sont appliquées,
`CHECK`, `FOREIGN KEY` et `PRIMARY KEY` ne le sont pas. Résultats consignés dans
le script lui-même. Voir OBS-36 et TS-08.

## Phase 6. Calcul distribué Snowpark

```powershell
# [PS] (procédure)
docker compose run --rm snowflake-cli python entrepot/snowpark_promotion.py
docker compose run --rm snowflake-cli python entrepot/snowpark_promotion.py --expliquer
```

Trois échecs successifs avant que le script ne tourne, et la méthode qui a fini
par marcher :

```powershell
# 1. information_schema.warehouses() n'existe pas -> requête simplifiée
# 2. invalid identifier 'DAY' -> la fenêtre ordonnait sur DAY alors que la
#    colonne s'appelle JOUR après renommage. Snowpark diffère la résolution
#    des noms : l'erreur ne survient qu'à l'exécution.
# 3. invalid identifier 'PARTITIONS_SCANNED' -> AU LIEU de tenter un troisième
#    nom plausible, lister les colonnes réellement exposées :
docker compose run --rm snowflake-cli python -c "...cur.description..."
# -> pas de PARTITIONS_SCANNED, mais CLUSTER_NUMBER, WAREHOUSE_SIZE,
#    BYTES_SCANNED, ROWS_PRODUCED. Requête réécrite, correcte du premier coup.
```

Résultat, avec la preuve du caractère distribué :

```
4. Calcul analytique distribue : fenetre glissante et classement
  jeu                  genre            joueurs   moy. 7j  rang  part %
  Stardew Valley       Simulation      59864.50  74212.75     1    61.8
  Terraria             Sandbox         33532.50  35230.25     1   100.0
  Slay the Spire       Deckbuilder      7216.00   8270.50     1    54.4
  ...

5. Preuve que le calcul a bien eu lieu dans l'entrepot
  type     entrepot       taille    cluster  octets lus   lignes  exec ms
  SELECT   GAMELENS_WH    X-Small         1        4608       15       26
  MERGE    GAMELENS_WH    X-Small         1        6144       30      229
  MERGE    GAMELENS_WH    X-Small         1        4096       15      314
```

SQL généré, extrait, montrant que les fenêtres sont poussées côté serveur :

```sql
rank() OVER (PARTITION BY "GENRE" ORDER BY ...)
round(avg("JOUEURS_MOYENS") OVER (PARTITION BY "GAME_ID" ORDER BY "JOUR" ASC
      NULLS FIRST ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2)
```

## Phase 7. Contrôles de la couche Gold Snowflake

```powershell
# [PS] (procédure) 8 contrôles d'intégrité, chacun cherchant les violations
docker compose run --rm snowflake-cli python entrepot/verifier_gold.py
# -> 15 dim_games, 1 dim_stores, 30 fact_popularity_history, 75 fact_prices
# -> 8 contrôles au vert
```

## Récapitulatif des états vérifiés en fin de session 4

| Vérification | Commande | Résultat observé |
|---|---|---|
| Connexion Snowflake | `verifier_connexion.py` | établie, paire de clés RSA |
| Schéma Gold appliqué | `executer_sql.py schema_gold_snowflake.sql` | 27 réussies, 0 erreur |
| Contraintes réellement appliquées | `executer_sql.py verify_... --continuer` | matrice établie, TS-08 |
| Promotion Snowpark | `snowpark_promotion.py` | 15 + 30 + 75 lignes promues |
| Idempotence Snowpark | 3 exécutions | 0 insertion, que des mises à jour |
| Calcul distribué prouvé | `--expliquer` et historique de session | fenêtres dans le SQL, `GAMELENS_WH` |
| Intégrité Gold Snowflake | `verifier_gold.py` | 8 contrôles au vert |
| Environnement du poste | `pytest` après restauration | 27 tests, intact |

## Mise en route complète, version courte

```powershell
docker compose up -d postgres kafka grafana
python -m pip install -r requirements.txt
python ingestion/create_topics.py
python ingestion/seed_game_mapping.py
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 30 --depuis-le-debut
python supervision/regles_alertes.py

docker compose build airflow-init
docker compose up airflow-init
docker compose up -d airflow-apiserver airflow-scheduler airflow-dag-processor airflow-triggerer

docker compose --profile outillage build snowflake-cli
docker compose run --rm snowflake-cli python entrepot/verifier_connexion.py
docker compose run --rm snowflake-cli python entrepot/executer_sql.py sql/schema_gold_snowflake.sql --sans-contexte
docker compose run --rm snowflake-cli python entrepot/snowpark_promotion.py
docker compose run --rm snowflake-cli python entrepot/verifier_gold.py

# Airflow : http://localhost:8080   Grafana : http://localhost:3000   (admin / admin)
```

---

# Session 5, 26 août 2026

Objectif unique : combler le seul angle mort de la chaîne d'intégration
continue. `entrepot/` passait au contrôle de qualité mais rien ne l'exécutait,
faute d'identifiants Snowflake sur le runner.

## Phase 1. État des lieux avant d'engager quoi que ce soit

```bash
# [BASH] (diagnostic) volumétrie réelle du dépôt, par domaine
find ./sql ./ingestion ./dags ./entrepot ./supervision ./tests ./docs \
  -name "*.py" -o -name "*.sql" -o -name "*.md" | wc -l
# -> 7 737 lignes au total, dont 2 687 de documentation

# [BASH] (diagnostic) qui planifie réellement le pipeline temps réel ?
grep -rn "steam_producer\|kafka_to_postgres" --include=*.py --include=*.yml .
# -> appelé par la CI et à la main, par AUCUN DAG. Trou identifié, hors périmètre
#    de cette session, reporté à la feuille de route.

# [BASH] (diagnostic) état de la supervision, plateforme laissée tourner
docker exec gamelens-postgres psql -U gamelens_app -d gamelens \
  -c "SELECT * FROM speed.v_supervision_synthese;"
# -> 5 alertes ouvertes, fraîcheur 8 505 min, Gold en retard de 6 jours.
#    La supervision détecte correctement son propre abandon : c'est un
#    résultat valide, pas une panne.
```

## Phase 2. Levée d'un risque avant de brancher la CI sur l'entrepôt

```bash
# [BASH] (diagnostic) DÉCISIF : que contient réellement le script de schéma ?
grep -nE "^(CREATE|USE|ALTER|GRANT|DROP)" sql/schema_gold_snowflake.sql
# -> CREATE OR REPLACE TABLE gamelens.mart.dim_games, et la base nommée en dur.
#    Un étage de CI qui l'aurait rejoué aurait DÉTRUIT la couche de
#    démonstration à chaque push, sans message d'erreur.

# [BASH] (diagnostic) les scripts Python sont-ils, eux, redirigeables ?
grep -n "mart\." entrepot/verifier_gold.py entrepot/snowpark_promotion.py
# -> ils écrivent mart.x sans préfixer la base : ils suivent CURRENT_DATABASE().
#    Seuls les deux .sql figent gamelens. La frontière de configuration paie.
```

## Phase 3. Redirection de base, éprouvée hors ligne d'abord

```bash
# [BASH] (procédure) vérifier la substitution AVANT tout appel à Snowflake
python -c "
import re
from pathlib import Path
MOTIF = re.compile(r'(?<![A-Za-z0-9_])gamelens(?![A-Za-z0-9_])')
src = Path('sql/schema_gold_snowflake.sql').read_text(encoding='utf-8')
out, n = MOTIF.subn('gamelens_ci_42', src)
print(n, 'redirections')
print(set(re.findall(r'gamelens[A-Za-z0-9_]*', out)))
"
# -> 24 redirections ; gamelens_wh, gamelens_analyst, gamelens_etl_service et
#    gamelens_dashboard_viewer INTACTS. L'entrepôt virtuel et les rôles sont
#    des objets de compte, pas des objets de base : les rediriger serait faux.
```

## Phase 4. Recette exécutée pour de vrai

```powershell
# [PS] (procédure) recette complète sur base jetable, sept étapes
docker compose --profile outillage run --rm snowflake-cli `
  python entrepot/recette_ci.py
# -> base gamelens_ci_local_37058 créée
# -> 27 instructions de schéma, 0 erreur
# -> 8 contrôles d'intégrité au vert sur données saines
# -> 3 lignes de classement conformes aux valeurs calculées à la main
# -> 2 contraintes appliquées par le moteur, 4 laissées à l'applicatif
# -> 4 violations rattrapées par le filet applicatif
# -> base supprimée. 36 secondes.

# [PS] (procédure) CONTRÔLE DE SÛRETÉ : la couche de démonstration est-elle intacte ?
docker compose --profile outillage run --rm snowflake-cli `
  python entrepot/verifier_gold.py
# -> 15 dim_games, 75 fact_prices, 8 contrôles au vert. Intacte.
```

## Phase 5. Le test négatif qui a démasqué un garde-fou mort

```powershell
# [PS] (procédure) TEST NÉGATIF : viser explicitement la base de démonstration
docker compose --profile outillage run --rm `
  -e SNOWFLAKE_DATABASE=gamelens snowflake-cli python entrepot/recette_ci.py
# -> PREMIER PASSAGE : "Recette Snowflake au vert en 41 s", code 0.
#    Le refus n'a JAMAIS eu lieu. nom_base() écartait discrètement les noms
#    protégés en retombant sur un nom généré : garde_fou() ne recevait jamais
#    de nom protégé et ne pouvait donc jamais refuser. Voir OBS-42.

# [PS] (procédure) après correction, le même test
docker compose --profile outillage run --rm `
  -e SNOWFLAKE_DATABASE=gamelens snowflake-cli python entrepot/recette_ci.py
# -> REFUS : la recette vise la base 'gamelens', qui est protegee.
# -> code de sortie 1, avant toute instruction envoyée à Snowflake.
```

## Phase 6. Authentification de la CI, éprouvée en local d'abord

```bash
# [BASH] (procédure) simuler exactement les conditions du runner : la clef
# arrive comme CONTENU PEM en environnement, pas comme chemin de fichier.
# La clef passe par une variable, jamais par la ligne de commande.
export SNOWFLAKE_PRIVATE_KEY="$(cat secrets/snowflake_key.p8)"
docker compose --profile outillage run --rm \
  -e SNOWFLAKE_PRIVATE_KEY -e SNOWFLAKE_PRIVATE_KEY_PATH= \
  snowflake-cli python entrepot/verifier_connexion.py
# -> authentification : paire de cles RSA (contenu en environnement)
# -> CONNEXION ETABLIE, Snowflake 10.30.101, AWS_EU_WEST_3
# -> credits consommes (30 j) : 0.60 sur 400 dollars d'enveloppe
```

```bash
# [BASH] (procédure) dépôt des secrets. La clef est lue DEPUIS LE FICHIER par
# redirection : elle ne transite ni par l'historique du shell ni par argv.
gh secret set SNOWFLAKE_ACCOUNT --body "RTZSXDV-PM63908"
gh secret set SNOWFLAKE_USER --body "GAMELENS_SERVICE"
gh secret set SNOWFLAKE_PRIVATE_KEY < secrets/snowflake_key.p8
gh secret list
# -> les trois secrets déposés sur le dépôt privé Mael8zinsou/gamelens-bloc4_0
```

## Phase 7. Sixième étage de CI, exécuté sur le runner

```bash
# [BASH] (procédure) valider le YAML avant de pousser
python -c "
import yaml, pathlib
d = yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text(encoding='utf-8'))
print(list(d['jobs']))
print(d['jobs']['publication']['needs'])
"
# -> 6 étages ; publication dépend désormais de [dag, integration, entrepot]

# [BASH] (procédure) pousser et suivre
git push
gh run watch 32954104664 --exit-status
# -> CONCLUSION: success, six étages verts
```

Trace réelle de l'étage Snowflake sur le runner, run **32954104664** :

```
  base jetable   : gamelens_ci_11_1
  authentification : paire de cles RSA (contenu en environnement)
  Base     : gamelens_ci_11_1 (24 mention(s) redirigee(s) depuis gamelens)
  27 reussie(s), 0 en erreur
  -> 8 controles, 0 violation : conforme
  -> 3 lignes conformes aux valeurs calculees a la main
  -> 2 contrainte(s) appliquee(s) par le moteur, 4 laissee(s) a l'applicatif
  -> 4 violation(s) detectee(s) par le filet applicatif : conforme
  Recette Snowflake au vert en 41 s.
  base jetable gamelens_ci_11_1 supprimee
```

Les trois secrets apparaissent masqués en `***` dans les journaux publics du
run, y compris la clef privée.

## Récapitulatif des états vérifiés en fin de session 5

| Vérification | Commande | Résultat observé |
|---|---|---|
| Redirection de base, hors ligne | substitution par expression régulière | 24 redirections, entrepôt et rôles intacts |
| Recette complète, en local | `recette_ci.py` | 7 étapes au vert, 36 s |
| Couche de démonstration intacte | `verifier_gold.py` | 75 tarifs, 8 contrôles au vert |
| Garde-fou sur base protégée | `-e SNOWFLAKE_DATABASE=gamelens` | refus, code 1 |
| Authentification par contenu PEM | `verifier_connexion.py` | connexion établie |
| Tests unitaires | `pytest tests` | 27 passés |
| Qualité du code | `ruff check` et `format --check` | 21 fichiers conformes |
| Chaîne complète | run 32954104664 | 6 étages verts, image publiée |

Note d'environnement : `pytest` lancé à la racine du dépôt échoue à la
collecte, sur un lien symbolique `docker/airflow/logs/dag_processor/latest`
illisible par Windows. Le répertoire est ignoré par git et la CI lance
`pytest tests`. Cibler le répertoire `tests` en local, pas la racine.

---

# Session 6, 27 août 2026 : ordonnancement de l'ingestion temps réel

## Phase 1. Constat de l'existant (diagnostic)

```bash
# Qui appelle les scripts d'ingestion ? Reponse : la CI et le clavier.
grep -rn "steam_producer\|kafka_to_postgres" --include=*.py --include=*.yml .

# L'image Airflow embarque-t-elle le client Kafka ? Non.
docker exec gamelens-airflow-scheduler python -c "import kafka"
# ModuleNotFoundError: No module named 'kafka'

# Seuil de la regle de fraicheur, pour caler la cadence du DAG dessus.
grep -nE "nom=|seuil=" supervision/regles_alertes.py
# fraicheur_frequentation, seuil 90 minutes
```

## Phase 2. Mise en place (procédure reproductible)

```bash
# 1. Ajouter le client Kafka a l'image Airflow, puis la reconstruire.
docker compose build airflow-scheduler
docker compose up -d airflow-scheduler airflow-apiserver \
                    airflow-dag-processor airflow-triggerer

# 2. Verifier que le client est present et que les DAG s'analysent.
docker exec gamelens-airflow-scheduler python -c "import kafka; print(kafka.__version__)"
docker exec gamelens-airflow-scheduler airflow dags reserialize
# Sync 3 DAGs

# 3. Declencher un cycle et suivre son etat.
docker exec gamelens-airflow-scheduler airflow dags trigger \
    gamelens_ingestion_temps_reel --run-id ingestion-01
docker exec gamelens-airflow-scheduler airflow tasks states-for-dag-run \
    gamelens_ingestion_temps_reel ingestion-01
```

## Phase 3. Lecture des journaux de tâche (procédure)

Les noms de dossiers de journaux contiennent des `:`, illisibles par un client
Windows. La lecture passe donc par le conteneur, et la sortie JSON est filtrée
pour ne garder que les messages :

```bash
docker exec gamelens-airflow-scheduler sh -c \
  'cat "/opt/airflow/logs/dag_id=gamelens_ingestion_temps_reel/run_id=ingestion-01/task_id=controler_ingestion/attempt=1.log"' \
  | grep -oE '"event":"[^"]*"' | sed 's/"event":"//;s/"$//'
```

## Phase 4. Vérification de l'étage de CI, en positif et en négatif (procédure)

```bash
docker tag gamelens/airflow:3.1.8 gamelens/airflow:ci

# Positif : les trois DAG attendus sont trouves.
MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W)/dags:/opt/airflow/dags:ro" \
  -e AIRFLOW__CORE__LOAD_EXAMPLES=false -e AIRFLOW__CORE__EXECUTOR=LocalExecutor \
  -e ATTENDUS="gamelens_promotion_gold gamelens_supervision gamelens_ingestion_temps_reel" \
  gamelens/airflow:ci bash -c '...'
# PASS x3

# Negatif : un nom inexistant doit faire sortir en code 1.
#   ATTENDUS="gamelens_promotion_gold gamelens_dag_inexistant"
# ECHEC: gamelens_dag_inexistant absent de la liste ; code de sortie 1
```

## Phase 5. Test négatif sur le broker (procédure)

```bash
docker stop gamelens-kafka
docker exec gamelens-airflow-scheduler airflow dags trigger \
    gamelens_ingestion_temps_reel --run-id test-broker-absent

# La tache echoue (NoBrokersAvailable), l'aval ne demarre pas. Mais :
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT component, status FROM speed.pipeline_runs
   WHERE started_at >= now() - interval '8 minutes';"
# (0 rows)  <- defaut reel, voir INC-008

# Apres correction de steam_producer.py et kafka_to_postgres.py, meme test :
# steam_producer | failed | NoBrokersAvailable: NoBrokersAvailable

docker start gamelens-kafka
# La reprise automatique d'Airflow repart seule 2 minutes plus tard.
```

## Phase 6. Vérification de bout en bout (diagnostic)

```bash
# Etat de la supervision, avant et apres.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT * FROM speed.v_supervision_synthese;"

# Durees d'ouverture des alertes, matiere pour la feuille de route C4.3.2.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT regle, severite, declenchee_le::timestamp(0), resolue_le::timestamp(0),
          age(resolue_le, declenchee_le) AS duree
     FROM speed.alertes ORDER BY declenchee_le DESC;"

# D'ou viennent les evenements ecrits, pour comprendre un records_in inattendu.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT collected_at::timestamp(0), count(*), min(ingested_at)::timestamp(0)
     FROM speed.player_count_events GROUP BY collected_at ORDER BY 1 DESC LIMIT 8;"
```

Cette dernière requête est celle qui a révélé qu'une collecte du 20/08 avait
attendu sept jours dans Kafka avant d'être écrite (OBS-47).

---

# Session 6 (suite), 27 août 2026 : construction de la couche Bronze

## Phase 7. Constat de la perte (diagnostic)

```bash
# La couche Bronze est-elle implementee quelque part ? Non.
grep -rniE "boto3|s3\.|bucket|bronze" --include=*.py --include=*.sql --include=*.yml .

# Que garde reellement le producteur de la reponse Steam ?
sed -n '/^def interroger_steam/,/^def main/p' ingestion/steam_producer.py
# Un entier est extrait, le reste est jete dans la ligne suivante.

# Retention Kafka : 168 heures. Une fenetre, pas un archivage, et le message
# transporte est deja transforme.
grep -nE "RETENTION" docker-compose.yml
```

## Phase 8. Mise en place (procédure reproductible)

```bash
# Le schema est monte a l'initialisation en 15_, apres le script Silver en 10_
# qui cree les roles auxquels bronze accorde des droits.
# Sur une instance deja demarree, les scripts d'init ne rejouent pas :
docker exec -i gamelens-postgres psql -U gamelens_app -d gamelens \
    -v ON_ERROR_STOP=1 < sql/schema_bronze.sql

# Verification des objets crees.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "\dt bronze.*"
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "\dv bronze.*"
```

## Phase 9. Vérification sur la plateforme réelle (procédure)

```bash
# Un cycle d'ingestion alimente Bronze sans action particuliere.
docker exec gamelens-airflow-scheduler airflow dags trigger \
    gamelens_ingestion_temps_reel --run-id bronze-01

docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT source, count(*), count(*) FILTER (WHERE exploitable) AS ok,
          count(*) FILTER (WHERE NOT exploitable) AS rejets
     FROM bronze.reponses_brutes GROUP BY source;"

# Ce qui est reellement conserve.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT identifiant, jsonb_pretty(charge) FROM bronze.reponses_brutes
    WHERE source = 'steam_appdetails' ORDER BY reponse_id LIMIT 1;"

# Collecte tarifaire, second point d'appel archive.
docker exec gamelens-airflow-scheduler python -c \
  "from steam_prices import collecter_et_tracer; print(collecter_et_tracer())"
```

## Phase 10. Test du chemin de rejet, par le code de production (procédure)

Le chemin qui compte est celui de l'échec, et il ne se teste pas en simulation
seule. Appel réel sur un identifiant inexistant, avec la gestion d'erreur
copiée de `cycle()` :

```bash
docker exec gamelens-airflow-scheduler python -c "
import logging, requests
from datetime import UTC, datetime
from bronze import archive
from steam_producer import interroger_steam, SOURCE_BRONZE
log = logging.getLogger('essai'); logging.basicConfig(level=logging.WARNING)
session = requests.Session(); instant = datetime.now(UTC).replace(microsecond=0)
with archive(log) as depot:
    for appid in (999999999, 413150):
        try:
            releve = interroger_steam(session, appid)
        except requests.RequestException as exc:
            depot.enregistrer(SOURCE_BRONZE, appid, instant,
                              motif_rejet=f'{type(exc).__name__}: {exc}'[:500])
            continue
        depot.enregistrer(SOURCE_BRONZE, appid, instant, charge=releve.charge,
                          statut_http=releve.statut_http, motif_rejet=releve.motif_rejet)
"
# Constat : Steam repond 404 pour un appid inconnu, pas 200 avec result != 1
# comme le commentaire du code l'affirmait (OBS-53).
```

Piège rencontré, déjà connu (INC-002) : `docker exec -e PYTHONPATH=/opt/...`
depuis Git Bash fait réécrire le chemin par MSYS et le module devient
introuvable. Le conteneur porte déjà la bonne valeur, il suffit de ne pas
passer le drapeau.

## Phase 11. Sécurité et volumétrie (procédure)

```bash
# L'immuabilite de l'archive se verifie en tentant l'interdit, pas en lisant
# les GRANT. 20 cas parametres, contre 13 avant Bronze.
POSTGRES_HOST=localhost POSTGRES_PORT=5433 python -m pytest tests/test_securite_roles.py -q

# Volumetrie mesuree, pour trancher l'objection de volume par un chiffre.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT source, count(*), pg_size_pretty(sum(pg_column_size(charge))::bigint),
          round(avg(pg_column_size(charge))) AS octets_moyens
     FROM bronze.reponses_brutes GROUP BY source;"
# 78 octets par frequentation, 238 par tarif, soit environ 41 Mo par an.
```

---

# Session 6 (fin), 27 août 2026 : mesures pour la feuille de route

Toutes ces requêtes servent à chiffrer la feuille de route d'exploitation
(C4.3.2) plutôt qu'à l'estimer. Elles sont reproductibles telles quelles.

## Phase 12. Volumétrie et croissance (diagnostic)

```bash
# Taille par table, tous schemas confondus.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT schemaname, relname, pg_size_pretty(pg_total_relation_size(relid)),
          n_live_tup FROM pg_stat_user_tables WHERE n_live_tup > 0
    ORDER BY pg_total_relation_size(relid) DESC;"

# Comparaison base metier / base de metadonnees Airflow.
docker exec gamelens-postgres psql -U gamelens_app -d postgres -c \
  "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database
    WHERE datname IN ('gamelens','airflow');"
# gamelens 8,6 Mo ; airflow 12 Mo. Le second est le premier poste de croissance.

# Detail cote Airflow, pour comprendre d'ou vient le volume.
docker exec gamelens-postgres psql -U airflow -d airflow -c \
  "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)), n_live_tup
     FROM pg_stat_user_tables WHERE n_live_tup > 0
    ORDER BY pg_total_relation_size(relid) DESC LIMIT 8;"
```

## Phase 13. Coût Snowflake (diagnostic)

```bash
docker compose --profile outillage run --rm snowflake-cli python -c "
from connexion import connexion
conn = connexion(avec_contexte=False)
with conn.cursor() as cur:
    cur.execute('''SELECT warehouse_name, round(sum(credits_used), 4)
                     FROM snowflake.account_usage.warehouse_metering_history
                    GROUP BY 1 ORDER BY 2 DESC''')
    for l in cur.fetchall(): print(l)
conn.close()
"
# GAMELENS_WH 0,5805 ; COMPUTE_WH 0,4372 ; CLOUD_SERVICES_ONLY 0,0004
# L'entrepot par defaut, jamais configure, pese 43 % de la depense (OBS-57).
```

Attention : cette commande passe par `docker compose run`, qui **recrée les
conteneurs dont dépend le service** si le fichier compose a changé depuis leur
démarrage. Le conteneur PostgreSQL a ainsi été recréé au passage. Sans
conséquence, le volume persiste, mais à savoir avant de la lancer en
exploitation.

## Phase 14. Durées d'incident (diagnostic)

```bash
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "SELECT regle, severite, count(*),
          max(coalesce(resolue_le, now()) - declenchee_le) AS duree_max,
          avg(coalesce(resolue_le, now()) - declenchee_le) AS duree_moyenne
     FROM speed.alertes GROUP BY regle, severite ORDER BY 4 DESC;"
# fraicheur_frequentation : 6 j 20 h 27 min au maximum.
```

## Phase 15. Vérification des procédures prescrites (procédure)

Une feuille de route qui prescrit des commandes non éprouvées ne vaut rien.
Les deux commandes d'exploitation ont donc été exécutées avant d'être écrites.

```bash
# Rejeu d'une journee passee par parametre, sans toucher au code.
docker exec gamelens-airflow-scheduler airflow dags trigger \
    gamelens_promotion_gold --conf '{"jour": "2026-08-26"}' --run-id rejeu-jour-passe
# Verification que le parametre a bien ete pris en compte :
docker exec gamelens-airflow-scheduler sh -c \
  'cat "/opt/airflow/logs/dag_id=gamelens_promotion_gold/run_id=rejeu-jour-passe/task_id=verifier_fraicheur_silver/attempt=1.log"'
# -> parameters: ('2026-08-26',) puis refus de la porte de fraicheur, la
#    journee etant reellement vide. Comportement attendu.

# Purge des metadonnees Airflow, en simulation.
docker exec gamelens-airflow-scheduler airflow db clean \
    --clean-before-timestamp "2026-05-29" --dry-run --yes
# -> parcourt chaque table et rend le decompte, sans rien supprimer.
```

---

# Session 7, 27 août 2026 : documentation technique et dictionnaire généré

## Phase 16. Mesurer avant de documenter (diagnostic)

```bash
# Combien d'objets et de colonnes sont reellement decrits ?
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -tAc \
  "SELECT count(*) FILTER (WHERE d.description IS NOT NULL) || ' / ' || count(*)
     FROM information_schema.columns c
     JOIN pg_class pc ON pc.relname = c.table_name
     JOIN pg_namespace n ON n.oid = pc.relnamespace AND n.nspname = c.table_schema
     LEFT JOIN pg_description d ON d.objoid = pc.oid AND d.objsubid = c.ordinal_position
    WHERE c.table_schema IN ('speed','mart','bronze') AND pc.relkind = 'r';"
# Avant : 7 / 126.  Apres : 78 / 78 (colonnes de tables).

# Lister nommement ce qui manque, plutot que de compter.
# Meme requete avec : AND d.description IS NULL
```

## Phase 17. Enrichir les schémas (procédure)

Les descriptions sont écrites en SQL, dans les fichiers de `sql/`, sous forme de
`COMMENT ON COLUMN`. `COMMENT ON` étant idempotent et non destructif, les
fichiers se rejouent sans risque sur une base déjà initialisée :

```bash
for f in schema_silver_speed schema_gold schema_supervision schema_bronze; do
  docker exec -i gamelens-postgres psql -U gamelens_app -d gamelens < sql/${f}.sql
done

# Cote Snowflake, fichier SEPARE : le schema contient des CREATE OR REPLACE
# TABLE et ne peut pas etre rejoue sans detruire la couche de demonstration.
docker compose --profile outillage run --rm snowflake-cli \
    python entrepot/executer_sql.py sql/commentaires_gold_snowflake.sql
```

## Phase 18. Générer et vérifier le dictionnaire (procédure)

```bash
# Generation.
python outils/generer_dictionnaire.py                      # PostgreSQL
docker compose --profile outillage run --rm snowflake-cli \
    python outils/generer_dictionnaire.py --cible snowflake

# Verification, mode utilise par la CI : ne rien ecrire, comparer, sortir en 1.
python outils/generer_dictionnaire.py --verifier
```

Éprouvé dans les deux sens avant d'être branché sur la CI :

```bash
# Negatif : on simule un schema modifie sans regeneration.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "ALTER TABLE speed.alertes ADD COLUMN colonne_de_test text;
   COMMENT ON COLUMN speed.alertes.colonne_de_test IS 'Colonne de test.';"
python outils/generer_dictionnaire.py --verifier
# ECHEC : ... ne correspond plus au catalogue.  321 dans le depot, 322 attendues.
# code de sortie 1

docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c \
  "ALTER TABLE speed.alertes DROP COLUMN colonne_de_test;"
python outils/generer_dictionnaire.py --verifier   # OK, code 0
```

## Phase 19. Montage nécessaire côté conteneur (procédure)

Le générateur Snowflake tourne dans le conteneur d'outillage et doit écrire dans
le dépôt. `docker-compose.yml` monte donc `./outils` en lecture seule et
`./docs/annexes` **en écriture**, seul point du projet où un conteneur écrit
dans l'arborescence versionnée.

---

# Session 8, 27 août 2026 : dbt sur Snowflake

## Phase 20. Reconnaissance avant de rien écrire (diagnostic ponctuel)

```bash
# Le repertoire dbt existe-t-il, et l'outillage sait-il deja faire tourner dbt ?
ls -la dbt/
docker compose --profile outillage run --rm --no-deps snowflake-cli dbt --version
# Core 1.12.2, plugin snowflake 1.12.0 : deja installes, jamais invoques.

# Quels champs d'authentification l'adaptateur accepte-t-il reellement ?
# Question tranchee par l'introspection plutot que par la documentation.
docker compose --profile outillage run --rm --no-deps snowflake-cli python -c "
from dbt.adapters.snowflake.connections import SnowflakeCredentials as C
import dataclasses
for f in dataclasses.fields(C): print(f.name)"
# private_key ET private_key_path existent : les deux modes de connexion.py
# sont transposables tels quels.
```

## Phase 21. Amorcer le projet dbt (procédure)

```bash
# DBT_PROJECT_DIR manquait dans l'image : dbt cherchait /projet/dbt_project.yml.
# Ajoute au Dockerfile a cote de DBT_PROFILES_DIR, puis reconstruction.
docker compose --profile outillage build snowflake-cli

# Resolution du paquet dbt_utils. Ecrit dbt/package-lock.yml, qui EST versionne :
# c'est lui qui rend la resolution reproductible sur le runner.
docker compose --profile outillage run --rm --no-deps snowflake-cli dbt deps

# Analyse hors connexion : valide le YAML et le graphe, ne touche pas Snowflake.
docker compose --profile outillage run --rm --no-deps snowflake-cli dbt parse

# Inventaire de ce qui a ete declare, pour verifier le compte avant d'executer.
docker compose --profile outillage run --rm --no-deps snowflake-cli \
  dbt ls --resource-type test
# 29 tests, 1 modele, 4 sources.
```

## Phase 22. Première exécution réelle (procédure)

```bash
# Connexion. Lecture seule, ne cree rien.
docker compose --profile outillage run --rm --no-deps snowflake-cli dbt debug
# All checks passed!

# Les 29 contrats sur la couche Gold de demonstration. Lecture seule egalement :
# un dbt test ne fait que des SELECT tant que store_failures n'est pas active.
docker compose --profile outillage run --rm --no-deps snowflake-cli dbt test
# PASS=29 WARN=0 ERROR=0 SKIP=0 en 7,12 s
```

## Phase 23. Éprouver les deux filets ensemble (procédure)

```bash
# La recette complete sur base jetable, dbt compris : 10 etapes, 3 tests negatifs.
docker compose --profile outillage run --rm --no-deps snowflake-cli \
  python entrepot/recette_ci.py
# 5. Materialisation des modeles dbt      -> 1 modele, droits et commentaire preserves
# 6. Contrats dbt sur donnees saines      -> 29 contrats, 0 violation
# 9. Controles applicatifs EN ECHEC       -> 4 violations detectees
# 10. Contrats dbt EN ECHEC               -> 5 contrats, exactement ceux attendus
# Recette au vert en 97 s.
```

## Phase 24. Les deux tests négatifs sur la vue (diagnostic ponctuel)

Le but n'est pas de vérifier que la configuration marche, ce que la phase
précédente montre déjà, mais que **l'assertion sait échouer**. Chacun de ces
deux essais retire une ligne du modèle, relance la recette, et remet la ligne.

```bash
# 1. Sans la configuration grants.
#    Attendu : la vue perd tous ses droits au profit du seul proprietaire.
sed -i '/grants={"select"/d' dbt/models/gold/v_popularity_dashboard.sql
docker compose --profile outillage run --rm --no-deps snowflake-cli \
  python entrepot/recette_ci.py
# La vue reconstruite par dbt n'accorde plus rien a GAMELENS_DASHBOARD_VIEWER.
# Beneficiaires trouves : ACCOUNTADMIN.
git checkout dbt/models/gold/v_popularity_dashboard.sql

# 2. Sans persist_docs.
#    Attendu : la vue perd son COMMENT, donc le dictionnaire genere divergerait.
sed -i '/persist_docs=/d' dbt/models/gold/v_popularity_dashboard.sql
docker compose --profile outillage run --rm --no-deps snowflake-cli \
  python entrepot/recette_ci.py
# La vue reconstruite par dbt a perdu son COMMENT.
git checkout dbt/models/gold/v_popularity_dashboard.sql
```

## Phase 25. Basculer la vue de démonstration sous dbt (procédure)

La vue de la base `gamelens` était encore celle du script SQL. La faire produire
par dbt lève l'incohérence, mais remplace un objet vivant : les deux
vérifications de la phase 24 sont ce qui rend l'opération sûre.

```bash
# Avant : verifier qu'aucun consommateur direct n'existe cote Snowflake.
grep -rn "v_popularity_dashboard" --include=*.py --include=*.json .
# La seule occurrence en CI vise l'homonyme PostgreSQL, pas la vue Snowflake.

docker compose --profile outillage run --rm --no-deps snowflake-cli dbt run
# OK created sql view model mart.v_popularity_dashboard

# Apres : le catalogue n'a pas bouge, donc l'annexe generee reste valide.
docker compose --profile outillage run --rm snowflake-cli \
  python outils/generer_dictionnaire.py --cible snowflake --verifier
# OK : docs/annexes/dictionnaire_gold_snowflake.md est a jour (89 lignes).

# Et les droits sont intacts sur la base de demonstration.
docker compose --profile outillage run --rm --no-deps snowflake-cli python -c "
import sys; sys.path.insert(0, 'entrepot')
from connexion import connexion
c = connexion()
with c.cursor() as cur:
    cur.execute('SHOW GRANTS ON VIEW mart.v_popularity_dashboard')
    for l in cur.fetchall(): print(f'  {l[1]:<12} -> {l[5]}')
c.close()"
#   OWNERSHIP    -> ACCOUNTADMIN
#   SELECT       -> GAMELENS_DASHBOARD_VIEWER
```

## Phase 26. Normaliser les fins de ligne avant de committer (procédure)

À faire après toute modification de fichier écrite depuis Python sur ce poste.
Sans cela, le diff présente des fichiers entièrement réécrits (OBS-68).

```bash
python - <<'FIN'
import subprocess
from pathlib import Path
CRLF, LF = b"\r\n", b"\n"
for c in subprocess.run(["git","diff","--name-only"],capture_output=True,text=True).stdout.split():
    r = subprocess.run(["git","show",f"HEAD:{c}"],capture_output=True)
    attendu = "CRLF" if CRLF in r.stdout else "LF"
    brut = Path(c).read_bytes()
    if ("CRLF" if CRLF in brut else "LF") != attendu:
        Path(c).write_bytes(brut.replace(CRLF,LF) if attendu=="LF" else brut.replace(LF,CRLF))
FIN
git diff --stat   # doit refleter le changement reel, pas la reecriture du fichier
```

## Bilan de session

| Vérification | Commande | Résultat |
|---|---|---|
| Contrats dbt, couche de démonstration | `dbt test` | 29 PASS, 7,12 s |
| Recette complète, base jetable | `recette_ci.py` | 10 étapes, 97 s en local, 82 s sur le runner |
| Échecs dbt attendus | étape 10 | 5 nommés, 0 surnuméraire |
| Concordance des deux filets | étapes 9 et 10 | applicatif 4, dbt 5 |
| Tests unitaires | `pytest tests` | 39 passed |
| Chaîne complète | run 33080391892 | 6 étages verts |

---

# Session 9, 31 août 2026 : contrôle de cohérence

Aucune brique construite ce jour-là. Ces commandes servent à confronter ce que
la documentation affirme à ce que le dépôt et les bases contiennent. Elles sont
reproductibles et méritent d'être rejouées avant la soutenance.

## Phase 27. Vérifier que tout chemin cité existe (procédure)

```bash
python - <<'FIN'
import re
from pathlib import Path
MOTIF = re.compile(r"`([a-zA-Z0-9_./-]+\.(?:py|sql|md|yml|yaml|json|txt))`")
absents = {}
for doc in list(Path("docs").rglob("*.md")) + [Path("CLAUDE.md"), Path("README.md")]:
    for n, ligne in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        for c in MOTIF.findall(ligne):
            if "/" in c and not Path(c).exists():
                absents.setdefault(c, []).append(f"{doc}:{n}")
print(absents or "Tous les chemins cites existent.")
FIN
# 31/08 : un seul, sql/test_schema_gold.sql, dont l'absence est deja documentee.
```

## Phase 28. Vérifier que tout renvoi désigne une entrée définie (procédure)

Les documents se citent entre eux par identifiant : OBS-, TS-, TDBT-, DA-, V-,
INC-. Un renvoi vers une entrée inexistante ne se voit pas à la lecture.

```bash
# Compare l'ensemble des identifiants CITES a l'ensemble des identifiants
# DEFINIS, un identifiant etant defini quand il ouvre un titre markdown.
# 31/08 : 147 definis, 147 cites, aucun orphelin.
```

## Phase 29. Confronter les chiffres annoncés au dépôt (procédure)

```bash
grep -c "^## T[A-Z]*-[0-9]" docs/cahier_recettes.md   # cas de recette numerotes
grep -c "^## DA-" docs/documentation_technique.md      # decisions d architecture
ls -1 dags/*.py | wc -l                                # DAG
wc -l docs/annexes/*.md                                # dictionnaires generes
python -m pytest tests -q --collect-only | tail -1     # tests unitaires
```

Le seul écart trouvé portait sur des volumes de données, et il était
structurel : `CLAUDE.md` annonçait « 15 faits popularité, 45 faits prix » sans
date, sur une couche alimentée chaque nuit. Un chiffre vivant cité sans date
est faux par construction. Corrigé en datant la mesure.

## Phase 30. Comparer les deux couches Gold (diagnostic ponctuel)

C'est ce contrôle qui a révélé V-12. À rejouer avant toute démonstration.

```bash
# Cote PostgreSQL, alimente chaque nuit par le DAG.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -tAc \
  "SELECT (SELECT count(*) FROM mart.dim_games) || ' jeux, '
       || (SELECT count(*) FROM mart.fact_popularity_history) || ' faits, '
       || (SELECT count(*) FROM mart.fact_prices) || ' tarifs'"
# 31/08 : 15 jeux, 45 faits, 120 tarifs

# Cote Snowflake, charge a la main.
docker compose --profile outillage run --rm --no-deps snowflake-cli python -c "
import sys; sys.path.insert(0, 'entrepot')
from connexion import connexion
c = connexion()
with c.cursor() as cur:
    for t in ('dim_games','fact_popularity_history','fact_prices'):
        cur.execute(f'SELECT count(*) FROM mart.{t}')
        print(t, cur.fetchone()[0])
    cur.execute('SELECT max(day) FROM mart.fact_popularity_history')
    print('derniere journee :', cur.fetchone()[0])
c.close()"
# 31/08 : 15, 30, 75, derniere journee 2026-08-20, soit 11 jours de retard.

# Et l indicateur de supervision ne voit que la premiere branche.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens \
  -c "SELECT * FROM speed.v_indicateur_gold"
# retard_jours = 0, alors que Snowflake accuse 11 jours. C est V-13.
```

## Phase 31. Vérifier une hypothèse plutôt que la déduire (diagnostic ponctuel)

L'absence de DAG vers Snowflake semblait s'expliquer par l'isolation des
dépendances (DA-08). Cette commande a démenti l'explication en une seconde.

```bash
docker exec gamelens-airflow-scheduler python -c "
from importlib.metadata import distributions
for d in sorted(distributions(), key=lambda x: x.metadata['Name'] or ''):
    n = d.metadata['Name'] or ''
    if 'snowflake' in n.lower() or n.lower() in ('pandas', 'pyarrow'):
        print(f'  {n} {d.version}')"
# apache-airflow-providers-snowflake 6.10.0
# snowflake-snowpark-python 1.47.0
# snowflake-connector-python 4.0.0
# pandas 2.3.3, pyarrow 18.1.0
#
# Tout est deja la, herite de l image de base. Voir OBS-69.
```

## Phase 32. Relever le cycle de vie des alertes après un arrêt (procédure)

```bash
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -c "
SELECT regle, declenchee_le::timestamp(0), resolue_le::timestamp(0),
       (resolue_le - declenchee_le)::interval(0) AS duree, valeur, seuil
FROM speed.alertes WHERE declenchee_le::date = CURRENT_DATE
ORDER BY declenchee_le;"
# 31/08 : 5 alertes ouvertes a 08:25:07 apres 4 jours d arret,
# 4 refermees a 08:30:01 et la cinquieme a 08:45:01. Voir TSUP-06.
```

## Phase 33. Réappliquer un commentaire corrigé (procédure)

Les scripts de `sql/` ne rejouent pas sur une instance deja initialisee. Toute
correction de `COMMENT ON` doit donc etre appliquee a la main, puis le
dictionnaire regenere, sinon la CI echoue sur la comparaison.

```bash
docker exec -i gamelens-postgres psql -U gamelens_app -d gamelens \
  -v ON_ERROR_STOP=1 <<'FIN'
COMMENT ON VIEW speed.v_indicateur_gold IS '...texte corrige...';
FIN

docker compose --profile outillage run --rm snowflake-cli \
  python outils/generer_dictionnaire.py --cible postgres
# genere (321 lignes, 31/08/2026 09:01 UTC)
```

## Bilan de session

| Contrôle | Résultat |
|---|---|
| Chemins de fichiers cités | 1 absent, déjà documenté comme tel |
| Renvois croisés | 147 cités, 147 définis, 0 orphelin |
| Comptes vérifiables (cas, DA, V, DAG, dictionnaires, étages CI, tests) | tous conformes |
| Volumes de données annoncés | **périmés**, non datés, corrigés |
| Affirmations au futur dans le code | **2 devenues fausses**, corrigées |
| Cohérence interne de `CLAUDE.md` | **une contradiction**, corrigée |
| Schéma d'architecture | **faux sur la promotion Gold**, corrigé |

---

# Session 10, 31 août 2026 : ordonnancement de la promotion Snowflake

## Phase 34. Ouvrir Snowflake à l'ordonnanceur (procédure)

Trois choses manquaient aux conteneurs Airflow : le code de la promotion, la
clef privée, et les variables de connexion. Ajoutées dans `docker-compose.yml`,
au bloc commun `x-airflow-commun`.

```yaml
    PYTHONPATH: /opt/gamelens/ingestion:/opt/gamelens/supervision:/opt/gamelens/entrepot
    SNOWFLAKE_ACCOUNT: ${SNOWFLAKE_ACCOUNT:-}
    SNOWFLAKE_USER: ${SNOWFLAKE_USER:-}
    SNOWFLAKE_PRIVATE_KEY_PATH: /opt/gamelens/secrets/snowflake_key.p8
  volumes:
    - ./entrepot:/opt/gamelens/entrepot:ro
    - ./secrets:/opt/gamelens/secrets:ro
```

Le chemin de la clef est ABSOLU et non celui de `.env`, qui est relatif au
répertoire de travail. Une tâche Airflow ne garantit pas lequel c'est.

```bash
docker compose config --quiet        # valide le fichier avant de recreer
docker compose up -d airflow-scheduler airflow-dag-processor \
                    airflow-apiserver airflow-triggerer
```

## Phase 35. Éprouver l'exécution avant d'écrire l'orchestration (procédure)

Étape à ne pas sauter. Elle sépare un problème d'exécution d'un problème
d'orchestration, et elle a répondu à la seule vraie inconnue : le code
fonctionne-t-il sur la version de Snowpark que porte l'image Airflow, 1.47.0,
alors que la chaîne d'intégration éprouve la 1.54.0 ?

```bash
MSYS_NO_PATHCONV=1 docker exec gamelens-airflow-scheduler \
  python /opt/gamelens/entrepot/snowpark_promotion.py
# 165 lignes fusionnees, 15 lignes de classement, MERGE sur GAMELENS_WH.
```

`MSYS_NO_PATHCONV=1` est obligatoire depuis Git Bash, sinon le chemin devient
`/opt/airflow/C:/Program Files/Git/opt/...`. C'est INC-002.

## Phase 36. Diagnostiquer la panne de l'interface (diagnostic ponctuel)

Douze minutes après la phase 34, l'interface web ne démarrait plus.

```bash
# Le journal nommait le fichier fautif entre parentheses :
#   cannot import name 'FlaskApi' from 'connexion'
#   (/opt/gamelens/entrepot/connexion.py)

# 1. Le paquet masque existe-t-il vraiment ?
docker exec gamelens-airflow-scheduler python -c \
  "from importlib.metadata import version; print(version('connexion'))"
# 2.14.2

# 2. Qui depend de ce nom chez nous ?
grep -rn "^from connexion import" --include=*.py .
# cinq fichiers, tous dans entrepot/

# 3. Quels conteneurs sont touches ?
docker ps --format "{{.Names}}\t{{.Status}}" | grep airflow
# scheduler sain, api-server en redemarrage permanent
```

Correction retenue, renommer plutôt que contourner. Voir INC-009.

```bash
git mv entrepot/connexion.py entrepot/connexion_snowflake.py
# puis les cinq imports, puis :
docker compose restart airflow-apiserver airflow-scheduler airflow-dag-processor
docker exec gamelens-airflow-scheduler airflow dags list-import-errors
# No data found
```

## Phase 37. Mettre en service et éprouver le DAG (procédure)

```bash
# L'analyseur ne rescanne le dossier que toutes les 5 minutes.
docker exec gamelens-airflow-scheduler airflow dags reserialize
docker exec gamelens-airflow-scheduler airflow dags list | grep gamelens

# Positif.
docker exec gamelens-airflow-scheduler airflow dags trigger gamelens_promotion_snowflake

# Negatif : une journee sans donnee, la porte doit refuser.
MSYS_NO_PATHCONV=1 docker exec gamelens-airflow-scheduler \
  airflow dags trigger gamelens_promotion_snowflake --conf '{"jour": "2020-01-01"}'
```

En Airflow 3, `airflow dags list-runs` n'accepte plus la syntaxe d'Airflow 2.
L'état se lit directement dans la base de métadonnées, qui est sur la **même**
instance PostgreSQL que la couche Silver.

```bash
docker exec gamelens-postgres psql -U airflow -d airflow -c "
SELECT dr.state AS run, ti.task_id, ti.state AS tache, ti.try_number
FROM dag_run dr JOIN task_instance ti ON ti.run_id=dr.run_id AND ti.dag_id=dr.dag_id
WHERE dr.dag_id='gamelens_promotion_snowflake' ORDER BY ti.start_date DESC;"
```

Résultat du test négatif : `verifier_fraicheur_silver` en `failed` après
3 tentatives, les deux tâches suivantes en `upstream_failed`, jamais exécutées.

Le journal d'une tâche se lit depuis le conteneur, jamais depuis l'hôte : les
noms de dossier contiennent des `:`, illisibles par un client Windows.

```bash
MSYS_NO_PATHCONV=1 docker exec gamelens-airflow-scheduler bash -c \
  "find /opt/airflow/logs -path '*promotion_snowflake*' -name '*.log' -newermt '-8 minutes'"
```

## Phase 38. Éprouver la règle de supervision dans les deux sens (procédure)

La règle `composant_muet` a été étendue au nouveau composant. Elle se teste sans
attendre 26 heures, en réduisant la fenêtre pour simuler une absence.

```bash
# Positif : fenetres reelles, les quatre composants ont tourne. Attendu 0.
docker exec gamelens-postgres psql -U gamelens_app -d gamelens -tAc "
SELECT count(*) FROM (VALUES ('steam_producer', INTERVAL '24 hours'),
                             ('kafka_to_postgres', INTERVAL '24 hours'),
                             ('steam_prices', INTERVAL '26 hours'),
                             ('snowpark_promotion', INTERVAL '26 hours')) AS a(composant, fenetre)
WHERE NOT EXISTS (SELECT 1 FROM speed.pipeline_runs r
                  WHERE r.component=a.composant AND r.started_at > now() - a.fenetre)"
# 0

# Negatif : fenetre d une seconde sur snowpark_promotion. Attendu 1.
# Meme requete, INTERVAL '1 second' sur la derniere ligne.
# 1
```

## Phase 39. Comparer les deux couches Gold après ordonnancement (procédure)

Même contrôle qu'en phase 30, qui avait révélé V-12. À rejouer avant toute
démonstration.

```bash
docker exec gamelens-postgres psql -U gamelens_app -d gamelens \
  -c "SELECT * FROM speed.v_indicateur_gold"
# retard_jours = 0

docker compose --profile outillage run --rm --no-deps snowflake-cli python -c "
import sys; sys.path.insert(0, 'entrepot')
from connexion_snowflake import connexion
c = connexion()
with c.cursor() as cur:
    cur.execute('SELECT max(day), current_date - max(day) FROM mart.fact_popularity_history')
    print('derniere journee, retard :', cur.fetchone())
c.close()"
# (datetime.date(2026, 8, 31), 0)
```

Noter l'import : `connexion_snowflake` et non `connexion`, depuis INC-009.

## Bilan de session

| Vérification | Résultat |
|---|---|
| Promotion exécutée dans le conteneur Airflow | 165 lignes fusionnées, Snowpark 1.47 |
| Runs du DAG | 3 en succès, dont 1 planifié, 38 à 40 s |
| Retard de la couche Snowflake | 11 j → **0 j** |
| Test négatif de la porte | `failed` après 3 essais, aval `upstream_failed` |
| Règle `composant_muet` | 0 en positif, 1 en négatif |
| Incident rencontré | INC-009, interface web indisponible 12 min |
| Tests unitaires | 39 passed |

