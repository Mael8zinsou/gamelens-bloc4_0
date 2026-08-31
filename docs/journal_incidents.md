# Journal d'incidents et d'obstacles techniques, GameLens Bloc 4

Ce journal est tenu **au fil de la construction**, pas reconstitue apres coup. Il sert deux usages :

1. alimenter la competence **C4.4.2** (methodologie d'investigation et de traitement d'un incident),
   qui exige un incident reel presente avec la methodologie appliquee ;
2. documenter les choix contraints par l'environnement, qui seront questionnes a l'oral.

La grille d'evaluation attend qu'une methodologie permette d'identifier quatre elements, repris
comme rubriques du gabarit ci-dessous : la **nature du probleme**, les **actions a mettre en oeuvre
selon les scenarios**, la **communication aupres des parties prenantes**, et les **resultats attendus**.
La rubrique communication est celle que l'on oublie le plus facilement dans un projet mene seul :
elle est ici traitee en identifiant qui aurait ete prevenu, quand et par quel canal, dans
l'organisation fictive Kestrel Interactive.

## Gabarit d'entree

```
### [ID] Titre court
- Date de detection :
- Detecte par / comment :
- Severite : bloquant | degrade | mineur
- Nature du probleme :
- Investigation menee (etapes, hypotheses testees, hypotheses ecartees) :
- Scenarios envisages et action retenue :
- Communication aux parties prenantes :
- Resultat obtenu et verification :
- Trace / preuve :
```

---

## INC-001 Apache Airflow inutilisable nativement sous Windows

- **Date de detection** : 19/08/2026, mise en place de l'environnement.
- **Detecte par / comment** : verification de l'environnement avant construction, via
  `python -c "import airflow"`.
- **Severite** : bloquant pour C4.2.2 (competence eliminatoire, l'orchestrateur est l'une des trois
  methodes exigees).
