# GameLens — Bloc 4 (Concevoir et opérer une infrastructure data)

## Contexte

Ce projet est la suite directe des Blocs 1 à 3 de la certification RNCP39586 de Maël Mike ZINSOU
(M2 Data Engineer, Paris YNOV Campus). Fil rouge : **GameLens**, plateforme de données interne
fictive pour **Kestrel Interactive**, éditeur de jeux vidéo indépendant (~15 titres), pensée comme
alternative "build vs buy" à des outils SaaS tiers coûteux (GameDiscoverCo Pro, StreamsCharts Pro).

Le Bloc 4 est une **soutenance orale de 45 min** (30 min de présentation, 15 min d'échange avec un
jury de 2 professionnels), pas un dossier écrit. Contrairement aux Blocs 1 à 3, qui pouvaient rester
une narration cohérente sur le papier, ce bloc exige des briques **réellement construites et testées** :
le jury peut demander "montrez-moi", "pourquoi ce choix plutôt qu'un autre", "que se passe-t-il si X
tombe en panne". Une architecture uniquement décrite ne suffit pas.

**Principe de travail : préférer un composant plus modeste mais réellement testé à un composant
ambitieux mais jamais exécuté.** Documenter les échecs rencontrés et la manière dont ils ont été
résolus est une preuve de compétence, pas un aveu de faiblesse : le référentiel demande explicitement
un incident réel et sa méthode d'investigation (C4.4.2).

## Continuité avec les Blocs 1 à 3 (à respecter, ne pas contredire)

- Architecture Medallion + Lambda hybride : Bronze (S3), Silver batch (Snowflake), Silver speed
  (PostgreSQL), Gold (Snowflake mart). Le compte Snowflake **existe depuis le 20/08/2026**
  (voir la note de calendrier en fin de fichier, réécrite le 31/08). Les deux couches Gold sont
  construites : la cible Snowflake (`sql/schema_gold_snowflake.sql`) et le prototype PostgreSQL
  (`sql/schema_gold.sql`), gardé comme mise au point initiale et référence de comparaison.
  Les deux sont promues par un DAG depuis le 31/08/2026 : `gamelens_promotion_gold` vers
  PostgreSQL à 02h30 UTC, `gamelens_promotion_snowflake` vers Snowflake à 03h00. Elles portent
  donc la même journée la plus récente. Leur PROFONDEUR diffère en revanche, et c'est normal :
  la promotion PostgreSQL traite une journée par run, la promotion Snowpark rejoue tout
  l'historique disponible par MERGE. Mesuré le 31/08/2026 : 4 journées côté Snowflake, 3 côté
  PostgreSQL, qui n'a jamais eu de run pour le 19/08. Ne pas lire cet écart comme un défaut.
  Avant cette date, seul le prototype était ordonnancé et la cible accusait onze jours de
  retard : c'était V-12, refermé, voir DA-11.
- Orchestration batch : Apache Airflow. Temps réel : Apache Kafka (ou toute alternative légère
  équivalente si Kafka est trop lourd à faire tourner en local — à documenter comme un choix assumé).
  Calcul distribué : **Snowpark** (choisi le 19/08/2026 plutôt que PySpark local, pour un calcul
  réellement distribué sur le compute Snowflake plutôt qu'en mode local sur une seule machine,
  plus défendable face au jury sur "en quoi est-ce distribué ?").
- ETL : Python/pandas, dbt, table `game_mapping` pour la résolution d'identifiants cross-plateformes.
  **Point d'architecture Snowflake, vérifié empiriquement le 20/08/2026** : les contraintes
  portées par la colonne elle-même sont appliquées (NOT NULL, type, longueur) ; celles qui
  portent sur une relation entre lignes ou entre tables ne le sont pas (CHECK, FOREIGN KEY,
  PRIMARY KEY, UNIQUE). La formulation antérieure, « seul NOT NULL est appliqué », était
  inexacte : voir les résultats consignés dans `sql/verify_snowflake_constraints.sql`.
  L'intégrité réelle est donc reportée hors du moteur, sur **deux filets rejoués à chaque
  push** : les 29 contrats déclaratifs de `dbt/models/gold/` (`not_null`, `unique`,
  `relationships`, `expression_is_true`, `accepted_values`) et les 8 contrôles applicatifs de
  `entrepot/verifier_gold.py`. Ils ne sont pas redondants : voir OBS-65. C'est un choix
  d'architecture à assumer explicitement à l'oral, pas un oubli. Voir
  `sql/verify_snowflake_constraints.sql` pour la vérification empirique de ce comportement,
  et DA-10 de la documentation technique pour le périmètre exact confié à dbt.
