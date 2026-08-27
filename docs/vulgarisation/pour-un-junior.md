# GameLens expliqué à un data engineer junior

Tu sors d'école. Tu sais écrire du SQL, tu as manipulé pandas, tu as sans doute
vu passer Airflow et Kafka dans un cours ou un projet. Ce qui te manque, ce
n'est pas le vocabulaire, c'est l'expérience de ce qui casse.

Ce document ne t'explique donc pas ce qu'est une clé étrangère. Il t'explique
pourquoi il n'y en a pas dans l'entrepôt de ce projet, comment on s'en est
aperçu, et ce qu'on a mis à la place.

## Comment lire ce document

Il est organisé par **décisions**, pas par composants. La liste des composants
est dans le `README.md` du dépôt et elle t'apprendra peu : tout le monde met du
Kafka et de l'Airflow. Ce qui distingue un projet d'un autre, ce sont les
arbitrages, et surtout ce qu'ils ont coûté.

Quand une affirmation ici est vérifiable, elle renvoie au document de suivi qui
porte la preuve. Rien n'est raconté de mémoire.

---

# 1. Le problème, et pourquoi il n'est pas trivial

**Kestrel Interactive** est un éditeur de jeux vidéo indépendant fictif, une
quinzaine de titres. Il veut savoir, jour après jour, comment ses jeux et ceux
de ses concurrents se portent : combien de joueurs, à quel prix, avec quelle
audience sur les plateformes de diffusion.

Des outils du marché font ça très bien, et cher. La question posée est un
classique du métier, le **build vs buy** : est-ce qu'on achète, ou est-ce qu'on
construit ? GameLens est la réponse « on construit », et le projet doit donc
démontrer que la construction tient debout.

Ça a l'air simple. Trois API publiques, un peu de Python, une base, un tableau
de bord. Voilà les cinq choses qui rendent ça beaucoup moins simple, et ce sont
elles qui structurent tout le reste du projet.

**La donnée est périssable et non rejouable.** Le nombre de joueurs connectés à
un instant donné n'existe qu'à cet instant. Si ta collecte tombe en panne
pendant six heures, ces six heures sont perdues pour toujours. Aucune API ne te
les rendra. Ça change complètement le rapport à la fiabilité : tu ne peux pas
« relancer demain » comme sur un batch qui lit un fichier.

**Les identifiants ne se correspondent pas.** Le même jeu s'appelle `413150`
chez Steam, autre chose chez Twitch, autre chose encore chez RAWG, et « Disco
Elysium - The Final Cut » là où ton catalogue interne dit « Disco Elysium ».
Rien ne relie ces identités entre elles. Il faut construire et maintenir cette
correspondance, c'est le rôle de la table `game_mapping`, et c'est un travail
qui ne finit jamais.

**Deux besoins contradictoires sur la même donnée.** Le pilote de production
veut savoir ce qui se passe *maintenant*. L'analyste veut comparer *sur six
mois*. La première question demande de la fraîcheur et tolère l'approximation ;
la seconde demande de la cohérence et tolère le délai. Un seul chemin technique
ne peut pas satisfaire les deux correctement. D'où l'architecture Lambda, qui
en pose deux.

**Les sources sont hors de ton contrôle.** L'API Steam peut ralentir, changer,
tomber. Tu n'as aucun recours. Ta seule défense, c'est de savoir rapidement que
quelque chose ne va plus, d'où tout le volet supervision.

**Personne ne te dira que le pipeline est en panne.** C'est le point le plus
important et le moins intuitif. Un pipeline de données qui échoue bruyamment
est un cas facile. Le cas difficile, c'est celui qui **réussit sans rien
faire** : le programme se termine en code 0, les journaux sont verts, et
personne ne s'aperçoit pendant trois semaines que la table ne reçoit plus rien.
Tu verras cette idée revenir partout dans ce document. C'est le fil conducteur
du projet.

---

# 2. L'architecture en une page

```
        Steam Web API  (temps reel, sans authentification)
                    |
                    v
        ingestion/steam_producer.py          <- collecte et publie
                    |
            Apache Kafka (mode KRaft)        <- tampon durable
        gamelens.steam.player_count
                    |
        ingestion/kafka_to_postgres.py       <- consomme et ecrit
                    |
                    v
        PostgreSQL, couche Silver speed      <- la donnee recente, nettoyee
                    |
        Airflow, promotion journaliere       <- orchestration
                    |
                    v
        Snowflake, couche Gold               <- l'entrepot analytique
        dim_games, dim_stores, fact_prices,
        fact_popularity_history
```

## Pourquoi trois couches, et pas une

C'est l'architecture **Medallion**, et son intérêt n'est pas esthétique.

**Bronze**, c'est la donnée brute telle qu'elle est arrivée, jamais modifiée.
Son utilité est unique et suffisante : le jour où tu découvres un bug dans ta
transformation, tu peux tout recalculer. Si tu as écrasé la source, tu ne peux
rien recalculer du tout. C'est une assurance, et comme toute assurance elle ne
sert que le jour où ça va mal.

**Silver**, c'est la donnée nettoyée, typée, dédoublonnée, avec les
identifiants réconciliés. C'est là que le travail réel a lieu.

