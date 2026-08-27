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
- **Méthode** : `sql/verify_snowflake_constraints.sql`, exécuté en mode
  poursuite sur erreur, certaines instructions devant échouer.
- **Exécuté le 20/08/2026** sur le compte `RTZSXDV-PM63908`, région
  `AWS_EU_WEST_3`, Snowflake 10.29.101.

| Contrainte déclarée | Appliquée à l'écriture ? | Preuve |
|---|---|---|
| `NOT NULL` | **OUI** | TEST 2 rejeté, erreur 100072 |
| Type et longueur, `VARCHAR(36)` | **OUI** | découvert par accident, voir ci-dessous |
| `CHECK (price > 0)` | NON | TEST 3 accepte un prix de -5,00 |
| `FOREIGN KEY` | NON | TEST 4 accepte un `game_id` absent de `dim_games` |
| `PRIMARY KEY (game_id, day)` | NON | TEST 5 insère deux fois le même couple |

- **Verdict** : **PASS**.

### Le test était lui-même défectueux

Première exécution : le TEST 4 **échoue**, ce qui semblait prouver que la clé
étrangère est appliquée. Le message disait pourtant
`String 'inexistant-0000-...' is too long`, et non une violation référentielle :
l'identifiant de test faisait 38 caractères pour une colonne `VARCHAR(36)` et
était rejeté sur la **longueur**, avant que la contrainte ne soit évaluée.
Raccourci à 35 caractères, le TEST 4 réussit. Voir OBS-36.

L'échec a livré une information non anticipée, portée au tableau ci-dessus :
Snowflake applique aussi les contraintes de type.

### Conséquence, démontrée et non supposée

Le TEST 6 interroge la vue de restitution après l'insertion volontaire du
doublon. Elle retourne **2 lignes**. Deux mesures contradictoires pour le même
jeu et le même jour atteignent donc le tableau de bord sans qu'aucune alerte ne
se déclenche. C'est ce qui justifie de reporter l'intégrité sur des contrôles
exécutés à chaque run, rôle tenu par `entrepot/verifier_gold.py` et, côté
PostgreSQL, par la tâche `controler_qualite_gold` du DAG.

### Reformulation induite

`CLAUDE.md` écrivait que « seul `NOT NULL` est réellement appliqué ». Formulation
exacte tirée des observations : **les contraintes portées par la colonne
elle-même sont appliquées** (NOT NULL, type, longueur), **celles qui portent sur
une relation entre lignes ou entre tables ne le sont pas**.

## TS-09. Application du schéma Gold sur Snowflake

- **Méthode** : `entrepot/executer_sql.py sql/schema_gold_snowflake.sql`.
- **Attendu** : toutes les instructions passent, entrepôt virtuel, base, schéma,
  4 tables, 1 vue, 3 rôles et leurs droits.
- **Observé (20/08/2026)** : **27 instructions réussies, 0 en erreur**.
- **Verdict** : **PASS**. Un premier passage avait signalé une 28e instruction en
  erreur : le découpeur traitait un bloc de commentaires de fin de fichier comme
  une instruction. Défaut de l'exécuteur, corrigé, pas du schéma.

## TS-10. Promotion distribuée Snowpark

- **Méthode** : `entrepot/snowpark_promotion.py`.
- **Attendu** : extraction Silver, transit, MERGE vers Gold, calcul analytique.
- **Observé (20/08/2026)** : 15 + 30 + 75 lignes extraites et téléversées,
  puis **15 dimensions, 30 faits de popularité, 75 faits tarifaires** promus.
- **Verdict** : **PASS**.

## TS-11. Idempotence de la promotion Snowpark

- **Objet** : Snowflake n'appliquant aucune contrainte d'unicité, la
  rejouabilité repose entièrement sur les clauses `MERGE`. Sans elles, rien
  n'empêcherait la duplication.
- **Méthode** : trois exécutions successives du même script.
- **Attendu** : 0 insertion aux passages suivants, uniquement des mises à jour.
- **Observé (20/08/2026)** : `dim_games : 0 insertion, 15 mises à jour`,
  `fact_popularity_history : 0 insertion, 30 mises à jour`,
  `fact_prices : 0 insertion, 75 mises à jour`.
- **Verdict** : **PASS**.

