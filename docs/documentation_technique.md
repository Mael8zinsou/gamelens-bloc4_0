# Documentation technique

Livrable **C4.3.3** de la certification RNCP39586, Bloc 4.

## Ce document et les autres

Ce dépôt contient déjà plus de six mille lignes de documentation. Ce document
n'en est pas le résumé : une documentation qui redit ce qui existe ailleurs
finit par diverger de sa source, et le lecteur ne sait plus laquelle croire.

Il joue donc deux rôles, et seulement ceux-là :

1. **Le point d'entrée.** Quelqu'un qui arrive sur le projet commence ici.
2. **Le matériau de référence qui n'existe nulle part ailleurs** : décisions
   d'architecture, traçabilité de la donnée, référence de configuration,
   matrice de droits, dictionnaire de données.

### Ce que ce document ne contient pas, et où ça vit

| Ce que vous cherchez | Où c'est |
|---|---|
| Démarrer la plateforme en cinq minutes | [`README.md`](../README.md) |
| Exploiter au quotidien, maintenir, surveiller | [`docs/feuille_route_exploitation.md`](feuille_route_exploitation.md) |
| Les tests et leurs résultats réels | [`docs/cahier_recettes.md`](cahier_recettes.md) |
| Les incidents et leur méthode d'investigation | [`docs/journal_incidents.md`](journal_incidents.md) |
| Les surprises, fausses pistes et arbitrages | [`docs/observations.md`](observations.md) |
| Les commandes réellement exécutées | [`docs/commandes_successives.md`](commandes_successives.md) |
| Une explication sans jargon | [`docs/vulgarisation/`](vulgarisation/) |

Si une information de ce document contredit l'une de ces sources, **c'est la
source qui fait foi** et ce document qui doit être corrigé.

---

# 1. Le système en une page

GameLens unifie catalogue, popularité jouée, popularité diffusée et tarification
pour **Kestrel Interactive**, éditeur de jeux vidéo indépendant fictif d'une
quinzaine de titres. C'est une alternative construite plutôt qu'achetée à des
outils du marché.

```
        Steam Web API                    Steam Store API
   GetNumberOfCurrentPlayers                appdetails
              |                                  |
              +--------- archivage brut ---------+
              |                                  |
              v                                  v
        bronze.reponses_brutes  (tout appel, abouti ou non)
              |
              v
   ingestion/steam_producer.py  --->  Apache Kafka (KRaft)
                                   gamelens.steam.player_count
                                             |
                              ingestion/kafka_to_postgres.py
                                             |
                                             v
                       PostgreSQL, schema speed  (Silver speed)
                    player_count_events, price_snapshots,
                    game_mapping, pipeline_runs, alertes
                                             |
                    +------------------------+------------------------+
                    |                                                 |
   Airflow, DAG gamelens_promotion_gold        entrepot/snowpark_promotion.py
        quotidien, 02h30 UTC                        INVOQUE A LA MAIN
                    |                            (aucun DAG ne le declenche)
                    v                                                 v
        PostgreSQL, schema mart                          Snowflake, schema mart
        prototype, TENU A JOUR                      cible annoncee, FIGEE au
        dim_games, dim_stores,                      dernier chargement manuel
        fact_prices,                                dim_games, dim_stores,
        fact_popularity_history                     fact_prices,
                    |                               fact_popularity_history
                    v                                                 |
        speed.v_indicateur_gold                                       v
        surveille cette branche                       29 contrats dbt + 8 controles
        et elle seule                                 applicatifs, mais AUCUN
                                                      indicateur de fraicheur
```

**Le schéma dit ce que le système fait, pas ce que l'architecture voulait.**
La version précédente montrait Airflow alimentant les deux couches Gold. C'est
faux, et il vaut mieux le lire ici que le découvrir en séance. Seul le
prototype PostgreSQL est promu par l'ordonnanceur ; la couche Snowflake est
chargée à la main. Les deux divergent donc en permanence : au 31/08/2026,
45 faits de popularité et 120 tarifs d'un côté, 30 et 75 de l'autre, ce dernier
état datant du 20/08. C'est une dette identifiée, suivie sous V-12 et V-13, et
non un choix d'architecture. Elle ne tient pas à un obstacle technique : l'image
Airflow embarque déjà Snowpark 1.47 (OBS-69).

**Trois DAG Airflow** orchestrent l'ensemble : ingestion toutes les 15 minutes,
promotion à 02h30 UTC, supervision toutes les 15 minutes.

