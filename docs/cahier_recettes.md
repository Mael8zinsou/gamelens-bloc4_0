# Cahier de recettes et de tests, GameLens Bloc 4

Livrable **C4.4.1**. Le critère d'évaluation demande que le cahier reprenne
l'ensemble des fonctionnalités attendues, et que les tests fonctionnels,
structurels et de sécurité exécutés soient conformes au plan défini.

## Principe retenu

Un test n'est validé que si un **résultat attendu explicite** a été comparé à un
**résultat observé**. « La commande s'exécute sans erreur » n'est pas un
résultat attendu : un pipeline qui écrit zéro ligne sans planter satisfait ce
critère tout en étant en panne.

Chaque cas porte donc ce qui est testé, la méthode, l'attendu, l'observé et la
date d'exécution réelle.

## Types de tests couverts

| Type | Ce qu'il vérifie ici |
|---|---|
| Fonctionnel | Le système produit la donnée attendue, du bon volume et du bon contenu |
| Structurel | Les contraintes d'intégrité, le grain des tables, la rejouabilité |
| Sécurité | Le cloisonnement des rôles et la non-exposition des secrets |
| Non-régression | Rejeu automatisé par la CI à chaque modification du dépôt |

---

# 1. Tests fonctionnels

## TF-01. Résolution des identifiants Steam de la watchlist

- **Méthode** : appel de `store.steampowered.com/api/appdetails` pour les
  15 titres, comparaison du nom retourné au nom unifié.
- **Attendu** : 15 identifiants résolus, 0 échec.
- **Observé (19/08/2026)** : **15 résolus, 0 échec**. Un écart de libellé sur
  Disco Elysium, nommé « Disco Elysium - The Final Cut » côté Steam.
- **Verdict** : **PASS**. L'écart est conservé comme cas de démonstration de la
  table `game_mapping`, ce n'est pas une anomalie.

## TF-02. Collecte temps réel de bout en bout

- **Méthode** : `steam_producer.py --once` puis `kafka_to_postgres.py`.
- **Attendu** : 15 événements publiés, 15 lignes dans `speed.player_count_events`.
- **Observé (19/08/2026)** : **15 publiés, 15 écrits**.
- **Verdict** : **PASS**.

## TF-03. Collecte tarifaire Steam

- **Objet** : la tarification est alimentée sans scraping, conformément à
  l'arbitrage du Bloc 3 qui a sorti GOG du périmètre.
- **Méthode** : `steam_prices.py`, endpoint `appdetails` avec `price_overview`.
- **Attendu** : un relevé par titre exposant un tarif, montants convertis des
  centimes vers l'euro, promotions détectées.
- **Observé (20/08/2026)** : **15 relevés sur 15 titres**, de 4,99 à 37,99 EUR,
  dont une promotion réelle de 60 % sur Cult of the Lamb (9,19 au lieu de 22,99).
- **Verdict** : **PASS**.

## TF-04. Promotion vers la couche Gold

- **Méthode** : exécution du DAG `gamelens_promotion_gold`, puis comptage.
- **Attendu** : dimensions et faits non vides, cohérents avec la watchlist.
- **Observé (20/08/2026)** : **15 `dim_games`, 1 `dim_stores`, 15
  `fact_popularity_history`, 45 `fact_prices`** (trois relevés horodatés distincts).
- **Verdict** : **PASS**.

## TF-05. Accès self-service par la vue de tableau de bord

- **Objet** : `mart.v_popularity_dashboard` expose une lecture agrégée sans
  donner accès aux tables de faits.
- **Attendu** : la vue retourne des lignes jointes dimension et fait.
- **Observé (20/08/2026)** : lignes retournées, colonnes limitées à
  `unified_name`, `genre`, `critical_tier`, `day`, `avg_player_count`,
  `avg_viewer_count`.
- **Verdict** : **PASS**. Les colonnes de popularité diffusée sont nulles, la
  source Twitch n'étant pas branchée : limite de périmètre à annoncer, pas un échec.

