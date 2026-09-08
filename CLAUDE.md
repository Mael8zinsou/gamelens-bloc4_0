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
  et `appdetails`/`price_overview` pour la tarification), **Twitch Helix
  (`/streams`, OAuth `client_credentials`), branchée le 08/09/2026**.
  **Le scraping GOG n'est plus une source du Bloc 4** : l'arbitrage du Bloc 3 (3.3) l'a sorti du
  périmètre, et la tarification passe donc par l'API Steam. L'incident GOG n'a plus à être rejoué
  pour le C4.4.2 : INC-004, réellement vécu le 19/08/2026, remplit ce rôle. GOG reste en filet
  de sécurité.

## Référentiel Bloc 4 — ce qui doit être livré

Tout est livré. Cette section ne dit plus l'avancement, qui est dans le tableau
juste en dessous : elle dit **où se trouve la preuve**, parce que c'est la
question que le jury pose ("montrez-moi") et qu'il faut pouvoir y répondre sans
chercher.

Réécrite le 31/08/2026. La version précédente portait encore « À faire » sur
C4.2.2 et C4.2.3, deux compétences éliminatoires exécutées et vertes en CI
depuis plusieurs jours, que le tableau d'avancement quarante lignes plus bas
donnait pour terminées. Même défaut que la note de calendrier : un fichier de
consignes qui se contredit fait perdre du temps à qui le lit.

**3 compétences éliminatoires :**

- **C4.2.1** — Concevoir l'architecture d'entrepôt (schéma de données).
  ✅ Deux couches Gold construites et exécutées : la cible
  `sql/schema_gold_snowflake.sql` sur `RTZSXDV-PM63908`, et le prototype
  `sql/schema_gold.sql` sur PostgreSQL, gardé comme référence de comparaison.
  Le prototype applique CHECK, FK, PK et UNIQUE ; la cible ne les applique pas,
  ce qui est vérifié empiriquement par `sql/verify_snowflake_constraints.sql`
  et compensé par deux filets rejoués à chaque push. Cloisonnement des 4 rôles
  testé des deux côtés, dictionnaires de données générés en annexe.
- **C4.2.2** — Mettre en place et orchestrer des pipelines temps réel ou
  asynchrones. Le référentiel exige **3 méthodes distinctes**, les trois sont
  exécutées :
  1. *pipeline temps réel* (SQL/Python) : Steam vers Kafka vers PostgreSQL,
     `ingestion/`, idempotence prouvée par rejeu des offsets ;
  2. *orchestrateur* : Airflow 3.1.8 en conteneurs, 5 DAG dans `dags/`, tests
     négatifs de porte de fraîcheur réussis sur les deux promotions ;
  3. *calcul distribué* : **Snowpark et non Spark**, choix assumé du
     19/08/2026, `entrepot/snowpark_promotion.py`. Le référentiel cite Spark en
     exemple, l'exigence porte sur le calcul distribué. Snowpark pousse
     l'exécution sur le compute Snowflake là où un Spark local aurait tourné en
     mono-machine. La question « en quoi est-ce distribué ? » est à attendre :
     la preuve est le SQL généré et l'historique de session, pas la brochure.
- **C4.2.3** — Automatiser l'intégration et le déploiement (CI/CD, DevOps).
  ✅ `.github/workflows/ci.yml`, 6 étages verts sur
  `Mael8zinsou/gamelens-bloc4_0` : qualité, tests, intégrité des DAG,
  intégration sur infrastructure jetable, recette Snowflake sur base jetable,
  publication d'image sur `ghcr.io`.

**Autres livrables attendus (non éliminatoires mais notés) :**

- **A4.1**, rapport d'analyse et présentation des composants.
  ✅ `docs/rapport_analyse.md`. Deux parties calquées sur les deux livrables de
  la grille, dépendance fournisseur analysée composant par composant, coûts
  **mesurés** sur l'historique de facturation et non estimés.
- **C4.3.1**, système de supervision et alertes.
  ✅ `sql/schema_supervision.sql` (5 vues d'indicateurs, seuils portés par le
  SQL), `supervision/regles_alertes.py` (6 règles à cycle de vie complet), DAG
  `gamelens_supervision` toutes les 15 min, tableau de bord Grafana provisionné
  comme code.