**Deux architectures croisées.** Medallion pour les couches (Bronze, Silver,
Gold), Lambda pour les chemins (rapide et batch). Le raisonnement est en
section 2.

---

# 2. Décisions d'architecture

Chaque décision est datée, motivée, et porte sa contrepartie. Une décision sans
contrepartie énoncée est une décision qu'on n'a pas instruite.

## DA-01 Medallion croisé avec Lambda

**Date** : Bloc 1, repris tel quel.

**Décision** : trois couches (Bronze brut, Silver nettoyé, Gold modélisé) et
deux chemins (rapide continu, batch nocturne).

**Pourquoi** : deux besoins contradictoires sur la même donnée. Le pilotage veut
la fraîcheur et tolère l'approximation ; l'analyse veut la cohérence et tolère
le délai. Un chemin unique fait mal les deux.

**Contrepartie assumée** : la logique métier existe en deux endroits. Changer
une règle de calcul impose de la changer des deux côtés, sous peine de voir le
tableau de bord temps réel et le rapport mensuel se contredire. C'est la
critique classique de Lambda, et elle est fondée. Tenable ici parce que le
périmètre est restreint et l'auteur unique.

## DA-02 Exactement-une-fois par puits idempotent

**Date** : session 1, 19/08/2026.

**Décision** : ne pas chercher à empêcher la répétition, mais à la rendre sans
effet. Contrainte `UNIQUE (steam_appid, collected_at)`, insertion
`ON CONFLICT DO NOTHING`, et validation de l'offset Kafka **après** celle de la
transaction PostgreSQL.

**Alternative écartée** : transaction distribuée entre Kafka et PostgreSQL, avec
validation en deux phases. Faisable, lourde, fragile, difficile à expliquer.

**Preuve** : rejeu volontaire après remise à zéro des offsets. 15 messages
relus, **0 inséré, 15 doublons absorbés**.

## DA-03 Calcul distribué par Snowpark, pas par PySpark local

**Date** : 19/08/2026.

**Décision** : Snowpark, qui traduit le code en SQL et le fait exécuter par
l'entrepôt virtuel.

**Pourquoi** : PySpark installé sur un poste tourne en mode local, sur un seul
processus. Le code ressemble à du calcul distribué sans que rien ne le soit. La
question « en quoi est-ce distribué ? » n'aurait pas eu de réponse honnête.

**Preuve** : le SQL généré est lisible par `classement.queries["queries"]`, et
`information_schema.query_history_by_session()` liste les requêtes compilées et
exécutées côté serveur.

**Contrepartie** : dépendance forte à Snowflake, dont le compte expire (feuille
de route, V-01).

## DA-04 Intégrité portée hors du moteur sur Snowflake

**Date** : établi empiriquement le 20/08/2026.

**Constat mesuré**, et non lu dans une documentation :

| Contrainte | Appliquée par Snowflake ? |
|---|---|
| `NOT NULL` | oui |
| Type et longueur | oui |
| `CHECK`, `FOREIGN KEY`, `PRIMARY KEY`, `UNIQUE` | **non** |

La règle qui s'en dégage : ce qui porte sur la colonne elle-même est appliqué,
ce qui porte sur une relation entre lignes ou entre tables ne l'est pas.

**Décision** : reporter l'intégrité hors du moteur, sur des contrôles qui ne le
doublent pas mais le remplacent. Deux filets la portent aujourd'hui, et le choix
de les garder tous les deux est détaillé en DA-10 :

| Filet | Nature | Ce qu'il couvre |
|---|---|---|
| `dbt/models/gold/` | déclaratif, 29 contrats | les contraintes du schéma, chaque `relationships` étant une clé étrangère que le moteur ignore |
| `entrepot/verifier_gold.py` | applicatif, 8 contrôles | les mêmes règles exprimées en SQL, plus la volumétrie et un échantillon lisible |

**Ce qui rend la décision durable** : le comportement du moteur est rejoué à
chaque push par `entrepot/recette_ci.py`. Si Snowflake se mettait à appliquer
les clés étrangères, la chaîne virerait au rouge et la décision serait
réexaminée. Une hypothèse d'architecture vérifiée une seule fois est une
hypothèse qui périme.

## DA-05 Frontière de configuration vers l'entrepôt

**Date** : session 1, alors que le compte Snowflake n'existait pas encore.

**Décision** : un seul module sait comment on se connecte à l'entrepôt
(`entrepot/connexion.py`). Tout le reste demande une connexion et ignore où elle
mène.