- **Nature du probleme** : le paquet `apache-airflow-core` 3.1.8 est bien installe et importable,
  mais l'import leve un `RuntimeWarning` explicite : Airflow ne peut fonctionner que sur un systeme
  POSIX. Le probleme n'est donc pas une erreur d'installation mais une incompatibilite de plateforme
  assumee par le projet Airflow lui-meme (issue amont apache/airflow#10388, non prioritaire).
  Un import reussi masque le probleme : l'echec ne serait apparu qu'a l'execution du scheduler.
- **Investigation menee** :
  - hypothese 1, installation incomplete : ecartee, l'import aboutit et la version est correcte ;
  - hypothese 2, dependance manquante specifique a Windows : ecartee, le message amont ne parle pas
    de dependance mais de systeme d'exploitation ;
  - hypothese 3, incompatibilite de plateforme : confirmee par le message de l'editeur, qui nomme
    les deux contournements supportes (WSL2 ou conteneurs Linux).
- **Scenarios envisages et action retenue** :
  | Scenario | Cout | Risque | Retenu |
  |---|---|---|---|
  | Airflow dans WSL2 Ubuntu | faible | environnement non reproductible, difficile a rejouer en CI | non |
  | Airflow en conteneurs Docker | moyen | consommation memoire | **oui** |
  | Remplacer Airflow par un ordonnanceur Windows | faible | s'ecarte du referentiel, qui cite Airflow en exemple d'orchestrateur | non |
  Retenu : Docker. Le fichier `docker-compose.yml` devient de surcroit une piece justificative pour
  C4.1.2 (choix des composants) et C4.3.3 (documentation technique), ce que WSL2 n'aurait pas apporte.
- **Communication aux parties prenantes** : dans le scenario Kestrel Interactive, ce type d'obstacle
  releve du chef de projet et se traite en sprint, sans remontee a la direction, puisqu'il n'a
  d'impact ni sur le delai ni sur le budget : le contournement est standard et documente par
  l'editeur. Il est en revanche consigne dans le wiki technique, car il conditionne la procedure
  d'installation de tout nouvel arrivant sur le projet.
- **Resultat obtenu et verification** : a verifier a la premiere execution reelle du scheduler.
- **Trace / preuve** : message d'avertissement complet a capturer dans `docs/preuves/`.

---

## INC-002 Reecriture des chemins Docker par Git Bash sous Windows

- **Date de detection** : 19/08/2026, premier test de montage de volume.
- **Detecte par / comment** : test deliberement provoque. Le repertoire de travail contient des
  accents et des espaces (`Formalites_Officiels`, `Bloc 4`, `GameLens 0`), risque identifie avant
  de construire quoi que ce soit dessus plutot que decouvert plus tard sur un pipeline complet.
- **Severite** : mineur, mais piegeur.
- **Nature du probleme** : le montage echoue depuis Git Bash avec
  `ls: C:/Program Files/Git/mnt: No such file or directory`. La cause n'est ni l'accent ni l'espace,
  contrairement a l'hypothese de depart : c'est la couche de traduction de chemins de MSYS2, qui
  interprete le `/mnt` de la partie droite du `-v` comme un chemin Windows a convertir. Le meme
  montage fonctionne sans aucune adaptation depuis PowerShell.
- **Investigation menee** : execution du meme conteneur `alpine:3.20` depuis les deux shells, avec
  le meme chemin source. Le succes cote PowerShell disqualifie l'hypothese des accents et isole la
  responsabilite du shell.
- **Scenarios envisages et action retenue** : deplacer le projet vers un chemin sans accent
  (ecarte, le probleme n'etait pas la), ou fixer la convention d'appel. Retenu : les commandes
  Docker sont passees depuis PowerShell ; si Git Bash est necessaire, prefixer par
  `MSYS_NO_PATHCONV=1` et utiliser `pwd -W`.
- **Communication aux parties prenantes** : point de configuration poste de travail, a inscrire
  dans la documentation technique (C4.3.3) destinee aux developpeurs, pas au commanditaire.
- **Resultat obtenu et verification** : montage verifie, le contenu du depot est lu depuis le
  conteneur (`ls /mnt` et lecture de `.gitignore`).
- **Trace / preuve** : sortie des deux commandes, a consigner dans `docs/preuves/`.

---

## INC-003 Compte d'essai Snowflake a recreer

- **Date de detection** : 19/08/2026, cadrage de session.
- **Severite** : bloquant pour la cible Gold reelle et pour le calcul distribue Snowpark.
- **Nature du probleme** : aucune configuration Snowflake presente sur le poste (`~/.snowflake` et
  `~/.snowsql` absents, aucune variable d'environnement), et compte d'essai vraisemblablement
  expire. Les scripts `sql/schema_gold_snowflake.sql` et `sql/verify_snowflake_constraints.sql`
  n'ont donc jamais ete executes reellement.
- **Statut** : ouvert. Traitement decale, la construction se poursuit sur les briques qui n'en
  dependent pas.

---

## INC-004 Collision de ports masquee par une erreur d'encodage Python

**Incident retenu comme candidat principal pour C4.4.2.** Son interet ne tient pas
a sa difficulte de resolution, qui est faible, mais au fait que le message
d'erreur designait un coupable qui n'avait rien a voir avec la cause reelle.

- **Date de detection** : 19/08/2026, premiere ecriture applicative en base.
- **Detecte par / comment** : echec du script `seed_game_mapping.py`, premier
  composant a ouvrir une connexion PostgreSQL depuis le poste hote.
- **Severite** : bloquant. Aucun composant d'ingestion ne pouvait ecrire en base.

### Nature du probleme

Symptome brut :

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 103:
invalid continuation byte
```

L'erreur est levee a l'interieur de `psycopg2.connect()`. Prise au premier degre,
elle oriente vers un probleme d'encodage du code applicatif, d'autant plus
credible que le projet est stocke sous un chemin comportant des accents
(`Formalites_Officiels`). C'est une fausse piste : l'octet `0xe9` est le `e`
accentue de « echouee », dans un message d'erreur PostgreSQL en francais.

Cause reelle, en trois maillons :

1. un service **PostgreSQL 18 natif** (`postgresql-x64-18`) tourne sur le poste
   et retient deja le port 5432 ;
2. Docker publie `0.0.0.0:5432->5432/tcp` **sans erreur visible** et l'affiche
   dans `docker compose ps`, alors que le port est en realite servi par le
   service natif. Rien dans l'etat rapporte par Docker ne signale le conflit ;
3. l'application se connecte donc au PostgreSQL natif, qui ne connait pas
   l'utilisateur `gamelens_app` et repond
   `authentification par mot de passe echouee`, en francais et en cp1252.
   psycopg2 tente de decoder ce message en UTF-8 et echoue avant d'avoir pu
   remonter l'erreur d'authentification.

L'erreur d'authentification, seule reellement informative, n'est jamais parvenue
au developpeur : elle a ete detruite par l'erreur de decodage de son propre
message.

### Investigation menee

| Etape | Hypothese | Verification | Resultat |
|---|---|---|---|
| 1 | Encodage du code ou du chemin accentue | Les scripts sont en UTF-8 et le montage Docker du meme chemin fonctionne (INC-002) | Ecartee |
| 2 | Le conteneur n'est pas demarre | `docker compose ps` : conteneur Up, healthcheck `pg_isready` au vert | Ecartee |
| 3 | Le port 5432 n'est pas servi par le conteneur | `Get-NetTCPConnection -LocalPort 5432` : PID 6284, processus `postgres`, service `postgresql-x64-18` en cours | **Confirmee** |
| 4 | Verifier qui repond reellement | Connexion vers `host.docker.internal:5432` depuis le conteneur | Reponse en **francais accentue** |
| 5 | Isoler les deux serveurs | `select version()` dans le conteneur | **PostgreSQL 16.15 Alpine** cote conteneur |

L'etape 4 est celle qui a tranche. L'image conteneur est une Alpine en locale C :
elle ne peut produire qu'un message en anglais ASCII. Un message d'erreur en
francais accentue etait donc, a lui seul, la preuve que l'interlocuteur n'etait
pas le conteneur. La langue du message d'erreur a servi d'empreinte pour
identifier le serveur.

### Scenarios envisages et action retenue

| Scenario | Effet | Effet de bord | Retenu |
|---|---|---|---|
| Arreter le service PostgreSQL 18 natif | Libere 5432 | Casse les travaux anterieurs du candidat qui en dependent ; a refaire a chaque redemarrage du poste | non |
| Desinstaller PostgreSQL natif | Libere 5432 definitivement | Destructif et disproportionne | non |
| **Publier le conteneur sur le port hote 5433** | Les deux serveurs coexistent | Une variable de configuration a ajuster | **oui** |

Retenu : port hote **5433**, port interne inchange a 5432. Les conteneurs
continuent de se joindre par `postgres:5432` sur le reseau Docker, seuls les
processus du poste hote passent par 5433. Le choix est inscrit dans
`docker-compose.yml` avec le commentaire expliquant pourquoi ce n'est pas 5432,
faute de quoi un lecteur futur « corrigerait » l'anomalie apparente et
reintroduirait l'incident.

### Communication aux parties prenantes

Incident de poste de developpement, sans impact sur un service rendu : dans le
cadre Kestrel Interactive, aucune remontee au commanditaire ni a la direction
n'est justifiee. La communication pertinente est interne a l'equipe technique,
en trois temps :

- **immediat** : mention en daily, car tout membre de l'equipe disposant d'un
  PostgreSQL local rencontrera exactement le meme blocage ;
- **court terme** : ajout d'un prerequis dans la procedure d'installation
  (documentation technique, C4.3.3), formule comme une verification a mener
  avant le premier demarrage plutot que comme un depannage a posteriori ;
- **durable** : entree dans ce journal, pour que le lien entre le symptome
  (`UnicodeDecodeError`) et la cause (collision de ports) reste retrouvable par
  recherche textuelle.

### Resultat obtenu et verification

Apres bascule sur 5433, verification par l'execution reelle et non par la seule
absence d'erreur :

- `seed_game_mapping.py` : 15 titres ecrits dans `speed.game_mapping` ;
- chaine complete Steam vers Kafka vers PostgreSQL : 15 evenements collectes,
  publies, consommes et ecrits ;
- rejeu volontaire apres remise a zero des offsets du groupe de consommation :
  15 messages relus, **0 insere, 15 doublons absorbes**, table toujours a
  15 lignes, ce qui valide au passage l'idempotence du puits.

### Enseignement

Un message d'erreur peut etre detruit par le mecanisme meme qui devait le
transmettre. Ici, l'erreur utile existait et etait parfaitement explicite, mais
elle a ete perdue dans sa traduction. La lecon operationnelle est de se mefier
d'une erreur technique de bas niveau (encodage, serialisation, parsing) surgie
au milieu d'une operation d'infrastructure : elle est souvent le linceul d'une
erreur fonctionnelle plus haute, pas le probleme lui-meme.

---

# Session 2, 20 août 2026

## INC-005 Le DAG dupliquait ses propres lignes au rejeu

- **Date de detection** : 20/08/2026, ecriture du DAG de promotion.
- **Detecte par / comment** : non pas par un plantage, mais en cherchant a
  ecrire un `ON CONFLICT` et en constatant qu'aucune contrainte ne pouvait
  l'ancrer.
- **Severite** : bloquant pour la rejouabilite, silencieux pour tout le reste.
- **Nature du probleme** : `mart.dim_games` et `mart.fact_prices` ne portaient
  pour toute unicite que leur cle primaire UUID, generee a l'insertion. Deux
  executions du DAG sur la meme journee auraient donc cree deux jeux de lignes
  identiques a l'UUID pres, sans qu'aucune contrainte ne s'y oppose et sans
  message d'erreur. Le schema Gold avait ete concu avant l'existence du
  pipeline : rien n'y designait la cle naturelle d'un jeu ni le grain reel d'un
  releve tarifaire.
- **Investigation menee** : lecture du schema en partant de la question
  « qu'est-ce qui, dans cette table, ne doit exister qu'une fois ? ». Pour
  `dim_games`, c'est `steam_appid`. Pour `fact_prices`, c'est le triplet
  (jeu, boutique, instant de collecte). `fact_popularity_history` etait deja
  correcte, sa cle primaire composite portant deja le grain.
- **Scenarios envisages et action retenue** : dedupliquer apres coup dans le
  DAG (ecarte : deplace le probleme d'integrite vers du code applicatif que
  rien ne garantit), ou declarer les contraintes manquantes. Retenu : deux
  contraintes `UNIQUE`, ajoutees au schema PostgreSQL et declarees en miroir
  dans le schema Snowflake, ou elles ne seront pas appliquees et devront donc
  etre relayees par des tests dbt.
- **Communication aux parties prenantes** : aucune, l'anomalie n'a jamais
  atteint de donnee reelle. En revanche, l'enseignement est consigne : un
  schema d'entrepot valide un modele, il ne valide pas une strategie de
  rechargement. Les deux se relisent separement.
- **Resultat obtenu et verification** : le DAG a ete execute trois fois de
  suite sur la meme journee. `mart.dim_games` est reste a 15 lignes et
  `mart.fact_popularity_history` a 15 lignes.

## INC-006 logical_date nul sur un run manuel en Airflow 3

- **Date de detection** : 20/08/2026, premier declenchement manuel du DAG.
- **Severite** : bloquant pour tout declenchement manuel, donc pour la
  demonstration en soutenance.
- **Nature du probleme** : Airflow 3 rend `logical_date` nullable et le laisse
  a `None` pour un run declenche a la main, alors qu'Airflow 2 en fournissait
  toujours un. Le code `context["logical_date"].date()` leve donc un
  `AttributeError` sur un run manuel, alors qu'il fonctionne parfaitement sur
  un run planifie. Le piege tient a cette asymetrie : la voie nominale marche,
  seule la voie utilisee pour tester echoue.
- **Investigation menee** : la sortie de `airflow dags trigger` affiche
  explicitement une colonne `logical_date` vide, ce qui a suffi a identifier la
  cause avant meme que la tache ne s'execute.
- **Action retenue** : repli en trois temps dans la tache, du plus explicite au
  plus general : parametre `jour` fourni par l'operateur, sinon `logical_date`
  si elle existe, sinon la date du jour en UTC. Le parametre `jour` a ete
  ajoute au DAG dans la foulee : il permet de rejouer une journee precise
  depuis l'interface, sans modifier le code ni desactiver `catchup`.
- **Communication aux parties prenantes** : point de migration a signaler a
  toute equipe passant d'Airflow 2 a Airflow 3, car il ne se manifeste pas en
  fonctionnement nominal.
- **Resultat obtenu et verification** : trois runs manuels declenches ensuite,
  tous en succes.

## INC-007 Quatre collectes reelles, une seule ligne de journal

- **Date de detection** : 20/08/2026, controle du contenu de la base apres les
  premiers runs orchestres.
- **Severite** : mineur en apparence, structurant pour la supervision.
- **Nature du probleme** : `speed.price_snapshots` contenait quatre horodatages
  de collecte distincts, alors que `speed.pipeline_runs`, la table qui sert de
  socle a la supervision (C4.3.1), n'en tracait qu'un seul. La tache Airflow
  appelait `collecter()`, qui ecrit les donnees, plutot que le point d'entree
  qui enregistre aussi l'execution. Les collectes lancees par l'orchestrateur
  etaient donc invisibles pour la supervision, alors meme qu'elles
  reussissaient.
- **Investigation menee** : rapprochement de deux comptages qui auraient du
  concorder, `SELECT collected_at, count(*) FROM speed.price_snapshots
  GROUP BY 1` d'un cote, contenu de `speed.pipeline_runs` de l'autre. L'ecart
  entre les deux est ce qui a revele le trou.
- **Action retenue** : introduction d'un point d'entree `collecter_et_tracer()`
  distinct de `collecter()`, et correction de l'appel dans le DAG. La
  distinction est documentee dans le code pour qu'elle ne soit pas defaite par
  une simplification ulterieure.
- **Communication aux parties prenantes** : a signaler a l'equipe
  d'exploitation, car le symptome d'un tel defaut est trompeur : la supervision
  ne montre pas une erreur, elle montre une absence, ce qui se confond avec un
  composant a l'arret.
- **Resultat obtenu et verification** : nouveau run declenche apres correction,
  la ligne correspondante apparait bien dans `speed.pipeline_runs`.
- **Enseignement** : ce defaut est le pendant exact de INC-004. Dans les deux
  cas, un indicateur au vert, ou muet, ne disait rien de la realite. Un
  systeme de supervision doit etre teste sur ce qu'il rate, pas seulement sur
  ce qu'il rapporte.

---

# Session 6, 27 août 2026

## INC-008 Une panne d'infrastructure ne laissait aucune trace en échec

- **Date de detection** : 27/08/2026, mise en service du DAG d'ingestion.
- **Detecte par / comment** : par un test negatif deliberé, et non par une
  panne subie. Le broker Kafka a ete arrete volontairement pour verifier que la
  chaine echoue bruyamment plutot que de reussir a vide.
- **Severite** : mineur en apparence, degradant pour la supervision.

### Nature du probleme

Le test a produit le resultat attendu au niveau de l'orchestrateur : la tache
`collecter_et_publier` echoue, l'aval ne demarre pas, le message est explicite
(`NoBrokersAvailable`). Jusque-la, tout est conforme.

La verification suivante, elle, ne l'etait pas :

```sql
SELECT component, status, error_message FROM speed.pipeline_runs
WHERE started_at >= now() - interval '8 minutes';
-- (0 rows)
```

**Zero ligne.** Une panne complete du broker n'avait laisse aucune trace dans
le journal d'executions, alors que ce journal est precisement la source de la
supervision.

Cause : dans `steam_producer.py`, l'objet `KafkaProducer` etait construit
**avant** l'ouverture du gestionnaire de contexte `execution()`. Or c'est sa
construction qui leve `NoBrokersAvailable`. L'exception survenait donc avant
que la ligne `started` ne soit inscrite, et le mecanisme de tracage, qui gere
pourtant parfaitement les exceptions, n'etait jamais atteint.

Le meme defaut existait dans `kafka_to_postgres.py`, ou `KafkaConsumer` et
`connexion_pg()` etaient egalement construits en amont du contexte.

### Consequence reelle

La panne n'etait pas invisible, elle etait **mal qualifiee**. La regle
`echecs_composants`, qui compte les executions en statut `failed`, ne voyait
rien. Seule la regle `composant_muet` aurait fini par se declencher, plus tard
et avec un diagnostic moins precis : elle dit « ce composant ne s'est pas
manifeste », la ou l'information disponible etait « ce composant a echoue, et
voici pourquoi ».

Sur une plateforme de production, cette nuance separe une astreinte qui sait
quoi regarder d'une astreinte qui cherche.

### Investigation menee

| Etape | Hypothese | Verification | Resultat |
|---|---|---|---|
| 1 | Le tracage ne gere pas les exceptions | Lecture de `execution()` : le bloc `except BaseException` ecrit bien `failed` puis relance | Ecartee |
| 2 | La connexion de tracage a echoue aussi | PostgreSQL est sain, les DAG voisins ecrivent normalement | Ecartee |
| 3 | L'exception precede l'ouverture du contexte | Lecture de l'ordre des instructions dans `main()` | **Confirmee** |

L'etape 1 est celle qui oriente : constater que le mecanisme est correct
deplace la question de « pourquoi n'a-t-il pas fonctionne ? » vers « pourquoi
n'a-t-il pas ete atteint ? ».

### Scenarios envisages et action retenue

| Scenario | Effet | Effet de bord | Retenu |
|---|---|---|---|
| Envelopper l'appel dans un `try` dedie au niveau du DAG | Trace l'echec | Duplique la logique de tracage dans chaque orchestrateur, et laisse les executions manuelles sans trace | non |
| Attraper l'exception dans `main()` et ecrire la ligne a la main | Trace l'echec | Deuxieme chemin d'ecriture a maintenir en parallele de `execution()` | non |
| **Deplacer la construction a l'interieur du contexte `execution()`** | Trace l'echec | Le `finally` doit tolerer un objet non construit | **oui** |

Retenu : la troisieme. Elle ne cree aucun chemin d'ecriture supplementaire et
vaut pour tous les appelants, DAG comme ligne de commande. Les blocs `finally`
ont ete rendus tolerants a une construction ratee.

### Communication aux parties prenantes

Defaut d'observabilite sans perte de donnee ni interruption de service rendu :
pas de remontee au commanditaire dans le cadre Kestrel Interactive. La
communication utile est destinee a l'equipe d'exploitation, qui s'appuie sur ce
journal pour ses astreintes, sous la forme d'une note precisant que les pannes
de dependance externe sont desormais qualifiees `failed` et non plus
silencieuses.

### Resultat obtenu et verification

Rejoue dans les memes conditions, broker toujours arrete :

```
   component    | status |     started_at      |               erreur
----------------+--------+---------------------+--------------------------------
 steam_producer | failed | 2026-08-27 09:40:07 | NoBrokersAvailable: NoBrokersA
```

Puis, broker relance, la **reprise automatique** d'Airflow deux minutes plus
tard a rendu la main sans intervention :

```
 steam_producer    | success | 2026-08-27 09:42:11 |              15 |
 kafka_to_postgres | success | 2026-08-27 09:42:22 |              15 |
```

Avant correction : 0 ligne. Apres : une ligne `failed` portant la cause, puis
une reprise reussie. Aucune donnee perdue.

### Enseignement

Un mecanisme d'observabilite correct ne sert a rien s'il n'est pas atteint. Le
code de `execution()` etait juste, testé, et gerait les exceptions exactement
comme il fallait : il etait simplement place apres la ligne qui echoue.

Corollaire de methode : ce defaut n'a ete trouve que parce que le test negatif
ne s'est pas arrete au premier resultat satisfaisant. La tache Airflow etait
rouge, ce qui suffisait a valider « la chaine echoue bruyamment ». C'est la
verification suivante, celle du journal, qui a revele que le bruit n'arrivait
pas jusqu'a la supervision.

---

## INC-009 Un module du projet masquait une bibliotheque d'Airflow

- **Date de detection** : 31/08/2026, pendant le cablage du DAG de promotion
  vers Snowflake.
- **Detecte par / comment** : par l'interface web d'Airflow, devenue
  inaccessible dans la minute qui a suivi l'ajout de `entrepot/` au
  `PYTHONPATH` des conteneurs.
- **Severite** : bloquant pour l'interface, sans effet sur les traitements.
  Latent depuis la creation du module, en session 2.

### Nature du probleme

Le DAG de promotion Snowflake a besoin d'appeler `entrepot/snowpark_promotion.py`.
Le repertoire `entrepot/` a donc ete monte dans les conteneurs Airflow et ajoute
a leur `PYTHONPATH`. Le montage est correct, la promotion a fonctionne du
premier coup.

Quelques secondes plus tard, le journal du planificateur affichait ceci :

```
cannot import name 'FlaskApi' from 'connexion' (/opt/gamelens/entrepot/connexion.py)
cannot load CLI commands from auth manager: The object could not be loaded.
Auth manager is not configured and api-server will not be able to start.
```

Le module `entrepot/connexion.py`, qui porte la connexion a Snowflake et qui
s'appelle `connexion_snowflake.py` depuis la resolution de cet incident, portait
aussi le nom d'un paquet PyPI reel et largement utilise : **`connexion`**, la
bibliotheque OpenAPI dont Airflow se sert pour son gestionnaire
d'authentification FAB. Version installee dans l'image : 2.14.2.

Les entrees de `PYTHONPATH` sont examinees **avant** `site-packages`. A partir
du moment ou `entrepot/` y figurait, tout `import connexion` du processus, y
compris ceux d'Airflow lui-meme, atteignait notre fichier.

La collision existait depuis toujours. Elle dormait parce qu'aucun processus
susceptible d'importer la vraie bibliotheque n'avait ce repertoire sur son
chemin de recherche.

### Consequence reelle

L'interface web a cesse de demarrer pendant environ douze minutes. Les
traitements, eux, n'ont rien vu : le planificateur n'a pas besoin du
gestionnaire d'authentification, et le DAG de promotion a tourne correctement
pendant l'indisponibilite.

C'est ce qui rend l'incident interessant. La panne ne touchait pas la donnee,
elle touchait le seul moyen humain de regarder la donnee.

**Et rien ne l'a signale.** Verification faite apres coup :

```sql
SELECT regle, declenchee_le FROM speed.alertes
WHERE declenchee_le > '2026-08-31 09:30';
-- (0 rows)
```

Zero alerte. La supervision surveille le pipeline, pas la couche web de
l'ordonnanceur qui l'execute. C'est la meme famille que V-07 : le dispositif
ne se surveille pas lui-meme.

### Investigation menee

Courte, parce que le message d'erreur etait exemplaire : il nommait le fichier
fautif entre parentheses. Trois verifications ont suffi.

```bash
# 1. Le paquet existe-t-il vraiment, ou l'import est-il simplement casse ?
docker exec gamelens-airflow-scheduler python -c \
  "from importlib.metadata import version; print(version('connexion'))"
# 2.14.2  -> c'est bien un paquet installe que l'on masque.

# 2. Qui, chez nous, depend de ce nom ?
grep -rn "^from connexion import" --include=*.py .
# cinq fichiers, tous dans entrepot/

# 3. Le planificateur est-il affecte, ou seulement l'interface ?
docker ps --format "{{.Names}}\t{{.Status}}" | grep airflow
# scheduler sain, api-server en redemarrage permanent
```

### Scenarios envisages et action retenue

**Scenario 1, retirer `entrepot/` du `PYTHONPATH`** et importer le module par
son chemin dans la tache, avec `importlib`. Repare l'interface. Ecarte : la
collision reste entiere, prete a se declencher au prochain qui ajoutera ce
repertoire quelque part, et le code de la tache devient obscur.

**Scenario 2, faire de `entrepot/` un paquet** avec un `__init__.py` et importer
`entrepot.connexion`. Techniquement propre. Ecarte pour son cout de bordure :
il faudrait changer le `PYTHONPATH` de la CI, celui de l'image d'outillage
Snowflake, et les cinq imports, sans supprimer la cause pour autant, puisque le
nom `connexion` resterait disponible a quiconque pointerait directement le
repertoire.

**Scenario 3, retenu : renommer le module** en `connexion_snowflake.py`. Cinq
imports a corriger, aucune bordure a toucher, et la cause disparait. Le nom
gagne au passage en precision : ce module ne connecte pas a n'importe quoi,
il connecte a Snowflake.

### Communication aux parties prenantes

Projet a un seul intervenant : la question devient celle de la transmission a
qui reprendra le depot, moi compris dans six mois.

Trois traces posees, delibrement redondantes parce qu'elles ne seront pas lues
dans les memes circonstances :

1. Un avertissement en tete du module lui-meme, la ou se trouvera quiconque
   sera tente de raccourcir le nom.
2. Un fait d'environnement dans `CLAUDE.md`, la ou on cherche avant de modifier
   la configuration des conteneurs.
3. Le present incident, qui porte le raisonnement complet.

La regle generale qui en decoule, et qui vaut d'etre dite a l'oral : **ajouter
un repertoire au `PYTHONPATH` n'est pas une operation additive.** Elle peut
retirer l'acces a des modules qui fonctionnaient, sans que rien ne le signale
ailleurs que dans le composant qui en dependait.

### Resultat obtenu et verification

- `git mv entrepot/connexion.py entrepot/connexion_snowflake.py`, cinq imports
  corriges, avertissement ajoute en tete du module.
- Les quatre conteneurs Airflow sont revenus sains, api-server compris.
- `airflow dags list-import-errors` rend `No data found`.
- Trois executions du DAG de promotion en succes, dont une **planifiee
  automatiquement** par l'ordonnanceur pour le creneau de 03h00.
- La porte de fraicheur a ete eprouvee en negatif sur une journee vide et a
  refuse avec le message attendu.

### Enseignement

Un nom de module local qui coincide avec celui d'un paquet installe est une
bombe a retardement dont la meche est le **chemin de recherche**, pas le code.
Tant que les deux ne se croisent pas, tout va bien, et rien n'avertit. Le jour
ou un besoin sans rapport, ici appeler une promotion depuis un DAG, fait se
croiser les deux, la panne apparait dans un composant qui n'a rien a voir avec
le changement.

Deuxieme enseignement, plus inconfortable : la panne a dure douze minutes sans
declencher quoi que ce soit, parce qu'elle touchait l'interface et non la
donnee. Une supervision construite autour des traitements ne voit pas
l'indisponibilite de ce qui permet de les regarder.