- **C4.3.2**, feuille de route d'exploitation.
  ✅ `docs/feuille_route_exploitation.md`, 10 sections, 13 points de vigilance
  dont 2 datés, procédures éprouvées avant d'être prescrites.
- **C4.3.3**, documentation technique.
  ✅ `docs/documentation_technique.md`, 11 décisions d'architecture datées avec
  leur contrepartie, traçabilité champ par champ, matrice de droits, plus
  2 annexes générées depuis le catalogue et vérifiées par la CI.
- **C4.4.1**, cahier de recettes et de tests.
  ✅ `docs/cahier_recettes.md`, **55 PASS, 0 partiel, 0 en attente**. Format
  retenu : PASS/FAIL vérifié sur un résultat attendu, pas seulement "la requête
  s'exécute sans erreur". Le test d'idempotence de la session 1 (rejeu des
  offsets Kafka, 0 inséré sur 15 relus) est le premier cas conforme à ce
  format. Note : `sql/test_schema_gold.sql`, référencé par une version
  antérieure de ce fichier, n'existe pas dans le dépôt.
- **C4.4.2**, méthodologie d'investigation et de traitement d'un incident réel.
  ✅ `docs/journal_incidents.md`. **INC-004 est l'incident retenu** : il couvre
  les quatre rubriques exigées, y compris la communication aux parties
  prenantes, souvent oubliée. INC-001 à INC-003 et INC-005 à INC-009 s'y
  ajoutent comme incidents secondaires, tous réellement vécus.

## État d'avancement

Mis à jour le 08/09/2026 en session 13 : canal de notification externe (V-02
et V-07 refermés), puis correction des commentaires annonçant des sources
absentes. Session 12 : support de soutenance, preuves
capturées, feuille du jury, puis rattrapage des quatre fichiers de suivi, où les
sessions 11 et 12 manquaient dans deux d'entre eux.