## TS-12. Le calcul a bien lieu dans l'entrepôt, pas en local

- **Objet** : répondre à « en quoi est-ce distribué ? » par une preuve.
- **Méthode** : affichage du SQL généré par Snowpark, puis interrogation de
  `information_schema.query_history_by_session()`.
- **Attendu** : les fenêtres analytiques apparaissent dans le SQL envoyé, et
  l'historique montre les requêtes exécutées par l'entrepôt virtuel.
- **Observé (20/08/2026)** : le SQL contient
  `rank() OVER (PARTITION BY "GENRE" ORDER BY ...)` et
  `avg(...) OVER (PARTITION BY "GAME_ID" ORDER BY "JOUR" ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)`.
  L'historique liste des requêtes `SELECT` et `MERGE` sur `GAMELENS_WH`, taille
  `X-Small`, cluster 1, de 4 096 à 6 144 octets parcourus, 17 à 314 ms
  d'exécution.
- **Verdict** : **PASS**. Le processus Python n'a envoyé qu'un plan et reçu un
  résultat.

## TS-13. Contrôles d'intégrité de la couche Gold Snowflake

- **Méthode** : `entrepot/verifier_gold.py`, 8 contrôles, chacun cherchant les
  violations et attendant 0.
- **Observé (20/08/2026)** : **8 contrôles au vert**, sur une couche contenant
  15 dimensions jeu, 1 boutique, 30 faits de popularité, 75 faits tarifaires.
- **Verdict** : **PASS**. Ces contrôles ne doublent pas le moteur ici, ils le
  remplacent : voir TS-08.

## TS-14. Recette automatisée de l'entrepôt sur base jetable

- **Objet** : couvrir par la CI la seule partie de la plateforme qui ne l'était
  pas. `entrepot/` passait au contrôle de qualité, mais rien ne l'exécutait,
  faute d'identifiants sur le runner.
- **Méthode** : `entrepot/recette_ci.py`. Une base Snowflake est créée pour la
  durée du run, éprouvée en sept étapes, puis supprimée. Le schéma appliqué est
  le script **livré**, redirigé vers la base jetable, et non une copie
  simplifiée : une erreur de DDL introduite dans le livrable est donc vue.
- **Attendu** : 27 instructions de schéma sans erreur, 8 contrôles d'intégrité
  au vert sur données saines, puis les résultats détaillés en TS-15 et TS-16.
- **Observé (26/08/2026)** : **27 réussies, 0 en erreur** ; **8 contrôles au
  vert** sur 3 jeux, 1 boutique, 24 faits de popularité et 3 tarifs ; durée
  totale **36 secondes**.
- **Verdict** : **PASS**.
- **Vérification collatérale** : la couche de démonstration `gamelens` a été
  recontrôlée après coup. 75 faits tarifaires, 8 contrôles au vert, intacte.

## TS-15. Le calcul distribué rend les valeurs calculées à la main

- **Objet** : le calcul Snowpark de C4.2.2 était prouvé par une exécution
  manuelle et par le SQL généré. Il manquait la vérification du **résultat**.
- **Méthode** : jeu de données déterministe conçu pour que les agrégats soient
  calculables de tête. Trois jeux sur huit jours, deux genres. Alpha croît de
  100 en 100, Beta et Gamma restent plats.
- **Attendu**, calculé à la main avant exécution :

  | Jeu | Moyenne glissante 7 j | Rang dans le genre | Part du genre |
  |---|---|---|---|
  | Recette Alpha | (200+...+800) / 7 = 500,0 | 1 | 800 / 850 = 94,1 % |
  | Recette Beta | 50,0 | 2 | 50 / 850 = 5,9 % |
  | Recette Gamma | 10,0 | 1 | 100,0 % |

- **Observé (26/08/2026)** : les trois lignes conformes, au chiffre près.
- **Verdict** : **PASS**. La fenêtre glissante, le classement par partition et
  la part du total sont vérifiés sur leur résultat, pas sur leur absence
  d'erreur.

## TS-16. Non-régression sur le comportement des contraintes Snowflake

- **Objet** : TS-08 avait établi empiriquement, le 20/08/2026, ce que Snowflake
  applique réellement. Ce constat porte une décision d'architecture lourde,
  reporter l'intégrité sur des tests applicatifs, et il n'était vrai que ce
  jour-là. Ce cas le transforme en test rejoué à chaque push.