---

# 2. Tests structurels

## TS-01. Idempotence du puits temps réel

Le test le plus important du projet : il vérifie une garantie revendiquée.

- **Méthode** : remise à zéro des offsets du groupe de consommation
  (`kafka-consumer-groups.sh --reset-offsets --to-earliest --execute`), puis
  relance du consumer sur des messages déjà traités.
- **Attendu** : 15 messages relus, **0 inséré**, table stable à 15 lignes.
- **Observé (19/08/2026)** : **15 relus, 0 inséré, 15 doublons absorbés**,
  `SELECT count(*)` retourne **15** et non 30.
- **Verdict** : **PASS**. L'*effectively-once* est obtenu par la contrainte
  `UNIQUE (steam_appid, collected_at)` combinée à `ON CONFLICT DO NOTHING` et à
  la validation de l'offset après le commit PostgreSQL.
- **Automatisé** : oui, étage `integration` de la CI.

## TS-02. Idempotence de la promotion batch

- **Méthode** : trois exécutions du DAG sur la même journée.
- **Attendu** : `mart.dim_games` et `mart.fact_popularity_history` stables à 15.
- **Observé (20/08/2026)** : **stables à 15 après trois runs**.
- **Verdict** : **PASS**, après correction. Les contraintes d'unicité nécessaires
  manquaient au schéma initial, voir INC-005.

## TS-03. Porte de fraîcheur, test négatif

- **Objet** : le DAG refuse de promouvoir une journée sans données, au lieu de
  réussir en n'écrivant rien.
- **Méthode** : déclenchement du DAG sur une journée volontairement vide.
- **Attendu** : **échec** de `verifier_fraicheur_silver`, avec un message nommant
  la cause probable.
- **Observé (20/08/2026)** : `ValueError: Aucun evenement de frequentation pour
  le 2026-08-20. Le pipeline temps reel a-t-il tourne ? Promotion interrompue.`
- **Verdict** : **PASS**. Un test dont l'attendu est un échec : une porte qu'on
  n'a jamais vue se fermer n'est pas une porte.

## TS-04. Reprise automatique après échec transitoire

- **Méthode** : non provoqué, observé. Échec de TS-03 à 07:52:17, données
  produites à 07:54, seconde tentative automatique à 07:57:17.
- **Attendu** : le run se termine en succès sans intervention.
- **Observé (20/08/2026)** : **run complet en succès à 07:57:36**, six tâches
  vertes, aucune intervention manuelle.
- **Verdict** : **PASS**.

## TS-05. Contrôles de qualité de la couche Gold

Exécutés à chaque run par la tâche `controler_qualite_gold`, en PASS/FAIL.

| Contrôle | Attendu | Observé (20/08/2026) |
|---|---|---|
| `dim_games` sans nom unifié | 0 | 0 |
| `fact_prices` avec prix négatif ou nul | 0 | 0 |
| `fact_popularity_history` orpheline de `dim_games` | 0 | 0 |
| Doublons sur le grain (`game_id`, `day`) | 0 | 0 |
| Popularité moyenne négative | 0 | 0 |
| Faits de popularité présents pour la journée | > 0 | 15 |

- **Verdict** : **PASS**, 6 contrôles au vert. Une violation fait échouer le run
  plutôt que d'être constatée plus tard sur un tableau de bord faux.

## TS-06. Intégrité du DAG Airflow

- **Méthode** : conteneur jetable, `airflow db migrate`, `airflow dags reserialize`,
  `airflow dags list-import-errors`, puis présence du DAG dans `airflow dags list`.
- **Attendu** : aucune erreur d'import, DAG présent.
- **Observé (20/08/2026)** : **ÉCHEC au premier essai**, DAG absent de la liste
  malgré l'absence d'erreur d'import. Cause : en Airflow 3, `dags list` lit la
  base de métadonnées et non le dossier. **PASS** après ajout de `reserialize`.
