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