- Conventions de nommage (posées au Bloc 2, 1.3) : préfixe `dim_`/`fact_`, snake_case, clé primaire
  interne UUID indépendante des identifiants sources.
- 4 rôles de sécurité déjà actés : `admin`, `etl_service`, `analyst`, `dashboard_viewer` (déclinés en
  rôles Snowflake `gamelens_etl_service`, `gamelens_analyst`, `gamelens_dashboard_viewer`).
- Schéma Gold (conçu et déclaré, **exécution réelle Snowflake à confirmer côté utilisateur** — pas
  d'accès réseau à Snowflake depuis l'environnement de conception) : `dim_games`, `dim_stores`,
  `fact_prices`, `fact_popularity_history` (grain journalier, colonnes larges, pas de modèle EAV),
  plus une vue `v_popularity_dashboard` et un warehouse `gamelens_wh` dimensionné XS avec
  auto-suspend à 60s pour préserver les crédits d'essai.
- Sources de données : API RAWG (catalogue), Steam Web API (`GetNumberOfCurrentPlayers`, sans auth,
  et `appdetails`/`price_overview` pour la tarification), Twitch API (OAuth).
  **Le scraping GOG n'est plus une source du Bloc 4** : l'arbitrage du Bloc 3 (3.3) l'a sorti du
  périmètre, et la tarification passe donc par l'API Steam. L'incident GOG n'a plus à être rejoué
  pour le C4.4.2 : INC-004, réellement vécu le 19/08/2026, remplit ce rôle. GOG reste en filet
  de sécurité.

## Référentiel Bloc 4 — ce qui doit être livré

**3 compétences éliminatoires (priorité absolue) :**
- **C4.2.1** — Concevoir l'architecture d'entrepôt (schéma de données). ✅ Fait : `sql/schema_gold.sql`,
  exécuté et testé (contraintes CHECK/FK/PK, cloisonnement des rôles vérifié).
- **C4.2.2** — Mettre en place et orchestrer des pipelines temps réel ou asynchrones. Le référentiel
  exige **3 méthodes distinctes** : un pipeline temps réel (SQL/Python), un orchestrateur (Airflow),
  un calcul distribué (Spark). À faire.
- **C4.2.3** — Automatiser l'intégration et le déploiement (CI/CD, DevOps). À faire.

**Autres livrables attendus (non éliminatoires mais notés) :**
- Rapport d'analyse et présentation des composants (A4.1) — peut largement s'appuyer sur le Bloc 1.
- Système de supervision et alertes (C4.3.1).
- Feuille de route d'exploitation (C4.3.2) — tâches, échéances, maintenance, points de vigilance.
- Documentation technique (C4.3.3).
- Cahier de recettes et de tests (C4.4.1). Format retenu : PASS/FAIL vérifié sur un résultat
  attendu, pas seulement "la requête s'exécute sans erreur". Le test d'idempotence de la session 1
  (rejeu des offsets Kafka, 0 inséré sur 15 relus) est le premier cas conforme à ce format.
  Note : `sql/test_schema_gold.sql`, référencé par une version antérieure de ce fichier, n'existe
  pas dans le dépôt.
- Méthodologie d'investigation et de traitement d'un incident réel (C4.4.2).

## État d'avancement

Mis à jour le 31/08/2026 en fin de session 10 (DAG de promotion Snowflake).

