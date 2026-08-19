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
  (PostgreSQL), Gold (Snowflake mart). **Compte d'essai Snowflake disponible** : le Gold cible
  désormais Snowflake réellement (`sql/schema_gold_snowflake.sql`), le prototype PostgreSQL
  (`sql/schema_gold.sql`) reste comme mise au point initiale et référence de comparaison, pas comme
  cible finale.
- Orchestration batch : Apache Airflow. Temps réel : Apache Kafka (ou toute alternative légère
  équivalente si Kafka est trop lourd à faire tourner en local — à documenter comme un choix assumé).
  Calcul distribué : **Snowpark** (choisi le 19/08/2026 plutôt que PySpark local, pour un calcul
  réellement distribué sur le compute Snowflake plutôt qu'en mode local sur une seule machine,
  plus défendable face au jury sur "en quoi est-ce distribué ?").
- ETL : Python/pandas, dbt, table `game_mapping` pour la résolution d'identifiants cross-plateformes.
  **Point d'architecture Snowflake important** : les contraintes PK/FK/CHECK sont déclarées dans le
  schéma mais ne sont pas appliquées à l'écriture par Snowflake (seul NOT NULL l'est réellement).
  L'intégrité réelle est donc reportée sur des tests dbt (`not_null`, `unique`, `relationships`,
  `expression_is_true`), qui font échouer le run du pipeline en cas de violation. C'est un choix
  d'architecture à assumer explicitement à l'oral, pas un oubli — voir
  `sql/verify_snowflake_constraints.sql` pour la vérification empirique de ce comportement.
- Conventions de nommage (posées au Bloc 2, 1.3) : préfixe `dim_`/`fact_`, snake_case, clé primaire
  interne UUID indépendante des identifiants sources.
- 4 rôles de sécurité déjà actés : `admin`, `etl_service`, `analyst`, `dashboard_viewer` (déclinés en
  rôles Snowflake `gamelens_etl_service`, `gamelens_analyst`, `gamelens_dashboard_viewer`).
- Schéma Gold (conçu et déclaré, **exécution réelle Snowflake à confirmer côté utilisateur** — pas
  d'accès réseau à Snowflake depuis l'environnement de conception) : `dim_games`, `dim_stores`,
  `fact_prices`, `fact_popularity_history` (grain journalier, colonnes larges, pas de modèle EAV),
  plus une vue `v_popularity_dashboard` et un warehouse `gamelens_wh` dimensionné XS avec
  auto-suspend à 60s pour préserver les crédits d'essai.
- Sources de données : API RAWG (catalogue), Steam Web API (`GetNumberOfCurrentPlayers`, sans auth),
  Twitch API (OAuth), scraping GOG (mesures anti-bot rencontrées et arbitrées au Bloc 3 — cet
  incident est un bon candidat pour l'incident réel du C4.4.2, à rejouer plutôt qu'à documenter a
  posteriori si l'occasion se présente).

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
- Cahier de recettes et de tests (C4.4.1) — voir `sql/test_schema_gold.sql` pour le format retenu
  (PASS/FAIL vérifié sur un résultat attendu, pas seulement "la requête s'exécute sans erreur").
- Méthodologie d'investigation et de traitement d'un incident réel (C4.4.2).

## État d'avancement

Mis à jour le 19/08/2026 en fin de session 1.

| Élément | Statut |
|---|---|
| Dépôt git dédié, structure, .gitignore | ✅ Fait (dépôt initialisé sur place, décision 2b) |
| Socle Docker (PostgreSQL 16 + Kafka 3.9 KRaft) | ✅ Construit, démarré, conteneurs *healthy* |
| Schéma Silver speed PostgreSQL | ✅ Construit et initialisé automatiquement au démarrage du conteneur |
| Pipeline temps réel (Steam Web API) | ✅ **Exécuté de bout en bout** : 15 titres collectés, publiés dans Kafka, écrits en base. Idempotence prouvée par rejeu (15 relus, 0 inséré). |
| Schéma Gold PostgreSQL (prototype) | ✅ Construit et testé (contraintes + rôles vérifiés) |
| Schéma Gold Snowflake (cible réelle) | 🔴 Bloqué : compte d'essai à recréer (INC-003) |
| Orchestrateur (Airflow) | 🔴 À faire, en conteneur obligatoirement (INC-001) |
| Calcul distribué (Snowpark, décidé le 19/08) | 🔴 Bloqué par la recréation du compte Snowflake |
| Pipeline CI/CD | 🔴 À faire |
| Supervision et alertes | 🟡 Amorcé : table `speed.pipeline_runs` alimentée par tous les composants |
| Documentation technique / feuille de route | 🟡 Amorcé : `README.md`. Le reste une fois le reste construit. |
| Cahier de recettes complet | 🟡 Premiers résultats réels disponibles (idempotence, résolution des 15 appid) |
| Incident réel documenté | ✅ **INC-004 retenu** : collision de ports masquée par une erreur d'encodage. Incident réellement vécu, investigué et résolu en session 1. L'incident GOG du Bloc 3 reste en filet de sécurité. |

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

1. Recréer le compte d'essai Snowflake, puis exécuter `sql/schema_gold_snowflake.sql`
   et `sql/verify_snowflake_constraints.sql` en consignant les résultats observés.
2. Monter Airflow en conteneur et écrire le DAG de promotion Silver speed vers Gold.
3. Écrire le pipeline CI/CD (GitHub Actions), C4.2.3 étant éliminatoire.

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

### Note de calendrier sur le compte d'essai Snowflake

Un compte d'essai Snowflake a une durée de vie limitée (30 jours, crédits
plafonnés). Le recréer avant d'en avoir l'usage immédiat consommerait la fenêtre
d'essai pendant une période où rien ne l'utilise, avec le risque qu'elle soit
expirée le jour de la soutenance. La recréation est donc **volontairement
différée** jusqu'au moment où les modèles dbt et le DAG de promotion seront
prêts à être pointés dessus.

Conséquence de conception à respecter d'ici là : tout ce qui est construit vers
la couche Gold doit l'être derrière une frontière de configuration, de sorte que
le basculement PostgreSQL vers Snowflake soit un changement de connexion et non
une réécriture.