**Gold**, c'est la donnée mise en forme pour répondre à des questions
métier : des tables de faits et des dimensions, un schéma en étoile, pensé
pour être interrogé et pas pour être alimenté.

La tentation, quand on débute, est de tout faire en une passe : lire l'API,
transformer, écrire la table finale. Ça marche jusqu'au jour où tu dois changer
la transformation, et là tu découvres que tu n'as plus la matière première.

## Pourquoi deux chemins pour la même donnée

C'est l'architecture **Lambda**, et elle répond au troisième point de la
section 1.

Le **chemin rapide** (speed layer) va de l'API à PostgreSQL en passant par
Kafka, en continu. Il donne la fraîcheur. Il est simple et il accepte d'être
approximatif.

Le **chemin batch** promeut chaque nuit les données consolidées vers Snowflake.
Il donne la cohérence et l'historique. Il a le droit d'être lent.

Le prix à payer, et il faut le savoir avant de choisir cette architecture,
c'est que **la logique métier existe en deux endroits**. Le jour où tu changes
la règle de calcul d'un indicateur, tu dois la changer des deux côtés, sous
peine de voir le tableau de bord temps réel et le rapport mensuel se
contredire. C'est la critique classique de Lambda, et elle est justifiée. Ici
le périmètre est petit, donc c'est tenable.

---

# 3. Les sept décisions qui structurent tout le reste

## 3.1 L'exactement-une-fois par puits idempotent, pas par transaction distribuée

**Le problème.** Tu lis un message dans Kafka, tu l'écris en base, tu confirmes
à Kafka que tu l'as traité. Trois opérations, deux systèmes. Si le processus
meurt entre l'écriture et la confirmation, Kafka te redonnera le message au
redémarrage et tu l'écriras deux fois. C'est le problème classique de la
livraison exactement une fois.

**La réponse ambitieuse**, celle qu'on a envie de donner en sortie d'école,
c'est une transaction distribuée entre Kafka et PostgreSQL, avec un protocole
de validation en deux phases. C'est faisable. C'est aussi lourd, fragile, et
difficile à expliquer.

**La réponse retenue** tient en trois éléments qui ne coûtent presque rien :

1. une contrainte `UNIQUE (steam_appid, collected_at)` sur la table de
   destination ;
2. un `INSERT ... ON CONFLICT DO NOTHING` ;
3. la confirmation de l'offset Kafka **après** la validation de la transaction
   PostgreSQL, jamais avant.

Résultat : le message peut arriver deux fois, la deuxième insertion ne fait
rien. On n'a pas obtenu l'exactement-une-fois au niveau du transport, on a
rendu la répétition **inoffensive**. C'est ce qu'on appelle un puits idempotent.

**Ce qu'il faut en retenir.** En ingénierie des données, on cherche presque
toujours à rendre le rejeu inoffensif plutôt qu'impossible. C'est plus simple,
plus robuste, et ça survit à des pannes qu'on n'avait pas prévues.

**La preuve.** Elle n'est pas théorique : les offsets du groupe de consommation
ont été remis à zéro et les 15 messages relus. Résultat, **0 ligne insérée, 15
doublons absorbés**, table toujours à 15 lignes. Un test qui n'aurait vérifié
que « le consommateur tourne sans erreur » n'aurait rien prouvé.

## 3.2 Snowpark plutôt que PySpark en local

Le référentiel demande une méthode de **calcul distribué**. La solution
évidente est PySpark. Le piège est que PySpark installé sur ton portable tourne
en mode local, c'est-à-dire sur un seul processus, sur une seule machine. Tu
peux écrire du code qui *ressemble* à du calcul distribué sans que rien ne soit
distribué.

Un jury qui demande « en quoi est-ce distribué ? » a alors une réponse
embarrassante : ça ne l'est pas, c'est du pandas avec une syntaxe différente.

D'où **Snowpark**. Tu écris du code qui ressemble à du DataFrame, mais Snowpark
ne calcule rien : il **traduit ton code en SQL** et l'envoie à l'entrepôt
virtuel Snowflake, qui le répartit sur ses noeuds. Le processus Python n'envoie
qu'un plan et reçoit un résultat.

Et surtout, c'est **prouvable**, ce qui est le vrai critère :

- `classement.queries["queries"]` te donne le SQL réellement envoyé, on le lit ;
- `information_schema.query_history_by_session()` liste les requêtes compilées
  et exécutées côté serveur, avec les octets scannés et le temps d'exécution.

Le calcul lui-même est une fenêtre glissante sur 7 jours par jeu, plus un
classement par genre. Trois opérations qui, sur un volume réel, ne tiendraient
pas en mémoire locale.

## 3.3 Airflow en conteneur, et ce que ça a coûté

Airflow **ne tourne pas nativement sous Windows**. Ce n'est pas un défaut
d'installation, c'est une incompatibilité assumée par le projet en amont : il
exige un système POSIX.

Le piège, c'est que `import airflow` **réussit** sur Windows. Tu n'aurais
découvert le problème qu'au démarrage du scheduler, beaucoup plus tard. C'est
une constante de ce métier : un import qui passe ne prouve pas qu'un composant
fonctionne.