**Dividende encaissé deux fois** : la bascule PostgreSQL vers Snowflake s'est
faite sans réécrire la logique de promotion ; et la recette d'intégration
continue a pu viser une base jetable sans modifier une ligne de
`verifier_gold.py`, parce que celui-ci écrit `mart.dim_games` sans préfixer la
base et suit donc `CURRENT_DATABASE()`.

## DA-06 Ordonnancement de l'échantillonnage, pas d'un flux

**Date** : session 6, 27/08/2026.

**Décision** : un DAG toutes les 15 minutes, avec `catchup=False`.

**Pourquoi** : `GetNumberOfCurrentPlayers` rend la valeur d'un compteur à
l'instant de l'appel. Il n'y a pas de flux à consommer, il y a un capteur à
interroger. Le temps réel de GameLens est un échantillonnage périodique, et cela
se planifie sans contresens.

**Corollaire non évident** : `catchup=False` n'est pas un confort mais une
correction. Rattraper un run manqué reviendrait à interroger Steam maintenant et
à estampiller le résultat à une heure passée, donc à fabriquer de l'histoire
fausse.

## DA-07 Couche Bronze en table, pas en stockage objet

**Date** : session 6, 27/08/2026.

**Décision** : `bronze.reponses_brutes`, une table PostgreSQL, alors que le
Bloc 1 annonçait S3.

**Pourquoi l'écart est assumé** : le support change, la propriété recherchée est
la même. Un service tiers de plus n'apportait rien à cette échelle, et faisait
dépendre la démonstration d'une brique supplémentaire.

**Pourquoi la couche compte ici plus qu'ailleurs** : les sources ne sont pas
rejouables. Personne ne dira jamais combien de joueurs étaient connectés mardi
dernier. Un défaut de transformation découvert dans trois mois aurait corrompu
trois mois d'historique définitivement.

**Ce que Kafka n'apportait pas**, malgré sa rétention de 168 heures : il
transporte le message déjà transformé, et une fenêtre de rétention n'est pas un
archivage.

## DA-08 Isolation des jeux de dépendances

**Date** : 20/08/2026, après un conflit réel.

**Décision** : trois environnements Python séparés. `requirements.txt` pour
l'ingestion, `requirements-snowflake.txt` dans une image dédiée pour Snowpark et
dbt, l'image Airflow pour l'orchestration.

**Pourquoi** : `snowflake-snowpark-python` impose `snowflake-connector-python` 4,
que `dbt-snowflake` 1.8 refusait, et l'installation avait au passage remonté la
version de `requests` épinglée pour l'ingestion.

**Principe retenu** : un conflit de dépendances qui résiste est un signal
d'architecture. Ces composants n'ont pas vocation à cohabiter, on les sépare au
lieu de négocier des versions.

## DA-09 Documentation générée plutôt que recopiée

**Date** : session 7, 27/08/2026.

**Décision** : le dictionnaire de données est produit par
`outils/generer_dictionnaire.py` depuis le catalogue des bases, et la chaîne
d'intégration continue échoue s'il n'est plus à jour.

**Pourquoi** : un dictionnaire recopié diverge du schéma en quelques semaines,
sans que rien ne le signale. Le document reste plausible et devient faux, ce qui
est le pire état pour une documentation.

**Contrepartie** : la description doit être écrite en SQL, sous forme de
`COMMENT ON COLUMN`, à côté de la définition. Moins confortable qu'un tableau
Markdown, et c'est le prix de la non-divergence.

---

# 3. Traçabilité de la donnée

De la source jusqu'à la restitution, champ par champ. C'est la section à
consulter pour répondre à « d'où vient ce chiffre ? », question qu'un analyste
finit toujours par poser.

## DA-10 dbt teste ce que Snowpark construit

**Date** : 27/08/2026, session 8.

**Ce qui a déclenché la décision** : un écart entre l'annoncé et le réel. Le
Bloc 1, `CLAUDE.md` et les commentaires de colonnes de
`sql/schema_gold_snowflake.sql` affirmaient tous les trois, au présent, que
l'intégrité de la couche Gold reposait sur des tests dbt nommément cités
(`not_null`, `unique`, `relationships`, `expression_is_true`, `accepted_values`).
Elle reposait en fait sur huit `SELECT count(*)` écrits à la main. Le répertoire
`dbt/` était vide, alors que `dbt-core` et `dbt-snowflake` étaient épinglés,
installés à chaque run de CI, que `.gitignore` prévoyait déjà `dbt/target/` et
que le Dockerfile d'outillage installait `git` avec le commentaire « requis par
dbt pour les packages ». Tout était prêt sauf le projet lui-même.

