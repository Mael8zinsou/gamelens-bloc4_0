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
        ingestion/steam_producer.py          <- archive, PUIS publie
              |                  |
              v                  v
  bronze.reponses_brutes    Apache Kafka (mode KRaft)   <- tampon durable
  tout appel, abouti ou     gamelens.steam.player_count
  non, jamais modifie                |
                                     v
                     ingestion/kafka_to_postgres.py     <- consomme et ecrit
                                     |
                                     v
                     PostgreSQL, couche Silver speed    <- la donnee recente
                                     |
        +----------------------------+-------------+
        |                                          |
   DAG promotion_gold                   DAG promotion_snowflake
     quotidien, 02h30 UTC                 quotidien, 03h00 UTC
        |                                          |
        v                                          v
   PostgreSQL, couche Gold              Snowflake, couche Gold
   prototype et repli                   cible de production
                                        dim_games, dim_stores,
                                        fact_prices,
                                        fact_popularity_history
```

**Bronze n'y figurait pas jusqu'au 02/09/2026**, alors que la couche existe
depuis le 27/08 et que le paragraphe suivant la décrit longuement. Un schéma qui
omet une couche entière la fait disparaître pour qui lit vite, et c'est
exactement le reproche fait ci-dessous à la version précédente, en plus discret.
Note aussi l'ordre, qui n'est pas décoratif : on archive **avant** d'exploiter,
sinon on ne conserve que ce qu'on a su lire.

**Ce schéma a été faux pendant onze jours, et l'histoire vaut mieux que le
schéma.** Jusqu'au 31/08/2026 il montrait l'orchestrateur alimentant directement
Snowflake, sans mentionner la couche PostgreSQL. C'était l'architecture voulue,
pas celle qui tournait. Dans les faits, seul le prototype PostgreSQL était promu
automatiquement ; la couche Snowflake, celle que l'architecture désigne comme la
cible, était chargée à la main et n'avait pas bougé depuis le 20/08.

Retiens surtout la façon dont c'est passé inaperçu. Le DAG s'appelait
`gamelens_promotion_gold`, l'indicateur de supervision s'appelle
`v_indicateur_gold`, et son commentaire dans la base annonçait « fraîcheur de
l'entrepôt ». Trois noms exacts pris séparément, et un contresens une fois lus
ensemble : « Gold » désignait ici la couche PostgreSQL, alors que « l'entrepôt »
désigne partout ailleurs Snowflake. Il n'y a pas eu de bug. Il y a eu un
vocabulaire qui recouvrait deux choses.

Depuis le 31/08, un second DAG promeut vers Snowflake, une demi-heure après le
premier pour que les deux couches portent la même journée. Deux DAG et non un
seul, délibérément : Snowflake est un service tiers facturé dont une
indisponibilité n'a aucune raison d'emporter la promotion locale.

Et la correction a coûté une panne, ce qui est instructif. Monter le répertoire
`entrepot/` dans les conteneurs de l'orchestrateur y a rendu visible un fichier
nommé `connexion.py`. Or `connexion` est aussi le nom d'une bibliothèque
qu'Airflow utilise pour son authentification. Notre fichier l'a masquée,
l'interface web a cessé de démarrer, et rien ne l'a signalé pendant douze
minutes. La leçon tient en une phrase : **ajouter un répertoire au chemin de
recherche des modules n'est pas une opération qui ne fait qu'ajouter.** Voir
INC-009.

## Pourquoi trois couches, et pas une

C'est l'architecture **Medallion**, et son intérêt n'est pas esthétique.

**Bronze**, c'est la donnée brute telle qu'elle est arrivée, jamais modifiée.
Son utilité est unique et suffisante : le jour où tu découvres un bug dans ta
transformation, tu peux tout recalculer. Si tu as écrasé la source, tu ne peux
rien recalculer du tout. C'est une assurance, et comme toute assurance elle ne
sert que le jour où ça va mal.

Ici, c'est `bronze.reponses_brutes`, une table PostgreSQL et non le stockage
objet annoncé au Bloc 1. Elle archive **tout appel, abouti ou non**, ce second
point étant le moins évident et le plus utile : voir la décision 3.8.

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

# 3. Les neuf décisions qui structurent tout le reste

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
personne ne le fait. La section 3.9 raconte comment ces contrôles ont fini par
être écrits deux fois, en Python et en dbt, et pourquoi ce n'est pas un doublon.

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

C'est le rôle d'`entrepot/connexion_snowflake.py`. Un seul module sait comment on se
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

## 3.8 Archiver ce qu'on ne sait pas encore vouloir

Décision de la session 6, et celle dont l'argument est le moins intuitif.

**Le constat.** L'architecture du Bloc 1 déclarait une couche Bronze. Elle
n'existait pas. Regarde ce que faisait le producteur :

```python
corps = reponse.json().get("response", {})
if corps.get("result") != 1 or "player_count" not in corps:
    return None