Trois scénarios ont été comparés, et le tableau figure dans le journal
d'incidents (INC-001) : WSL2, conteneurs Docker, ou un ordonnanceur Windows en
remplacement. Retenu : Docker, parce que c'est le seul des trois qui soit
**reproductible ailleurs**, notamment sur un runner d'intégration continue.
WSL2 aurait marché sur ce poste et nulle part ailleurs.

Il faut savoir qu'Airflow 3 diffère nettement d'Airflow 2, et que la plupart
des tutoriels en ligne parlent d'Airflow 2 :

- `api-server` remplace `webserver` ;
- `dag-processor` devient un service séparé et obligatoire ;
- `logical_date` peut valoir `None` sur un lancement manuel, ce qui a produit
  un incident réel (INC-006).

Règle pratique : pars toujours du `docker-compose.yaml` officiel de la version
exacte, jamais d'un tutoriel.

## 3.4 Un environnement Python par jeu de dépendances

Vouloir installer Snowpark et dbt à côté du code d'ingestion casse
l'environnement. Ce n'est pas une hypothèse, c'est ce qui s'est passé :
`snowflake-snowpark-python` impose `snowflake-connector-python` en version 4,
que `dbt-snowflake` 1.8 refuse, et l'installation a au passage remonté la
version de `requests` épinglée pour l'ingestion.

Deux réactions possibles.

**Arbitrer**, c'est-à-dire chercher le jeu de versions qui satisfait tout le
monde. C'est ce qu'on fait instinctivement, et ça finit en général par une
contrainte impossible, ou pire, par un `--force-reinstall` qui laisse
l'environnement dans un état que personne ne saura reproduire.

**Isoler**, c'est-à-dire donner à chaque famille de dépendances son propre
conteneur. C'est ce qui a été retenu : `requirements.txt` pour l'ingestion,
`requirements-snowflake.txt` pour l'outillage Snowflake, dans une image à part,
invoquée à la demande.

**Ce qu'il faut en retenir.** Un conflit de dépendances qui résiste est un
signal : ces deux choses n'ont pas vocation à cohabiter. Sépare-les au lieu de
négocier.

Détail utile pour le diagnostic : la question « est-ce moi qui viens de casser
ça ? » s'est tranchée en regardant les **dates de modification des dossiers
`dist-info`**. Elles ont montré que certains conflits préexistaient. C'est un
réflexe à avoir, l'horodatage d'un environnement raconte son histoire.

## 3.5 L'intégrité portée par l'applicatif, pas par le moteur

C'est la décision la plus contre-intuitive du projet, et celle qu'il faut le
mieux comprendre.

Tu as appris que la base garantit l'intégrité : une clé étrangère empêche
d'insérer une ligne orpheline, un `CHECK` empêche un prix négatif, une clé
primaire empêche un doublon. C'est vrai sur PostgreSQL. **Ce n'est pas vrai sur
Snowflake.**

Snowflake accepte la *syntaxe* de ces contraintes, les stocke comme métadonnées
utiles à l'optimiseur, et ne les applique pas à l'écriture. Le test a été fait
et voici ce qu'il donne :

| Contrainte | Appliquée par Snowflake ? |
|---|---|
| `NOT NULL` | **oui** |
| Type et longueur (`VARCHAR(36)`) | **oui** |
| `CHECK` | non |
| `FOREIGN KEY` | non |
| `PRIMARY KEY` | non |
| `UNIQUE` | non |

La règle qui s'en dégage est simple à retenir : **ce qui porte sur la colonne
elle-même est appliqué, ce qui porte sur une relation entre lignes ou entre
tables ne l'est pas.** La raison est architecturale : vérifier une clé
étrangère suppose de consulter une autre table à chaque insertion, ce qui est
incompatible avec un entrepôt conçu pour ingérer massivement en parallèle.

Conséquence directe : sur Snowflake, tes contrôles d'intégrité applicatifs ne
**doublent** pas le moteur, ils le **remplacent**. Si tu ne les écris pas,
personne ne le fait.

Deux choses valent d'être signalées ici.

**Le premier test disait le contraire de la vérité.** Il utilisait un
identifiant de 38 caractères dans une colonne `VARCHAR(36)`. L'insertion était
rejetée sur la longueur, avant même que la clé étrangère ne soit évaluée. Le
test semblait donc prouver que Snowflake applique les clés étrangères, alors
qu'il ne l'avait jamais mise à l'épreuve. Corrigé à 35 caractères, l'insertion
passe, et la clé étrangère n'est effectivement pas appliquée. La ligne
« type et longueur : oui » du tableau ci-dessus est un sous-produit de ce
défaut. Voir TS-08 dans le cahier de recettes.

**Ce constat est désormais surveillé.** Un comportement de fournisseur vérifié
une seule fois est vrai une seule fois. La CI rejoue ces six insertions à
chaque push. Si Snowflake se met un jour à appliquer les clés étrangères, la
chaîne vire au rouge avec un message qui désigne la décision à réexaminer.
C'est la différence entre documenter une hypothèse et la surveiller.

## 3.6 Une frontière de configuration au lieu d'une réécriture

Pendant une partie du projet, la cible Snowflake n'existait pas : le compte
d'essai devait être recréé, et le recréer trop tôt aurait consommé sa fenêtre
de validité pour rien.