**Décision, et surtout son périmètre.** dbt ne construit pas les tables de
faits et de dimensions. Elles restent produites par
`entrepot/snowpark_promotion.py`, et sont déclarées ici en **sources**, c'est-à-
dire en tables que dbt lit sans les avoir écrites.

**Alternative écartée** : porter la promotion elle-même en modèles dbt.
Rejetée pour deux raisons distinctes, dont la seconde suffirait seule.

D'abord, cette promotion porte la compétence C4.2.2 méthode 3, le calcul
distribué, déjà exécutée et vérifiée. La réécrire échangerait une preuve contre
une autre sans rien gagner, en déstabilisant ce qui est acquis.

Ensuite, dbt ne saurait pas la faire. La promotion lit la couche Silver speed
dans PostgreSQL et téléverse vers Snowflake par `write_pandas`. dbt ne
transforme qu'à l'intérieur de l'entrepôt : il n'a pas d'étape d'extraction.
Une architecture « tout dbt » aurait exigé un composant d'ingestion séparé de
toute façon.

**Un seul modèle**, la vue `v_popularity_dashboard`. Elle vivait dans un fichier
de 24 `CREATE OR REPLACE TABLE` qu'on ne peut pas rejouer sans détruire la
couche de démonstration : la corriger imposait de découper le fichier à la main.
En modèle, elle se reconstruit seule et suit la base de la cible au lieu de
nommer `gamelens.mart.` en dur, ce qui la rend éprouvable sur base jetable.

**Contrepartie, et elle est réelle.** La plateforme porte désormais deux filets
d'intégrité sur les mêmes faits. Deux autorités sur un même fait divergent tôt
ou tard, et le jour où elles divergent, l'une des deux est fausse sans que rien
ne le signale. C'est précisément le mécanisme décrit en OBS-63.

**Ce qui rend la contrepartie tenable** : leur accord est testé, pas déclaré.
Les étapes 9 et 10 de `entrepot/recette_ci.py` confrontent les deux filets à
**exactement le même jeu de données fautif** et exigent que les deux tombent. Si
l'un rattrape une violation que l'autre laisse passer, la recette s'arrête au
lieu de laisser la divergence s'installer.

**Ce que ce test a appris, et qui n'était pas prévu** : les deux filets ne sont
pas redondants. Sur les mêmes violations, l'applicatif en rattrape 4 et dbt 5.
Le cinquième est le test posé sur la vue, qui détecte le gonflement de la
**jointure** lorsqu'un doublon apparaît dans une table de faits.
`verifier_gold.py` n'interroge que les tables et ne peut pas le voir. Garder les
deux n'est donc pas une prudence, c'est une couverture plus large.

**Deux propriétés qu'un `CREATE OR REPLACE VIEW` détruit en silence** sont
vérifiées après chaque matérialisation, et les deux vérifications ont été
éprouvées en négatif :

| Propriété | Ce qui se passe sans la configuration | Comment on le voit |
|---|---|---|
| Droits | seul `ACCOUNTADMIN` garde un accès ; le tableau de bord affiche un panneau vide, plus tard | `SHOW GRANTS ON VIEW`, exigence de `gamelens_dashboard_viewer` |
| `COMMENT` | le dictionnaire généré diverge du catalogue, et c'est **un autre étage** de la CI qui échoue, sur un message parlant du dictionnaire | `information_schema.views`, exigence d'un commentaire non vide |

**Dépendance assumée** : `dbt_utils` 1.3.1, figée par `dbt/package-lock.yml`.
Trois contrôles de bornes et deux unicités de grain portant sur une combinaison
de colonnes ne s'expriment pas avec les seuls tests du cœur de dbt. S'en passer
reviendrait à les réécrire en SQL à la main, c'est-à-dire à retomber sur ce que
ce chantier remplace.

## 3.1 Fréquentation

| Étape | Objet | Transformation appliquée |
|---|---|---|
| Source | `GetNumberOfCurrentPlayers`, champ `response.player_count` | aucune |
| Bronze | `bronze.reponses_brutes.charge` | aucune, corps JSON conservé tel quel |
| Transport | message Kafka `{steam_appid, unified_name, player_count, collected_at}` | projection de 4 champs, l'horodatage étant posé une fois par cycle |
| Silver | `speed.player_count_events.player_count` | aucune ; `ingested_at` ajouté par la base |
| Agrégat | `speed.v_daily_player_stats` | `AVG` arrondie à 2 décimales et `MAX` par jeu et par jour, en UTC |
| Gold | `mart.fact_popularity_history.avg_player_count`, `.max_player_count` | reprise de la vue d'agrégat |