return int(corps["player_count"])
```

La réponse de Steam est lue, un entier en est extrait, et **le reste est jeté
dans la ligne même qui l'exploite**. Une ligne plus loin, la réponse d'origine
n'existe plus nulle part, même pas en mémoire.

**L'objection habituelle**, et elle est raisonnable : à quoi bon conserver une
réponse dont on n'exploite qu'un champ, alors qu'on peut toujours réinterroger
l'API ?

**La réponse tient en trois mots : la source n'est pas rejouable.** Personne ne
te dira jamais combien de joueurs étaient connectés mardi dernier, ni à quel
prix un jeu était vendu ce jour-là. Un défaut de transformation découvert dans
trois mois aurait donc corrompu trois mois d'historique définitivement, sans
aucun chemin de réparation. C'est le seul endroit du projet où une erreur
serait irrattrapable ; tout le reste se reconstruit.

**Pourquoi Kafka ne suffisait pas**, alors qu'il retient les messages 168
heures et que la session 6 a justement démontré une récupération à sept jours.
Deux raisons : il transporte le message **déjà transformé**, pas la réponse
d'origine, et sept jours est une fenêtre de rétention, pas un archivage. Il
donne un rejeu de sept jours au niveau Silver. C'est utile, ça a servi, et ce
n'est pas la même chose.

**Ce qui est archivé, et l'ordre compte.** Chaque appel est écrit en Bronze
**avant** toute exploitation. Archiver après reviendrait à ne conserver que ce
qu'on a su lire.

Et surtout, **les appels qui échouent sont archivés aussi**. C'est la moitié
la moins évidente et probablement la plus utile. Avant, une réponse
inexploitable ne produisait qu'un `logger.warning` puis disparaissait. Or
« la source a répondu pour cet identifiant à cet instant, mais sans donnée
utilisable » est précisément le signal d'un jeu retiré du catalogue ou d'une
API qui se dégrade. La contrainte du schéma l'impose :

```sql
CONSTRAINT ck_reponses_brutes_motif
    CHECK (exploitable OR motif_rejet IS NOT NULL)