Il fallait donc construire vers un entrepôt qui n'existait pas encore. La
contrainte de conception posée à ce moment-là est la suivante : **tout ce qui
vise l'entrepôt doit passer par une frontière de configuration, pour que la
bascule soit un changement de connexion et non une réécriture.**

C'est le rôle d'`entrepot/connexion.py`. Un seul module sait comment on se
connecte. Tout le reste demande une connexion et ignore où elle mène.

Le dividende s'est encaissé deux fois, et la deuxième était imprévue.

La première : la bascule PostgreSQL vers Snowflake s'est faite sans réécrire la
logique de promotion.

La seconde : quand il a fallu faire tourner la recette d'intégration continue
sur une **base jetable**, `verifier_gold.py` et le calcul Snowpark ont
fonctionné sans modification. Pourquoi ? Parce qu'ils écrivent `mart.dim_games`
sans préfixer la base, donc ils suivent `CURRENT_DATABASE()`. Il a suffi de
changer une variable d'environnement.

**Ce qu'il faut en retenir.** Une frontière de configuration n'est pas de la
sur-ingénierie quand elle isole une dépendance externe susceptible de changer.
Elle paie souvent dans un scénario auquel tu n'avais pas pensé en l'écrivant.

## 3.7 Orchestrer du temps réel commence par admettre que ce n'en est pas

Décision de la session 6, et c'est celle où la formulation du problème comptait
plus que la solution.

**Le blocage.** La chaîne batch était orchestrée par Airflow, la chaîne temps
réel ne l'était pas : `steam_producer.py` et `kafka_to_postgres.py` étaient
lancés à la main. Conséquence mesurée le 26/08/2026, la couche Gold accusait
six jours de retard et cinq alertes étaient ouvertes. La supervision faisait
parfaitement son travail ; c'est le pipeline qui ne tournait pas.

L'objection évidente à « il n'y a qu'à mettre un DAG » est juste : on
n'exécute pas une boucle infinie sous un ordonnanceur batch. C'est un
contresens, et c'est ce qui bloquait.

**Le déblocage vient de la source, pas de l'outil.**
`GetNumberOfCurrentPlayers` rend la valeur d'un compteur à l'instant de
l'appel. Il n'y a **pas de flux à consommer**, il y a un capteur à interroger.
Le temps réel de GameLens est un échantillonnage périodique, et un
échantillonnage périodique se planifie sans le moindre contresens.

Le mot « temps réel » venait du Bloc 1 et décrivait un besoin métier, la
fraîcheur. Il avait été lu comme une contrainte d'implémentation.

**Ce que le recadrage débloque immédiatement.** `catchup=False` cesse d'être un
confort pour devenir une correction. Rattraper le run manqué de 03h15
consisterait à interroger Steam maintenant et à estampiller le résultat à
03h15 : on fabriquerait de l'histoire fausse, ce qui est pire que le trou qu'on
prétend combler. Un échantillon manqué est perdu, c'est une propriété de la
donnée et non un défaut du pipeline.

**Cadence.** 15 minutes, choisie contre le seuil de la règle d'alerte
`fraicheur_frequentation`, fixé à 90 minutes. La marge absorbe cinq cycles
manqués avant qu'une alerte ne se déclenche. Un seuil et une cadence qui
s'ignorent finissent toujours par se contredire.

**Kafka reste utile malgré l'enchaînement séquentiel.** Le producteur et le
consommateur tournent l'un après l'autre dans le même run, ce qui peut donner
l'impression que le tampon ne sert plus à rien. Il sert : le consommateur ne
valide son offset qu'après l'écriture en base, donc si PostgreSQL est
indisponible, les messages restent dans Kafka et le run suivant les reprend.

Ce n'est pas resté théorique. Au premier run, le consommateur a rapporté
30 messages là où le producteur venait d'en publier 15 :

```
      collecte       | evenements |      ecrit_le
---------------------+------------+---------------------
 2026-08-27 09:22:12 |         15 | 2026-08-27 09:22:54
 2026-08-20 12:36:09 |         15 | 2026-08-27 09:22:54
```

Quinze événements collectés le 20 août ont été écrits le 27, **sept jours plus
tard**, sans perte ni doublon. Le tampon avait fait exactement son travail
pendant une interruption qu'on n'avait pas organisée.

**Un piège de nommage à connaître.** L'option `--depuis-le-debut` ne signifie
pas « tout relire à chaque fois ». Elle pilote `auto_offset_reset`, que Kafka
ne consulte **que** lorsque le groupe n'a aucun offset validé. Sans elle, la
valeur par défaut `latest` positionne un groupe neuf *après* les messages déjà
présents : le premier run après une remise à zéro du broker publierait quinze
messages, sauterait par-dessus, et n'écrirait rien, en se terminant en succès.
`earliest` est le défaut sûr pour une chaîne qui ne doit rien perdre.

**Résultat.** Cinq alertes ouvertes, refermées d'elles-mêmes en deux
évaluations de règles, sans une seule écriture manuelle dans `speed.alertes`.

---

# 4. Comment le code est organisé, et pourquoi

## La traçabilité des exécutions

Chaque exécution d'un composant écrit une ligne dans `speed.pipeline_runs` :
quel composant, quand, combien de lignes lues et écrites, succès ou échec. Le
mécanisme est un gestionnaire de contexte dans `ingestion/common.py` :