- **Verdict** : **PASS** après correction. Cas typique de test qui a servi à
  quelque chose, en attrapant un défaut du test lui-même.
- **Automatisé** : oui, étage `dag` de la CI.

## TS-07. Cohérence du schéma Silver speed

- **Méthode** : comptage des objets du schéma `speed` après initialisation
  automatique du conteneur PostgreSQL.
- **Attendu** : 4 tables de base et 1 vue.
- **Observé (20/08/2026)** : **ÉCHEC au premier passage en CI**. L'assertion
  comptait `information_schema.tables` sans filtrer `table_type`, or cette vue
  système inclut les vues : 4 attendues, 5 trouvées. Le défaut était dans le
  test, pas dans l'infrastructure. **PASS** après séparation des deux comptages.
- **Verdict** : **PASS** après correction.
- **Automatisé** : oui, étage `integration` de la CI.

## TS-08. Contraintes Snowflake, vérification empirique

- **Objet** : établir ce que Snowflake applique réellement à l'écriture, plutôt
  que de le supposer d'après la documentation.
- **Méthode** : `sql/verify_snowflake_constraints.sql`.
- **Attendu** : seul `NOT NULL` rejette ; `CHECK`, `FOREIGN KEY` et `PRIMARY KEY`
  sont déclaratifs et laissent passer.
- **Observé** : **non exécuté**, compte d'essai à recréer (INC-003).
- **Verdict** : **EN ATTENTE**. Ce résultat conditionne l'argumentaire sur le
  report de l'intégrité vers des tests dbt.

---

# 3. Tests de sécurité

## TSEC-01. Cloisonnement effectif des rôles applicatifs

- **Objet** : vérifier la matrice complète des droits, **refus compris**. Un
  droit accordé se vérifie en l'exerçant, un droit refusé ne se constate qu'en
  tentant l'opération interdite.
- **Méthode** : `tests/test_securite_roles.py`, une connexion par rôle, 13 cas
  paramétrés, chacun dans une transaction annulée. Seule
  `InsufficientPrivilege` est interceptée : une table manquante lèverait
  `UndefinedTable` et ferait échouer le test au lieu de se déguiser en refus.

| Rôle | Vue Gold | Agrégat Silver | Table de faits Gold | Dimension Gold | Événements bruts | Écriture | Suppression |
|---|---|---|---|---|---|---|---|
| `dashboard_viewer` | ✅ | ✅ | ⛔ | ⛔ | ⛔ | ⛔ | n/a |
| `analyst` | ✅ | ✅ | ✅ | ✅ | ✅ | ⛔ | ⛔ |
| `etl_service` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⛔ |

- **Observé (20/08/2026)** : **13 tests sur 13 conformes**, dont 7 refus.
- **Verdict** : **PASS**.
- **Automatisé** : oui, étage `integration` de la CI. Ignorés automatiquement
  quand la base n'est pas joignable, donc sautés par l'étage `tests`.

### Validation du test lui-même

Un test de refus peut passer pour de mauvaises raisons. Vérification faite :

1. `GRANT SELECT ON mart.fact_popularity_history TO dashboard_viewer`
2. relance du test : **échec**, `attendu refuse, obtenu autorise`
3. `REVOKE`, relance : **13 tests verts**

Le test détecte donc réellement une brèche de cloisonnement.

### Défaut corrigé à cette occasion

L'écriture de ce test a révélé que la plateforme portait **deux modèles de rôles
concurrents** : `etl_service` / `analyst` / `dashboard_viewer` côté Gold, et
`gamelens_etl` / `gamelens_reader` côté Silver. Aligné sur le modèle du Bloc 1,
rôles orphelins supprimés. Voir OBS-25.

## TSEC-02. Non-exposition des secrets dans le dépôt

