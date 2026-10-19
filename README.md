# GameLens, infrastructure data

Plateforme de données interne de **Kestrel Interactive**, éditeur de jeux vidéo
indépendant. Elle unifie catalogue, popularité jouée, popularité diffusée et
tarification des titres du portefeuille et d'un panel concurrent suivi.

Ce dépôt porte le **Bloc 4** de la certification RNCP39586 (Concevoir et opérer
une infrastructure data). Les Blocs 1 à 3 ont posé l'architecture, l'analyse et
le pilotage ; ce dépôt en est la réalisation exécutable.

## Architecture

Medallion croisée avec une architecture Lambda, reprise du Bloc 1.

```
   Steam Web API           Twitch Helix            Steam appdetails
   GetNumberOf             /streams                price_overview
   CurrentPlayers          OAuth client_creds      (tarification)
   (qui joue)              (qui regarde)
        |                       |                        |
        v                       v                        v
   steam_producer.py       twitch_producer.py      steam_prices.py
        |       \               |        \              /      |
        |        +--------------+---------+------------+       |
        |                       |                              |
        |                       v                              |
        |           bronze.reponses_brutes                     |
        |           archive de tout appel,                     |
        |           abouti ou non, sans UPDATE                 |
        |                       |                              |
        v                       v                              |
   Apache Kafka (mode KRaft), DEUX topics separes              |
   gamelens.steam.player_count                                 |
   gamelens.twitch.viewer_count                                |
                    |                                          |
        ingestion/kafka_to_postgres.py                         |
        un seul consumer, abonne aux deux topics,              |
        qui choisit sa table sur le topic d'origine            |
                    |                                          |
                    v                                          v
   PostgreSQL, couche Silver speed (schema speed)
   player_count_events, viewer_count_events, price_snapshots
                 |
        +--------+-----------------------------+
        |                                      |
   DAG gamelens_promotion_gold      DAG gamelens_promotion_snowflake
   02h30 UTC, une journee par run   03h00 UTC, Snowpark, MERGE de
        |                           tout l'historique disponible
        v                                      |
   PostgreSQL, couche Gold                     v
   prototype et reference          Snowflake, couche Gold (schema mart)
   de comparaison                  dim_games, dim_stores, fact_prices,
                                   fact_popularity_history,
                                   v_popularity_dashboard
```

**Deux sources, deux axes.** Steam mesure qui joue, Twitch mesure qui
regarde, et le rapport des deux ne se déduit d'aucun des deux. Les topics sont
**séparés** et non distingués par un type d'événement sur un topic unique : les
deux flux n'ont ni la même cadence de panne ni le même puits, et rejouer les
offsets d'une source ne doit pas rejouer ceux de l'autre. Voir DA-13 dans
`docs/documentation_technique.md`.

**Deux couches Gold, deux DAG, et c'est délibéré.** Snowflake est la cible ;
le prototype PostgreSQL est conservé comme référence de comparaison et comme
repli. Les deux ne sont pas fusionnées dans un seul DAG parce que Snowflake est
un service tiers facturé dont l'indisponibilité ne doit pas emporter la
promotion locale. Leur profondeur diffère et ce n'est pas un défaut : la
promotion PostgreSQL traite une journée par run, la promotion Snowpark rejoue
tout l'historique par MERGE. Voir DA-11 dans `docs/documentation_technique.md`.

La couche Bronze est une table PostgreSQL et non un stockage objet, écart
assumé avec le `Bronze (S3)` annoncé au Bloc 1 : le support change, la propriété
recherchée est la même, et un service tiers de plus n'apportait rien à cette
échelle (17,5 Go par an mesurés le 08/09/2026, 41 Mo avant le raccordement
de Twitch).

## Démarrage

Prérequis : Docker Desktop démarré, Python 3.12.

```powershell
docker compose up -d                 # 7 conteneurs : PostgreSQL, Kafka, 4 Airflow, Grafana
Copy-Item .env.example .env          # puis ajuster si besoin
python -m pip install -r requirements.txt

python ingestion/create_topics.py      # les deux topics, declares explicitement
python ingestion/seed_game_mapping.py  # referentiel des 150 titres suivis
python ingestion/seed_twitch_ids.py    # resolution des identifiants Twitch
python ingestion/steam_producer.py --once
python ingestion/twitch_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 30 --depuis-le-debut
python ingestion/steam_prices.py --once
```

