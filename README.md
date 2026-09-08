# GameLens, infrastructure data

Plateforme de donnees interne de **Kestrel Interactive**, editeur de jeux video
independant. Elle unifie catalogue, popularite jouee, popularite diffusee et
tarification des titres du portefeuille et d'un panel concurrent suivi.

Ce depot porte le **Bloc 4** de la certification RNCP39586 (Concevoir et operer
une infrastructure data). Les Blocs 1 a 3 ont pose l'architecture, l'analyse et
le pilotage ; ce depot en est la realisation executable.

## Architecture

Medallion croisee avec une architecture Lambda, reprise du Bloc 1.

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
regarde, et le rapport des deux ne se deduit d'aucun des deux. Les topics sont
**separes** et non distingues par un type d'evenement sur un topic unique : les
deux flux n'ont ni la meme cadence de panne ni le meme puits, et rejouer les
offsets d'une source ne doit pas rejouer ceux de l'autre. Voir DA-13 dans
`docs/documentation_technique.md`.

**Deux couches Gold, deux DAG, et c'est delibere.** Snowflake est la cible ;
le prototype PostgreSQL est conserve comme reference de comparaison et comme
repli. Les deux ne sont pas fusionnees dans un seul DAG parce que Snowflake est
un service tiers facture dont l'indisponibilite ne doit pas emporter la
promotion locale. Leur profondeur differe et ce n'est pas un defaut : la
promotion PostgreSQL traite une journee par run, la promotion Snowpark rejoue
tout l'historique par MERGE. Voir DA-11 dans `docs/documentation_technique.md`.

La couche Bronze est une table PostgreSQL et non un stockage objet, ecart
assume avec le `Bronze (S3)` annonce au Bloc 1 : le support change, la propriete
recherchee est la meme, et un service tiers de plus n'apportait rien a cette
echelle (17,5 Go par an mesures le 08/09/2026, 41 Mo avant le raccordement
de Twitch).

## Demarrage

Prerequis : Docker Desktop demarre, Python 3.12.

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
sans rien tenter. Le reste de la chaine fonctionne a l'identique.

Les cinq schemas PostgreSQL (Silver speed, audience Twitch, Bronze, Gold
prototype, supervision) sont appliques automatiquement au premier demarrage : ils sont
montes dans `docker-entrypoint-initdb.d`. **Ils ne rejouent pas** sur un volume
deja initialise ; les appliquer alors a la main par
`docker exec -i gamelens-postgres psql ... < sql/<fichier>.sql`.

**Point de configuration important.** PostgreSQL est publie sur le port hote
**5433**, pas 5432. Un service PostgreSQL natif occupe frequemment 5432 sur un
poste Windows et Docker publie alors le port sans effet reel ni message
d'erreur. Voir INC-004 dans `docs/journal_incidents.md`.

**Depuis Git Bash**, prefixer les commandes Docker montant un volume par
`MSYS_NO_PATHCONV=1` et utiliser `pwd -W`. Depuis PowerShell, aucune adaptation
n'est necessaire.

## Entrepot Snowflake, dbt et calcul distribue

L'outillage Snowflake vit dans son propre conteneur, jamais dans l'environnement
Python du poste : Snowpark impose `snowflake-connector-python` 4.x, incompatible
avec la version que reclame `dbt-snowflake` 1.8, et l'ingestion epingle
`requests`. Il se lance a la demande, sous le profil `outillage`.

```powershell
docker compose --profile outillage run --rm snowflake-cli `
  python /projet/entrepot/verifier_gold.py
docker compose --profile outillage run --rm snowflake-cli `
  dbt test --project-dir /projet/dbt --profiles-dir /projet/dbt
```