- **Méthode** : six insertions, chacune assortie d'un verdict attendu.
- **Attendu et observé (26/08/2026)** :

  | Contrainte éprouvée | Attendu | Observé |
  |---|---|---|
  | NOT NULL sur `unified_name` | rejet | **rejetée** |
  | Longueur `VARCHAR(36)` dépassée | rejet | **rejetée** |
  | CHECK implicite, prix négatif | acceptation | **acceptée** |
  | Clef étrangère, `game_id` inexistant | acceptation | **acceptée** |
  | Clef primaire, `(game_id, day)` en doublon | acceptation | **acceptée** |
  | Contrainte UNIQUE sur `steam_appid` | acceptation | **acceptée** |

- **Verdict** : **PASS**. 2 contraintes appliquées par le moteur, 4 laissées à
  la charge de l'applicatif.
- **Portée** : si Snowflake se mettait à appliquer les clefs étrangères, ce cas
  virerait au rouge avec un message désignant explicitement la décision
  d'architecture à réexaminer. C'est la réponse à « et si le fournisseur change
  de comportement ? ».

## TS-17. Les contrôles d'intégrité savent échouer

- **Objet** : un contrôle qui ne sait pas échouer ne prouve rien quand il
  réussit. TS-13 et TS-14 les montrent au vert ; ce cas les met en échec.
- **Méthode** : les insertions de TS-16 qui **réussissent** laissent
  volontairement des données invalides derrière elles. Les 8 contrôles sont
  rejoués sur cette couche corrompue, et le run échoue si les contrôles passent
  au vert.
- **Attendu** : 4 violations détectées, une par contrainte non appliquée.
- **Observé (26/08/2026)** :

  ```
  [FAIL] dim_games en doublon sur steam_appid           1
  [FAIL] fact_prices avec un prix negatif ou nul        1
  [FAIL] fact_prices orpheline de dim_games             1
  [FAIL] doublons sur le grain (game_id, day)           1
  -> 4 violation(s) detectee(s) par le filet applicatif : conforme
  ```

- **Verdict** : **PASS**. Quatre contraintes ignorées par le moteur, quatre
  violations rattrapées par le filet applicatif. La correspondance est exacte.

## TS-18. Le garde-fou refuse les bases protégées

- **Objet** : `sql/schema_gold_snowflake.sql` contient des
  `CREATE OR REPLACE TABLE`. Une recette mal dirigée détruirait la couche de
  démonstration sans le moindre message d'erreur.
- **Méthode** : lancer la recette en la pointant explicitement sur `gamelens`.
- **Attendu** : refus immédiat, avant toute instruction, code de sortie non nul.
- **Observé (26/08/2026)** :

  ```
  REFUS : la recette vise la base 'gamelens', qui est protegee.
  Le script de schema contient des CREATE OR REPLACE TABLE : l'executer ici
  detruirait la couche de demonstration.
  code de sortie : 1
  ```

- **Verdict** : **PASS**.
- **Défaut corrigé à cette occasion** : au premier passage, ce test **a réussi
  sans rien prouver**. La fonction de nommage écartait discrètement les noms
  protégés en retombant sur un nom généré, si bien que le garde-fou ne recevait
  jamais de nom protégé et ne pouvait jamais refuser. Le comportement était sûr
  mais mensonger. Voir OBS-42.

## TS-19. Authentification par contenu PEM, voie de l'intégration continue

- **Objet** : un dispositif de CI stocke des chaînes, pas des fichiers. La clef
  privée ne doit pas être écrite sur le disque du runner.
- **Méthode** : connexion avec `SNOWFLAKE_PRIVATE_KEY` porteur du contenu PEM
  et `SNOWFLAKE_PRIVATE_KEY_PATH` vidé, dans les conditions exactes de la CI.
- **Attendu** : connexion établie, mode d'authentification annoncé comme tel.
- **Observé (26/08/2026)** :

  ```
  authentification    paire de cles RSA (contenu en environnement)
  CONNEXION ETABLIE
  version Snowflake   10.30.101
  region              AWS_EU_WEST_3
  ```

- **Verdict** : **PASS**. Éprouvé en local avant d'être poussé, pour ne pas
  découvrir un défaut d'authentification sur le runner.

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