La collecte d'audience est **facultative** : sans `TWITCH_CLIENT_ID` ni
`TWITCH_CLIENT_SECRET` dans `.env`, `twitch_producer.py` journalise et rend 0
sans rien tenter. Le reste de la chaîne fonctionne à l'identique.

Les cinq schémas PostgreSQL (Silver speed, audience Twitch, Bronze, Gold
prototype, supervision) sont appliqués automatiquement au premier démarrage : ils sont
montés dans `docker-entrypoint-initdb.d`. **Ils ne rejouent pas** sur un volume
déjà initialisé ; les appliquer alors à la main par
`docker exec -i gamelens-postgres psql ... < sql/<fichier>.sql`.

**Point de configuration important.** PostgreSQL est publié sur le port hôte
**5433**, pas 5432. Un service PostgreSQL natif occupe fréquemment 5432 sur un
poste Windows et Docker publie alors le port sans effet réel ni message
d'erreur. Voir INC-004 dans `docs/journal_incidents.md`.

**Depuis Git Bash**, préfixer les commandes Docker montant un volume par
`MSYS_NO_PATHCONV=1` et utiliser `pwd -W`. Depuis PowerShell, aucune adaptation
n'est nécessaire.

## Entrepôt Snowflake, dbt et calcul distribué

L'outillage Snowflake vit dans son propre conteneur, jamais dans l'environnement
Python du poste : Snowpark impose `snowflake-connector-python` 4.x, incompatible
avec la version que réclame `dbt-snowflake` 1.8, et l'ingestion épingle
`requests`. Il se lance à la demande, sous le profil `outillage`.

```powershell
docker compose --profile outillage run --rm snowflake-cli `
  python /projet/entrepot/verifier_gold.py
docker compose --profile outillage run --rm snowflake-cli `
  dbt test --project-dir /projet/dbt --profiles-dir /projet/dbt
```

Snowflake **n'applique pas** les contraintes qui portent sur une relation entre
lignes ou entre tables : CHECK, FOREIGN KEY, PRIMARY KEY et UNIQUE sont
déclarées et ignorées, seules celles portées par la colonne elle-même (NOT NULL,
type, longueur) sont appliquées. C'est vérifié empiriquement par
`sql/verify_snowflake_constraints.sql`. L'intégrité est donc reportée hors du
moteur, sur deux filets rejoués à chaque push : les **29 contrats déclaratifs**
de `dbt/models/gold/` et les **8 contrôles applicatifs** de
`entrepot/verifier_gold.py`. Ils ne font pas double emploi, et les deux sont
éprouvés en négatif sur un même jeu de données fautif.

L'authentification se fait par **paire de clés RSA** et non par mot de passe :
Snowflake impose la MFA aux utilisateurs humains, ce qu'un pipeline ne peut pas
satisfaire. La clé privée vit dans `secrets/`, ignorée par git, montée en
lecture seule dans les conteneurs, et n'entre jamais dans une image.

**`sql/schema_gold_snowflake.sql` contient des `CREATE OR REPLACE TABLE` et
nommé la base en dur.** Ne jamais le rejouer sans redirection : il détruirait la
couche de démonstration sans message d'erreur. Passer par
`entrepot/executer_sql.py --base <autre>`.

## Organisation du dépôt