Snowflake **n'applique pas** les contraintes qui portent sur une relation entre
lignes ou entre tables : CHECK, FOREIGN KEY, PRIMARY KEY et UNIQUE sont
declarees et ignorees, seules celles portees par la colonne elle-meme (NOT NULL,
type, longueur) sont appliquees. C'est verifie empiriquement par
`sql/verify_snowflake_constraints.sql`. L'integrite est donc reportee hors du
moteur, sur deux filets rejoues a chaque push : les **29 contrats declaratifs**
de `dbt/models/gold/` et les **8 controles applicatifs** de
`entrepot/verifier_gold.py`. Ils ne font pas double emploi, et les deux sont
eprouves en negatif sur un meme jeu de donnees fautif.

L'authentification se fait par **paire de cles RSA** et non par mot de passe :
Snowflake impose la MFA aux utilisateurs humains, ce qu'un pipeline ne peut pas
satisfaire. La cle privee vit dans `secrets/`, ignoree par git, montee en
lecture seule dans les conteneurs, et n'entre jamais dans une image.

**`sql/schema_gold_snowflake.sql` contient des `CREATE OR REPLACE TABLE` et
nomme la base en dur.** Ne jamais le rejouer sans redirection : il detruirait la
couche de demonstration sans message d'erreur. Passer par
`entrepot/executer_sql.py --base <autre>`.

## Organisation du depot

| Chemin | Contenu |
|---|---|
| `config/watchlist.json` | Titres suivis, source du referentiel `game_mapping` |
| `docker-compose.yml` | Composants d'infrastructure locaux |
| `ingestion/` | Pipeline temps reel et tarifaire : deux producers (Steam, Twitch), un consumer abonne aux deux topics, referentiel, topics, archivage Bronze |
| `sql/schema_bronze.sql` | Couche Bronze, archive brute en append only |
| `sql/schema_silver_speed.sql` | Couche Silver speed, PostgreSQL |
| `sql/schema_silver_twitch.sql` | Audience diffusee, table separee : zero spectateur est une observation, l'absence n'en est pas une |
| `sql/schema_gold_snowflake.sql` | Couche Gold, cible Snowflake |
| `sql/commentaires_gold_snowflake.sql` | Commentaires des colonnes Snowflake, separes du schema qui n'est pas rejouable |
| `sql/schema_gold.sql` | Prototype PostgreSQL du Gold, conserve comme reference |
| `sql/verify_snowflake_constraints.sql` | Verification empirique des contraintes Snowflake |
| `sql/schema_supervision.sql` | Indicateurs de supervision et journal d'alertes |
| `dags/` | 5 DAG Airflow : ingestion temps reel, promotion PostgreSQL, promotion Snowflake, supervision, battement |
| `entrepot/` | Connexion Snowflake, promotion Snowpark, controles d'integrite et recette de CI |
| `dbt/` | Projet dbt : 4 sources et 1 modele, 29 contrats declaratifs au total (25 portes par les sources, 4 par le modele) |
| `supervision/` | Moteur d'alertes et verification du tableau de bord |
| `outils/construire_panel.py` | Generateur de `config/watchlist.json` : chaque appid confronte au nom rendu par Steam |
| `outils/generer_dictionnaire.py` | Generateur des dictionnaires de donnees, depuis le catalogue des bases |
| `outils/generer_schema.py` | Generateur du schema de donnees : catalogue et DDL recoupes, puis dessin |
| `outils/diagramme.py` | Rendu du schema en SVG et PNG, sans moteur de rendu externe |
| `outils/capturer_preuves.py` | Captures datees et rejouables des sorties reelles, vers `docs/preuves/` |
| `outils/generer_support.py` | Generateur du support de soutenance : le Markdown vers le PPTX |
| `outils/visuels.py` | Schemas et graphiques du support, palette de dataviz validee |
| `outils/generer_feuille_jury.py` | Feuille A4 remise au jury : les 31 sous-criteres et leur diapositive |
| `docker/grafana/` | Source de donnees et tableau de bord provisionnes comme code |
| `docker/snowflake/` | Image d'outillage Snowflake, isolee des dependances d'ingestion |
| `secrets/` | Cle privee Snowflake, ignoree par git |
| `tests/` | Tests automatises, executes par la CI |