Exécutés par la CI à chaque `push` et chaque `pull request`, dépôt privé
`Mael8zinsou/gamelens-bloc4_0`.

| Étage | Contenu | État au 20/08/2026 |
|---|---|---|
| `qualite` | `ruff check` et `ruff format --check` sur 4 répertoires | ✅ |
| `tests` | Tests unitaires, sans réseau ni base | ✅ `14 passed, 13 skipped` |
| `dag` | Intégrité du DAG dans un conteneur jetable | ✅ |
| `integration` | Socle Docker réel, 6 contrôles métier | ✅ |
| `publication` | Image Airflow poussée sur `ghcr.io` | ✅ deux étiquettes |

## Orchestration de l'ingestion temps réel (session 6)

## TING-01. Les trois DAG sont enregistrés, et le contrôle sait échouer

- **Objet** : l'étage d'intégrité de la CI ne vérifiait qu'un DAG sur trois.
- **Procédure** : image Airflow du projet, dossier `dags/` monté, base de
  métadonnées éphémère, `airflow dags reserialize` puis recherche de chaque nom
  attendu dans `airflow dags list`.
- **Résultat attendu** : les trois noms trouvés, code de sortie 0.
- **Résultat observé** :
  ```
  PASS: aucune erreur d import
  PASS: gamelens_promotion_gold est enregistre
  PASS: gamelens_supervision est enregistre
  PASS: gamelens_ingestion_temps_reel est enregistre
  ```
- **Test négatif** : même contrôle avec `gamelens_dag_inexistant` dans la liste
  attendue. Observé : `ECHEC: gamelens_dag_inexistant absent de la liste`,
  **code de sortie 1**.
- **Verdict** : PASS.

## TING-02. Un cycle complet d'ingestion orchestrée

- **Objet** : le DAG `gamelens_ingestion_temps_reel` collecte, publie, consomme
  et écrit sans intervention.
- **Procédure** : `airflow dags trigger gamelens_ingestion_temps_reel`.
- **Résultat attendu** : trois tâches en succès, au moins un événement écrit,
  les 15 titres de la watchlist couverts, fraîcheur sous le seuil de 90 minutes,
  et les deux composants tracés dans `speed.pipeline_runs`.
- **Résultat observé** :
  ```
  Ecritures sur les 10 dernieres minutes : 45 evenement(s) sur 15 titre(s) distinct(s).
  Fraicheur de la frequentation apres ce run : 0.9 minute(s), seuil d'alerte 90.
    trace kafka_to_postgres    2 execution(s), statut success
    trace steam_producer       2 execution(s), statut success
  Ingestion conforme : 45 evenement(s), 15 titre(s), fraicheur 0.9 min, deux composants traces.
  ```
  Fraîcheur passée de **8505 minutes à 0,9 minute**.
- **Verdict** : PASS.

## TING-03. Le tampon Kafka n'a rien perdu pendant sept jours

- **Objet** : vérifier que les messages non consommés survivent à l'absence du
  consommateur. Constat non provoqué, relevé au premier run.
- **Résultat attendu** : les messages publiés sans consommateur restent
  disponibles et sont écrits au passage suivant, sans doublon.
- **Résultat observé** : le consommateur rapporte `records_in = 30` pour
  15 messages fraîchement publiés.
  ```
        collecte       | evenements |      ecrit_le
  ---------------------+------------+---------------------
   2026-08-27 09:22:12 |         15 | 2026-08-27 09:22:54
   2026-08-20 12:36:09 |         15 | 2026-08-27 09:22:54
  ```
  Quinze événements collectés le 20/08 écrits le 27/08, **sept jours plus
  tard**, sans perte et sans doublon.
- **Verdict** : PASS.

## TING-04. Broker arrêté : la chaîne échoue bruyamment et laisse une trace

- **Objet** : test négatif. Un pipeline qui réussit à ne rien faire est un
  pipeline qui ment ; encore faut-il que son échec parvienne à la supervision.
- **Procédure** : `docker stop gamelens-kafka`, puis déclenchement du DAG.
- **Résultat attendu** : tâche en échec, aval non démarré, **et** une ligne de
  statut `failed` dans `speed.pipeline_runs` portant la cause.