| Chemin | Contenu |
|---|---|
| `config/watchlist.json` | Titres suivis, source du référentiel `game_mapping` |
| `docker-compose.yml` | Composants d'infrastructure locaux |
| `ingestion/` | Pipeline temps réel et tarifaire : deux producers (Steam, Twitch), un consumer abonné aux deux topics, référentiel, topics, archivage Bronze |
| `sql/schema_bronze.sql` | Couche Bronze, archive brute en append only |
| `sql/schema_silver_speed.sql` | Couche Silver speed, PostgreSQL |
| `sql/schema_silver_twitch.sql` | Audience diffusée, table séparée : zéro spectateur est une observation, l'absence n'en est pas une |
| `sql/schema_gold_snowflake.sql` | Couche Gold, cible Snowflake |
| `sql/commentaires_gold_snowflake.sql` | Commentaires des colonnes Snowflake, séparés du schéma qui n'est pas rejouable |
| `sql/schema_gold.sql` | Prototype PostgreSQL du Gold, conservé comme référence |
| `sql/verify_snowflake_constraints.sql` | Vérification empirique des contraintes Snowflake |
| `sql/schema_supervision.sql` | Indicateurs de supervision et journal d'alertes |
| `dags/` | 5 DAG Airflow : ingestion temps réel, promotion PostgreSQL, promotion Snowflake, supervision, battement |
| `entrepot/` | Connexion Snowflake, promotion Snowpark, contrôles d'intégrité et recette de CI |
| `dbt/` | Projet dbt : 4 sources et 1 modèle, 29 contrats déclaratifs au total (25 portés par les sources, 4 par le modèle) |
| `supervision/` | Moteur d'alertes et vérification du tableau de bord |
| `outils/construire_panel.py` | Générateur de `config/watchlist.json` : chaque appid confronté au nom rendu par Steam |
| `outils/generer_dictionnaire.py` | Générateur des dictionnaires de données, depuis le catalogue des bases |
| `outils/generer_schema.py` | Générateur du schéma de données : catalogue et DDL recoupés, puis dessin |
| `outils/diagramme.py` | Rendu du schéma en SVG et PNG, sans moteur de rendu externe |
| `outils/capturer_preuves.py` | Captures datées et rejouables des sorties réelles, vers `docs/preuves/` |
| `outils/generer_support.py` | Générateur du support de soutenance : le Markdown vers le PPTX |
| `outils/visuels.py` | Schémas et graphiques du support, palette de dataviz validée |
| `outils/generer_feuille_jury.py` | Feuille A4 remise au jury : les 31 sous-critères et leur diapositive |
| `docker/grafana/` | Source de données et tableau de bord provisionnés comme code |
| `docker/snowflake/` | Image d'outillage Snowflake, isolée des dépendances d'ingestion |
| `secrets/` | Clé privée Snowflake, ignorée par git |
| `tests/` | Tests automatisés, exécutés par la CI |

## Documentation

| Chemin | Contenu |
|---|---|
| `docs/plan_soutenance.md` | Plan minute de la soutenance, tracé sur les 31 sous-critères de la grille |
| `docs/rapport_analyse.md` | Analyse des besoins et présentation des composants (A4.1) |
| `docs/documentation_technique.md` | Point d'entrée, décisions d'architecture, traçabilité, configuration, sécurité (C4.3.3) |
| `docs/feuille_route_exploitation.md` | Tâches récurrentes, maintenance, points de vigilance (C4.3.2) |
| `docs/cahier_recettes.md` | Cahier de recettes et de tests (C4.4.1) |
| `docs/journal_incidents.md` | Journal d'incidents, format imposé par la grille C4.4.2 |
| `docs/observations.md` | Observations de session : surprises, fausses pistes, arbitrages |
| `docs/commandes_successives.md` | Trace chronologique des commandes réellement exécutées |
| `docs/annexes/` | Dictionnaires de données et schéma en diagramme, GÉNÉRÉS depuis le catalogue |
| `docs/preuves/` | Sorties réelles capturées, avec leur en-tête de provenance |
| `docs/feuille_jury.pdf` | Feuille A4 à imprimer en deux exemplaires, GÉNÉRÉE |
| `docs/support_soutenance.md` | Support de soutenance, diapo par diapo : la SOURCE du PPTX |
| `docs/script_soutenance.md` | Idée générale, objectif de la présentation, et le texte parlé mot pour mot |
| `docs/captures/` | Captures d'écran d'interfaces, déposées à la main |
| `docs/vulgarisation/` | Deux versions vulgarisées du projet, pour un junior et pour un non-spécialiste |

Les dictionnaires de `docs/annexes/` ne s'éditent pas à la main : ils sont
générés par `outils/generer_dictionnaire.py`, et la CI échoue si le fichier
versionné ne correspond plus. Attention à la source exacte, elle n'est pas celle
qu'on suppose : voir « Documentation générée » plus bas.

## Où se trouve la preuve de chaque compétence