**Point de vigilance de lecture** : `collected_at` est l'instant de l'appel à
Steam, `ingested_at` celui de l'écriture en base. L'écart entre les deux est la
latence du pipeline, et c'est ce que mesure l'indicateur correspondant. Un
message resté longtemps dans Kafka gonfle cet écart sans que rien ne soit en
panne.

## 3.2 Tarification

| Étape | Objet | Transformation appliquée |
|---|---|---|
| Source | `appdetails`, bloc `price_overview` | filtré côté API par `filters=price_overview`, région `cc=fr` |
| Bronze | `bronze.reponses_brutes.charge` | aucune |
| Silver | `speed.price_snapshots.price_final` | **division par 100** : Steam exprime les montants en centimes |
| Silver | `speed.price_snapshots.price_initial` | `initial` divisé par 100, avec repli sur `final` si absent |
| Silver | `speed.price_snapshots.discount_percent` | repris tel quel, zéro par défaut |
| Gold | `mart.fact_prices.price` | reprise de `price_final` |
| Gold | `mart.fact_prices.promotion_flag` | **dérivé** : `discount_percent > 0` |

Trois vraies décisions de transformation vivent ici : la conversion des
centimes, le repli de `initial` sur `final`, et la dérivation du drapeau de
promotion. C'est précisément parce qu'elles existent que la couche Bronze
importe : une erreur sur l'une d'elles ne serait pas rattrapable autrement.

## 3.3 Référentiel des jeux

| Étape | Objet | Transformation appliquée |
|---|---|---|
| Saisie | `config/watchlist.json` | panel de 15 titres, chaque `appid` vérifié en direct |
| Silver | `speed.game_mapping` | table de correspondance entre identifiants Steam, Twitch et RAWG |
| Gold | `mart.dim_games` | promotion des titres `is_active`, clef naturelle `steam_appid`, mise à jour sur conflit |

`mart.dim_games.game_id` est un UUID interne, généré à la promotion et
indépendant de tout identifiant source. C'est la convention posée au Bloc 2 :
une clef technique ne doit rien devoir à un fournisseur, sous peine de casser le
jour où celui-ci change de numérotation.

## 3.4 Ce qui n'est pas alimenté

À dire clairement, pour qu'un lecteur ne cherche pas une donnée absente.

| Colonne | État |
|---|---|
| `avg_viewer_count`, `max_viewer_count` | vides, la source Twitch n'est pas branchée |
| `dim_games.twitch_game_id` | vide, même raison |
| `dim_games.gog_slug` | vide, le suivi GOG est hors périmètre depuis le Bloc 3 |
| `dim_games.release_date`, `metacritic_score`, `critical_tier` | vides, source catalogue RAWG non branchée |
| `dim_stores` | une seule boutique, Steam |

---

# 4. Référence de configuration

Toute la configuration passe par des variables d'environnement, lues depuis
`.env` sur le poste et depuis `environment:` du fichier compose dans les
conteneurs. Aucune valeur de connexion n'est écrite en dur dans le code.

## 4.1 Couche Silver speed

| Variable | Défaut | Lue par | Remarque |
|---|---|---|---|
| `POSTGRES_HOST` | `localhost` | `ingestion/common.py` | `postgres` dans les conteneurs |
| `POSTGRES_PORT` | `5433` | idem | **5433 sur le poste, 5432 dans le réseau Docker.** Voir 4.5 |
| `POSTGRES_DB` | `gamelens` | idem | |
| `POSTGRES_USER` | `gamelens_app` | idem | propriétaire des schémas |
| `POSTGRES_PASSWORD` | `devlocal_app` | idem | mot de passe de développement local |

## 4.2 Kafka

| Variable | Défaut | Remarque |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | `kafka:29092` dans les conteneurs |
| `KAFKA_TOPIC_PLAYERS` | `gamelens.steam.player_count` | |

Deux écouteurs distincts, et c'est volontaire : `INTERNAL` sur `kafka:29092`
pour le réseau Docker, `EXTERNAL` sur `localhost:9092` pour le poste. Un client
qui utilise le mauvais obtient une résolution de nom en échec, pas un refus de
connexion, ce qui égare le diagnostic.

## 4.3 Entrepôt Snowflake