- **Résultat observé, première exécution** : tâche en échec avec
  `NoBrokersAvailable`, aval non démarré. Mais **zéro ligne** dans
  `pipeline_runs` : la panne était invisible pour la supervision. Défaut réel,
  documenté en INC-008 et corrigé.
- **Résultat observé après correction**, mêmes conditions :
  ```
     component    | status |     started_at      |               erreur
  ----------------+--------+---------------------+--------------------------------
   steam_producer | failed | 2026-08-27 09:40:07 | NoBrokersAvailable: NoBrokersA
  ```
- **Verdict** : PASS après correction. C'est ce test qui a trouvé le défaut.

## TING-05. Reprise automatique après retour du broker

- **Objet** : vérifier que la chaîne repart seule, sans intervention.
- **Procédure** : `docker start gamelens-kafka` pendant que le run précédent
  était en attente de reprise.
- **Résultat attendu** : la reprise automatique d'Airflow réussit, les données
  sont écrites, aucune perte.
- **Résultat observé** : reprise à 09:42:11, soit le délai de 2 minutes
  configuré, sans aucune action de l'opérateur.
  ```
   steam_producer    | success | 2026-08-27 09:42:11 |              15 |
   kafka_to_postgres | success | 2026-08-27 09:42:22 |              15 |
  ```
- **Verdict** : PASS.

## TING-06. La plateforme referme ses propres alertes

- **Objet** : vérifier que l'ingestion orchestrée résorbe l'écart que la
  supervision signalait, sans action manuelle sur les alertes.
- **Résultat attendu** : les alertes ouvertes se ferment d'elles-mêmes à
  l'évaluation suivante des règles, avec `resolue_le` renseigné.
- **Résultat observé** :

  | Moment | Fraîcheur | Complétude | Latence p95 | Retard Gold | Alertes ouvertes |
  |---|---|---|---|---|---|
  | Avant | 8505 min | 0 % | inconnue | 6 j | **5** |
  | Après ingestion | 4,4 min | 100 % | 42 s | 7 j | 1 |
  | Après promotion | 1,0 min | 100 % | 42 s | 0 j | **0** |

  Cinq indicateurs sur cinq au nominal, zéro alerte ouverte, aucune écriture
  manuelle dans `speed.alertes`.
- **Verdict** : PASS.

## Couche Bronze (session 6)

## TBRZ-01. Toute collecte alimente l'archive sans qu'on y pense

- **Objet** : la couche Bronze n'a d'intérêt que si le chemin normal l'alimente.
- **Procédure** : déclenchement du DAG d'ingestion, sans action particulière.
- **Résultat attendu** : autant de réponses archivées que de titres suivis, et
  la réponse conservée telle que reçue.
- **Résultat observé** :
  ```
         source       | lignes | ok | rejets
  --------------------+--------+----+--------
   steam_player_count |     15 | 15 |      0
  ```
  Charge archivée pour l'appid 1145360 :
  `{"response": {"result": 1, "player_count": 2776}}`
- **Verdict** : PASS.

## TBRZ-02. Un appel en échec est archivé avec son motif

- **Objet** : test du chemin de rejet, la moitié la plus utile de cette couche.
  Avant elle, une réponse inexploitable ne laissait qu'un avertissement dans les
  journaux, puis disparaissait.
- **Procédure** : appel réel à Steam sur l'appid inexistant 999999999, par le
  code de production et non par une simulation.
- **Résultat attendu** : une ligne `exploitable = false` portant la cause.
- **Résultat observé** :
  ```
   identifiant | exploitable | statut_http |            motif             | sans_charge
  -------------+-------------+-------------+------------------------------+-------------
   999999999   | f           |             | HTTPError: 404 Client Error  | t
  ```
  `charge` est NULL, aucun corps n'ayant été obtenu, ce que la contrainte
  autorise explicitement.
- **Constat collatéral** : Steam répond **404** pour un identifiant inconnu, et
  non 200 avec `result != 1` comme le commentaire du code l'affirmait depuis
  l'origine. Voir OBS-53.
- **Verdict** : PASS.

## TBRZ-03. La collecte tarifaire archive une charge plus riche que ce qu'elle exploite

- **Objet** : vérifier que la couche conserve ce que la transformation jette.
- **Procédure** : `collecter_et_tracer()` sur la watchlist complète.
- **Résultat attendu** : 15 réponses archivées, contenant des champs absents de
  `speed.price_snapshots`.