| Compétence | Réalisation | Preuve |
|---|---|---|
| C4.2.1, architecture d'entrepôt | Deux couches Gold, Snowflake et PostgreSQL | `sql/schema_gold_snowflake.sql`, `sql/schema_gold.sql`, `sql/verify_snowflake_constraints.sql` |
| C4.2.2, méthode 1, temps réel | Steam et Twitch vers Kafka vers PostgreSQL, idempotent sur les deux topics | `ingestion/`, DAG `gamelens_ingestion_temps_reel` |
| C4.2.2, méthode 2, orchestrateur | Airflow 3.1.8, 5 DAG | `dags/`, http://localhost:8080 |
| C4.2.2, méthode 3, calcul distribué | Snowpark, et non Spark local | `entrepot/snowpark_promotion.py`, DA-04 |
| C4.2.3, CI/CD | 6 étages, base Snowflake jetable, image publiée | `.github/workflows/ci.yml` |
| C4.3.1, supervision | 5 indicateurs SQL, 6 règles, Grafana comme code | `sql/schema_supervision.sql`, `supervision/`, `docker/grafana/` |
| C4.3.2, exploitation | 10 sections, 14 points de vigilance dont 9 ouverts | `docs/feuille_route_exploitation.md` |
| C4.3.3, documentation technique | 13 décisions datées, 2 annexes générées | `docs/documentation_technique.md` |
| C4.4.1, recettes | 70 PASS, 0 partiel, 0 en attente | `docs/cahier_recettes.md` |
| C4.4.2, incident réel | INC-004 retenu, 9 incidents documentés | `docs/journal_incidents.md` |
| A4.1, rapport d'analyse | Coûts mesurés, dépendance fournisseur par composant | `docs/rapport_analyse.md` |

## Supervision

Les indicateurs sont définis en SQL dans `sql/schema_supervision.sql` : fraîcheur
de la donnée, complétude de la collecte, latence du pipeline, fiabilité par
composant, fraîcheur de la couche Gold PostgreSQL. Grafana les affiche, il ne les
calcule pas, ce qui les garde interrogeables par n'importe quel client même si
l'outil est arrêté.

Le moteur d'alertes (`supervision/regles_alertes.py`) évalue six règles, ouvre
une alerte au plus par règle, et la referme automatiquement quand la condition
disparaît. La règle de composant muet porte une fenêtre **par composant** et non
une fenêtre unique : 24 h pour les collectes fréquentes, 26 h pour celles qui ne
tournent qu'une fois par jour, sans quoi un composant quotidien serait déclaré
muet à chaque cycle. Le DAG `gamelens_supervision` l'exécute toutes les
15 minutes et fait échouer son run en présence d'une alerte critique.

```powershell
docker compose up -d grafana
python supervision/regles_alertes.py           # evaluation ponctuelle
python supervision/verifier_tableau_bord.py    # controle des 7 panneaux
```

Interfaces : Airflow sur http://localhost:8080, Grafana sur http://localhost:3000,
compte `admin` / `admin` pour les deux.

**Canal de notification externe, depuis le 07/09/2026.** Les alertes critiques
partent sur un canal Telegram, mesuré à 2 secondes entre le déclenchement et la
réception. Le canal est FACULTATIF : sans `TELEGRAM_BOT_TOKEN` ni
`TELEGRAM_CHAT_ID`, la notification est un no-op qui rend un succès ; un jeton
présent mais injoignable, en revanche, trace un échec. L'asymétrie est voulue et
testée : un dispositif d'alerte ne doit jamais faire tomber la chaîne qu'il
surveille, mais son propre silence ne doit pas être silencieux.

Le DAG `gamelens_battement`, à 8h et 20h, est un témoin séparé qui dénonce
l'arrêt de la supervision : un dispositif qui se surveille lui-même ne prouve
rien.

Ces deux briques referment V-02 et V-07, jusque-là les deux écarts les plus
importants entre cette plateforme et une plateforme exploitée. Ce que leur
absence avait coûté est mesuré : une alerte de fraîcheur était restée ouverte
6 j 20 h en août, sans que personne n'en soit averti.

## Intégration continue

Dépôt : `Mael8zinsou/gamelens-bloc4_0`. Le workflow `.github/workflows/ci.yml`
s'exécute à chaque push et chaque pull request, en six étages : qualité du code,
tests unitaires, intégrité des DAG Airflow, intégration sur infrastructure
jetable, recette de l'entrepôt Snowflake, puis publication de l'image Airflow sur
`ghcr.io` depuis la branche principale uniquement.

L'étage Snowflake applique le même principe que l'étage d'intégration : une base
est créée pour la durée du run, éprouvée, puis supprimée. Il vérifie que le
schéma livré s'applique, que le calcul distribué rend les valeurs attendues, que
le moteur applique toujours les mêmes contraintes et pas d'autres, et que les
deux filets d'intégrité, contrôles applicatifs et contrats dbt, savent échouer
quand les données sont invalides. La couche de démonstration n'est jamais visée :
`entrepot/recette_ci.py` refuse de démarrer si elle l'était.