```

Sans elle, le cas le plus intéressant serait aussi le moins documenté.

**Une archive ne se modifie pas.** Contrairement au schéma `speed`, aucun
`UPDATE` n'est accordé sur Bronze, pas même à `etl_service`. Le seul droit
d'écriture est l'ajout. Ce n'est pas un oubli de droits, c'est ce qui distingue
une archive d'un cache, et c'est testé : la matrice de sécurité tente
l'opération interdite et vérifie le refus.

**Ce que ça a révélé immédiatement.** Première réponse tarifaire archivée :

```json
{"price_overview": {
    "final": 2450, "initial": 2450, "currency": "EUR",
    "final_formatted": "24,50€", "initial_formatted": "",
    "discount_percent": 0
}}
```

`final_formatted` et `initial_formatted` étaient jetés depuis le début. Ils ne
servent à rien aujourd'hui. Le jour où une question se posera sur l'affichage
régional d'un prix, ils auraient manqué, et personne n'aurait su qu'ils avaient
existé. C'est le renversement propre à Bronze : **on ne conserve pas ce dont on
a besoin, on conserve ce dont on ignore encore avoir besoin.** Tant qu'on
n'archive pas, la question « qu'est-ce qu'on perd ? » est structurellement
impossible à poser.

**Le coût, mesuré et pas estimé.** L'objection réflexe à une couche Bronze est
le volume. 78 octets par relevé de fréquentation, 238 par relevé tarifaire,
soit environ 114 Ko par jour et **41 Mo par an** à la cadence en place. La
leçon n'est pas « c'est petit », c'est qu'une objection de volume formulée sans
mesure ne vaut rien, et qu'il suffisait de trois minutes pour la trancher.

**Ce qui manque encore** : une politique de conservation. Rien ne purge cette
table aujourd'hui. À 41 Mo par an ce n'est pas urgent, mais une couche qui
grossit sans règle finit par en imposer une dans l'urgence.

## 3.9 Deux filets valent mieux qu'un, à condition de vérifier qu'ils s'accordent

Décision de la session 8, et suite directe de la 3.5. Relis-la d'abord : elle
établit que sur Snowflake, les contrôles applicatifs ne doublent pas le moteur,
ils le remplacent.

**Le constat de départ n'était pas technique, il était documentaire.**
L'architecture du Bloc 1 affirmait, au présent, que l'intégrité de la couche
Gold reposait sur des tests dbt nommément cités. Les commentaires de colonnes du
schéma Snowflake le répétaient, colonne par colonne : « valeur contrôlée par
test dbt `accepted_values` ». Les dépendances `dbt-core` et `dbt-snowflake`
étaient épinglées et installées à chaque exécution de la chaîne d'intégration.
Le `.gitignore` prévoyait déjà `dbt/target/`.

Le répertoire `dbt/` était vide.

Retiens le mode de défaillance, il est plus intéressant que l'oubli lui-même :
**un composant annoncé mais jamais construit laisse plus de traces qu'un
composant dont personne n'a parlé**, et ces traces le font passer pour fait.
Tous les signaux qu'on regarde d'ordinaire pour savoir si une brique existe
étaient au vert. Le seul qui aurait tranché est celui qui manquait : l'exécuter.

### Ce que dbt fait, et surtout ce qu'il ne fait pas

dbt transforme et teste **à l'intérieur** de l'entrepôt. Il n'a pas d'étape
d'extraction : il ne sait pas aller chercher de la donnée ailleurs pour la
poser dans Snowflake. C'est le T de ELT, pas le E ni le L.

Cela a une conséquence directe sur le périmètre. La promotion vers la couche
Gold lit PostgreSQL et téléverse vers Snowflake : dbt ne saurait pas la faire.
Elle reste donc en Snowpark, et dbt se voit confier deux choses.

**Les sources.** Une source, pour dbt, est une table qu'il **lit sans l'avoir
construite**. Les quatre tables Gold sont déclarées ainsi, et les contraintes
que Snowflake n'applique pas leur sont accrochées sous forme de tests. Vingt-neuf
au total. Chaque `relationships` est très exactement une clé étrangère écrite
dans le schéma et jamais vérifiée par le moteur.

C'est la distinction à retenir de tout ce paragraphe : **dbt teste ce que
Snowpark construit, sans lui prendre la propriété de quoi que ce soit.** Rien de
ce qui marchait n'a été déplacé.

**Un seul modèle**, la vue de tableau de bord. Elle vivait au milieu d'un
fichier SQL contenant vingt-quatre `CREATE OR REPLACE TABLE` : la corriger
imposait soit d'en extraire l'instruction à la main, soit de rejouer un script
qui aurait détruit toute la couche de démonstration. En modèle dbt, elle se
reconstruit seule. Elle passe en outre par une référence symbolique au lieu de
nommer la base en dur, ce qui la rend enfin testable sur une base jetable.

### La vraie difficulté n'était pas d'écrire les tests

Elle était de décider quoi faire des huit contrôles Python qui existaient déjà.

L'argument pour tout basculer sur dbt est solide : deux mécanismes qui vérifient
les mêmes faits finissent par diverger, et le jour où ils divergent, l'un des
deux est faux sans que rien ne le signale. C'est un piège classique, et le
projet l'avait déjà rencontré ailleurs, sur deux documents qui décrivaient la
même procédure dans un ordre différent.

L'arbitrage a été de garder les deux, mais de rendre leur accord **testé plutôt
que déclaré**. La recette automatisée insère volontairement quatre violations
que Snowflake laisse passer, puis exécute les deux filets sur ce même jeu de
données fautif et exige que les deux tombent. Si l'un rattrape une violation que
l'autre laisse passer, la recette s'arrête au lieu de laisser la divergence
s'installer.

### Ce que ce test a appris, et que personne n'avait prévu

Sur les mêmes violations, le filet applicatif en rattrape **quatre**, dbt en
rattrape **cinq**.

Le cinquième est le test posé sur la vue. Un doublon sur `(jeu, jour)` dans une
table de faits ne duplique pas seulement une ligne de faits : il duplique
**chaque journée au travers de la jointure** de la vue. Les contrôles Python
n'interrogent que les tables et ne peuvent pas voir ce gonflement.

Autrement dit, le test destiné à surveiller la coexistence des deux filets a
démontré au passage qu'ils n'étaient pas redondants. La décision de les garder
tous les deux était bonne, pour une raison que personne n'avait su formuler en
la prenant.

### Deux pièges à connaître, parce qu'ils sont silencieux

Sur Snowflake, remplacer une vue **détruit ses privilèges** et **efface son
commentaire**. Aucune erreur n'est levée dans les deux cas.

Le premier se manifesterait bien plus tard, sous la forme d'un tableau de bord
vide : la vue existe, elle est correcte, elle est simplement devenue invisible
pour le seul rôle qui la consultait. Le second ferait échouer **un autre étage**
de la chaîne d'intégration, celui qui compare le dictionnaire de données généré
au catalogue réel, sur un message parlant du dictionnaire et jamais de dbt.

Les deux sont donc vérifiés après chaque reconstruction de la vue. Et, fidèlement
à la doctrine de test de la section 5, les deux vérifications ont été éprouvées
en retirant la configuration correspondante pour confirmer qu'elles savent
échouer. Sans la configuration de droits, un seul bénéficiaire reste :
le compte d'administration.

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

Neuf incidents sont documentés. Un seul mérite d'être raconté en détail, parce
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

## Les huit autres, en une ligne chacune

| ID | Ce qui s'est passé | Ce qu'on en retient |
|---|---|---|
| INC-001 | Airflow ne tourne pas nativement sous Windows, mais `import airflow` réussit | Un import qui passe ne prouve pas qu'un composant fonctionne |
| INC-002 | Git Bash réécrit les chemins de volume Docker. L'hypothèse « c'est l'accent dans le chemin » était fausse | Change une variable à la fois : le même montage depuis PowerShell a disculpé les accents |
| INC-003 | Compte Snowflake à recréer, recréation volontairement différée | Un compte d'essai a une durée de vie : ne l'allume pas avant d'en avoir l'usage |
| INC-005 | Le DAG aurait dupliqué ses lignes au rejeu, faute de contrainte d'unicité | Détecté sans plantage, en cherchant à écrire un `ON CONFLICT` et en constatant qu'il n'avait rien où s'ancrer |
| INC-006 | `logical_date` vaut `None` sur un lancement manuel en Airflow 3 | Ne suppose pas qu'une valeur fournie par le cadre est toujours présente |
| INC-007 | Quatre collectes réelles, une seule ligne de journal | Vérifie l'effet de bord attendu, pas seulement le résultat principal |
| INC-008 | Une panne de broker ne laissait aucune trace en échec : l'exception précédait l'ouverture du journal | Un mécanisme d'observabilité correct ne sert à rien s'il n'est pas atteint |
| INC-009 | Monter `entrepot/` dans les conteneurs Airflow y a rendu visible un `connexion.py` qui a masqué la bibliothèque `connexion` dont Airflow se sert pour s'authentifier. Interface web indisponible 12 minutes | Ajouter un répertoire au `PYTHONPATH` n'ajoute pas seulement, ça peut masquer. Et rien ne l'a signalé : la supervision regarde la chaîne de production, pas l'écran qui sert à la regarder |

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

## Résolu le 27/08/2026 : dbt est branché

Cette section listait « dbt est installé, pas encore branché » comme une
faiblesse. Elle est levée, voir la décision 3.9 : vingt-neuf contrats
déclaratifs couvrent désormais les contraintes que Snowflake n'applique pas, et
la chaîne d'intégration les rejoue à chaque poussée, sur données saines puis sur
données volontairement corrompues.

La mention reste ici, comme la précédente. Ce qui est instructif dans ce cas
précis, ce n'est pas le travail accompli, c'est la durée pendant laquelle
l'écart est passé inaperçu : l'architecture annonçait ces tests depuis le
Bloc 1, les commentaires du schéma les nommaient colonne par colonne, et les
dépendances étaient installées à chaque exécution de la chaîne. Tout avait l'air
fait.

## Rien ne porte l'alerte jusqu'à un humain

C'est l'écart le plus important entre cette plateforme et une plateforme
réellement exploitée. C'est aussi celui qu'il vaut mieux énoncer soi-même que se
faire signaler.

Le moteur d'alertes fonctionne, et son cycle de vie est complet : six règles,
déclenchement sur seuil, non-duplication tant que la condition dure, fermeture
automatique au retour à la normale. Tout est testé, y compris en négatif, sur
une plateforme délibérément cassée.

Ce qui manque est l'étage suivant. Aucun canal de notification n'est branché :
ni courriel, ni webhook, ni astreinte. Les alertes sont **persistées** dans
`speed.alertes`, et c'est tout. Une alerte que personne ne lit vaut exactement
une alerte qui ne s'est pas déclenchée.

La mesure le dit mieux qu'un argument. En août, une rupture de fraîcheur a été
**détectée en 90 minutes**, ce qui est bon, et elle est restée ouverte
**6 jours et 20 heures**. Le délai de détection n'est pas le problème. Le délai
de réaction l'est, et il l'est parce qu'il n'y a personne au bout du fil.

Le corollaire est plus vicieux : **la supervision ne se surveille pas
elle-même**. Si le DAG `gamelens_supervision` s'arrête, plus aucune alerte n'est
produite, et un tableau sans alerte ressemble trait pour trait à un tableau dont
le producteur d'alertes est mort. C'est le principe 1 de la section 8, celui du
composant qui réussit sans rien faire, retourné contre l'outil même qui devrait
le détecter.

Ce que ça coûterait à corriger : peu de chose. Un canal de notification est une
heure de travail, pas une difficulté d'architecture. C'est précisément pour ça
que l'absence mérite d'être racontée : elle ne mesure pas un obstacle technique,
elle mesure ce qu'on laisse tomber quand on construit seul et qu'on est aussi le
seul lecteur du tableau de bord.

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

15 jeux, et des faits qui se comptent en dizaines. Dernière mesure, le
31/08/2026 : côté PostgreSQL 45 faits de popularité et 120 faits tarifaires ;
côté Snowflake 60 et 165, répartis sur quatre journées. L'écart entre les deux
couches n'est pas une anomalie et vaut d'être compris : la promotion PostgreSQL
traite une journée par run, la promotion Snowpark rejoue tout l'historique
disponible par `MERGE`. Les deux portent la même journée la plus récente, pas la
même profondeur.

Tout cela tient en mémoire. Les questions qui se posent à l'échelle ne se sont
donc jamais posées :

- **partitionnement et regroupement** : `CLUSTER BY (day)` est déclaré sur la
  table de faits, mais sur ce volume il ne sert à rien et on ne peut pas
  démontrer qu'il sert à quelque chose ;
- **données en retard** : que faire d'un relevé qui arrive avec deux jours de
  retard, alors que l'agrégat du jour est déjà calculé ? Non traité ;
- **reprise historique** : recalculer six mois d'agrégats suppose une stratégie
  de traitement par lots que le DAG actuel n'a pas ;
- **évolution de schéma** : le jour où Steam ajoute un champ, rien n'est prévu.

## Autres manques assumés

- **La couche Bronze existe depuis le 27/08, mais pas sur S3.** C'est une table
  PostgreSQL, `bronze.reponses_brutes`. L'écart avec l'architecture annoncée au
  Bloc 1 est assumé : le support change, la propriété recherchée est la même.
  Elle n'a pas de politique de conservation, et croît d'environ 41 Mo par an.
- **Un seul environnement.** Pas de séparation développement / recette /
  production. La chaîne d'intégration crée bien une base jetable, ce qui en est
  une ébauche.
- **La base de métadonnées Airflow partage l'instance PostgreSQL de Silver.**
  Choix d'échelle assumé, à ne pas reproduire en production : une saturation de
  l'un affecterait l'autre.
- **Mots de passe de développement en clair** dans le dépôt (`devlocal_*`,
  `admin/admin`). Acceptable parce qu'ils ne donnent accès qu'à des conteneurs
  locaux, mais c'est une habitude à ne pas prendre. Et cette acceptabilité
  reposait sur une prémisse fausse jusqu'au 07/09/2026 : écrits `- "5433:5432"`,
  les ports étaient publiés sur toutes les interfaces réseau et non sur la seule
  boucle locale. Retiens le mécanisme plus que le cas : **un arbitrage de
  sécurité formulé au conditionnel doit avoir un contrôle qui vérifie sa
  condition**, sinon c'est un souhait. La feuille de route de ce projet avait
  même écrit la condition, « toute exposition réseau », sans jamais la relire.
- **Le compte Snowflake expire.** Compte étudiant, 120 jours de validité depuis
  le 20/08/2026, donc une fin attendue à la mi-décembre. Rien n'est prévu pour
  ce jour-là : la couche Gold cible disparaîtra et il ne restera que le
  prototype PostgreSQL. C'est le seul point de vigilance réellement bloquant du
  projet, et c'est une date qui contraint, pas un budget : la consommation
  mesurée est d'une vingtaine de crédits sur les 400 accordés.
- **`dim_games.critical_tier` est vide**, alors que le commentaire de la colonne
  annonce qu'elle est dérivée par un modèle dbt. Ce modèle n'existe pas, et il
  ne pourrait rien dériver aujourd'hui puisque la note critique dont il
  partirait est vide elle aussi, faute de catalogue RAWG branché. C'est le même
  écart entre l'annoncé et le réel que celui décrit en 3.9, en plus petit, et
  il est signalé ici plutôt que corrigé en silence.

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
| Les surprises, fausses pistes, arbitrages | `docs/observations.md`, 75 entrées |
| Les tests et leurs résultats réels | `docs/cahier_recettes.md`, 55 cas, tous PASS |
| Les commandes réellement exécutées | `docs/commandes_successives.md` |
| Ce qu'il faut faire tourner, surveiller et purger | `docs/feuille_route_exploitation.md` |
| L'état d'avancement et les pièges d'environnement | `CLAUDE.md` |
| Le pipeline temps réel | `ingestion/` |
| L'orchestration | `dags/` |
| Tout ce qui vise Snowflake | `entrepot/` |
| La supervision | `supervision/` et `sql/schema_supervision.sql` |
| La chaîne d'intégration continue | `.github/workflows/ci.yml`, six étages |

Dernière mise à jour : 02/09/2026, fin de session 12. Les chiffres cités
(incidents, observations, cas de recette, volumes) sont datés : ils étaient
exacts au jour dit, et les volumes croissent chaque nuit.