- **Méthode** : `.env` listé dans `.gitignore`, contrôle par `git ls-files`.
- **Attendu** : `.env` absent des fichiers suivis.
- **Observé (20/08/2026)** : **absent**, correctement ignoré. Les seuls mots de
  passe présents sont des valeurs de développement local (`devlocal_*`), et le
  dépôt distant est **privé**.
- **Verdict** : **PASS**.

## TSEC-03. Moindre privilège de l'outil de visualisation

- **Objet** : Grafana ne se connecte pas avec le propriétaire de la base.
- **Méthode** : source de données provisionnée avec le rôle `analyst`, en
  lecture seule.
- **Attendu** : connexion fonctionnelle, écriture impossible.
- **Observé (20/08/2026)** : `Database Connection OK` via l'API Grafana, et
  l'impossibilité d'écrire est garantie par TSEC-01, qui teste ce rôle.
- **Verdict** : **PASS**.

---

# 4. Tests de supervision (C4.3.1)

## TSUP-01. Les indicateurs reflètent l'état réel de la plateforme

- **Méthode** : lecture de `speed.v_supervision_synthese` après une session de
  travail réelle.
- **Attendu** : un état par élément surveillé, cohérent avec ce qui s'est
  effectivement passé.
- **Observé (20/08/2026)** :

| Élément | Valeur | État |
|---|---|---|
| Fraîcheur fréquentation | 209,3 min | critique |
| Complétude de la collecte | 100 % | nominal |
| Latence du pipeline (p95) | 64 890 s | critique |
| Retard de l'entrepôt Gold | 0 jour | nominal |

- **Verdict** : **PASS**. Les deux états critiques sont **exacts** : le
  producteur ne tourne pas en continu sur un poste de développement, et les
  15 messages de la session 1 sont réellement restés 18 heures dans Kafka avant
  d'être consommés. L'indicateur de latence a donc détecté un incident réel dès
  sa création, sans qu'on le lui demande. Voir OBS-29.

## TSUP-02. Cycle de vie complet d'une alerte

Trois comportements vérifiés séparément.

| Étape | Attendu | Observé (20/08/2026) |
|---|---|---|
| Déclenchement | Alertes ouvertes avec valeur et seuil | 2 déclenchées, 2 nouvelles |
| Persistance sans doublon | Condition inchangée, aucune nouvelle ligne | 2 déclenchées, **0 nouvelle**, 2 lignes en base |
| Fermeture automatique | Condition levée, alerte résolue et horodatée | `[RESOLUE] fraicheur_frequentation` |

- **Verdict** : **PASS**. La colonne `resolue_le` permet de mesurer la durée d'un
  incident, pas seulement son occurrence.

## TSUP-03. Remontée des alertes par l'orchestrateur

- **Méthode** : DAG `gamelens_supervision`, déclenché avec un avertissement
  ouvert et aucune alerte critique.
- **Attendu** : `evaluer_regles` réussit, `remonter_alertes_critiques` réussit
  en signalant l'avertissement, sans faire échouer le run.
- **Observé (20/08/2026)** : les deux tâches en succès, avec en journal
  `[AVERTISSEMENT] latence_pipeline (ouverte depuis 2026-08-20 11:24)` puis
  `1 avertissement(s) ouvert(s), aucune alerte critique.`
- **Verdict** : **PASS**. La séparation entre évaluer et s'alarmer permet de
  distinguer « la plateforme va mal » de « le moteur d'alertes est cassé ».
  Voir OBS-31.

## TSUP-04. Tous les panneaux du tableau de bord fonctionnent

- **Objet** : un panneau dont la requête échoue reste affiché avec un message
  discret et se confond avec un panneau vide.
- **Méthode** : `supervision/verifier_tableau_bord.py`, qui exécute la requête
  de chaque panneau **à travers l'API Grafana**, donc en passant par la source
  de données provisionnée et son rôle en lecture seule.