- **Résultat observé** : 15 réponses, 15 exploitables. Charge conservée :
  ```json
  {"1145360": {"data": {"price_overview": {
      "final": 2450, "initial": 2450, "currency": "EUR",
      "final_formatted": "24,50€", "discount_percent": 0,
      "initial_formatted": ""
  }}, "success": true}}
  ```
  `final_formatted` et `initial_formatted` n'existaient nulle part auparavant.
- **Verdict** : PASS.

## TBRZ-04. L'archive est immuable, y compris pour le compte qui l'alimente

- **Objet** : une archive que l'on peut modifier n'est plus une archive. La
  propriété se vérifie en tentant l'opération interdite, pas en lisant le GRANT.
- **Procédure** : matrice de droits exécutée sous chaque rôle réel.
- **Résultat attendu** :

  | Rôle | Lire | Ajouter | Modifier | Supprimer |
  |---|---|---|---|---|
  | `etl_service` | autorisé | autorisé | **refusé** | **refusé** |
  | `analyst` | autorisé | refusé | **refusé** | refusé |
  | `dashboard_viewer` | **refusé** | refusé | refusé | refusé |

- **Résultat observé** : conforme. 20 cas de sécurité exécutés, 20 conformes,
  contre 13 avant l'ajout de cette couche.
- **Verdict** : PASS.

## TBRZ-05. La vue de santé des sources distingue source et composant

- **Objet** : `bronze.v_sante_sources` mesure la santé des **sources**, ce que
  la supervision existante ne savait pas faire : elle ne surveillait que les
  composants du pipeline.
- **Résultat observé** :
  ```
         source       | appels_24h | exploitables | rejets | taux_exploitable_pct
  --------------------+------------+--------------+--------+----------------------
   steam_player_count |         32 |           31 |      1 |                 96.9
   steam_appdetails   |         15 |           15 |      0 |                100.0
  ```
  Le 96,9 % vient du rejet volontaire de TBRZ-02, délibérément conservé
  (OBS-56).
- **Verdict** : PASS.

## TBRZ-06. Volumétrie mesurée plutôt qu'estimée

- **Objet** : trancher l'objection de volume par la mesure.
- **Résultat observé** : 78 octets par réponse de fréquentation, 238 par
  réponse tarifaire, soit environ 114 Ko par jour et **41 Mo par an** à la
  cadence en place.
- **Verdict** : PASS. Le chiffre alimente la politique de conservation de la
  feuille de route (C4.3.2).

## Détail des contrôles de l'étage d'intégration

Chacun a une assertion explicite, aucun ne se contente d'un code de retour nul.

| Contrôle | Assertion | Observé |
|---|---|---|
| Initialisation des schémas | Les 17 objets nommés de `speed` et `mart` existent | aucun manquant |
| Cloisonnement des rôles | 13 cas de la matrice de droits, refus compris | `13 passed`, dont `refuse] PASSED` |
| Pipeline temps réel | Le pipeline écrit réellement des lignes | > 0 |
| Idempotence du puits | Le rejeu ne duplique rien | `avant rejeu : 15, apres rejeu : 15` |
| Moteur d'alertes | Il évalue ses règles **et se trace lui-même** | `executions du moteur tracees : 1` |

Le partage entre les deux étages est vérifié et non supposé : les 13 tests de
sécurité sont **ignorés** par l'étage `tests`, qui n'a pas de base, et
**exécutés** par l'étage `integration`. Un test qui se saute silencieusement là
où il devrait tourner serait un faux vert, exactement le travers que le reste du
cahier cherche à éviter.

## Ce que la CI a réellement attrapé

Trois échecs sur les quatre premières exécutions réelles, tous instructifs, et
aucun n'était une régression du code livré :

1. **Session 2** : le contrôle du schéma comptait `information_schema.tables`
   sans filtrer `table_type`, qui inclut les vues. Défaut de l'assertion.
2. **Session 2** : le nom d'image `ghcr.io` conservait la majuscule du compte,
   or un nom d'image Docker doit être en minuscules. Repéré par relecture avant
   qu'il ne se manifeste.