| Variable | Défaut | Remarque |
|---|---|---|
| `SNOWFLAKE_ACCOUNT` | aucun | forme `ORGANISATION-COMPTE`, pas l'URL |
| `SNOWFLAKE_USER` | aucun | `GAMELENS_SERVICE`, de type `SERVICE` |
| `SNOWFLAKE_ROLE` | `ACCOUNTADMIN` | écart au moindre privilège assumé, feuille de route V-03 |
| `SNOWFLAKE_WAREHOUSE` | `gamelens_wh` | XS, suspension automatique à 60 s |
| `SNOWFLAKE_DATABASE` | `gamelens` | redirigé vers une base jetable par la recette de CI |
| `SNOWFLAKE_SCHEMA` | `mart` | |
| `SNOWFLAKE_PRIVATE_KEY_PATH` | aucun | **usage local** : chemin du fichier de clef |
| `SNOWFLAKE_PRIVATE_KEY` | aucun | **usage CI** : contenu PEM, jamais écrit sur le disque du runner |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | aucun | vide, la clef n'est pas chiffrée |
| `SNOWFLAKE_PASSWORD` | aucun | mise au point seulement, inutilisable en pratique (voir 4.4) |

`entrepot/connexion.py` choisit dans cet ordre : chemin de clef, puis contenu
PEM, puis mot de passe. Le premier renseigné gagne.

## 4.4 Pourquoi la clef et non le mot de passe

Snowflake impose l'authentification multifacteur aux utilisateurs humains sur
les comptes récents. Une connexion par mot de passe reste donc bloquée en
attente d'une validation qu'un pipeline ne peut pas donner. Une paire de clefs
RSA attachée à un utilisateur de type `SERVICE` contourne ce mur sans
l'affaiblir, et c'est de toute façon la pratique attendue en production.

La clef privée vit dans `secrets/`, ignoré par git, et dans les secrets du
dépôt privé pour la CI. Elle n'apparaît dans aucun fichier versionné.

## 4.5 Le port 5433, et pourquoi ce n'est pas une erreur

Un service PostgreSQL 18 natif occupe déjà le port 5432 sur le poste de
développement. Docker publie alors le port **sans erreur visible et sans effet
réel** : `docker compose ps` affiche la publication, mais c'est le service natif
qui répond.

Le conteneur est donc publié sur le port hôte **5433**, port interne inchangé à
5432. Les conteneurs se joignent par `postgres:5432`, seuls les processus du
poste passent par 5433.

Ne pas « corriger » ce port. Le symptôme initial était un `UnicodeDecodeError`
sans rapport apparent, et l'incident complet est en INC-004.

---

# 5. Modèle de sécurité

Quatre rôles, posés au Bloc 1, déclinés à l'identique sur PostgreSQL et
Snowflake. **Un seul modèle pour toute la plateforme** : les rôles `gamelens_etl`
et `gamelens_reader` d'une version antérieure ont été supprimés, deux modèles
concurrents étant pires qu'un modèle imparfait.

## 5.1 Matrice des droits, PostgreSQL

| Rôle | `bronze` | `speed` | `mart` | Vues de restitution |
|---|---|---|---|---|
| `gamelens_app` (propriétaire) | tout | tout | tout | tout |
| `etl_service` | lire, **ajouter** | lire, ajouter, modifier | lire, ajouter, modifier | lire |
| `analyst` | lire | lire | lire | lire |
| `dashboard_viewer` | **rien** | rien | rien | **lire uniquement** |

Trois propriétés méritent d'être signalées.

**Aucun rôle applicatif ne peut supprimer.** Ni `DELETE` sur `speed`, ni sur
`mart`. Une anomalie du pipeline ou un compte compromis peut enrichir ou
corriger l'historique, jamais l'effacer.

**La couche Bronze n'accorde pas non plus de modification.** Contrairement à
`speed`, `etl_service` n'y a pas d'`UPDATE`. Une archive que l'on peut modifier
n'est plus une archive : le seul droit d'écriture est l'ajout.

**`dashboard_viewer` lit des vues sans aucun droit sur les tables
sous-jacentes.** C'est possible parce que PostgreSQL évalue les droits d'une vue
avec ceux de son **propriétaire** et non de l'appelant. C'est ce qui rend le
cloisonnement réel et non déclaratif.

Ces droits ne sont pas seulement accordés, ils sont **testés en tentant les
opérations interdites** : 20 cas paramétrés dans `tests/test_securite_roles.py`,
rejoués par la CI. Un droit refusé ne se constate qu'en obtenant le refus.