```python
with execution("kafka_to_postgres", logger) as compteurs:
    ...
```

L'intérêt n'est pas le confort. C'est cette table qui permet ensuite de
répondre à « est-ce que ce composant tourne encore ? », qui est la question de
supervision la plus utile et la plus souvent oubliée. Un composant muet et un
composant en panne se ressemblent beaucoup vus de l'extérieur.

## Un point d'entrée tracé, distinct de la fonction nue

Voici un vrai incident qui vaut une leçon durable (INC-007).

Le DAG appelait `collecter()`. Cette fonction fait le travail : elle appelle
l'API et écrit en base. Mais la fonction qui **trace** l'exécution dans
`pipeline_runs`, c'est `collecter_et_tracer()`.

Résultat : quatre collectes réelles ont eu lieu, et une seule ligne de journal
a été écrite. Rien n'a planté. Les données étaient correctes. Seule la
traçabilité était fausse, donc la supervision voyait un composant qui tournait
quatre fois moins souvent qu'en réalité.

**La leçon.** Quand tu as un point d'entrée instrumenté et une fonction nue,
nomme-les de façon à ce que la confusion soit impossible, et vérifie l'effet de
bord attendu, pas seulement le résultat principal. Ici, le test aurait dû
compter les lignes de `pipeline_runs`, pas seulement les lignes collectées.

## La redirection de base, et pourquoi elle existe

### Le problème

`sql/schema_gold_snowflake.sql` nomme la base **en dur, vingt-quatre fois** :

```sql
CREATE OR REPLACE TABLE gamelens.mart.dim_games (...)
```

`CREATE OR REPLACE`, ça veut dire « détruis la table et refais-la vide ». Un
étage d'intégration continue qui aurait rejoué ce script à chaque push aurait
donc vidé la couche de démonstration à chaque push, **sans le moindre message
d'erreur**, puisque l'opération réussit parfaitement.

### La fausse bonne idée

Écrire un second script de schéma, allégé, réservé aux tests. C'est tentant et
c'est une mauvaise idée : la chaîne d'intégration validerait alors une copie, et
le fichier réellement livré ne serait jamais exécuté par personne. On aurait une
CI verte sur du code que l'on ne déploie pas.

### Ce qui a été retenu

Jouer **le script livré**, sans le modifier sur le disque, en remplaçant le nom
de la base au moment de le lire. Une base jetable est créée pour la durée du
run, puis supprimée.

La version naïve de ce remplacement ne marche pas :

```python
contenu.replace("gamelens", "gamelens_ci_42")   # faux
```

Parce que le script contient quatre sortes de noms qui commencent tous par
`gamelens`, et que deux d'entre elles ne doivent surtout pas bouger :

| Dans le script | Ce que c'est | À rediriger ? |
|---|---|---|
| `gamelens.mart.dim_games` | la **base** | oui |
| `CREATE DATABASE gamelens` | la **base** | oui |
| `gamelens_wh` | l'**entrepôt virtuel** | non |
| `gamelens_etl_service` | un **rôle** | non |

L'entrepôt virtuel et les rôles sont des objets **de compte**, pas des objets
**de base**. Ils existent en un seul exemplaire, partagé, et la base jetable
doit les réutiliser tels quels. Le remplacement naïf produirait `gamelens_ci_42_wh`
et `gamelens_ci_42_etl_service`, qui n'existent nulle part.

D'où le motif, qui ne remplace `gamelens` que lorsque c'est un **mot entier** :

```python
MOTIF_BASE = re.compile(r"(?<![A-Za-z0-9_])gamelens(?![A-Za-z0-9_])")
```

Il se lit en trois morceaux :

- `(?<![A-Za-z0-9_])` est un **regard arrière négatif** : le caractère qui
  précède ne doit être ni une lettre, ni un chiffre, ni un souligné ;
- `gamelens` est le texte cherché ;
- `(?![A-Za-z0-9_])` est un **regard avant négatif** : même condition sur le
  caractère qui suit.

Les deux regards ne consomment aucun caractère, ils posent seulement une
condition sur le voisinage. Dans `gamelens_wh`, le caractère suivant est `_` :
la condition échoue, le motif ne correspond pas, le nom reste intact. Dans
`gamelens.mart`, le suivant est `.` : la condition passe.

L'effet est visible sur une seule instruction, où la base est redirigée et le
rôle ne l'est pas :

```
GRANT USAGE ON DATABASE gamelens TO ROLE gamelens_etl_service;
                        ^^^^^^^^         ^^^^^^^^^^^^^^^^^^^^
                        redirige         laisse tel quel
```

### Une question légitime : pourquoi pas simplement `\b` ?

`\bgamelens\b` donne exactement le même résultat, vérification faite : 24
correspondances des deux côtés sur le vrai script. La raison est que le
souligné compte comme un caractère de mot dans une expression régulière, donc
`gamelens_wh` n'a pas de frontière de mot entre le `s` et le `_`.

La forme explicite a été préférée parce qu'elle **dit** quels caractères
comptent, au lieu de s'en remettre à une convention que le lecteur doit
connaître. C'est un choix de lisibilité, pas une nécessité technique, et il
vaut mieux le présenter comme tel.

### Vérifié avant d'être utilisé