3. **Session 3** : le même contrôle a de nouveau échoué, cette fois pour une
   raison légitime, la supervision ayant ajouté une table et six vues.
   L'assertion par comptage a été remplacée par une vérification des objets
   nommés. Voir OBS-32.

**Point à assumer à l'oral** : la première exécution réelle du workflow a
échoué, et deux des trois échecs portaient sur le test lui-même plutôt que sur
le système testé. C'est le fonctionnement normal d'une chaîne d'intégration. Les
étages rejoués localement passaient ; ceux qui ont cassé sont ceux qui ne
pouvaient pas l'être, faute d'environnement jetable en local. Une CI qui passe
au vert du premier coup sur cinq étages n'a en général rien vérifié.

---

# 6. Fonctionnalités attendues non encore couvertes

Le critère demande que le cahier reprenne **l'ensemble** des fonctionnalités
attendues. Ce qui suit est donc listé explicitement plutôt qu'omis.

| Fonctionnalité | État | Blocage |
|---|---|---|
| Popularité diffusée (Twitch) | Non branchée | Colonnes présentes mais nulles |
| Catalogue RAWG | Non branché | `dim_games` alimentée depuis la watchlist |
| Alertes vers un canal externe | Non construit | Les alertes sont persistées et remontées par Airflow, mais aucune notification par courriel ou messagerie n'est configurée |

---

# 7. Synthèse

| Catégorie | PASS | PARTIEL | EN ATTENTE |
|---|---|---|---|
| Fonctionnels | 5 | 0 | 0 |
| Structurels | 19 | 0 | 0 |
| Sécurité | 3 | 0 | 0 |
| Supervision | 5 | 0 | 0 |
| Ingestion orchestrée | 6 | 0 | 0 |
| Couche Bronze | 6 | 0 | 0 |
| **Total** | **44** | **0** | **0** |

Le cloisonnement des rôles est décrit par 3 cas de la section Sécurité et par
TBRZ-04, compté avec la couche Bronze. À l'exécution, ces quatre cas se
déploient en **20 cas paramétrés**, contre 13 avant l'ajout de Bronze.

Six de ces tests ont échoué avant de passer, et c'est ce qui leur donne de la
valeur :

- **TS-02** a révélé des contraintes d'unicité manquantes dans le schéma Gold ;
- **TS-03** a été conçu pour échouer, et l'a fait ;
- **TS-06** et **TS-07** ont chacun mis au jour un défaut de l'assertion elle-même ;
- **TS-08** a échoué en semblant démontrer le contraire de la réalité, parce que
  l'identifiant de test était rejeté sur sa longueur avant que la contrainte
  visée ne soit évaluée ;
- **TING-04** a trouvé un défaut réel, en ne s'arrêtant pas au premier résultat
  satisfaisant : la tâche Airflow était bien rouge, mais la panne ne laissait
  aucune trace dans le journal d'exécutions et restait donc invisible pour la
  supervision (INC-008) ;
- **TS-18** a d'abord **réussi sans rien prouver**, cas plus insidieux qu'un
  échec : le garde-fou qu'il vérifiait était rendu inatteignable par la fonction
  de nommage, et le vert obtenu ne mesurait rien.

Un test qui n'a jamais rien attrapé n'a pas encore prouvé qu'il testait quelque
chose. Et un test qui échoue ne désigne pas nécessairement le système testé :
dans trois cas sur cinq ici, le défaut était dans le test.

## Couverture par compétence

| Compétence | Tests correspondants |
|---|---|
| C4.2.1 schéma de données | TS-08, TS-09, TS-13, TF-04, TF-05 |
| C4.2.2 temps réel | TF-01, TF-02, TS-01 |
| C4.2.2 orchestrateur | TS-02, TS-03, TS-04, TS-05, TS-06 |
| C4.2.2 calcul distribué | TS-10, TS-11, TS-12, TS-15 |
| C4.2.3 CI/CD | section 5 complète, TS-14, TS-19 |
| C4.2.1 intégrité applicative | TS-16, TS-17, TS-18 |
| C4.3.1 supervision | TSUP-01 à TSUP-05, TING-06 |
| C4.2.2 ingestion orchestrée | TING-01 à TING-05 |
| Sécurité transverse | TSEC-01 à TSEC-03, TBRZ-04 |
| Couche Bronze (A4.1, Medallion) | TBRZ-01 à TBRZ-06 |