Trois secrets sont attendus sur le dépôt : `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`
et `SNOWFLAKE_PRIVATE_KEY`, ce dernier portant le contenu PEM de la clef plutôt
qu'un chemin, pour qu'elle ne soit jamais écrite sur le disque du runner.

    gh secret set SNOWFLAKE_PRIVATE_KEY < secrets/snowflake_key.p8

Image publiée : `ghcr.io/mael8zinsou/gamelens-bloc4_0/airflow`, étiquetée `latest`
et par le SHA du commit.

`pytest` lancé à la racine échoue à la collecte, sur un lien symbolique des logs
Airflow qu'un client Windows ne sait pas lire. Lancer `pytest tests`, comme le
fait la CI.

## Pièges d'environnement

Ces points ont tous coûté du temps au moins une fois. Ce qui est déjà couvert
plus haut n'est pas répété : port hôte 5433, `MSYS_NO_PATHCONV=1` depuis Git
Bash, scripts de `sql/` qui ne rejouent pas sur un volume déjà initialisé.

- **Airflow ne tourne pas nativement sous Windows**, il lui faut un POSIX. Le
  conteneur n'est pas un confort, il est obligatoire.
- **Airflow 3 diffère nettement d'Airflow 2** : `api-server` remplace
  `webserver`, `dag-processor` est un service séparé obligatoire, et
  `logical_date` vaut `None` sur un run manuel. Toujours partir du
  `docker-compose.yaml` officiel de la version exacte plutôt que d'un tutoriel
  Airflow 2, qui donnera une configuration qui ne démarre pas. Voir INC-006.
- **Après toute modification d'un DAG**, lancer `airflow dags reserialize` :
  l'analyseur ne rescanne le dossier que toutes les cinq minutes, et l'attente
  passe facilement pour une erreur de code.
- **Les logs Airflow contiennent des `:` dans les noms de dossier**, qu'un
  client Windows ne sait pas lire. Les consulter par `docker exec ... cat`, pas
  depuis l'hôte.
- **`pytest` lancé à la racine échoue à la collecte**, sur le lien symbolique
  `docker/airflow/logs/dag_processor/latest`, qu'un client Windows ne sait pas
  lire non plus. Lancer `pytest tests`, comme le fait la CI. Ce n'est pas une
  régression.
- **`python -m venv` ne fonctionne pas sur ce poste** : le module `venv` de
  l'installation Python est vide. Ne pas chercher pourquoi, passer par un
  conteneur.
- **PostgreSQL et Kafka ne répondent pas à un navigateur**, et c'est normal :
  ils parlent leur protocole binaire sur TCP, pas HTTP, et `curl` y rend
  « Empty reply from server ». Seuls 8080 et 3000 sont des interfaces web.
- **Le chemin de travail contient accents et espaces, et cela ne pose pas de
  problème** à Docker Desktop. L'hypothèse a été testée puis écartée, voir
  INC-002 : ne pas la reprendre au premier symptôme venu.
- **Le dépôt n'a pas de `.gitattributes` et mélange LF et CRLF** selon les
  fichiers. Après une édition écrite depuis Python, vérifier que le régime du
  fichier n'a pas changé avant de committer : une conversion involontaire
  présente un fichier entièrement réécrit là où sept lignes ont bougé. Voir
  OBS-68.

## Ce qui ressemble à un défaut et n'en est pas

Chacun de ces choix a l'air d'un oubli. Chacun est délibéré et testé, et
« corriger » l'un d'eux casse quelque chose, parfois en silence.

- **Les quatre ports publiés sont liés à `127.0.0.1`**, pas à `0.0.0.0` :
  `- "127.0.0.1:5433:5432"` et ses trois voisins. Sans adresse de liaison,
  Docker publie sur toutes les interfaces, or le mot de passe de la base est
  dans le dépôt. Rien n'en pâtit : les conteneurs se joignent par le réseau
  Docker, et la CI se connecte depuis le runner en local. Voir OBS-89.
- **`bronze.reponses_brutes` n'accorde ni UPDATE ni DELETE**, pas même à
  `etl_service`. Une archive modifiable n'est plus une archive. Testé par
  TBRZ-04.
- **La tâche Twitch du DAG d'ingestion ne lève jamais**, et sans
  `TWITCH_CLIENT_ID` la collecte est un no-op qui rend un succès. Une source
  facultative ne doit pas casser une chaîne éliminatoire ; son échec est tracé
  dans `speed.pipeline_runs`, où la supervision le relève. Testé par TTWI-05.
