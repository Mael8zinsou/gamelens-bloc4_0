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

| Élément | Statut |
|---|---|
| Schéma Gold PostgreSQL (prototype) | ✅ Construit et testé (contraintes + rôles vérifiés) |
| Schéma Gold Snowflake (cible réelle) | 🟡 Conçu et relu, **exécution réelle à faire côté utilisateur** (Snowsight ou Claude Code) |
| Pipeline temps réel (Steam Web API) | 🔴 À faire |
| Orchestrateur (Airflow) | 🔴 À faire |
| Calcul distribué (Snowpark, décidé le 19/08) | 🔴 À faire |
| Pipeline CI/CD | 🔴 À faire |
| Supervision et alertes | 🔴 À faire |
| Documentation technique / feuille de route | 🔴 À faire, une fois le reste construit (décrire le réel, pas l'anticiper) |
| Cahier de recettes complet | 🔴 À faire au fil de l'eau, pas à la fin. Voir `sql/verify_snowflake_constraints.sql` : à exécuter pour de vrai et consigner les résultats observés. |
| Incident réel documenté | 🔴 À faire (candidat : rejouer l'incident GOG du Bloc 3) |

## Prochaine étape immédiate

1. Ouvrir ce dossier dans VS Code avec Claude Code.
2. Exécuter `sql/schema_gold_snowflake.sql` dans Snowsight ou via Claude Code (connecteur Python /
   SnowSQL). Noter tout ajustement de syntaxe nécessaire dans ce fichier CLAUDE.md et dans le script
   lui-même (commentaire daté).
3. Exécuter `sql/verify_snowflake_constraints.sql` et remplacer les commentaires "ATTENDU" par les
   résultats réellement observés (avec capture d'écran si utile pour le support de soutenance).
4. Revenir en conversation pour concevoir le premier des 3 pipelines (temps réel, Steam Web API).

## Conventions de travail

- Toujours tester réellement avant de documenter. Un composant "conçu" mais jamais exécuté n'est pas
  terminé.
- Conserver les logs et sorties réelles des tests et des runs (fichiers `.log`, captures), ils
  serviront de preuve et de matière pour le support de soutenance.
- Pas de tiret cadratin (—) dans les documents écrits destinés au dossier ou au support final.
- Ce fichier (`CLAUDE.md`) doit être tenu à jour au fil de l'avancement : cocher les cases,
  documenter les choix techniques assumés (ex : alternative à Kafka) et les échecs rencontrés.