## Documentation

| Chemin | Contenu |
|---|---|
| `docs/plan_soutenance.md` | Plan minute de la soutenance, trace sur les 31 sous-criteres de la grille |
| `docs/rapport_analyse.md` | Analyse des besoins et presentation des composants (A4.1) |
| `docs/documentation_technique.md` | Point d'entree, decisions d'architecture, tracabilite, configuration, securite (C4.3.3) |
| `docs/feuille_route_exploitation.md` | Taches recurrentes, maintenance, points de vigilance (C4.3.2) |
| `docs/cahier_recettes.md` | Cahier de recettes et de tests (C4.4.1) |
| `docs/journal_incidents.md` | Journal d'incidents, format impose par la grille C4.4.2 |
| `docs/observations.md` | Observations de session : surprises, fausses pistes, arbitrages |
| `docs/commandes_successives.md` | Trace chronologique des commandes reellement executees |
| `docs/annexes/` | Dictionnaires de donnees et schema en diagramme, GENERES depuis le catalogue |
| `docs/preuves/` | Sorties reelles capturees, avec leur en-tete de provenance |
| `docs/feuille_jury.pdf` | Feuille A4 a imprimer en deux exemplaires, GENEREE |
| `docs/support_soutenance.md` | Support de soutenance, diapo par diapo : la SOURCE du PPTX |
| `docs/script_soutenance.md` | Idee generale, objectif de la presentation, et le texte parle mot pour mot |
| `docs/captures/` | Captures d'ecran d'interfaces, deposees a la main |
| `docs/vulgarisation/` | Deux versions vulgarisees du projet, pour un junior et pour un non-specialiste |

Les dictionnaires de `docs/annexes/` ne s'editent pas a la main : ils sont
generes par `outils/generer_dictionnaire.py`, et la CI echoue si le fichier
versionne ne correspond plus. Attention a la source exacte, elle n'est pas celle
qu'on suppose : voir « Documentation generee » plus bas.

## Ou se trouve la preuve de chaque competence

| Competence | Realisation | Preuve |
|---|---|---|
| C4.2.1, architecture d'entrepot | Deux couches Gold, Snowflake et PostgreSQL | `sql/schema_gold_snowflake.sql`, `sql/schema_gold.sql`, `sql/verify_snowflake_constraints.sql` |
| C4.2.2, methode 1, temps reel | Steam et Twitch vers Kafka vers PostgreSQL, idempotent sur les deux topics | `ingestion/`, DAG `gamelens_ingestion_temps_reel` |
| C4.2.2, methode 2, orchestrateur | Airflow 3.1.8, 5 DAG | `dags/`, http://localhost:8080 |
| C4.2.2, methode 3, calcul distribue | Snowpark, et non Spark local | `entrepot/snowpark_promotion.py`, DA-04 |
| C4.2.3, CI/CD | 6 etages, base Snowflake jetable, image publiee | `.github/workflows/ci.yml` |
| C4.3.1, supervision | 5 indicateurs SQL, 6 regles, Grafana comme code | `sql/schema_supervision.sql`, `supervision/`, `docker/grafana/` |
| C4.3.2, exploitation | 10 sections, 14 points de vigilance dont 9 ouverts | `docs/feuille_route_exploitation.md` |
| C4.3.3, documentation technique | 13 decisions datees, 2 annexes generees | `docs/documentation_technique.md` |
| C4.4.1, recettes | 70 PASS, 0 partiel, 0 en attente | `docs/cahier_recettes.md` |
| C4.4.2, incident reel | INC-004 retenu, 9 incidents documentes | `docs/journal_incidents.md` |
| A4.1, rapport d'analyse | Couts mesures, dependance fournisseur par composant | `docs/rapport_analyse.md` |

## Supervision

