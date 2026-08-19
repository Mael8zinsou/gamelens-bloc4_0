# Observations de session, GameLens Bloc 4

Ce document recueille ce que le travail fait apparaître en chemin : surprises,
fausses pistes, arbitrages pris sur le vif, détails qui n'ont pas leur place
dans un livrable mais qui expliquent pourquoi le projet a la forme qu'il a.

Il se distingue de deux voisins :

- `docs/journal_incidents.md` ne retient que les incidents, dans un format
  imposé par la grille du C4.4.2 (nature, scénarios, communication, résultats) ;
- `docs/commandes_successives.md` retient le geste technique, pas le raisonnement.

Ici, c'est le raisonnement et l'anecdote. Beaucoup de ces observations sont de
la matière directement réutilisable pour les 15 minutes d'échange avec le jury,
qui portent rarement sur ce qui a marché du premier coup.

---

# Session 1, 19 août 2026

Objet : prise de connaissance du projet, mise en place du socle, premier des
trois pipelines exigés par C4.2.2.

## OBS-01. L'environnement était déjà armé, sans que ce soit noté nulle part

`CLAUDE.md` décrivait sept briques restant à construire, en laissant entendre
qu'il fallait tout installer. La vérification a montré l'inverse : Airflow 3.1.8,
dbt-core et dbt-snowflake 1.8.3, snowflake-connector-python, kafka-python,
duckdb, pandas, Docker Desktop 29.1.3, WSL2 avec Ubuntu, gh CLI 2.92 étaient
déjà présents. Presque rien n'a eu besoin d'être installé de la session.

L'enseignement est de méthode : l'état d'avancement noté dans un document de
suivi décrit les *livrables*, pas l'*environnement*. Les deux dérivent l'un de
l'autre avec le temps. Vérifier l'environnement avant de planifier a évité de
prévoir une session d'installation qui n'avait pas lieu d'être.

## OBS-02. Le vrai risque n'était pas celui qui était identifié

Le chemin de travail contient des accents et des espaces
(`Formalités_Officiels`, `Bloc 4`, `GameLens 0`). C'était le risque numéro un
identifié en début de session, au point d'avoir motivé une proposition de
déplacer tout le projet vers `C:\gamelens`.

Testé immédiatement plutôt que contourné par précaution : **Docker Desktop monte
ce chemin sans aucune difficulté**. L'hypothèse était fausse. Le seul effet
observé vient de Git Bash, dont la couche MSYS2 réécrit le chemin, et il se
règle par une variable d'environnement.

Le risque réel, lui, n'était identifié par personne : la collision de ports
PostgreSQL (INC-004). Il a coûté la seule vraie séance d'investigation de la
session.

À retenir pour l'oral, si la question du choix d'environnement vient : le
raisonnement par précaution aurait fait déplacer le projet pour rien, et
n'aurait rien fait contre le problème qui s'est réellement produit.

## OBS-03. Un message d'erreur peut être détruit par sa propre traduction

Détaillé en INC-004. L'anecdote mérite d'être racontée telle quelle, parce
qu'elle est courte et qu'elle frappe.

`psycopg2.connect()` lève `UnicodeDecodeError: 'utf-8' codec can't decode byte
0xe9 in position 103`. Tout désigne un problème d'encodage du code applicatif.

En réalité, l'octet `0xe9` est le `é` de « échouée », dans le message
`authentification par mot de passe échouée pour l'utilisateur « gamelens_app »`
renvoyé par un PostgreSQL 18 francophone installé nativement sur le poste, qui
occupait le port 5432 avant Docker. L'erreur utile existait, était parfaitement
explicite, et a été détruite au moment précis où elle allait être lue.

Ce qui a permis de trancher est un détail : l'image conteneur est une Alpine en
locale C, elle ne peut répondre qu'en anglais ASCII. Recevoir un message
accentué prouvait à lui seul que l'interlocuteur n'était pas le conteneur. **La
langue du message d'erreur a servi d'empreinte pour identifier le serveur.**

## OBS-04. Docker peut publier un port sans le publier