- **Le canal Telegram est facultatif de la même façon, mais un jeton présent et
  injoignable trace un échec.** L'asymétrie est voulue : un dispositif d'alerte
  ne doit pas faire tomber la chaîne qu'il surveille, et son propre silence ne
  doit pas être silencieux. Testé par TNOT-04 et TNOT-05.
- **Le consumer est abonné aux DEUX topics** et choisit sa table sur le topic
  d'origine du message. Un topic inconnu lève plutôt que d'être ignoré : écrire
  une audience dans la table de fréquentation serait pire qu'une panne.
- **`entrepot/recette_ci.py` refuse les bases protégées**, `gamelens` en tête,
  et sort en code 1. Laisser `SNOWFLAKE_DATABASE` vide pour obtenir une base
  jetable nommée d'après le run. Ne pas contourner ce refus : c'est lui qui
  empêche la CI de détruire la couche de démonstration.
- **`entrepot/connexion_snowflake.py` ne doit pas être raccourci** en
  `connexion.py`. Ce nom-la masquait le paquet PyPI `connexion`, celui dont
  Airflow se sert pour son authentification, des lors que `entrepot/` figurait
  sur son `PYTHONPATH` : l'interface web cessait de démarrer. Voir INC-009.
- **Un seul modèle de rôles** pour toute la plateforme : `etl_service`,
  `analyst`, `dashboard_viewer`, plus `gamelens_app` comme propriétaire. Les
  rôles `gamelens_etl` et `gamelens_reader` d'une version antérieure ont été
  supprimés, ne pas les réintroduire. Voir OBS-25.
- **Ne pas retirer `grants` ni `persist_docs`** du modèle
  `dbt/models/gold/v_popularity_dashboard.sql`. Sans le premier, la vue perd
  ses droits et le tableau de bord se vide sans erreur ; sans le second, elle
  perd son `COMMENT`, et c'est le contrôle du dictionnaire, à un autre étage de
  la CI, qui échoue sur un message sans rapport. Testés par TDBT-04 et TDBT-05.
- **`dbt/profiles.yml` à deux cibles, `local` et `ci`, et il faut les deux.**
  `dbt-snowflake` refuse `private_key` et `private_key_path` renseignes
  ensemble, et un `env_var()` sur une variable absente rend un champ présent et
  vide, ce qui déclenche ce refus. Ne pas les fusionner.

## Documentation générée : d'où le générateur lit la vérité

Les dictionnaires et le schéma de données de `docs/annexes/` sont **générés,
jamais édités à la main**, et la CI échoue si le fichier versionné ne
correspond plus. Le piège est ailleurs, et il a produit une correction fantôme :
**le générateur ne lit pas les fichiers de `sql/`, il lit le catalogue vivant**,
`obj_description()` côté PostgreSQL et `information_schema` côté Snowflake.

Corriger un `COMMENT ON` dans `sql/` puis régénérer ne change donc rien. Le
chemin réel est en trois temps : éditer le `.sql`, **appliquer** le `COMMENT ON`
à la base, puis régénérer par `python outils/generer_dictionnaire.py`, avec
`--cible snowflake` pour la couche Gold.

`sql/commentaires_gold_snowflake.sql` porte les commentaires de colonnes
Snowflake séparément du schéma, parce que celui-ci contient des
`CREATE OR REPLACE TABLE` et ne peut pas être rejoué. Le réappliquer après toute
recréation du schéma.

Enfin, **la base stocke en UTC et seul l'affichage est converti**, par
`GAMELENS_TIMEZONE` dont le défaut est `Europe/Paris`. Piège associé : ce qui
est formaté par `to_char()` en SQL sort dans le fuseau de la SESSION et échappe
au convertisseur Python. Voir OBS-92.

## État d'avancement

Tous les livrables du Bloc 4 sont écrits, et les trois compétences
éliminatoires sont couvertes par des briques exécutées et vertes en intégration
continue.

Les écarts connus ne sont pas dissimulés : ils sont numérotés dans la section 6
de `docs/feuille_route_exploitation.md`, quatorze points de vigilance dont neuf
restent ouverts. Les incidents réellement vécus sont dans
`docs/journal_incidents.md`, les arbitrages et fausses pistes dans
`docs/observations.md`.