Les indicateurs sont definis en SQL dans `sql/schema_supervision.sql` : fraicheur
de la donnee, completude de la collecte, latence du pipeline, fiabilite par
composant, fraicheur de la couche Gold PostgreSQL. Grafana les affiche, il ne les
calcule pas, ce qui les garde interrogeables par n'importe quel client meme si
l'outil est arrete.

Le moteur d'alertes (`supervision/regles_alertes.py`) evalue six regles, ouvre
une alerte au plus par regle, et la referme automatiquement quand la condition
disparait. La regle de composant muet porte une fenetre **par composant** et non
une fenetre unique : 24 h pour les collectes frequentes, 26 h pour celles qui ne
tournent qu'une fois par jour, sans quoi un composant quotidien serait declare
muet a chaque cycle. Le DAG `gamelens_supervision` l'execute toutes les
15 minutes et fait echouer son run en presence d'une alerte critique.

```powershell
docker compose up -d grafana
python supervision/regles_alertes.py           # evaluation ponctuelle
python supervision/verifier_tableau_bord.py    # controle des 7 panneaux
```

Interfaces : Airflow sur http://localhost:8080, Grafana sur http://localhost:3000,
compte `admin` / `admin` pour les deux.

**Canal de notification externe, depuis le 07/09/2026.** Les alertes critiques
partent sur un canal Telegram, mesure a 2 secondes entre le declenchement et la
reception. Le canal est FACULTATIF : sans `TELEGRAM_BOT_TOKEN` ni
`TELEGRAM_CHAT_ID`, la notification est un no-op qui rend un succes ; un jeton
present mais injoignable, en revanche, trace un echec. L'asymetrie est voulue et
testee : un dispositif d'alerte ne doit jamais faire tomber la chaine qu'il
surveille, mais son propre silence ne doit pas etre silencieux.

Le DAG `gamelens_battement`, a 8h et 20h, est un temoin separe qui denonce
l'arret de la supervision : un dispositif qui se surveille lui-meme ne prouve
rien.

Ces deux briques referment V-02 et V-07, jusque-la les deux ecarts les plus
importants entre cette plateforme et une plateforme exploitee. Ce que leur
absence avait coute est mesure : une alerte de fraicheur etait restee ouverte
6 j 20 h en aout, sans que personne n'en soit averti.

## Integration continue

Depot : `Mael8zinsou/gamelens-bloc4_0` (prive). Le workflow `.github/workflows/ci.yml`
s'execute a chaque push et chaque pull request, en six etages : qualite du code,
tests unitaires, integrite des DAG Airflow, integration sur infrastructure
jetable, recette de l'entrepot Snowflake, puis publication de l'image Airflow sur
`ghcr.io` depuis la branche principale uniquement.

L'etage Snowflake applique le meme principe que l'etage d'integration : une base
est creee pour la duree du run, eprouvee, puis supprimee. Il verifie que le
schema livre s'applique, que le calcul distribue rend les valeurs attendues, que
le moteur applique toujours les memes contraintes et pas d'autres, et que les
deux filets d'integrite, controles applicatifs et contrats dbt, savent echouer
quand les donnees sont invalides. La couche de demonstration n'est jamais visee :
`entrepot/recette_ci.py` refuse de demarrer si elle l'etait.

Trois secrets sont attendus sur le depot : `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`
et `SNOWFLAKE_PRIVATE_KEY`, ce dernier portant le contenu PEM de la clef plutot
qu'un chemin, pour qu'elle ne soit jamais ecrite sur le disque du runner.

    gh secret set SNOWFLAKE_PRIVATE_KEY < secrets/snowflake_key.p8

Image publiee : `ghcr.io/mael8zinsou/gamelens-bloc4_0/airflow`, etiquetee `latest`
et par le SHA du commit.

`pytest` lance a la racine echoue a la collecte, sur un lien symbolique des logs
Airflow qu'un client Windows ne sait pas lire. Lancer `pytest tests`, comme le
fait la CI.

## Pieges d'environnement