| Élément | Statut |
|---|---|
| Dépôt git dédié, structure, .gitignore | ✅ Fait (dépôt local, décision 2b) |
| Socle Docker (PostgreSQL 16 + Kafka 3.9 KRaft) | ✅ **7 conteneurs** au démarrage, tous *healthy* : 2 de socle, 4 Airflow, 1 Grafana. `snowflake-cli` reste hors compte, profil `outillage`, lancé à la demande. |
| **Couche Bronze** | ✅ **Construite et alimentée** : `bronze.reponses_brutes`, archivage de tout appel abouti ou non, vue de santé des sources. Écart assumé avec le S3 du Bloc 1. |
| Schéma Silver speed PostgreSQL | ✅ Construit, initialisé automatiquement |
| **C4.2.2 méthode 1, pipeline temps réel** | ✅ **Exécuté et désormais orchestré** : Steam vers Kafka vers PostgreSQL. Idempotence prouvée par rejeu. DAG `gamelens_ingestion_temps_reel` toutes les 15 min, porte de sortie, test négatif broker coupé et reprise automatique vérifiée. |
| **C4.2.2 méthode 2, orchestrateur** | ✅ **Exécuté** : Airflow 3.1.8 en conteneurs, **5 DAG**. `gamelens_promotion_gold` (6 tâches), `gamelens_promotion_snowflake`, `gamelens_ingestion_temps_reel`, `gamelens_supervision`, `gamelens_battement`. Tests négatifs de porte de fraîcheur réussis sur les deux promotions. |
| **C4.2.2 méthode 3, calcul distribué** | ✅ **Exécuté et désormais orchestré** : Snowpark, MERGE idempotents et calcul analytique (fenêtre glissante 7 j, classement par genre). Nature distribuée prouvée par le SQL généré et l'historique de session. DAG `gamelens_promotion_snowflake` quotidien depuis le 31/08/2026. |
| Schéma Gold PostgreSQL | ✅ Construit, testé, **alimenté quotidiennement** par le DAG de promotion. Volumes au 08/09/2026 : **150 dim_games** (tous avec `twitch_game_id`), 240 faits popularité dont 150 avec audience, 504 faits prix. Chiffres datés : ils croissent à chaque nuit. |
| Schéma Gold Snowflake (cible finale) | ✅ **Exécuté** sur `RTZSXDV-PM63908` (AWS_EU_WEST_3) : 27 instructions, 0 erreur, 8 contrôles au vert. **Alimentée quotidiennement** par `gamelens_promotion_snowflake` depuis le 31/08/2026, V-12 refermé. Volumes mesurés le 08/09/2026 : **150 dim_games**, 255 faits popularité sur 8 journées dont 150 avec audience, 504 faits prix. Plus profonde que la couche PostgreSQL, et c'est attendu : la promotion Snowpark rejoue tout l'historique par MERGE. |
| **C4.2.3 pipeline CI/CD** | ✅ **Exécuté, 6 étages verts** sur `Mael8zinsou/gamelens-bloc4_0` (privé). Qualité, tests, intégrité du DAG, intégration sur infrastructure jetable, **recette Snowflake sur base jetable**, publication d'image sur `ghcr.io` avec double étiquetage `latest` et SHA. Le premier run avait échoué : défaut dans l'assertion, pas dans l'infra (OBS-22). |
| Recette automatisée de l'entrepôt | ✅ **Exécutée sur le runner** (run 32954104664, 41 s). Base Snowflake créée pour le run, schéma livré appliqué, calcul distribué confronté à des valeurs calculées à la main, contraintes du moteur éprouvées, contrôles d'intégrité et contrats dbt vérifiés en positif **et en négatif** sur le même jeu fautif, base supprimée. |
| **C4.3.1 supervision et alertes** | ✅ **Construit et exécuté.** 5 vues d'indicateurs SQL, 6 règles d'alerte avec cycle de vie complet (déclenchement, non-duplication, fermeture automatique), DAG `gamelens_supervision` toutes les 15 min, tableau de bord Grafana provisionné comme code, 7 panneaux vérifiés. **Canal externe depuis le 07/09/2026** : notification Telegram immédiate des alertes critiques (mesurée à 2 s), plus `gamelens_battement` à 8h et 20h, DAG séparé qui dénonce l'arrêt de la supervision. V-02 et V-07 refermés, DA-12. |
| **C4.3.2 feuille de route d'exploitation** | ✅ **Écrite** : `docs/feuille_route_exploitation.md`, 10 sections. Tâches quotidiennes à trimestrielles, planification de maintenance, 13 points de vigilance dont 2 datés, durées d'incident mesurées, procédures d'intervention éprouvées avant d'être prescrites. |
| **A4.1 rapport d'analyse** | ✅ **Écrit** : `docs/rapport_analyse.md`. Deux parties, calquées sur les deux livrables de la grille. Besoins métiers traduits en exigences, état de l'existant, contraintes, puis les composants un par un avec l'alternative écartée, l'analyse de dépendance fournisseur composant par composant, et une estimation des coûts **mesurée** sur l'historique de facturation, pas estimée. |
| **C4.3.3 documentation technique** | ✅ **Écrite** : `docs/documentation_technique.md`. Point d'entrée, 11 décisions d'architecture datées avec leur contrepartie, traçabilité champ par champ, référence de configuration, matrice de droits, plus **2 annexes générées** depuis le catalogue et vérifiées par la CI. |
| **dbt sur Snowflake** | ✅ **Construit et exécuté** : 29 contrats déclaratifs sur 4 sources, 1 modèle (la vue de tableau de bord, sortie d'un script SQL non rejouable). Éprouvés en positif et en négatif, sur base jetable et sur la couche de démonstration. |
| Cahier de recettes complet | ✅ `docs/cahier_recettes.md` : **70 PASS, 0 partiel, 0 en attente**. |
| Incident réel documenté | ✅ **INC-004 retenu** pour le C4.4.2. 9 incidents au total, INC-001 à INC-009, tous réellement vécus. Le dernier, INC-009, est né de la correction de V-12. |
| **Support de soutenance** | ✅ **Construit** : `docs/support_soutenance.md` est la source, deux PPTX en sont des sorties, la version projetée sans marquage de conformité et la version de répétition avec. 30 diapositives, 33 replis compris, **27:30 de contenu sur 30:00**. Organisé sur la grille et non chronologiquement : les 31 sous-critères ont chacun leur diapositive, vérifié par script (phase 47). |
| **Preuves et feuille du jury** | ✅ 10 preuves textuelles datées dans `docs/preuves/`, rejouables par `outils/capturer_preuves.py`. 5 visuels plus le schéma de données, tous générés. `docs/feuille_jury.pdf` met les 31 critères en regard des numéros de diapositive, depuis trois sources et sans saisie manuelle. **Reste 1 capture d'écran**, GitHub Actions, réseau requis. |

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
- **Les quatre ports publiés sont liés à `127.0.0.1`**, pas à `0.0.0.0` :
  `- "127.0.0.1:5433:5432"` et ses trois voisins. Sans adresse de liaison,
  Docker publie sur toutes les interfaces réseau, et le mot de passe de la
  base est dans le dépôt. Ne pas revenir à la forme courte. Rien n'en pâtit :
  les conteneurs se joignent par le réseau Docker, `localhost` **est**
  `127.0.0.1`, et la CI se connecte depuis le runner en local (OBS-89).
- **PostgreSQL et Kafka ne répondent pas à un navigateur**, et c'est normal :
  ils parlent leur protocole binaire sur TCP, pas HTTP. `curl` y rend
  « Empty reply from server ». Seuls 8080 et 3000 sont des interfaces web.
- **Un seul modèle de rôles** pour toute la plateforme, celui du Bloc 1 :
  `etl_service`, `analyst`, `dashboard_viewer`, plus `gamelens_app` comme propriétaire.
  Les rôles `gamelens_etl` et `gamelens_reader` d'une version antérieure ont été
  supprimés (OBS-25). Ne pas en réintroduire.
- Les **seuils de supervision sont définis en SQL** (`sql/schema_supervision.sql`),
  pas dans Grafana : l'outil affiche les indicateurs, il ne les définit pas.
- Les logs Airflow contiennent des `:` dans les noms de dossier, **illisibles par un
  client Windows**. Les lire via `docker exec ... cat`, pas depuis l'hôte.
- **Le canal Twitch est FACULTATIF**, comme celui de Telegram : sans
  `TWITCH_CLIENT_ID` ni `TWITCH_CLIENT_SECRET`, la collecte d'audience est un
  no-op qui rend un succès. Et la tâche Twitch du DAG d'ingestion **ne lève
  jamais** : une source facultative ne doit pas casser une chaîne éliminatoire,
  son échec étant tracé dans `speed.pipeline_runs` où la supervision le voit.
  Ne pas « corriger » ce silence apparent, il est testé (TTWI-05).
- **Une ligne Bronze d'audience Twitch pèse 3 231 octets contre 176 pour un
  compteur Steam**, dix-huit fois plus, parce que `/helix/streams` décrit jusqu'à
  cent diffusions. La projection Bronze passe de 41 Mo à **17,5 Go par an**, dont
  16 pour la seule audience. V-05 a été requalifié de faible à forte en
  conséquence. Ne pas tronquer la charge archivée pour économiser : voir DA-13.
- **Le consumer est abonné aux DEUX topics** et choisit sa table sur le topic
  d'origine du message. Un topic inconnu lève plutôt que d'être ignoré : écrire
  une audience dans la table de fréquentation serait pire qu'une panne.
- **Le canal Telegram est FACULTATIF et le restera** : sans `TELEGRAM_BOT_TOKEN`
  ni `TELEGRAM_CHAT_ID`, la notification est un no-op qui rend un succès. Un
  jeton présent mais injoignable, en revanche, trace un échec et déclenche
  `echecs_composants`. Ne pas « corriger » cette asymétrie, elle est testée
  (TNOT-04, TNOT-05).
- **La base stocke en UTC, l'affichage seul est converti** par
  `GAMELENS_TIMEZONE`, défaut `Europe/Paris`. Piège : ce qui est formaté par
  `to_char()` en SQL sort dans le fuseau de la SESSION et échappe au
  convertisseur Python. Voir OBS-92.
- **Compte Snowflake étudiant** `RTZSXDV-PM63908`, région `AWS_EU_WEST_3`, 120 jours
  et 400 dollars de crédits (et non un essai de 30 jours). Utilisateur de service
  `GAMELENS_SERVICE` en `TYPE = SERVICE`, authentifié par **paire de clés RSA** :
  Snowflake impose la MFA aux utilisateurs humains, ce qu'un pipeline ne peut pas
  satisfaire. Clé privée dans `secrets/`, ignorée par git.
  **Ce choix a pré-empté la Phase 3 de Snowflake**, qui supprime le 09/09/2026
  les connexions par mot de passe seul et le type `LEGACY_SERVICE` :
  `GAMELENS_SERVICE` était déjà conforme, aucune brique n'a été touchée. Le
  compte humain `MAEL8ZINSOU`, lui, était en mot de passe seul ; passé en
  `TYPE = PERSON` avec MFA le 07/09/2026. **Une paire de clés ne donne pas
  accès à Snowsight** : pour un humain, la MFA est la seule voie. Voir V-14 de
  la feuille de route et la phase 49 pour la commande de contrôle.
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
- **Le schéma de données en diagramme est GÉNÉRÉ** par
  `outils/generer_schema.py` vers `docs/annexes/schema_donnees.md` : colonnes,
  types et contraintes lus dans le catalogue Snowflake, cibles des clefs
  étrangères lues dans le DDL parce que le catalogue ne les expose pas
  (`SHOW IMPORTED KEYS` refusé, `key_column_usage` inexistant chez ce moteur).
  Les deux sources sont recoupées sur le nombre de contraintes par type, et la
  génération s'arrête si elles divergent. La matrice de droits de la section 3
  est lue en direct par `SHOW GRANTS`.
- **Les dictionnaires de `docs/annexes/` sont GÉNÉRÉS, jamais édités à la main.**
  Source : les `COMMENT ON` des fichiers de `sql/`. **Piège** : le générateur ne
  lit pas ces fichiers, il lit le **catalogue vivant** (`obj_description` côté
  PostgreSQL, `information_schema` côté Snowflake). Corriger un commentaire dans
  `sql/` puis régénérer ne change donc rien : il faut d'abord **appliquer** le
  `COMMENT ON` à la base. Voir la phase 55. Après toute modification de schéma,
  lancer `python outils/generer_dictionnaire.py` (et `--cible snowflake`
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
- **Panel de titres** : porté à **150 jeux** le 08/09/2026, chaque `appid` vérifié
  contre `appdetails` par `outils/construire_panel.py`, qui reproduit
  `config/watchlist.json` à l'octet près. Ne pas éditer ce fichier à la main.
  Cinq `appid` présumés désignaient un autre jeu et ont été rejetés par le
  contrôle de nom. Était de 15 jeux jusqu'à cette date.
  Les trois AAA cités en exemple au Bloc 1 (570, 730, 1091500) sont écartés, incohérents
  avec le positionnement d'éditeur indépendant de Kestrel Interactive.
- **Incident C4.4.2** : privilégier un incident réellement vécu pendant la construction
  plutôt que rejouer GOG. INC-004 remplit ce rôle et couvre les quatre rubriques exigées
  par la grille, y compris la communication aux parties prenantes, souvent oubliée.

## La soutenance : ce que disent les documents de cadrage

Lu le 01/09/2026 dans trois documents que le projet n'avait jamais ouverts :
`25-26 Modalités_Evaluations_Titre ISD RNCP39586_YNOV_M2_filiere IAData.pptx`,
`25 09 15 Réglement spécial de certification`, et surtout l'onglet
**« Grille Eval spé Bloc 4 »** du fichier
`24 10 10 - Grille évaluation Ingénieur en science des données (1).xlsx`.
Tous trois sont dans `Certification/`, deux niveaux au-dessus de ce dépôt.

**Date : vendredi 11/09/2026.** La fenêtre du référentiel courait du 01 au
29/09 ; la date retenue est la plus précoce du calendrier.

### Il n'y a pas de « rapport de soutenance »

Règlement spécial, page 4, mot pour mot : « À l'aide d'**un support de
présentation de son choix**, le candidat présente lors d'une soutenance orale
de 45 min (30 min de présentation et 15 de temps d'échange avec le jury) »,
suivi de la liste des dix livrables. Un support unique, format libre, à travers
lequel dix choses sont présentées. Deux d'entre elles s'appellent littéralement
« une présentation de » : les composants de l'architecture, le système de
supervision.

### Dix compétences, et non neuf : C4.1.2 existe

La grille en liste dix, chacune avec un livrable et ses critères. Ce fichier
n'en suivait que neuf, ayant fusionné les deux premières sous l'étiquette
« A4.1 ». Or A4.1 est le nom de l'**activité** ; le jury coche des
**compétences**, et il en coche deux là où nous en comptions une.

| Compétence | Livrable attendu | |
|---|---|---|
| C4.1.1 | Un rapport d'analyse | |
| **C4.1.2** | Une présentation des composants de l'architecture DATA | jamais nommée avant le 01/09 |
| C4.2.1 | Un schéma de données | éliminatoire |
| C4.2.2 | Des pipelines de traitement de la donnée | éliminatoire |
| C4.2.3 | Un pipeline CI/CD | éliminatoire |
| C4.3.1 | Une présentation du système de supervision | |
| C4.3.2 | Une feuille de route d'exploitation | |
| C4.3.3 | Une documentation technique | |
| C4.4.1 | Un cahier de recettes et de tests | |
| C4.4.2 | Une méthodologie d'investigation et de traitement d'un incident | |

Le contenu de C4.1.2 existe : la partie 2 de `docs/rapport_analyse.md` couvre
ses quatre critères (liste des composants, avantages attendus, points de
vigilance, estimation des coûts), sections 7, 9 et 10. C'est l'étiquette qui
manquait, pas le travail.

### Le mot qui change les priorités : « présentées »

Critère de C4.2.2, verbatim : « **3 méthodes de traitement de la donnée sont
présentées.** » Pas « sont réalisées », pas « existent dans le dépôt ». Le jury
coche sur ce qui se passe pendant les 30 minutes.

Conséquence à tenir jusqu'au 11/09 : **une brique construite, testée et verte
en CI mais non montrée peut être notée non acquise**, et pour C4.2.2 elle est
éliminatoire. La règle « ne rien documenter qui n'ait été exécuté » reste juste
mais ne suffit plus. Ce qui compte désormais est de rendre visible en 30 minutes
ce qui est déjà construit, pas de construire davantage.

### L'arithmétique, qui est la vraie contrainte

Les dix compétences se déploient en **31 sous-critères explicites** dans la
grille : 5 pour C4.1.1, 4 pour C4.1.2, 3 pour C4.2.1, 3 pour C4.2.2, 1 pour
C4.2.3, 4 pour C4.3.1, 4 pour C4.3.2, 1 pour C4.3.3, 2 pour C4.4.1, 4 pour
C4.4.2. Trente minutes pour 31 points cochables : **moins d'une minute chacun**.

Le support ne peut donc pas raconter le projet chronologiquement, ni suivre
l'ordre dans lequel il a été construit. Il doit être organisé sur la grille,
sinon un critère passe à la trappe sans que personne s'en aperçoive.

### Trois couperets qui ne dépendent pas de la qualité du travail

1. **Le dépôt.** Modalités, diapositive 11 : déposer les livrable(s) **et** le
   support sur DigiformaCertif dans le délai imparti, « à défaut, le bloc sera
   invalidé par le jury d'évaluation ». Le règlement général, section 1.2, est
   plus dur encore : « Tout livrable remis après la date et l'heure limites
   fixées pour une épreuve certificative sera déclaré non recevable et
   entraînera **automatiquement** une évaluation des compétences associées comme
   "non acquises". » **La date limite ne figure dans aucun règlement : elle est
   dans la convocation**, envoyée par courriel un mois avant l'épreuve, soit
   autour du 11/08/2026.
2. **La validation.** Bloc validé si au moins 50 % des compétences sont acquises
   **et** aucune éliminatoire n'est non acquise. Avec dix compétences : au moins
   cinq acquises, dont obligatoirement les trois éliminatoires.
3. **L'accès à la salle.** Règlement général 2.1 : contrôle d'identité par la
   convocation **et** la pièce d'identité. Sans les deux, pas d'accès à
   l'épreuve. Seuls le candidat et les deux membres du jury sont dans la salle.

### Conséquence sur la démonstration en direct

Choix retenu le 01/09 : support de preuves capturées, **plus deux ou trois
moments en direct courts et répétés**, chacun avec son repli capturé.

Le règlement ne dit rien de l'équipement ni du réseau de la salle. Il faut donc
traiter l'accès Internet comme indisponible, ce qui partage nettement les
briques :

- **Sûres hors ligne** : Grafana, l'interface Airflow et son historique de runs,
  les requêtes sur la couche Gold PostgreSQL, les tests unitaires sans réseau.
  Tout est local, dans des conteneurs.
- **Impossibles hors ligne** : tout ce qui vise Snowflake (dbt, Snowpark,
  `verifier_gold.py`, la promotion), et toute ingestion, qui appelle l'API Steam.

Les moments en direct doivent donc être choisis dans la première liste, et
Snowflake présenté par des traces capturées, sauf réseau confirmé sur place.

## Prochaine étape immédiate

**Tous les livrables du Bloc 4 sont écrits, et le support de soutenance est
construit.** Les trois compétences éliminatoires sont couvertes par des briques
exécutées, la chaîne est autonome de bout en bout, et les trente minutes de
présentation existent sous forme de fichier généré depuis une source versionnée.

**Deux dates, et c'est la première qui contraint** : dépôt sur DigiformaCertif
le **mercredi 09/09/2026**, soutenance le **vendredi 11/09/2026**. Le support est
donc gelé deux jours avant l'oral, pendant que les répétitions ont lieu. Un dépôt
en retard rend les compétences « non acquises » automatiquement, quel que soit le
contenu.

### Ce qu'il reste à faire, dans l'ordre

1. **Répéter.** C'est désormais le premier poste de travail, et de loin. Le
   budget annonce 27:30 de contenu pour 30:00, mais un budget calculé n'est pas
   un budget tenu. Répéter sur `docs/support_soutenance_repetition.pptx`, qui
   porte en pied de page l'identifiant, la minute, la compétence et les critères
   de chaque diapositive. La version projetée n'en porte rien, délibérément.
2. **Une capture d'écran manque** : GitHub Actions, réseau requis, laissant un
   cadre vide sur la diapositive 20. Les autres sont prises.
3. **Convertir les six livrables écrits en PDF.** Ils n'existent qu'en Markdown,
   et un correcteur qui ouvre un `.md` sur DigiformaCertif verra du texte brut
   avec ses `##` et ses `|---|`, alors qu'ils contiennent beaucoup de tableaux.
   Le poste n'a ni pandoc ni LibreOffice : la conversion se fera depuis un
   éditeur.
4. **Imprimer `docs/feuille_jury.pdf`** en deux exemplaires, un par membre du
   jury.

Ce qui **ne** reste **pas** à faire : ajouter des briques. Le critère de la
grille dit « 3 méthodes de traitement de la donnée sont **présentées** », pas
« sont réalisées » (OBS-79). Une brique construite et non montrée peut être
notée non acquise ; une brique de plus ne rapporte rien.

Décision prise le 31/08/2026 : **gel du dépôt**. Tout écart trouvé à partir de
maintenant va sur la liste ci-dessous, pas dans un commit. Le critère pour
rouvrir : est-ce que cela change ce qui sera dit ou montré pendant les
45 minutes ?

Refermé le 31/08/2026 : V-12 et V-13, la couche Gold Snowflake est
désormais promue par son propre DAG et son arrêt est visible de la
supervision (DA-11). Coût de l'opération : un incident, INC-009.

Refermés le 07/09/2026 : **V-14**, la dépréciation d'authentification
Snowflake, qui ne touchait pas la plateforme ; puis **V-02 et V-07**, par un
canal Telegram et un DAG témoin séparé (DA-12). Les deux écarts que la
documentation présentait depuis trois semaines comme les plus importants sont
donc traités, et le plus important de ceux qui restent est V-03.

### Écarts connus, gelés

Aucun ne bloque. Les trois sont aussi des points de vigilance de la feuille de
route. Les écarts entre l'annoncé et le réel qui figuraient ici, du même genre
que celui qu'a refermé DA-10 en plus petit, ont été traités le 08/09/2026.

Cette liste comptait sept entrées jusqu'au 07/09/2026, et le conseil qui suivait
était de ne pas les refermer une par une, la tentation étant le mécanisme même
qui produit du travail justifié mais hors priorité. Ce conseil valait sous le
gel du dépôt, décidé pour protéger la préparation de l'oral. Le gel a été levé
par le lecteur pour reprendre les travaux sur la plateforme, et V-02 et V-07 ont
été traités : c'est une décision de priorité, pas un contournement de la règle.
Elle est passée à trois le 08/09, les deux commentaires fautifs ayant été
corrigés en marge de l'analyse des sources de données.

Ce qui reste vrai, et qu'il faut garder : **nommer une limite de sa propre
plateforme est un exercice que le jury cherche à provoquer.** Les trois écarts
ci-dessous valent mieux assumés à l'oral que corrigés en silence, et V-03 est
désormais celui qu'il faut savoir énoncer le premier.

- **V-03, `GAMELENS_SERVICE` en `ACCOUNTADMIN`.** Devient le plus important des
  écarts ouverts depuis que V-02 et V-07 sont refermés.
- **V-01, expiration du compte Snowflake les 17 ou 18/12/2026.** À confirmer
  dans Snowsight. Seul point de vigilance réellement bloquant : c'est la date
  qui contraint, pas le budget, mesuré à une vingtaine de crédits sur 400 pour
  les 108 jours restants.
- Réduire `COMPUTE_WH` et lui imposer une suspension automatique : cet entrepôt
  jamais configuré pesait 43 % de la consommation au 27/08/2026 et **32 % au
  31/08** (0,4372 puis 0,6899 crédit). La part recule parce que l'entrepôt du
  projet sert davantage, pas parce que le problème se résorbe. Citer la mesure
  datée, jamais le pourcentage seul (OBS-57).
- ~~**`dim_games.critical_tier` est vide** alors que son commentaire annonçait une
  dérivation par un modèle dbt inexistant, et le commentaire de `fact_prices`
  annonçait encore « Alimentee par le scraping GOG ».~~ **Traités le
  08/09/2026**, en réponse au point 5 du lecteur sur les sources de données. Les
  deux commentaires disent désormais le vrai, dans les deux couches, et les
  dictionnaires ont été régénérés.

  Deux enseignements valent plus que la correction elle-même.

  D'abord, **cette entrée affirmait à son tour quelque chose de faux** : « la
  cible Snowflake, elle, est juste ». Elle ne l'était pas.
  `sql/commentaires_gold_snowflake.sql` ne contenait que des
  `COMMENT ON COLUMN`, jamais un seul `COMMENT ON TABLE`. Les commentaires de
  table ne vivaient donc que dans la clause `COMMENT =` du fichier de schéma,
  celui qu'on ne peut pas rejouer sans détruire la couche de démonstration.
  L'écart était deux fois plus large qu'annoncé, et il l'est resté trois
  semaines parce que personne n'avait vérifié l'affirmation qui le minorait.

  Ensuite, le manque n'était pas dans un commentaire mais dans **l'absence de
  tout moyen de le corriger**. Les quatre tables portent maintenant leur
  `COMMENT ON TABLE`, y compris les deux dont le texte était déjà juste. Voir
  OBS-94.

  Ce qui subsiste, désormais déclaré plutôt que masqué : `critical_tier` et
  `metacritic_score` restent vides, faute de catalogue branché. C'est une
  conséquence de la source unique, pas un défaut de schéma.

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