Le motif a été éprouvé hors ligne, sur le vrai fichier, **avant tout appel
réseau** : 24 redirections, entrepôt virtuel et rôles intacts. Sur une opération
dont l'échec silencieux détruirait les données de soutenance, essayer d'abord
pour voir n'était pas une option.

---

# 5. La doctrine de test

C'est probablement la partie la plus transférable de ce projet. Les outils
changeront, ces réflexes non.

## Un résultat attendu, pas une absence d'erreur

Règle du cahier de recettes : un test n'est validé que si un **résultat attendu
explicite** a été comparé à un **résultat observé**.

« La commande s'exécute sans erreur » n'est pas un résultat attendu. Un
pipeline qui écrit zéro ligne sans planter satisfait ce critère tout en étant
en panne.

Exemple concret. Le test du calcul distribué ne se contente pas de vérifier que
la requête aboutit. Le jeu de données est construit pour que les résultats
soient calculables de tête, et ils sont écrits **avant** l'exécution :

| Jeu | Moyenne glissante 7 j | Rang dans le genre | Part du genre |
|---|---|---|---|
| Alpha | (200+...+800) / 7 = 500,0 | 1 | 800 / 850 = 94,1 % |
| Beta | 50,0 | 2 | 50 / 850 = 5,9 % |
| Gamma | 10,0 | 1 | 100,0 % |

Si Snowflake changeait sa définition de fenêtre glissante, ce test le verrait.
Un test qui vérifie seulement « ça n'a pas planté » ne le verrait pas.

## Le test négatif

Un contrôle qui ne sait pas échouer ne prouve rien quand il réussit.

C'est facile à énoncer et systématiquement oublié en pratique, parce qu'un
tableau tout vert est satisfaisant et qu'on n'a pas envie de le déranger.

Dans ce projet, chaque dispositif de sécurité a été mis à l'épreuve de son
échec :

- la porte de fraîcheur du DAG a été testée sur une journée sans données. Elle
  a correctement interrompu la promotion ;
- le moteur d'alertes a été testé sur une plateforme en panne, pas seulement
  sur une plateforme saine ;
- les contrôles d'intégrité de l'entrepôt sont exécutés deux fois dans la
  recette : une fois sur données saines, où ils doivent tous passer, une fois
  sur données corrompues, où le run **échoue s'ils passent** ;
- le garde-fou qui protège la base de démonstration a été testé en le pointant
  délibérément sur elle.

Le troisième cas a une élégance particulière. Les données corrompues ne sont
pas fabriquées pour l'occasion : ce sont exactement celles que Snowflake vient
de laisser entrer à l'étape précédente, faute d'appliquer les contraintes.
Quatre contraintes ignorées par le moteur, quatre violations rattrapées par le
filet applicatif. La correspondance est exacte et tient en dix lignes de sortie.

## Les quatre fois où un test a menti

Ce sont les cas les plus instructifs du projet.

**Une assertion par comptage.** L'étage d'intégration vérifiait que le schéma
contenait le bon *nombre* d'objets. Elle a cassé une première fois parce que
`information_schema.tables` inclut les vues. Elle a cassé une seconde fois
parce que la supervision avait légitimement ajouté une table et six vues.
Remplacée par une vérification d'objets **nommés** via `to_regclass`.

La formule à retenir : *une assertion qu'on ajuste à chaque évolution ne teste
plus rien, elle enregistre.*

**Un test qui prouvait le contraire de la vérité.** Le test de clé étrangère
sur Snowflake, décrit en 3.5. L'identifiant était trop long, le rejet venait de
la longueur, et on en concluait l'inverse de la réalité.

**Un composant qui traçait mal ses exécutions.** INC-007, décrit en section 4.

**Un garde-fou inatteignable.** Le plus insidieux, parce qu'il n'a jamais
échoué. La recette d'intégration refuse de viser la base de démonstration. Le
refus était écrit. Mais la fonction qui choisit le nom de base écartait
*discrètement* les noms protégés en retombant sur un nom généré. Le garde-fou
ne recevait donc jamais rien à refuser.

Lancé sur la base protégée, le test a rendu un run parfaitement vert et un code
de sortie 0. Le comportement était sûr, mais il mentait. Deux précautions
raisonnables prises séparément s'annulaient l'une l'autre, et aucune relecture
de code ne l'aurait signalé puisque les deux morceaux sont corrects.

**Ce qu'il faut en retenir.** Un test qui échoue ne désigne pas nécessairement
le système testé. Dans trois de ces quatre cas, le défaut était dans le test.
Et un test qui réussit ne prouve pas qu'il teste quelque chose.

---

# 6. Les incidents, et la méthode

Huit incidents sont documentés. Un seul mérite d'être raconté en détail, parce
qu'il illustre une méthode plutôt qu'une astuce.

## INC-004 : quand le message d'erreur désigne un innocent