Ces points ont tous coute du temps au moins une fois. Ce qui est deja couvert
plus haut n'est pas repete : port hote 5433, `MSYS_NO_PATHCONV=1` depuis Git
Bash, scripts de `sql/` qui ne rejouent pas sur un volume deja initialise.

- **Airflow ne tourne pas nativement sous Windows**, il lui faut un POSIX. Le
  conteneur n'est pas un confort, il est obligatoire.
- **Airflow 3 differe nettement d'Airflow 2** : `api-server` remplace
  `webserver`, `dag-processor` est un service separe obligatoire, et
  `logical_date` vaut `None` sur un run manuel. Toujours partir du
  `docker-compose.yaml` officiel de la version exacte plutot que d'un tutoriel
  Airflow 2, qui donnera une configuration qui ne demarre pas. Voir INC-006.
- **Apres toute modification d'un DAG**, lancer `airflow dags reserialize` :
  l'analyseur ne rescanne le dossier que toutes les cinq minutes, et l'attente
  passe facilement pour une erreur de code.
- **Les logs Airflow contiennent des `:` dans les noms de dossier**, qu'un
  client Windows ne sait pas lire. Les consulter par `docker exec ... cat`, pas
  depuis l'hote.
- **`pytest` lance a la racine echoue a la collecte**, sur le lien symbolique
  `docker/airflow/logs/dag_processor/latest`, qu'un client Windows ne sait pas
  lire non plus. Lancer `pytest tests`, comme le fait la CI. Ce n'est pas une
  regression.
- **`python -m venv` ne fonctionne pas sur ce poste** : le module `venv` de
  l'installation Python est vide. Ne pas chercher pourquoi, passer par un
  conteneur.
- **PostgreSQL et Kafka ne repondent pas a un navigateur**, et c'est normal :
  ils parlent leur protocole binaire sur TCP, pas HTTP, et `curl` y rend
  « Empty reply from server ». Seuls 8080 et 3000 sont des interfaces web.
- **Le chemin de travail contient accents et espaces, et cela ne pose pas de
  probleme** a Docker Desktop. L'hypothese a ete testee puis ecartee, voir
  INC-002 : ne pas la reprendre au premier symptome venu.
- **Le depot n'a pas de `.gitattributes` et melange LF et CRLF** selon les
  fichiers. Apres une edition ecrite depuis Python, verifier que le regime du
  fichier n'a pas change avant de committer : une conversion involontaire
  presente un fichier entierement reecrit la ou sept lignes ont bouge. Voir
  OBS-68.

## Ce qui ressemble a un defaut et n'en est pas

Chacun de ces choix a l'air d'un oubli. Chacun est delibere et teste, et
« corriger » l'un d'eux casse quelque chose, parfois en silence.

- **Les quatre ports publies sont lies a `127.0.0.1`**, pas a `0.0.0.0` :
  `- "127.0.0.1:5433:5432"` et ses trois voisins. Sans adresse de liaison,
  Docker publie sur toutes les interfaces, or le mot de passe de la base est
  dans le depot. Rien n'en patit : les conteneurs se joignent par le reseau
  Docker, et la CI se connecte depuis le runner en local. Voir OBS-89.
- **`bronze.reponses_brutes` n'accorde ni UPDATE ni DELETE**, pas meme a
  `etl_service`. Une archive modifiable n'est plus une archive. Teste par
  TBRZ-04.
- **La tache Twitch du DAG d'ingestion ne leve jamais**, et sans
  `TWITCH_CLIENT_ID` la collecte est un no-op qui rend un succes. Une source
  facultative ne doit pas casser une chaine eliminatoire ; son echec est trace
  dans `speed.pipeline_runs`, ou la supervision le releve. Teste par TTWI-05.
- **Le canal Telegram est facultatif de la meme facon, mais un jeton present et
  injoignable trace un echec.** L'asymetrie est voulue : un dispositif d'alerte
  ne doit pas faire tomber la chaine qu'il surveille, et son propre silence ne
  doit pas etre silencieux. Teste par TNOT-04 et TNOT-05.