- **Attendu** : 7 panneaux fonctionnels, 0 en échec.
- **Observé (20/08/2026)** : **7 sur 7**, de 1 à 5 lignes chacun.
- **Verdict** : **PASS**. Le contrôle valide d'un coup le SQL, la résolution de
  la source de données, les droits du rôle `analyst` et la présence effective du
  tableau de bord provisionné.

## TSUP-05. Le moteur d'alertes se supervise lui-même

- **Objet** : conséquence directe d'INC-007, où un composant tournait sans
  laisser de trace.
- **Attendu** : une ligne `moteur_alertes` dans `speed.pipeline_runs` après
  chaque évaluation.
- **Observé (20/08/2026)** : ligne présente, `lus=6, ecrits=2`.
- **Verdict** : **PASS**.
- **Automatisé** : oui, étage `integration` de la CI, avec assertion explicite.

---

# 5. Tests de non-régression automatisés

Exécutés par la CI à chaque `push` et chaque `pull request`, dépôt
`Mael8zinsou/gamelens-bloc4_0`.

| Étage | Contenu | Première exécution réelle |
|---|---|---|
| `qualite` | `ruff check` et `ruff format --check` | ✅ vert du premier coup |
| `tests` | 14 tests unitaires, sans réseau ni base | ✅ vert du premier coup |
| `dag` | Intégrité du DAG dans un conteneur jetable | ✅ vert du premier coup |
| `integration` | Socle Docker réel, pipeline complet, rejeu d'idempotence | ❌ puis corrigé, voir TS-07 |
| `publication` | Image Airflow poussée sur `ghcr.io` | Ignoré tant que l'intégration échoue |

Les 14 tests unitaires couvrent la structure de la watchlist (5 cas) et la
lecture des réponses tarifaires Steam (9 cas : tarif plein, promotion à 60 %,
prix initial absent, jeu sans tarif exposé, réponse en échec, et 4 cas de
conversion des centimes).

**Point à assumer à l'oral** : la première exécution réelle du workflow a
échoué. C'est le résultat normal et utile d'une chaîne d'intégration. Les trois
premiers étages avaient été rejoués localement avec les mêmes commandes et
passaient ; l'étage qui a échoué est précisément celui qui ne pouvait pas
l'être, faute d'un environnement jetable en local. Une CI qui passe au vert du
premier coup sur cinq étages n'a en général rien vérifié.

---

# 6. Fonctionnalités attendues non encore couvertes

Le critère demande que le cahier reprenne **l'ensemble** des fonctionnalités
attendues. Ce qui suit est donc listé explicitement plutôt qu'omis.

| Fonctionnalité | État | Blocage |
|---|---|---|
| Calcul distribué (Snowpark) | Non construit | Compte d'essai Snowflake à recréer |
| Couche Gold sur Snowflake | Non exécutée | Idem |
| Popularité diffusée (Twitch) | Non branchée | Colonnes présentes mais nulles |
| Catalogue RAWG | Non branché | `dim_games` alimentée depuis la watchlist |
| Alertes vers un canal externe | Non construit | Les alertes sont persistées et remontées par Airflow, mais aucune notification par courriel ou messagerie n'est configurée |

---

# 7. Synthèse

| Catégorie | PASS | PARTIEL | EN ATTENTE |
|---|---|---|---|
| Fonctionnels | 5 | 0 | 0 |
| Structurels | 7 | 0 | 1 |
| Sécurité | 3 | 0 | 0 |
| Supervision | 5 | 0 | 0 |
| **Total** | **20** | **0** | **1** |

Les tests de sécurité comptent pour 3 cas au niveau du cahier, mais 13 cas
paramétrés au niveau de l'exécution.

Trois de ces tests ont échoué avant de passer, et c'est ce qui leur donne de la
valeur : TS-02 a révélé des contraintes d'unicité manquantes, TS-03 a été conçu
pour échouer et l'a fait, TS-06 et TS-07 ont chacun mis au jour un défaut de
l'assertion elle-même. Un test qui n'a jamais rien attrapé n'a pas encore
prouvé qu'il testait quelque chose.