**Symptôme.**

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 103
```

Levée à l'intérieur de `psycopg2.connect()`. Prise au premier degré, elle
oriente vers un problème d'encodage du code, hypothèse d'autant plus crédible
que le projet est stocké sous un chemin contenant des accents.

**Cause réelle**, en trois maillons :

1. un service PostgreSQL 18 **natif** tourne sur le poste et retient déjà le
   port 5432 ;
2. Docker publie le port **sans erreur visible** et l'affiche comme si tout
   allait bien. Rien dans son état ne signale le conflit ;
3. l'application se connecte donc au PostgreSQL natif, qui ne connaît pas
   l'utilisateur et répond « authentification par mot de passe échouée », en
   français et en cp1252. psycopg2 tente de décoder ce message en UTF-8 et
   échoue **avant** d'avoir pu remonter l'erreur d'authentification.

L'erreur utile existait, elle était parfaitement explicite, et elle a été
détruite par le mécanisme censé la transmettre.

**L'étape qui a tranché.** Pas une lecture de documentation, une déduction.
L'image du conteneur est une Alpine en locale C : elle ne peut produire que des
messages en anglais ASCII. Un message d'erreur en français accentué était donc,
à lui seul, la preuve que l'interlocuteur n'était pas le conteneur. La langue du
message d'erreur a servi d'empreinte pour identifier le serveur.

**La solution.** Publier le conteneur sur le port hôte **5433**, port interne
inchangé. Les deux serveurs coexistent. Le commentaire dans `docker-compose.yml`
explique pourquoi ce n'est pas 5432, sans quoi un lecteur futur corrigerait
l'anomalie apparente et réintroduirait l'incident.

**La leçon opérationnelle.** Méfie-toi d'une erreur technique de bas niveau
(encodage, sérialisation, analyse syntaxique) qui surgit au milieu d'une
opération d'infrastructure. C'est souvent le linceul d'une erreur fonctionnelle
plus haute, pas le problème lui-même.

## Les sept autres, en une ligne chacune

| ID | Ce qui s'est passé | Ce qu'on en retient |
|---|---|---|
| INC-001 | Airflow ne tourne pas nativement sous Windows, mais `import airflow` réussit | Un import qui passe ne prouve pas qu'un composant fonctionne |
| INC-002 | Git Bash réécrit les chemins de volume Docker. L'hypothèse « c'est l'accent dans le chemin » était fausse | Change une variable à la fois : le même montage depuis PowerShell a disculpé les accents |
| INC-003 | Compte Snowflake à recréer, recréation volontairement différée | Un compte d'essai a une durée de vie : ne l'allume pas avant d'en avoir l'usage |
| INC-005 | Le DAG aurait dupliqué ses lignes au rejeu, faute de contrainte d'unicité | Détecté sans plantage, en cherchant à écrire un `ON CONFLICT` et en constatant qu'il n'avait rien où s'ancrer |
| INC-006 | `logical_date` vaut `None` sur un lancement manuel en Airflow 3 | Ne suppose pas qu'une valeur fournie par le cadre est toujours présente |
| INC-007 | Quatre collectes réelles, une seule ligne de journal | Vérifie l'effet de bord attendu, pas seulement le résultat principal |
| INC-008 | Une panne de broker ne laissait aucune trace en échec : l'exception précédait l'ouverture du journal | Un mécanisme d'observabilité correct ne sert à rien s'il n'est pas atteint |

## Ce que la grille attend d'un incident

Utile à connaître même hors certification, parce que c'est ce qu'on te
demandera en poste. Un incident correctement traité comporte quatre rubriques,
et c'est la troisième qu'on oublie systématiquement :

1. la **nature** du problème ;
2. les **actions** envisagées selon les scénarios, avec leur coût et leur
   risque, y compris celles qu'on a écartées et pourquoi ;
3. la **communication aux parties prenantes** : qui prévenir, quand, par quel
   canal ;
4. le **résultat** obtenu et sa vérification.

---

# 7. Ce qui manque, et ce que ça coûterait

Cette section est aussi importante que les précédentes. Un projet dont on ne
sait pas nommer les limites est un projet qu'on ne comprend pas.

## Résolu le 27/08/2026 : l'ingestion est désormais planifiée

Cette section listait « rien ne planifie l'ingestion temps réel » comme le trou
le plus visible du projet. Il est comblé, voir la décision 3.7. Le DAG
`gamelens_ingestion_temps_reel` tourne toutes les 15 minutes, la chaîne est
autonome de bout en bout, et les cinq alertes qui étaient ouvertes se sont
refermées d'elles-mêmes.

La mention reste ici plutôt que d'être effacée : l'écart entre le moment où le
manque a été constaté, le 26/08, et celui où il a été comblé, le 27/08, fait
partie de l'histoire du projet.

Ce qui subsiste, et qui est plus modeste : le DAG collecte, il ne **surveille**
pas la collecte en continu. Entre deux cycles, une panne de quatorze minutes
passe inaperçue jusqu'à l'évaluation suivante des règles. C'est acceptable pour
un échantillonnage au quart d'heure, ça ne le serait pas pour une chaîne
d'événements.

## L'utilisateur de service tourne en ACCOUNTADMIN

`GAMELENS_SERVICE` dispose du rôle `ACCOUNTADMIN` sur Snowflake, y compris dans
la chaîne d'intégration continue. Sur un projet qui fait un argument de la
séparation des rôles, et qui a vérifié le cloisonnement côté PostgreSQL, c'est
une incohérence.

La justification circonstancielle existe : la recette crée et supprime des
bases, ce qui demande des droits élevés. Mais `ACCOUNTADMIN` va bien au-delà de
ce qui est nécessaire, et le principe du moindre privilège dit qu'on aurait dû
créer un rôle dédié avec `CREATE DATABASE` et rien de plus.

## Les volumes sont ceux d'un laboratoire

15 jeux, 30 faits de popularité, 75 faits tarifaires. Tout tient en mémoire.
Les questions qui se posent à l'échelle ne se sont donc jamais posées :

- **partitionnement et regroupement** : `CLUSTER BY (day)` est déclaré sur la
  table de faits, mais sur ce volume il ne sert à rien et on ne peut pas
  démontrer qu'il sert à quelque chose ;
- **données en retard** : que faire d'un relevé qui arrive avec deux jours de
  retard, alors que l'agrégat du jour est déjà calculé ? Non traité ;
- **reprise historique** : recalculer six mois d'agrégats suppose une stratégie
  de traitement par lots que le DAG actuel n'a pas ;
- **évolution de schéma** : le jour où Steam ajoute un champ, rien n'est prévu.

## Autres manques assumés

- **La couche Bronze n'existe pas physiquement.** L'architecture la décrit sur
  S3, mais le projet passe de l'API à Silver. En cas de bug de transformation,
  on ne peut pas recalculer.
- **Un seul environnement.** Pas de séparation développement / recette /
  production. La chaîne d'intégration crée bien une base jetable, ce qui en est
  une ébauche.
- **La base de métadonnées Airflow partage l'instance PostgreSQL de Silver.**
  Choix d'échelle assumé, à ne pas reproduire en production : une saturation de
  l'un affecterait l'autre.
- **Mots de passe de développement en clair** dans le dépôt (`devlocal_*`,
  `admin/admin`). Acceptable parce qu'ils ne donnent accès qu'à des conteneurs
  locaux, mais c'est une habitude à ne pas prendre.
- **dbt est installé, pas encore branché.** Les contrôles d'intégrité sont en
  Python dans `verifier_gold.py` alors qu'ils devraient être des tests dbt
  (`not_null`, `unique`, `relationships`, `expression_is_true`).

---

# 8. Ce que je retiendrais à ta place

Huit principes qui survivront aux outils employés ici.

**1. Un composant qui réussit sans rien faire est un composant en panne.**
C'est le mode de défaillance le plus courant et le plus coûteux en données,
parce qu'il est silencieux. Conçois tes vérifications autour de « combien de
lignes ont bougé », pas autour de « est-ce que ça a planté ».

**2. Rends le rejeu inoffensif plutôt qu'impossible.** Contrainte d'unicité,
insertion idempotente, ordre de validation réfléchi. C'est presque toujours
plus simple et plus robuste que le mécanisme sophistiqué qui prétend garantir
l'unicité du traitement.

**3. Teste ce que ton dispositif rate, pas seulement ce qu'il rapporte.** Un
système de supervision se valide en cassant la plateforme, pas en la regardant
tourner. Un contrôle qui ne sait pas échouer ne prouve rien.

**4. Interroge le système sur ce qu'il est, plutôt que de lui supposer une
forme.** Face à trois erreurs successives sur des noms de colonnes Snowflake,
ce qui a débloqué la situation n'est pas la quatrième tentative de deviner :
c'est d'avoir listé les colonnes réellement disponibles. Même chose pour les
contraintes, vérifiées empiriquement plutôt que lues dans la documentation.

**5. Une assertion qu'on ajuste à chaque évolution ne teste plus rien.** Si tu
te surprends à corriger le nombre attendu dans un test après chaque
modification légitime, ton test n'est pas une assertion, c'est un journal.
Vérifie des objets nommés, pas des comptages.

**6. Un conflit de dépendances qui résiste est un signal d'architecture.** Ces
deux choses n'ont pas vocation à cohabiter. Isole-les au lieu de négocier des
versions.

**7. Documente ce qui a l'air d'une anomalie.** Le port 5433 ressemble à une
erreur. Sans le commentaire qui explique pourquoi ce n'est pas 5432, quelqu'un
le « corrigera » et réintroduira l'incident. La documentation la plus utile est
celle qui protège une décision contre-intuitive.

**8. Une hypothèse d'architecture vérifiée une seule fois est une hypothèse qui
périme.** Le comportement des contraintes Snowflake était vrai le jour du test.
Le transformer en test de non-régression est ce qui sépare une architecture
documentée d'une architecture surveillée.

---

# Pour aller plus loin dans le dépôt

| Ce que tu cherches | Où |
|---|---|
| Les incidents au format complet | `docs/journal_incidents.md` |
| Les surprises, fausses pistes, arbitrages | `docs/observations.md`, 46 entrées |
| Les tests et leurs résultats réels | `docs/cahier_recettes.md`, 32 cas |
| Les commandes réellement exécutées | `docs/commandes_successives.md` |
| L'état d'avancement et les pièges d'environnement | `CLAUDE.md` |
| Le pipeline temps réel | `ingestion/` |
| L'orchestration | `dags/` |
| Tout ce qui vise Snowflake | `entrepot/` |
| La supervision | `supervision/` et `sql/schema_supervision.sql` |
| La chaîne d'intégration continue | `.github/workflows/ci.yml`, six étages |

Dernière mise à jour : 27/08/2026, fin de session 6.
