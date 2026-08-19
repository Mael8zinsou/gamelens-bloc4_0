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