## 5.2 Rôles Snowflake

`gamelens_etl_service`, `gamelens_analyst`, `gamelens_dashboard_viewer`, avec la
même répartition. Particularité du moteur : un rôle doit aussi recevoir l'usage
de l'entrepôt virtuel pour exécuter la moindre requête. C'est un oubli fréquent,
qui produit des « insufficient privileges » malgré des `GRANT SELECT` corrects.

## 5.3 Secrets

| Secret | Où il vit | Versionné |
|---|---|---|
| Clef privée RSA Snowflake | `secrets/snowflake_key.p8` et secrets du dépôt | **non** |
| Identifiant et utilisateur Snowflake | `.env` et secrets du dépôt | non |
| Mots de passe PostgreSQL de développement | `docker-compose.yml`, valeurs `devlocal_*` | oui, assumé |
| Compte Grafana et Airflow | `admin` / `admin` | oui, assumé |

Les valeurs versionnées n'ouvrent que des conteneurs locaux. `.env`, `secrets/`,
`*.pem` et `*.p8` sont ignorés par git, ce qui a été vérifié par
`git check-ignore` et non supposé.

---

# 6. Inventaire des composants

| Composant | Version | Rôle | Accès |
|---|---|---|---|
| PostgreSQL | 16-alpine | Silver speed, Bronze, Gold prototype (seul Gold tenu à jour), métadonnées Airflow | `localhost:5433` |
| Apache Kafka | 3.9.0, mode KRaft | tampon entre collecte et écriture | `localhost:9092` |
| Apache Airflow | 3.1.8, LocalExecutor | orchestration, 3 DAG | `localhost:8080`, `admin`/`admin` |
| Grafana | 11.6.0 | restitution des indicateurs | `localhost:3000`, `admin`/`admin` |
| Snowflake | compte étudiant | entrepôt Gold cible, calcul distribué, contrats dbt. Chargé à la main, voir V-12 | `RTZSXDV-PM63908` |
| Outillage Snowflake | image dédiée | Snowpark, dbt, génération du dictionnaire | `docker compose run --rm snowflake-cli` |

**Kafka tourne en mode KRaft**, sans ZooKeeper et en conteneur unique. C'est bien
Apache Kafka, pas une alternative allégée : l'autorisation de substituer un
équivalent plus léger n'a pas eu à être utilisée.

**Airflow 3 diffère nettement d'Airflow 2**, et la plupart des tutoriels en ligne
parlent d'Airflow 2. `api-server` remplace `webserver`, `dag-processor` est un
service séparé obligatoire, et `logical_date` peut valoir `None` sur un
lancement manuel. Partir du fichier compose officiel de la version exacte.

## Organisation du dépôt

| Répertoire | Contenu |
|---|---|
| `ingestion/` | pipeline temps réel, collecte tarifaire, archivage Bronze |
| `dags/` | trois DAG Airflow |
| `entrepot/` | tout ce qui vise Snowflake : connexion, exécution SQL, Snowpark, contrôles, recette de CI |
| `supervision/` | règles d'alerte et vérification du tableau de bord |
| `sql/` | schémas et documentation des colonnes |
| `outils/` | génération du dictionnaire de données |
| `tests/` | tests unitaires et tests de sécurité |
| `docker/` | images Airflow et outillage, provisionnement Grafana |
| `docs/` | documentation, dont ce fichier |

---

# 7. Installation et déploiement

## 7.1 Depuis un poste vierge

Prérequis : Docker Desktop démarré, Python 3.12.

```bash
cp .env.example .env          # completer la section Snowflake si besoin
docker compose up -d          # 7 conteneurs
docker compose ps             # attendre que tous soient healthy
python -m pip install -r requirements.txt
python ingestion/create_topics.py       # declaration explicite des topics
python ingestion/seed_game_mapping.py   # referentiel des titres suivis
```

Les schémas PostgreSQL sont appliqués automatiquement au premier démarrage, par
les scripts montés dans `docker-entrypoint-initdb.d`, dans l'ordre `00`, `10`,
`15`, `20`, `30`.

**Piège à connaître** : ces scripts ne se rejouent **que sur un volume vierge**.
Sur une instance déjà initialisée, appliquer à la main :

```bash
docker exec -i gamelens-postgres psql -U gamelens_app -d gamelens \
    -v ON_ERROR_STOP=1 < sql/<fichier>.sql
```

## 7.2 Ce qui garantit que cette procédure fonctionne