| Élément | Statut |
|---|---|
| Dépôt git dédié, structure, .gitignore | ✅ Fait (dépôt local, décision 2b) |
| Socle Docker (PostgreSQL 16 + Kafka 3.9 KRaft) | ✅ 6 conteneurs, tous *healthy* |
| **Couche Bronze** | ✅ **Construite et alimentée** : `bronze.reponses_brutes`, archivage de tout appel abouti ou non, vue de santé des sources. Écart assumé avec le S3 du Bloc 1. |
| Schéma Silver speed PostgreSQL | ✅ Construit, initialisé automatiquement |
| **C4.2.2 méthode 1, pipeline temps réel** | ✅ **Exécuté et désormais orchestré** : Steam vers Kafka vers PostgreSQL. Idempotence prouvée par rejeu. DAG `gamelens_ingestion_temps_reel` toutes les 15 min, porte de sortie, test négatif broker coupé et reprise automatique vérifiée. |
| **C4.2.2 méthode 2, orchestrateur** | ✅ **Exécuté** : Airflow 3.1.8 en conteneurs, **4 DAG**. `gamelens_promotion_gold` (6 tâches), `gamelens_promotion_snowflake`, `gamelens_ingestion_temps_reel`, `gamelens_supervision`. Tests négatifs de porte de fraîcheur réussis sur les deux promotions. |
| **C4.2.2 méthode 3, calcul distribué** | ✅ **Exécuté et désormais orchestré** : Snowpark, MERGE idempotents et calcul analytique (fenêtre glissante 7 j, classement par genre). Nature distribuée prouvée par le SQL généré et l'historique de session. DAG `gamelens_promotion_snowflake` quotidien depuis le 31/08/2026. |
| Schéma Gold PostgreSQL | ✅ Construit, testé, **alimenté quotidiennement** par le DAG de promotion. Volumes au 31/08/2026 : 15 dim_games, 45 faits popularité, 120 faits prix. Chiffres datés : ils croissent à chaque nuit. |
| Schéma Gold Snowflake (cible finale) | ✅ **Exécuté** sur `RTZSXDV-PM63908` (AWS_EU_WEST_3) : 27 instructions, 0 erreur. 8 contrôles au vert. ⚠️ **Alimentée à la main uniquement**, dernier chargement le 20/08/2026 : 15 dim_games, 30 faits popularité, 75 faits prix. Voir V-12. |
| **C4.2.3 pipeline CI/CD** | ✅ **Exécuté, 6 étages verts** sur `Mael8zinsou/gamelens-bloc4_0` (privé). Qualité, tests, intégrité du DAG, intégration sur infrastructure jetable, **recette Snowflake sur base jetable**, publication d'image sur `ghcr.io` avec double étiquetage `latest` et SHA. Le premier run avait échoué : défaut dans l'assertion, pas dans l'infra (OBS-22). |
| Recette automatisée de l'entrepôt | ✅ **Exécutée sur le runner** (run 32954104664, 41 s). Base Snowflake créée pour le run, schéma livré appliqué, calcul distribué confronté à des valeurs calculées à la main, contraintes du moteur éprouvées, contrôles d'intégrité et contrats dbt vérifiés en positif **et en négatif** sur le même jeu fautif, base supprimée. |
| **C4.3.1 supervision et alertes** | ✅ **Construit et exécuté.** 5 vues d'indicateurs SQL, 6 règles d'alerte avec cycle de vie complet (déclenchement, non-duplication, fermeture automatique), DAG `gamelens_supervision` toutes les 15 min, tableau de bord Grafana provisionné comme code, 7 panneaux vérifiés. |
| **C4.3.2 feuille de route d'exploitation** | ✅ **Écrite** : `docs/feuille_route_exploitation.md`, 10 sections. Tâches quotidiennes à trimestrielles, planification de maintenance, 13 points de vigilance dont 2 datés, durées d'incident mesurées, procédures d'intervention éprouvées avant d'être prescrites. |
| **C4.3.3 documentation technique** | ✅ **Écrite** : `docs/documentation_technique.md`. Point d'entrée, 11 décisions d'architecture datées avec leur contrepartie, traçabilité champ par champ, référence de configuration, matrice de droits, plus **2 annexes générées** depuis le catalogue et vérifiées par la CI. |
| **dbt sur Snowflake** | ✅ **Construit et exécuté** : 29 contrats déclaratifs sur 4 sources, 1 modèle (la vue de tableau de bord, sortie d'un script SQL non rejouable). Éprouvés en positif et en négatif, sur base jetable et sur la couche de démonstration. |
| Cahier de recettes complet | ✅ `docs/cahier_recettes.md` : **55 PASS, 0 partiel, 0 en attente**. |
| Incident réel documenté | ✅ **INC-004 retenu**. INC-005 à INC-008 s'y ajoutent comme incidents secondaires. |

## Faits d'environnement à ne pas redécouvrir

- **PostgreSQL est publié sur le port hôte 5433**, pas 5432 : un service
  `postgresql-x64-18` natif occupe 5432 et Docker publie alors sans effet réel ni
  message d'erreur. Ne pas « corriger » ce port. Voir INC-004.
- **Airflow ne tourne pas nativement sous Windows** (POSIX requis). Conteneur obligatoire.
- **Docker depuis Git Bash** : préfixer par `MSYS_NO_PATHCONV=1` et utiliser `pwd -W`,
  sinon MSYS réécrit le chemin du volume. Depuis PowerShell, rien à faire.
- **Kafka tourne en mode KRaft**, sans ZooKeeper : c'est bien Apache Kafka, pas une
  alternative allégée. L'autorisation de substituer Kafka n'a pas eu à être utilisée.
- Le chemin de travail contient accents et espaces, et cela **ne pose pas** de problème
  à Docker Desktop : hypothèse testée et écartée (INC-002).
- **Airflow 3 diffère nettement d'Airflow 2** : `api-server` remplace `webserver`,
  `dag-processor` est un service séparé obligatoire, et `logical_date` vaut `None`
  sur un run manuel (INC-006). Toujours partir du `docker-compose.yaml` officiel de
  la version exacte plutôt que d'un tutoriel Airflow 2.
- **Après toute modification d'un DAG**, lancer `airflow dags reserialize` : l'analyseur
  ne rescanne le dossier que toutes les 5 minutes.
- Interface Airflow sur **http://localhost:8080**, Grafana sur **http://localhost:3000**,
  compte `admin` / `admin` pour les deux.
- **Un seul modèle de rôles** pour toute la plateforme, celui du Bloc 1 :
  `etl_service`, `analyst`, `dashboard_viewer`, plus `gamelens_app` comme propriétaire.
  Les rôles `gamelens_etl` et `gamelens_reader` d'une version antérieure ont été
  supprimés (OBS-25). Ne pas en réintroduire.
- Les **seuils de supervision sont définis en SQL** (`sql/schema_supervision.sql`),
  pas dans Grafana : l'outil affiche les indicateurs, il ne les définit pas.
- Les logs Airflow contiennent des `:` dans les noms de dossier, **illisibles par un
  client Windows**. Les lire via `docker exec ... cat`, pas depuis l'hôte.
- **Compte Snowflake étudiant** `RTZSXDV-PM63908`, région `AWS_EU_WEST_3`, 120 jours
  et 400 dollars de crédits (et non un essai de 30 jours). Utilisateur de service
  `GAMELENS_SERVICE` en `TYPE = SERVICE`, authentifié par **paire de clés RSA** :
  Snowflake impose la MFA aux utilisateurs humains, ce qu'un pipeline ne peut pas
  satisfaire. Clé privée dans `secrets/`, ignorée par git.
- **L'outillage Snowflake (dbt, Snowpark) vit dans son propre conteneur**, jamais dans
  l'environnement Python du poste : Snowpark impose `snowflake-connector-python` 4.x,
  incompatible avec `dbt-snowflake` 1.8, et remonte `requests` épinglé pour l'ingestion.
  L'invoquer par `docker compose run --rm snowflake-cli ...`.
- **`python -m venv` ne fonctionne pas sur ce poste** : le module `venv` de
  l'installation Python est vide. Ne pas perdre de temps à chercher pourquoi, passer
  par un conteneur.
- **Deux couches Gold, deux DAG distincts**, et c'est délibéré (DA-11) :
  `gamelens_promotion_gold` vers PostgreSQL à 02h30, `gamelens_promotion_snowflake`
  vers Snowflake à 03h00. Ne pas les fusionner : Snowflake est un service tiers
  facturé dont l'indisponibilité ne doit pas emporter la promotion locale.
- **`entrepot/connexion.py` s'appelle désormais `connexion_snowflake.py`.**
  L'ancien nom masquait le paquet PyPI `connexion`, celui dont Airflow se sert
  pour son authentification, dès lors que `entrepot/` figurait sur son
  `PYTHONPATH`. L'interface web cessait de démarrer. Ne pas raccourcir ce nom,
  voir INC-009.
- **L'image Airflow embarque déjà l'outillage Snowflake**, hérité de
  `apache/airflow:3.1.8` sans qu'aucune ligne du Dockerfile ne l'installe :
  `apache-airflow-providers-snowflake` 6.10.0, `snowflake-snowpark-python`
  1.47.0, `snowflake-connector-python` 4.0.0, `pandas`, `pyarrow`. L'isolation
  des dépendances de DA-08 ne s'oppose donc pas à orchestrer la promotion
  Snowflake. Vérifié le 31/08/2026 (OBS-69), ne pas re-supposer le contraire.
- **`sql/schema_gold_snowflake.sql` contient des `CREATE OR REPLACE TABLE`** et
  nomme la base en dur, 24 fois. Ne jamais le rejouer sans redirection : il
  détruirait la couche de démonstration sans message d'erreur. Utiliser
  `executer_sql.py --base <autre>`, qui redirige la base **sans** toucher à
  `gamelens_wh` ni aux rôles `gamelens_*`, qui sont des objets de compte.
- **`entrepot/recette_ci.py` refuse les bases protégées** (`gamelens` en tête)
  et sort en code 1. Laisser `SNOWFLAKE_DATABASE` vide pour obtenir une base
  jetable nommée d'après le run. Ne pas contourner ce refus.
- **La clef privée Snowflake s'utilise de deux façons** :
  `SNOWFLAKE_PRIVATE_KEY_PATH` en local (chemin de fichier),
  `SNOWFLAKE_PRIVATE_KEY` en CI (contenu PEM en environnement, jamais écrit
  sur le disque du runner). Les trois secrets sont déposés sur le dépôt privé.
- **`pytest` lancé à la racine échoue à la collecte**, sur le lien symbolique
  `docker/airflow/logs/dag_processor/latest` qu'un client Windows ne sait pas
  lire. Lancer `pytest tests`, comme le fait la CI. Ce n'est pas une régression.
- **Les heredocs bash tronquent au-delà d'environ 8 Ko** et l'antislash y est
  parfois avalé, ce qui casse les séquences d'échappement dans le Python
  généré. Écrire par morceaux et construire les échappements par `chr(92)`.
- **La couche Bronze est une table PostgreSQL, pas un stockage objet.** Écart
  assumé avec le `Bronze (S3)` annoncé au Bloc 1 : le support change, la
  propriété recherchée est la même, et un service tiers de plus n'apportait
  rien à cette échelle. Volumétrie mesurée : 78 octets par relevé de
  fréquentation, 238 par relevé tarifaire, environ 41 Mo par an.
- **`bronze.reponses_brutes` n'accorde aucun UPDATE ni DELETE**, pas même à
  `etl_service`. Une archive modifiable n'est plus une archive. Ne pas
  « corriger » ce qui ressemble à un oubli de droits : c'est testé (TBRZ-04).
- **Les dictionnaires de `docs/annexes/` sont GÉNÉRÉS, jamais édités à la main.**
  Source : les `COMMENT ON` des fichiers de `sql/`. Après toute modification de
  schéma, lancer `python outils/generer_dictionnaire.py` (et `--cible snowflake`
  pour la couche Gold), sinon la CI échoue. Le fichier ne porte volontairement
  aucune date de génération : elle ferait échouer la comparaison à chaque run.
- **`sql/commentaires_gold_snowflake.sql` documente les colonnes Snowflake**,
  séparément du schéma parce que celui-ci contient des `CREATE OR REPLACE TABLE`
  et ne peut pas être rejoué. Le réappliquer après toute recréation du schéma.
- **Les scripts de `sql/` ne rejouent pas sur une instance déjà initialisée** :
  `docker-entrypoint-initdb.d` ne s'exécute que sur un volume vierge. Appliquer
  à la main par `docker exec -i ... psql < sql/<fichier>.sql`.
- La base de métadonnées Airflow est une base séparée sur la **même** instance
  PostgreSQL que la couche Silver speed. Choix d'échelle de développement assumé.
- **Le projet dbt vit dans `dbt/` et s'invoque par le conteneur d'outillage.**
  L'image pose `DBT_PROFILES_DIR` et `DBT_PROJECT_DIR`, mais les appels
  programmés passent `--project-dir` et `--profiles-dir` explicitement : la CI
  installe dbt sur le runner et n'hérite de rien de l'image.
- **`dbt/profiles.yml` a deux cibles, `local` et `ci`, et il faut les deux.**
  `dbt-snowflake` refuse `private_key` et `private_key_path` renseignés
  ensemble, et un `env_var()` sur une variable absente rend un champ **présent
  et vide**, ce qui déclenche ce refus. Ne pas fusionner les deux cibles.
  `_cible_dbt()` déduit laquelle utiliser du mode d'authentification présent.
- **dbt CONCATÈNE le schéma personnalisé à celui de la cible** : un
  `+schema: mart` dans `dbt_project.yml` donne `mart_mart`. Le schéma est donc
  porté par le profil seul (OBS-67).
- **`dbt/package-lock.yml` est versionné**, volontairement : c'est lui qui rend
  la résolution de `dbt_utils` reproductible sur le runner.
- **Ne pas retirer `grants` ni `persist_docs`** du modèle
  `dbt/models/gold/v_popularity_dashboard.sql`. Sans le premier, la vue perd
  ses droits et le tableau de bord se vide sans erreur ; sans le second, elle
  perd son `COMMENT` et c'est le contrôle du dictionnaire, à un autre étage de
  la CI, qui échoue sur un message sans rapport. Les deux sont testés (TDBT-04,
  TDBT-05).
- **Normaliser les fins de ligne avant de committer** après toute édition
  écrite depuis Python : le dépôt n'a pas de `.gitattributes`, mélange LF et
  CRLF selon les fichiers, et une conversion involontaire présente un fichier
  entièrement réécrit là où sept lignes ont changé. Procédure en phase 26 du
  journal des commandes (OBS-68).

## Décisions de session 1 (19/08/2026)

- Runtime : Docker Desktop (1a). Dépôt : sur place, `git init` local (2b).
  Snowflake : compte d'essai à recréer (3d). Échéance : jalonnement par livrable (4d).
- **Tarification sans GOG** : l'arbitrage du Bloc 3 (3.3) a sorti le suivi tarifaire GOG
  du périmètre. `fact_prices` est donc alimentée par l'API Steam `appdetails`
  (`price_overview`), vérifiée fonctionnelle. Cela lève la contradiction entre le schéma
  Gold et le Bloc 3, sans vider la table de faits.
- **Panel de titres** : 15 jeux indépendants réels, chaque `appid` vérifié en direct.
  Les trois AAA cités en exemple au Bloc 1 (570, 730, 1091500) sont écartés, incohérents
  avec le positionnement d'éditeur indépendant de Kestrel Interactive.
- **Incident C4.4.2** : privilégier un incident réellement vécu pendant la construction
  plutôt que rejouer GOG. INC-004 remplit ce rôle et couvre les quatre rubriques exigées
  par la grille, y compris la communication aux parties prenantes, souvent oubliée.

## Prochaine étape immédiate

**Tous les livrables du Bloc 4 sont écrits, et dbt est branché.** Les trois
compétences éliminatoires sont couvertes par des briques exécutées, la chaîne
est autonome de bout en bout, l'architecture Medallion est complète, et le
dernier écart connu entre ce que l'architecture annonçait et ce que le dépôt
contenait a été refermé le 27/08 (session 8, DA-10).

Il ne reste que le support oral et une amélioration non éliminatoire.

1. **Préparer le support de soutenance** (30 min de présentation). C'est
   désormais le poste le plus rentable, et de loin : tout ce qui doit être
   montré existe, a été exécuté, et laisse des traces consultables.
2. A4.1, rapport d'analyse : s'appuie largement sur le Bloc 1.

Refermé le 31/08/2026 : V-12 et V-13, la couche Gold Snowflake est
désormais promue par son propre DAG et son arrêt est visible de la
supervision (DA-11). Coût de l'opération : un incident, INC-009.

Piste identifiée pendant la session 8, non traitée et sans urgence :
`dim_games.critical_tier` est vide, et le commentaire de la colonne annonce
qu'elle est « dérivée de metacritic_score par le modèle dbt ». Ce modèle
n'existe pas, et il ne pourrait rien dériver aujourd'hui puisque
`metacritic_score` est vide lui aussi, faute de catalogue RAWG branché. C'est
le même genre d'écart entre l'annoncé et le réel que celui qu'a refermé
DA-10, en plus petit. Le traiter suppose soit de brancher RAWG, soit de
corriger le commentaire.

Corrections courtes identifiées, aucune ne bloque, toutes sont documentées
comme points de vigilance dans la feuille de route :

- **V-02, aucun canal de notification.** L'écart le plus important entre cette
  plateforme et une plateforme exploitée : les alertes sont persistées, mais
  rien ne prévient un humain. Chiffré : la fraîcheur est restée en alerte
  6 j 20 h en août, détectée en 90 minutes.
- **V-07, la supervision ne se surveille pas elle-même.** Son arrêt rend
  l'absence d'alerte indiscernable du bon fonctionnement.
- **V-03, `GAMELENS_SERVICE` en `ACCOUNTADMIN`.**
- **V-01, expiration du compte Snowflake les 17 ou 18/12/2026.** À confirmer
  dans Snowsight.
- Réduire `COMPUTE_WH` et lui imposer une suspension automatique : cet entrepôt
  jamais configuré pèse 43 % de la consommation de crédits (OBS-57).

## Conventions de travail

- Toujours tester réellement avant de documenter. Un composant "conçu" mais jamais exécuté n'est pas
  terminé.
- Conserver les logs et sorties réelles des tests et des runs (fichiers `.log`, captures), ils
  serviront de preuve et de matière pour le support de soutenance.
- Pas de tiret cadratin (—) dans les documents écrits destinés au dossier ou au support final.
- Ce fichier (`CLAUDE.md`) doit être tenu à jour au fil de l'avancement : cocher les cases,
  documenter les choix techniques assumés (ex : alternative à Kafka) et les échecs rencontrés.

### Trois documents de suivi à tenir à jour à chaque session

Ils ne se recouvrent pas et n'ont pas le même lecteur. Aucun ne doit être écrit
rétrospectivement en fin de projet.

| Document | Contenu | Sert à |
|---|---|---|
| `docs/journal_incidents.md` | Uniquement les incidents, au format imposé par la grille C4.4.2 (nature, investigation, scénarios, communication aux parties prenantes, résultat) | Livrable C4.4.2 |
| `docs/observations.md` | Surprises, fausses pistes, hypothèses démenties, arbitrages pris sur le vif, anecdotes | Les 15 minutes d'échange avec le jury, qui portent rarement sur ce qui a marché du premier coup |
| `docs/commandes_successives.md` | Trace chronologique des commandes et requêtes réellement exécutées, en distinguant diagnostic ponctuel et procédure reproductible | Cahier de recettes C4.4.1 et documentation technique C4.3.3 |

En fin de session, les quatre fichiers de suivi sont mis à jour ensemble :
ces trois-là plus le tableau d'avancement de `CLAUDE.md`.

### Le sous-dossier de vulgarisation, à une cadence différente

`docs/vulgarisation/` n'est pas un livrable de la certification. Il contient
deux documents qui expliquent le projet à deux lecteurs distincts :
`pour-un-junior.md` (a le vocabulaire, pas l'expérience de la production) et
`explique-simplement.md` (aucun vocabulaire de la donnée, méthode Feynman).

Il ne se met pas à jour à chaque session, contrairement aux trois précédents,
parce qu'il décrit des intentions et pas des fichiers. Règle retenue : il est
relu et corrigé **à chaque session qui ajoute ou retire une brique, ou qui
invalide une explication qui s'y trouve**. Une correction de détail ne le
justifie pas.

Un document de vulgarisation faux est pire qu'absent : il enseigne quelque
chose d'inexact avec assurance. Deux affirmations y sont aujourd'hui datées et
deviendront fausses dès qu'elles seront traitées : l'ingestion temps réel n'est
planifiée par rien, et `GAMELENS_SERVICE` tourne en `ACCOUNTADMIN`.

### Note de calendrier sur le compte Snowflake

Réécrite le 31/08/2026. La version précédente décrivait un compte **à recréer**,
un essai de 30 jours et une création volontairement différée. Les trois points
étaient faux depuis le 20/08, et contredisaient la section des faits
d'environnement du même fichier, quarante lignes plus haut. Un fichier de
consignes qui se contredit lui-même est pire qu'incomplet : il fait perdre du
temps à qui le lit et il fait prendre de mauvaises décisions à qui le croit.

**État réel.** Compte étudiant `RTZSXDV-PM63908`, créé les 19 ou 20/08/2026,
**120 jours et 400 dollars de crédits** et non un essai de 30 jours. Expiration
attendue les **17 ou 18/12/2026**, à confirmer dans Snowsight : c'est V-01, le
seul point de vigilance bloquant.

**Ce que la contrainte d'alors a produit, et qui vaut d'être gardé.** Tant que
le compte n'existait pas, la règle était que tout ce qui vise la couche Gold
soit construit derrière une frontière de configuration. Cette contrainte a été
tenue, et elle a payé deux fois plutôt qu'une : la bascule vers Snowflake s'est
faite sans réécrire la logique de promotion, puis la recette d'intégration
continue a pu viser une base jetable sans modifier une ligne des scripts de
contrôle. Voir DA-05. La contrainte n'a plus de raison d'être, la règle si.