Le plus inquiétant dans INC-004 n'est pas la collision, c'est le silence.
`docker compose up` n'a rien signalé, `docker compose ps` affichait
`0.0.0.0:5432->5432/tcp`, et le healthcheck `pg_isready` était au vert, puisqu'il
s'exécute *à l'intérieur* du conteneur et ne teste donc jamais le chemin réseau
que l'application emprunte.

Trois indicateurs au vert, service inatteignable. C'est un cas d'école pour
C4.3.1 : un healthcheck qui ne traverse pas le même chemin que le trafic réel ne
supervise pas le service, il supervise le processus. À reprendre lors de la
conception de la supervision.

## OBS-05. Kafka n'a pas eu besoin d'être remplacé

`CLAUDE.md` autorisait explicitement une alternative légère à Kafka si celui-ci
s'avérait trop lourd en local, à condition de documenter le choix. Cette
autorisation n'a pas servi.

Depuis Kafka 3.3, le mode KRaft supprime la dépendance à ZooKeeper : le cluster
tient dans un conteneur unique, démarré en une trentaine de secondes, et il est
resté *healthy* toute la session. Il n'y avait donc pas d'arbitrage à faire.

C'est meilleur pour la soutenance : présenter Apache Kafka est plus simple à
défendre que présenter un substitut et justifier la substitution. La question
« pourquoi pas Kafka ? » ne se posera pas.

Piège rencontré au passage, classique et coûteux quand on le découvre tard : un
broker local a besoin de **deux listeners**, un pour les conteneurs
(`kafka:29092`) et un pour les processus du poste hôte (`localhost:9092`). Avec
un listener unique, l'un des deux côtés échoue systématiquement, avec un message
qui parle de métadonnées et pas de réseau. Traité en amont dans
`docker-compose.yml`, il n'a rien coûté.

## OBS-06. L'idempotence a été prouvée, pas affirmée

Le point technique dont le projet peut le plus se prévaloir en temps réel.

Kafka ne garantit qu'un *at-least-once* dès qu'on écrit vers un système externe :
entre l'écriture en base et la validation de l'offset, un arrêt brutal fait
rejouer les mêmes messages. La réponse habituelle, une transaction distribuée
entre Kafka et PostgreSQL, est disproportionnée ici.

Choix retenu : rendre le puits idempotent. Contrainte
`UNIQUE (steam_appid, collected_at)`, écriture en `ON CONFLICT DO NOTHING`, et
validation de l'offset **après** le commit PostgreSQL.

La revendication a été vérifiée en provoquant le scénario au lieu de le décrire :
remise à zéro des offsets du groupe de consommation, puis relance. Résultat
observé : **15 messages relus, 0 inséré, 15 doublons absorbés, table toujours à
15 lignes**. L'*effectively-once* est obtenu par une contrainte d'intégrité, pas
par un protocole distribué.

Détail de conception qui compte : le consumer journalise l'écart entre messages
reçus et lignes insérées. Cet écart n'est pas une anomalie, c'est la mesure des
doublons absorbés. Un pipeline qui ne mesure pas ce qu'il ignore ne sait pas
s'il est idempotent ou simplement silencieux.

## OBS-07. Une incohérence dormante entre le Bloc 3 et le Bloc 4

Trouvée en relisant le Bloc 3, pas en lisant le Bloc 4.

L'arbitrage de la section 3.3 du Bloc 3 retient l'option 2 : le suivi tarifaire
GOG est **sorti du périmètre du projet**. Or le schéma Gold du Bloc 4 déclare
`dim_stores` et `fact_prices`, avec un commentaire indiquant que la table est
« alimentée par le scraping GOG ». Un jury ayant lu le Bloc 3 pouvait
légitimement demander pourquoi le Bloc 4 construit une table pour une source
abandonnée.

Résolution sans rien renier : l'API Steam `appdetails` expose `price_overview`
avec `currency`, `initial`, `final` et `discount_percent`. Vérifié en direct sur
Hades, réponse 200. `fact_prices` reste alimentée, sans scraping, et l'arbitrage
du Bloc 3 est respecté à la lettre puisqu'il précisait « sans affecter les autres
sources ».

Observation de méthode plus générale : les incohérences entre blocs ne se voient
pas en relisant le bloc en cours. Elles se voient en relisant le bloc précédent
avec les yeux du suivant.

