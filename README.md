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
      Steam Web API                        Steam appdetails
      GetNumberOfCurrentPlayers            price_overview
      (temps reel, sans authentification)  (tarification)
                 |                                    |
                 v                                    v
      ingestion/steam_producer.py         ingestion/steam_prices.py
                 |     \                            /     |
                 |      +--------------------------+      |
                 |                    |                   |
                 |                    v                   |
                 |        bronze.reponses_brutes          |
                 |        archive de tout appel,          |
                 |        abouti ou non, sans UPDATE      |
                 |                                        |
                 v                                        |
      Apache Kafka (mode KRaft)                           |
      gamelens.steam.player_count                         |
                 |                                        |
      ingestion/kafka_to_postgres.py                      |
                 |                                        |
                 v                                        v
      PostgreSQL, couche Silver speed (schema speed)
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
echelle (41 Mo par an, mesures).

## Demarrage

Prerequis : Docker Desktop demarre, Python 3.12.

```powershell
docker compose up -d                 # 7 conteneurs : PostgreSQL, Kafka, 4 Airflow, Grafana
Copy-Item .env.example .env          # puis ajuster si besoin
python -m pip install -r requirements.txt

python ingestion/create_topics.py      # declaration explicite des topics
python ingestion/seed_game_mapping.py  # referentiel des titres suivis
python ingestion/steam_producer.py --once
python ingestion/kafka_to_postgres.py --timeout 30 --depuis-le-debut
python ingestion/steam_prices.py --once
```

Les quatre schemas PostgreSQL (Silver speed, Bronze, Gold prototype,
supervision) sont appliques automatiquement au premier demarrage : ils sont
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
| `ingestion/` | Pipeline temps reel et tarifaire : producer, consumer, referentiel, topics, archivage Bronze |
| `sql/schema_bronze.sql` | Couche Bronze, archive brute en append only |
| `sql/schema_silver_speed.sql` | Couche Silver speed, PostgreSQL |
| `sql/schema_gold_snowflake.sql` | Couche Gold, cible Snowflake |
| `sql/commentaires_gold_snowflake.sql` | Commentaires des colonnes Snowflake, separes du schema qui n'est pas rejouable |
| `sql/schema_gold.sql` | Prototype PostgreSQL du Gold, conserve comme reference |
| `sql/verify_snowflake_constraints.sql` | Verification empirique des contraintes Snowflake |
| `sql/schema_supervision.sql` | Indicateurs de supervision et journal d'alertes |
| `dags/` | 4 DAG Airflow : ingestion temps reel, promotion PostgreSQL, promotion Snowflake, supervision |
| `entrepot/` | Connexion Snowflake, promotion Snowpark, controles d'integrite et recette de CI |
| `dbt/` | Projet dbt : 4 sources et 1 modele, 29 contrats declaratifs au total (25 portes par les sources, 4 par le modele) |
| `supervision/` | Moteur d'alertes et verification du tableau de bord |
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
| `docs/captures/` | Captures d'ecran d'interfaces, deposees a la main |
| `docs/vulgarisation/` | Deux versions vulgarisees du projet, pour un junior et pour un non-specialiste |

Les dictionnaires de `docs/annexes/` ne s'editent pas a la main : ils sont
generes depuis les `COMMENT ON` des fichiers de `sql/` par
`outils/generer_dictionnaire.py`, et la CI echoue si le fichier versionne ne
correspond plus au catalogue.

## Ou se trouve la preuve de chaque competence

| Competence | Realisation | Preuve |
|---|---|---|
| C4.2.1, architecture d'entrepot | Deux couches Gold, Snowflake et PostgreSQL | `sql/schema_gold_snowflake.sql`, `sql/schema_gold.sql`, `sql/verify_snowflake_constraints.sql` |
| C4.2.2, methode 1, temps reel | Steam vers Kafka vers PostgreSQL, idempotent | `ingestion/`, DAG `gamelens_ingestion_temps_reel` |
| C4.2.2, methode 2, orchestrateur | Airflow 3.1.8, 4 DAG | `dags/`, http://localhost:8080 |
| C4.2.2, methode 3, calcul distribue | Snowpark, et non Spark local | `entrepot/snowpark_promotion.py`, DA-04 |
| C4.2.3, CI/CD | 6 etages, base Snowflake jetable, image publiee | `.github/workflows/ci.yml` |
| C4.3.1, supervision | 5 indicateurs SQL, 6 regles, Grafana comme code | `sql/schema_supervision.sql`, `supervision/`, `docker/grafana/` |
| C4.3.2, exploitation | 10 sections, 13 points de vigilance | `docs/feuille_route_exploitation.md` |
| C4.3.3, documentation technique | 11 decisions datees, 2 annexes generees | `docs/documentation_technique.md` |
| C4.4.1, recettes | 55 PASS, 0 partiel, 0 en attente | `docs/cahier_recettes.md` |
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

**Limite connue et assumee : rien ne previent un humain.** Les alertes sont
persistees et visibles, aucun canal de notification n'est branche. C'est V-02
dans `docs/feuille_route_exploitation.md`, l'ecart le plus important entre cette
plateforme et une plateforme exploitee, et il est chiffre : une alerte de
fraicheur est restee ouverte 6 j 20 h en aout.

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

## Etat d'avancement

Voir le tableau de suivi et la liste des ecarts connus dans `CLAUDE.md`.