- **Le consumer est abonne aux DEUX topics** et choisit sa table sur le topic
  d'origine du message. Un topic inconnu leve plutot que d'etre ignore : ecrire
  une audience dans la table de frequentation serait pire qu'une panne.
- **`entrepot/recette_ci.py` refuse les bases protegees**, `gamelens` en tete,
  et sort en code 1. Laisser `SNOWFLAKE_DATABASE` vide pour obtenir une base
  jetable nommee d'apres le run. Ne pas contourner ce refus : c'est lui qui
  empeche la CI de detruire la couche de demonstration.
- **`entrepot/connexion_snowflake.py` ne doit pas etre raccourci** en
  `connexion.py`. Ce nom-la masquait le paquet PyPI `connexion`, celui dont
  Airflow se sert pour son authentification, des lors que `entrepot/` figurait
  sur son `PYTHONPATH` : l'interface web cessait de demarrer. Voir INC-009.
- **Un seul modele de roles** pour toute la plateforme : `etl_service`,
  `analyst`, `dashboard_viewer`, plus `gamelens_app` comme proprietaire. Les
  roles `gamelens_etl` et `gamelens_reader` d'une version anterieure ont ete
  supprimes, ne pas les reintroduire. Voir OBS-25.
- **Ne pas retirer `grants` ni `persist_docs`** du modele
  `dbt/models/gold/v_popularity_dashboard.sql`. Sans le premier, la vue perd
  ses droits et le tableau de bord se vide sans erreur ; sans le second, elle
  perd son `COMMENT`, et c'est le controle du dictionnaire, a un autre etage de
  la CI, qui echoue sur un message sans rapport. Testes par TDBT-04 et TDBT-05.
- **`dbt/profiles.yml` a deux cibles, `local` et `ci`, et il faut les deux.**
  `dbt-snowflake` refuse `private_key` et `private_key_path` renseignes
  ensemble, et un `env_var()` sur une variable absente rend un champ present et
  vide, ce qui declenche ce refus. Ne pas les fusionner.

## Documentation generee : d'ou le generateur lit la verite

Les dictionnaires et le schema de donnees de `docs/annexes/` sont **generes,
jamais edites a la main**, et la CI echoue si le fichier versionne ne
correspond plus. Le piege est ailleurs, et il a produit une correction fantome :
**le generateur ne lit pas les fichiers de `sql/`, il lit le catalogue vivant**,
`obj_description()` cote PostgreSQL et `information_schema` cote Snowflake.

Corriger un `COMMENT ON` dans `sql/` puis regenerer ne change donc rien. Le
chemin reel est en trois temps : editer le `.sql`, **appliquer** le `COMMENT ON`
a la base, puis regenerer par `python outils/generer_dictionnaire.py`, avec
`--cible snowflake` pour la couche Gold.

`sql/commentaires_gold_snowflake.sql` porte les commentaires de colonnes
Snowflake separement du schema, parce que celui-ci contient des
`CREATE OR REPLACE TABLE` et ne peut pas etre rejoue. Le reappliquer apres toute
recreation du schema.

Enfin, **la base stocke en UTC et seul l'affichage est converti**, par
`GAMELENS_TIMEZONE` dont le defaut est `Europe/Paris`. Piege associe : ce qui
est formate par `to_char()` en SQL sort dans le fuseau de la SESSION et echappe
au convertisseur Python. Voir OBS-92.

## Etat d'avancement

Tous les livrables du Bloc 4 sont ecrits, et les trois competences
eliminatoires sont couvertes par des briques executees et vertes en integration
continue.

Les ecarts connus ne sont pas dissimules : ils sont numerotes dans la section 6
de `docs/feuille_route_exploitation.md`, quatorze points de vigilance dont neuf
restent ouverts. Les incidents reellement vecus sont dans
`docs/journal_incidents.md`, les arbitrages et fausses pistes dans
`docs/observations.md`.