## OBS-08. Le Bloc 1 suivait Dota 2 pour un éditeur indépendant

Le Bloc 1 illustre la collecte Steam avec les appid 570, 730 et 1091500, soit
Dota 2, Counter-Strike 2 et Cyberpunk 2077, présentés comme « portefeuille et
panel concurrent, exemple ». Trois titres AAA pour illustrer la veille
concurrentielle d'un éditeur indépendant d'une quinzaine de titres.

Sans gravité au Bloc 1, où ce n'était qu'un extrait de code. Intenable au Bloc 4,
où la liste devient la configuration réelle d'un système qui tourne. Remplacée
par un panel de 15 jeux indépendants (Hades, Hollow Knight, Stardew Valley,
Balatro, Disco Elysium et autres), cohérent avec le positionnement de Kestrel
Interactive.

Chaque appid a été vérifié en direct contre l'API Steam plutôt que recopié de
mémoire : 15 sur 15 résolus.

## OBS-09. La vérification a produit gratuitement un cas de démonstration

Effet de bord heureux de la vérification ci-dessus. Sur les 15 titres, un seul
écart : GameLens connaît « Disco Elysium », Steam répond
« Disco Elysium - The Final Cut ».

C'est exactement le problème que la table `game_mapping`, posée au Bloc 1,
existe pour résoudre : un même jeu porte des libellés différents selon la
plateforme, et la clé interne doit rester indépendante des identifiants sources.

Ce cas n'a pas été fabriqué pour la démonstration, il est apparu tout seul en
15 appels d'API. Il vaut mieux qu'un exemple inventé, et il est conservé comme
tel dans `config/watchlist.json` avec sa note explicative.

## OBS-10. Airflow s'importe sans erreur et ne fonctionnerait pas

`import airflow` réussit et retourne la version 3.1.8. Seul un `RuntimeWarning`
signale qu'Airflow ne tourne que sur un système POSIX.

Un avertissement, pas une exception. Le paquet est installable, importable, et
inutilisable : l'échec ne serait apparu qu'au démarrage du scheduler, c'est à
dire une fois les DAG écrits et le temps investi.

À retenir pour la feuille de route d'exploitation (C4.3.2) : la vérification d'un
prérequis doit porter sur l'exécution, pas sur l'installation. Un `pip install`
réussi ne prouve rien d'autre qu'un téléchargement réussi.

## OBS-11. Le référentiel réclame une rubrique que le travail en solo fait oublier

Lecture attentive des critères du C4.4.2 dans la grille officielle. La
méthodologie doit permettre d'identifier quatre éléments, dont un passe
facilement inaperçu : **la communication auprès des différentes parties
prenantes**.

Sur un projet mené seul, sur son propre poste, il n'y a spontanément personne à
prévenir : la rubrique s'évapore. Elle est traitée dans le journal en se
replaçant dans l'organisation fictive Kestrel Interactive et en répondant à trois
questions concrètes : qui aurait été prévenu, quand, et par quel canal. Pour
INC-004, la réponse est graduée, mention en daily, puis prérequis ajouté à la
procédure d'installation, puis entrée durable dans le journal, et elle exclut
explicitement toute remontée au commanditaire, faute d'impact sur le service.

Autre relecture utile du même document : le règlement spécial confirme les trois
compétences éliminatoires C4.2.1, C4.2.2 et C4.2.3, et ajoute pour C4.2.3 une
mention absente du référentiel d'activités, « DevOps ». Le pipeline CI/CD ne
devra donc pas se réduire à une exécution de tests.

## OBS-12. Ce que la session dit du calendrier

Aucune date de soutenance n'est fixée. La session a montré qu'une brique
d'apparence simple, le pipeline temps réel, tient en une session incident
compris, ce qui est plutôt encourageant. Mais elle a aussi montré que
l'investigation d'un seul incident réel occupe une part significative du temps.

Conséquence pratique retenue pour la suite : ne pas provisionner de ressource à
durée de vie limitée avant d'en avoir l'usage immédiat. C'est le raisonnement
appliqué au compte d'essai Snowflake, dont la recréation est volontairement
différée.