Elle n'est pas seulement écrite, elle est **exécutée à chaque push**. L'étage
d'intégration de la chaîne monte un socle Docker neuf, applique les schémas,
vérifie la présence des 19 objets attendus **par leur nom**, exécute le pipeline
de bout en bout, contrôle le résultat en base, éprouve l'idempotence, et
vérifie que la couche Bronze s'est alimentée.

Une procédure d'installation qu'on ne rejoue jamais devient fausse sans que
personne ne le remarque.

## 7.3 Depuis Git Bash sous Windows

Préfixer les commandes Docker par `MSYS_NO_PATHCONV=1` et utiliser `pwd -W`,
sinon la couche de traduction de chemins de MSYS réécrit les chemins de volume.
Depuis PowerShell, rien à faire. Voir INC-002.

Ce piège se reproduit sur `docker exec -e VARIABLE=/chemin/...`, où le chemin
passé en valeur de variable est également réécrit.

## 7.4 Déploiement

La chaîne publie sur `ghcr.io` une image étiquetée `latest` **et** avec le SHA du
commit, uniquement depuis la branche principale et seulement si les six étages
sont verts. Le retour arrière consiste à repointer sur un SHA connu. Sans la
seconde étiquette, il consisterait à espérer que `latest` pointe encore sur la
bonne image.

## 7.5 Après toute modification d'un DAG

```bash
docker exec gamelens-airflow-scheduler airflow dags reserialize
```

L'analyseur ne rescanne le dossier que toutes les 5 minutes, et
`airflow dags list` lit la base de métadonnées et non le dossier.

---

# 8. Chaîne d'intégration continue

Six étages, du moins coûteux au plus coûteux, pour que l'erreur la plus
fréquente soit aussi la plus rapide à détecter.

| Étage | Ce qu'il vérifie |
|---|---|
| Qualité | lint et format sur cinq répertoires |
| Tests unitaires | 39 tests, sans infrastructure |
| Intégrité des DAG | les trois DAG s'analysent et sont enregistrés, vérifié par leur nom |
| Intégration | socle Docker neuf, pipeline complet, sécurité, idempotence, Bronze, dictionnaire |
| Recette de l'entrepôt | base Snowflake jetable, schéma appliqué, calcul distribué confronté à des valeurs calculées à la main, contraintes du moteur éprouvées, contrôles en positif **et en négatif** |
| Publication | image poussée avec double étiquetage |

Deux principes gouvernent ces contrôles.

**Vérifier des objets nommés, jamais des comptages.** Une assertion par
comptage se brise à chaque évolution légitime, ce qui pousse à l'affaiblir
plutôt qu'à la lire. Elle a cassé deux fois avant d'être remplacée.

**Tester ce qui doit échouer.** Les contrôles d'intégrité de l'entrepôt sont
exécutés deux fois dans la recette : sur données saines, où ils doivent tous
passer, et sur données corrompues, où le run échoue s'ils passent. Les données
corrompues ne sont d'ailleurs pas fabriquées : ce sont exactement celles que
Snowflake vient de laisser entrer faute d'appliquer ses contraintes.

---

# 9. Annexes

| Annexe | Contenu | Nature |
|---|---|---|
| [A1, dictionnaire PostgreSQL](annexes/dictionnaire_donnees.md) | schémas `bronze`, `speed`, `mart` : tables, vues, colonnes, types, contraintes | **généré** |
| [A2, dictionnaire Gold Snowflake](annexes/dictionnaire_gold_snowflake.md) | couche Gold cible | **généré** |

Ces deux annexes sont produites depuis le catalogue des bases par
`outils/generer_dictionnaire.py`, et **ne doivent jamais être modifiées à la
main**. La source des descriptions est constituée par les `COMMENT ON` des
fichiers de `sql/`.

```bash
python outils/generer_dictionnaire.py                       # PostgreSQL
python outils/generer_dictionnaire.py --cible snowflake     # Gold
python outils/generer_dictionnaire.py --verifier            # sans ecrire
```

La chaîne d'intégration continue exécute le mode `--verifier` sur les deux
cibles et **échoue si un dictionnaire n'est plus à jour**. Ajouter une colonne
sans régénérer fait donc virer la chaîne au rouge, avec le message qui indique
la commande à lancer.

C'est ce qui distingue une garantie d'une consigne. « Penser à régénérer après
modification du schéma » n'est pas un mécanisme, c'est un espoir.

---

Dernière mise à jour : 27/08/2026. Les annexes se régénèrent, ce document se
relit à chaque décision d'architecture nouvelle.
