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

---

# Session 2, 20 août 2026

Objet : orchestrateur Airflow en conteneurs, DAG de promotion vers la couche
Gold, pipeline CI/CD. Les deux compétences éliminatoires restantes.

## OBS-13. Airflow 3 n'est pas Airflow 2 avec un numéro de plus

Trois différences rencontrées en une seule session, toutes capables de faire
perdre une heure à qui suit un tutoriel écrit pour Airflow 2 :

- le composant `webserver` n'existe plus, il s'appelle `api-server` et sert à
  la fois l'interface et l'API que les tâches utilisent pour s'exécuter ;
- le `dag-processor` est un service séparé et obligatoire, alors qu'il était
  intégré à l'ordonnanceur ;
- `logical_date` est désormais nullable et vaut `None` pour un run manuel
  (INC-006).

Le réflexe qui a évité de deviner : récupérer le `docker-compose.yaml` officiel
de la version exacte, 3.1.8, et en lire les noms de variables plutôt que les
reconstituer de mémoire. Les variables `AIRFLOW__API_AUTH__JWT_SECRET` et
`AIRFLOW__CORE__EXECUTION_API_SERVER_URL` n'existaient tout simplement pas
avant Airflow 3.

## OBS-14. Le compose officiel est surdimensionné pour ce projet

Le fichier de référence d'Airflow retient `CeleryExecutor`, ce qui impose un
Redis et des conteneurs worker, soit sept conteneurs. Repris tel quel, il
aurait fait tourner un courtier de messages pour distribuer six tâches sur une
seule machine.

Retenu : `LocalExecutor`, qui exécute les tâches en sous-processus parallèles.
Quatre conteneurs Airflow au lieu de sept, aucune fonctionnalité perdue à cette
échelle.

C'est un argument à préparer, parce que le jury peut le prendre dans les deux
sens. La réponse honnête n'est pas « Celery était trop lourd » mais « Celery
répond à un besoin de montée en charge horizontale que ce projet n'a pas ». Un
dimensionnement se justifie par le besoin, pas par le confort.

## OBS-15. Le pire échec d'un pipeline est celui qui réussit

La tâche `verifier_fraicheur_silver` refuse de promouvoir une journée sans
données. Elle a l'air superflue : sans elle, le DAG aurait tourné, écrit zéro
ligne, et se serait terminé en succès.

C'est exactement le problème. La supervision aurait affiché un run vert, alors
que la collecte temps réel était à l'arrêt. Le tableau de bord serait resté
figé sur la veille sans que rien ne l'annonce.

Formulation retenue pour l'oral : **un pipeline qui réussit à ne rien faire est
un pipeline qui ment.** Une porte d'entrée qui échoue franchement vaut mieux
qu'un succès vide.

Le test négatif a été fait avant le test positif : DAG déclenché sur une
journée sans données, échec obtenu avec le message attendu, `Aucun evenement de
frequentation pour le 2026-08-20`. Une porte qu'on n'a jamais vue se fermer
n'est pas une porte.

## OBS-16. Le run s'est réparé tout seul, et ce n'était pas prévu

Enchaînement non scénarisé, et le plus démonstratif de la session.

Le run planifié de 02h30 a échoué sur la porte de fraîcheur à 07:52:17, faute
de données pour la journée. Les données ont été produites à 07:54. La seconde
tentative, déclenchée automatiquement cinq minutes après l'échec par la
politique de reprise, est passée à 07:57:17, et le run complet s'est terminé en
succès à 07:57:36.

Personne n'est intervenu entre les deux. C'est la démonstration concrète de ce
à quoi servent `retries` et `retry_delay` face à une dépendance amont en
retard, plutôt que la description théorique qu'on en donne d'habitude.

## OBS-17. Un schéma valide ne dit rien de la stratégie de rechargement

Détaillé en INC-005. Le schéma Gold avait été relu, exécuté et testé en
session 1. Il était juste, au sens du modèle : bon grain, bons types, bonnes
clés étrangères.

Il était pourtant impossible d'y écrire de façon rejouable. `dim_games` et
`fact_prices` n'avaient pour toute unicité que leur clé primaire UUID, générée
à l'insertion, donc différente à chaque exécution. Un second run aurait
dupliqué en silence.

La faille n'apparaît pas en relisant un schéma, parce qu'elle n'est pas dans le
schéma : elle est dans l'absence de réponse à une question qu'on ne pose qu'en
écrivant le pipeline, « qu'est-ce qui, ici, ne doit exister qu'une fois ? ».
`fact_popularity_history`, dont la clé primaire composite portait déjà le
grain, n'avait aucun problème. La différence tient entièrement à cela.

## OBS-18. La supervision avait un angle mort, découvert par recoupement

Détaillé en INC-007. Quatre collectes tarifaires réellement effectuées, une
seule ligne dans la table de supervision.

Ce qui l'a révélé n'est pas une alerte, c'est un recoupement fait par curiosité
entre deux comptages qui auraient dû concorder. Aucun mécanisme du système ne
signalait l'écart, et rien n'était en erreur : les données étaient correctes,
seule leur trace manquait.

C'est le pendant exact d'INC-004 en session 1. Dans un cas un indicateur était
au vert sur un service inatteignable, dans l'autre la supervision était muette
sur un composant qui tournait. Les deux disent la même chose : **un système de
supervision doit être testé sur ce qu'il rate, pas sur ce qu'il rapporte.**

À reprendre tel quel dans le livrable C4.3.1, où ces deux cas donnent une
matière concrète que peu de candidats auront.

## OBS-19. Ce que le linter a réellement trouvé

`ruff` a relevé 11 anomalies sur du code qui fonctionnait parfaitement :
imports mal ordonnés, et surtout `datetime.timezone.utc` là où Python 3.12
attend `datetime.UTC`.

Aucune n'aurait causé de panne. C'est précisément l'intérêt de l'avoir dans la
CI plutôt qu'en relecture humaine : ce sont des anomalies que personne ne voit
et que personne ne signale, jusqu'à ce qu'un jour l'une d'elles compte.

Le point de méthode qui compte pour la soutenance : la configuration `ruff.toml`
est partagée par le poste de développement et la CI. Un contrôle qui passe en
local et échoue en intégration, ou l'inverse, décrédibilise la chaîne entière.

## OBS-20. La CI ne peut pas encore être présentée comme fonctionnelle

Le fichier `.github/workflows/ci.yml` est écrit et ses cinq étages sont
cohérents, mais **il n'a jamais été exécuté par GitHub Actions**, faute de
dépôt distant : la décision 2b de la session 1 a retenu un dépôt git local.

Ce qui a pu être vérifié localement, en exécutant les mêmes commandes que le
workflow : l'étage qualité (`ruff check` et `ruff format --check` passent),
l'étage tests (14 tests verts), et l'étage d'intégrité du DAG, testé dans le
conteneur et corrigé à cette occasion, `airflow dags list` lisant la base de
métadonnées et non le dossier, il fallait une sérialisation préalable.

Ce qui reste non vérifié : l'exécution réelle par le runner, l'étage
d'intégration sur infrastructure jetable, et la publication d'image sur
`ghcr.io`.

C4.2.3 étant éliminatoire, présenter un fichier YAML jamais exécuté serait
exactement le travers que `CLAUDE.md` interdit. Il faut un dépôt distant et au
moins un run vert avant la soutenance.

> **Résolu le 20/08/2026, dans la même session.** Dépôt privé créé et poussé,
> deux exécutions réelles du workflow, la seconde verte sur les cinq étages.
> Voir OBS-21 à OBS-23. Cette observation est conservée telle quelle parce que
> le raisonnement qu'elle porte reste valable : ce qui n'a jamais été exécuté
> ne se présente pas comme fonctionnel.

## OBS-21. La CI a échoué à sa première exécution réelle, et c'est le résultat utile

Le dépôt distant privé `Mael8zinsou/gamelens-bloc4_0` a été créé et poussé le
20/08/2026, ce qui a déclenché la première exécution réelle du workflow.

Résultat : **trois étages verts du premier coup** (qualité, tests unitaires,
intégrité du DAG), **un étage en échec** (intégration), le cinquième ignoré par
dépendance.

Ce n'est pas un hasard. Les trois étages verts avaient été rejoués localement
avec exactement les mêmes commandes. L'étage qui a cassé est précisément celui
que je ne pouvais pas rejouer en local, faute d'environnement jetable : il
démarre le socle Docker de zéro, sur une machine où rien ne préexiste.

Formulation retenue pour l'oral : **une CI qui passe au vert du premier coup sur
cinq étages n'a en général rien vérifié.** Ce qui compte n'est pas qu'elle soit
verte, c'est qu'elle ait été rouge pour une bonne raison au moins une fois.

## OBS-22. Le défaut était dans le test, pas dans l'infrastructure

La cause de l'échec ci-dessus mérite d'être détaillée, parce qu'elle est
contre-intuitive.

Le contrôle vérifiait que le schéma `speed` contient bien 4 tables après
initialisation automatique du conteneur, par
`SELECT count(*) FROM information_schema.tables WHERE table_schema='speed'`.

En local, `\dt speed.*` affiche bien 4 tables, ce qui semblait confirmer
l'attendu. Mais `information_schema.tables` **inclut les vues** : le schéma
contient 4 tables de base plus la vue `v_daily_player_stats`, soit 5 lignes.
L'infrastructure était parfaitement conforme, c'est l'assertion qui était fausse.

Deux enseignements :

- un test qui échoue ne désigne pas nécessairement le système testé. Avant de
  corriger le code, il faut vérifier que l'attendu était juste ;
- deux commandes qui semblent poser la même question, `\dt` et
  `information_schema.tables`, n'y répondent pas de la même façon. Le raccourci
  interactif d'un client et la vue système normalisée ne recensent pas les
  mêmes objets.

Le contrôle vérifie désormais séparément les 4 tables et la vue, ce qui rend
aussi le diagnostic immédiat au lieu d'un simple `grep` qui ne dit rien.

## OBS-23. Le défaut prédit avant qu'il ne survienne

L'étage de publication n'a pas eu l'occasion d'échouer, l'intégration l'ayant
précédé, mais il aurait planté.

Il construisait le nom d'image depuis `${{ github.repository }}`, qui vaut
`Mael8zinsou/gamelens-bloc4_0` en conservant la majuscule du compte, alors qu'un
nom d'image Docker doit être **entièrement en minuscules**. L'erreur aurait été
`invalid reference format`, qui ne dit rien de la casse et envoie chercher
ailleurs.

Repéré en relisant le workflow pendant que le premier run tournait, et corrigé
dans le même commit que l'assertion de schéma. La seconde exécution est passée
au vert sur les cinq étages, et l'image a bien été publiée sous
`ghcr.io/mael8zinsou/gamelens-bloc4_0/airflow`, avec deux étiquettes : `latest`
et le SHA complet du commit.

Le double étiquetage n'est pas décoratif. Sans l'étiquette par SHA, revenir à
une version antérieure consisterait à espérer que `latest` pointe encore sur la
bonne image, ce qui n'est pas une procédure de retour arrière mais un pari.

## OBS-24. La CI dépend d'une API tierce, et c'est un compromis à assumer

Trois exécutions du workflow, les deux dernières vertes sur les cinq étages :
la chaîne est reproductible et non un coup de chance.

Mais l'étage d'intégration appelle **la vraie API Steam** à chaque exécution.
C'est ce qui lui donne sa valeur, il teste le pipeline réel de bout en bout
plutôt qu'une simulation, et c'est aussi sa fragilité : si Steam est
indisponible, modifie son format de réponse ou limite les adresses des runners
GitHub, la CI passe au rouge pour une raison **étrangère au code livré**.

Le compromis est assumé plutôt que corrigé, pour deux raisons. D'abord, une
rupture de contrat d'une API amont est exactement ce qu'un pipeline de données
doit détecter, et l'apprendre par la CI vaut mieux que par un tableau de bord
faux. Ensuite, les tests unitaires, eux, sont entièrement hors ligne : les neuf
cas de lecture tarifaire s'exécutent sur des réponses simulées. La logique reste
donc vérifiable même si Steam tombe, seul l'étage d'intégration devient rouge.

À inscrire comme point de vigilance dans la feuille de route d'exploitation
(C4.3.2) : une CI rouge n'implique pas nécessairement une régression, et savoir
distinguer les deux fait partie de la procédure d'exploitation. C'est aussi une
question probable du jury sur la fiabilité d'une chaîne dépendant de tiers.

---

# Session 3, 20 août 2026

Objet : test de sécurité manquant, puis système de supervision et d'alertes
(C4.3.1).

## OBS-25. Deux modèles de sécurité concurrents, découverts en écrivant le test

Le test de sécurité devait simplement combler la lacune TSEC-01 du cahier de
recettes. En préparant la matrice de droits, un problème plus profond est
apparu : **la plateforme avait deux modèles de rôles incompatibles**.

Le schéma Gold reprenait fidèlement les quatre rôles du Bloc 1 (`admin`,
`etl_service`, `analyst`, `dashboard_viewer`). Le schéma Silver speed, écrit en
session 1, avait inventé de son côté `gamelens_etl` et `gamelens_reader`. Deux
couches d'une même plateforme, deux vocabulaires, aucun recouvrement.

Rien ne cassait, ce qui explique que personne ne l'ait vu : chaque couche
fonctionnait avec ses propres rôles. Le défaut ne se manifeste qu'au moment où
l'on cherche à répondre à la question « qui a le droit de faire quoi sur la
plateforme ? », et où l'on découvre qu'il n'y a pas de réponse unique.

Corrigé en alignant Silver sur le modèle du Bloc 1, avec suppression des deux
rôles orphelins. Le même modèle s'applique désormais aux deux couches, ce qui
est la seule version défendable devant un jury qui a lu le Bloc 1.

Enseignement : écrire un test de sécurité oblige à énoncer le modèle de
sécurité. Tant qu'on se contente d'accorder des droits, on peut en avoir deux
sans s'en apercevoir.

## OBS-26. Le test de refus a été testé lui-même

Sept des treize tests de sécurité vérifient qu'une opération est **refusée**. Un
tel test est piégeux : il peut passer pour de mauvaises raisons, par exemple si
la table n'existe pas ou si la connexion échoue silencieusement.

Vérification faite : `GRANT SELECT ON mart.fact_popularity_history TO
dashboard_viewer`, relance du test, qui **échoue** avec `attendu refuse, obtenu
autorise`. Puis `REVOKE`, relance, retour au vert.

Le test détecte donc réellement une brèche de cloisonnement, il ne se contente
pas de passer. C'est la même discipline que le test négatif de la porte de
fraîcheur en session 2, appliquée à la sécurité.

Détail de conception qui rend le piège moins probable : seule
`InsufficientPrivilege` est interceptée. Une table manquante lèverait
`UndefinedTable`, qui remonterait en erreur de test plutôt que de se déguiser
en refus.

## OBS-27. Grafana plutôt que Prometheus, et pourquoi ce n'est pas de la paresse

Le réflexe attendu pour de la supervision est Prometheus plus Grafana. Ce projet
n'utilise que Grafana, branché directement sur PostgreSQL, et c'est un choix
qu'il faut savoir défendre.

Prometheus excelle sur des métriques système collectées par des exporteurs :
processus, mémoire, requêtes par seconde. Les indicateurs surveillés ici sont
d'une autre nature, ce sont des indicateurs **métier et de pipeline** : fraîcheur
de la donnée, complétude de la collecte, latence de bout en bout, fiabilité par
composant. Ils sont déjà calculés dans une base relationnelle, à partir du
journal d'exécution que tous les composants alimentent.

Les réexporter vers Prometheus ajouterait un composant, un format de stockage et
un exporteur, sans ajouter la moindre information. Pire, cela rendrait les
indicateurs dépendants d'un outil, alors qu'ils restent aujourd'hui
interrogeables en SQL par n'importe quel client.

Formulation courte pour l'oral : **Prometheus aurait transporté des indicateurs
déjà disponibles, sans en produire un seul de plus.**

## OBS-28. Les indicateurs sont définis en SQL, pas dans l'outil

Corollaire du choix précédent, et le point de conception dont je suis le plus
convaincu sur cette session.

Les seuils et les états (`nominal`, `avertissement`, `critique`) sont calculés
dans la vue `speed.v_supervision_synthese`, pas dans la configuration des
panneaux Grafana. Trois conséquences :

- le même état est renvoyé quel que soit le client, Grafana, `psql`, un DAG
  Airflow ou le moteur d'alertes, alors que des seuils saisis dans l'interface
  n'existeraient que pour Grafana ;
- les seuils sont versionnés et relisibles en revue de code ;
- si Grafana est arrêté, la supervision reste interrogeable.

**L'outil affiche les indicateurs, il ne les définit pas.** Source de données et
tableau de bord sont eux-mêmes provisionnés depuis le dépôt : aucune
configuration n'est saisie à la main dans l'interface.

## OBS-29. L'indicateur de latence a détecté un incident réel dès sa création

Le meilleur genre de validation : celle qu'on ne cherchait pas.

À peine créé, l'indicateur de latence p95 est monté à **64 890 secondes, soit
plus de 18 heures**, et a déclenché son alerte. Ce n'est ni un bug ni une valeur
de test : les 15 messages produits en fin de session 1 sont restés dans Kafka
jusqu'à ce que le consumer soit relancé le lendemain matin. Leur écart entre
`collected_at` et `ingested_at` est donc réellement de 18 heures.

L'indicateur a donc mesuré, sans qu'on lui demande, exactement ce pour quoi il
est fait : un consumer arrêté pendant que le producteur continue. Et il reste
allumé tant que ces événements sont dans la fenêtre de 24 heures, ce qui est le
comportement correct.

C'est la meilleure preuve possible qu'un indicateur n'est pas décoratif. Il vaut
mieux le raconter ainsi que d'exhiber un tableau de bord entièrement vert.

## OBS-30. Une alerte doit se refermer toute seule, et se souvenir

Trois comportements du moteur d'alertes, vérifiés séparément plutôt que
supposés.

- **Déclenchement** : deux alertes ouvertes sur six règles, avec le message et
  la valeur observée.
- **Pas de doublon** : à la seconde évaluation, condition inchangée, `2
  déclenchées dont 0 nouvelle`, et toujours deux lignes en base. Sans cela, une
  règle évaluée tous les quarts d'heure produirait 96 lignes par jour pour un
  seul problème, et le journal deviendrait illisible au moment précis où l'on en
  a besoin.
- **Fermeture automatique** : après relance du producteur et du consumer,
  `[RESOLUE] fraicheur_frequentation revenue sous le seuil`, avec horodatage de
  résolution.

Ce dernier point est ce qui distingue un journal d'alertes d'un flux de
notifications : la colonne `resolue_le` permet de mesurer **combien de temps** un
incident a duré, pas seulement qu'il a eu lieu. C'est directement réutilisable
pour la feuille de route d'exploitation (C4.3.2).

## OBS-31. Séparer « évaluer » de « s'alarmer »

Dans le DAG de supervision, la tâche qui évalue les règles **réussit toujours**,
y compris quand des alertes se déclenchent. C'est une seconde tâche qui échoue
en présence d'une alerte critique.

La distinction paraît byzantine et ne l'est pas. Sans elle, un run en échec ne
permettrait pas de distinguer deux situations qui appellent des réactions
opposées : **la plateforme va mal**, ou **le moteur d'alertes est cassé**. Dans
le premier cas on traite l'incident métier, dans le second on ne peut plus faire
confiance à rien de ce que la supervision affiche.

Même raison pour laquelle la tâche de remontée n'écrit pas dans
`speed.pipeline_runs` : son échec décrit l'état de la plateforme, pas une
défaillance de composant. Les confondre fausserait la règle `echecs_composants`,
qui compterait la supervision elle-même parmi les pannes qu'elle surveille.

## OBS-32. Une assertion par comptage se brise à chaque évolution normale

Deuxième échec de la CI sur le même contrôle, pour une raison différente et
plus instructive que la première.

En session 2, le contrôle du schéma attendait 4 tables et en trouvait 5, parce
que `information_schema.tables` inclut les vues (OBS-22). Corrigé en séparant
les deux comptages. En session 3, le même contrôle a de nouveau échoué :
`schema speed : 5 table(s), 7 vue(s)`. Cette fois l'écart était **légitime**,
la supervision ayant ajouté la table `alertes` et six vues d'indicateurs.

Le défaut n'était donc pas le filtre, c'était la nature même de l'assertion.
Un contrôle par comptage échoue à chaque évolution normale du schéma, ce qui
pousse celui qui le maintient à l'affaiblir mécaniquement plutôt qu'à le lire.
Un contrôle qu'on ajuste sans réfléchir a cessé de tester quoi que ce soit.

Remplacé par une vérification des objets **nommés** : les 17 tables et vues
attendues des schémas `speed` et `mart` sont listées explicitement, et
`to_regclass` renvoie `NULL` pour celles qui manquent. Le contrôle donne
directement la liste de ce qui est absent, au lieu d'un écart de comptage à
interpréter, et ne bronche pas quand une table légitime s'ajoute.

Contrepartie assumée : cette version ne détecte plus un objet **inattendu**.
C'est un compromis conscient. Un objet manquant casse le pipeline, un objet en
trop ne casse rien, et une revue de code voit passer un `CREATE TABLE` bien
mieux qu'un compteur ne le fera jamais.

Formulation retenue : **une assertion qu'on ajuste à chaque évolution ne teste
plus rien, elle enregistre.**

---

# Session 4, 20 août 2026

Objet : bascule réelle vers Snowflake et calcul distribué Snowpark, dernière
brique éliminatoire.

## OBS-33. Le compte est étudiant, pas d'essai : 120 jours au lieu de 30

Maël a créé un compte étudiant, 120 jours et 400 dollars de crédits, là où le
raisonnement de la session 2 portait sur un essai de 30 jours.

Toute l'argumentation calendaire qui justifiait de différer la création tombe
donc d'elle-même. Elle reste néanmoins juste dans son principe, et mérite d'être
racontée à l'oral pour ce qu'elle montre : ne pas provisionner une ressource à
durée de vie limitée avant d'en avoir l'usage. Le fait que la contrainte se soit
avérée plus souple ne rend pas la précaution inutile, elle la rend seulement
sans conséquence cette fois-ci.

## OBS-34. Vérifier une dépendance a cassé l'environnement, et c'est instructif

Avant de laisser Maël lancer le compte à rebours, j'ai voulu lever un risque
identifié en session 1 : Snowpark est-il disponible pour Python 3.12 ? Réponse
oui, version 1.54.

Mais l'installation a modifié l'environnement global : `snowflake-connector-python`
est passé en 4.x, que `dbt-snowflake 1.8` refuse, et `requests` a été remonté
alors qu'il est épinglé dans `requirements.txt` et utilisé par l'ingestion.

Deux réflexes ont limité les dégâts. D'abord vérifier **ce que j'avais réellement
changé**, par les dates de modification des distributions, plutôt que de croire
la liste de conflits affichée par pip : celle-ci mentionnait aussi `pydantic`,
`starlette` et `uvicorn`, dont les conflits **préexistaient** et n'avaient rien à
voir. Ensuite restaurer les versions épinglées et revérifier que les 27 tests
passaient.

La conclusion n'est pas « faire attention » mais structurelle : **l'outillage
Snowflake vit désormais dans son propre conteneur**, pour exactement la même
raison qu'Airflow. Un jeu de dépendances qui entre en conflit avec le reste ne
s'arbitre pas, il s'isole.

Effet de bord découvert au passage : le module `venv` de l'installation Python
du poste est vide, il n'y reste qu'un `requirements.txt` égaré daté d'août 2024.
`python -m venv` ne fonctionne donc pas, ce qui a écarté l'option de
l'environnement virtuel et rendu le conteneur d'autant plus naturel.

## OBS-35. Le mur d'authentification que peu anticipent

Snowflake impose désormais l'authentification multifacteur aux utilisateurs
humains sur les comptes récents. Un pipeline ne peut pas valider une
notification sur téléphone : l'accès par mot de passe est donc structurellement
inutilisable pour un accès programmatique.

Le piège est que l'erreur obtenue parle d'identifiants incorrects, ce qui envoie
chercher une faute de frappe pendant que la cause est une politique de sécurité.

Traité en amont plutôt que subi : utilisateur de service `GAMELENS_SERVICE` créé
en `TYPE = SERVICE`, exempté de MFA et restreint à l'authentification par paire
de clés RSA. Ce n'est pas un contournement, c'est la pratique attendue en
production, et cela a une conséquence pratique appréciable : **aucun secret n'a
transité par la conversation**, la clé privée restant sur le disque et `.env` ne
faisant que la désigner.

## OBS-36. Le test qui prouvait le contraire de ce qu'il croyait prouver

Le meilleur épisode de la session, et probablement l'un des meilleurs du projet.

`sql/verify_snowflake_constraints.sql` cherche à établir empiriquement quelles
contraintes Snowflake applique vraiment. Le TEST 4 devait montrer qu'une clé
étrangère vers une ligne inexistante passe sans résistance. Première exécution :
il **échoue**, ce qui semblait prouver que Snowflake applique bien les clés
étrangères.

Sauf que le message disait `String 'inexistant-0000-...' is too long`, et non une
violation de contrainte référentielle. L'identifiant de test faisait 38
caractères pour une colonne `VARCHAR(36)` : l'insertion était rejetée sur la
**longueur**, avant que la clé étrangère ne soit seulement évaluée. Le test
n'avait jamais mis la contrainte à l'épreuve.

Identifiant raccourci à 35 caractères, réexécution : l'insertion **réussit**. La
clé étrangère n'est effectivement pas appliquée.

Deux enseignements. Un test qui échoue peut échouer pour une raison qui n'a rien
à voir avec ce qu'il teste, et **lire le message plutôt que le statut** est ce
qui fait la différence. Et l'échec a livré une information non anticipée :
Snowflake applique les contraintes de **type**, longueur comprise.

## OBS-37. La formulation de CLAUDE.md était trop approximative

Conséquence directe de l'observation précédente. `CLAUDE.md` écrivait que sur
Snowflake « seul NOT NULL est réellement appliqué ». La vérification empirique
montre que c'est mal découpé.

Formulation exacte, tirée des résultats observés : **les contraintes portées par
la colonne elle-même sont appliquées** (NOT NULL, type, longueur), **celles qui
portent sur une relation entre lignes ou entre tables ne le sont pas** (CHECK,
FOREIGN KEY, PRIMARY KEY, UNIQUE).

C'est plus juste, plus mémorable, et cela explique le mécanisme au lieu de
lister des exceptions : Snowflake peut valider une valeur à l'écriture d'une
ligne, mais pas interroger le reste de la table sans coût, sur un moteur conçu
pour l'analytique.

## OBS-38. Le TEST 6 donne la démonstration la plus parlante

Le script insère volontairement deux lignes en doublon sur ce qui est déclaré
comme clé primaire, puis interroge la vue de restitution servie aux tableaux de
bord. Elle en retourne **deux**.

Un analyste verrait donc deux mesures contradictoires pour le même jeu et le
même jour, sans qu'aucune alerte ne se déclenche et sans que rien dans le schéma
ne s'y soit opposé. C'est l'argument concret qui justifie de reporter
l'intégrité sur des tests exécutés à chaque run, plutôt qu'un raisonnement
abstrait sur des contraintes déclaratives.

## OBS-39. « En quoi est-ce distribué ? », et comment y répondre sans bluffer

La question que le jury posera sur Snowpark. Répondre « c'est Snowflake, donc
c'est distribué » ne vaut rien.

Le script le prouve au lieu de l'affirmer, de deux façons.

Il affiche le **SQL réellement généré** par l'API DataFrame, où l'on lit
`rank() OVER (PARTITION BY "GENRE" ORDER BY ...)` et
`avg(...) OVER (PARTITION BY "GAME_ID" ORDER BY "JOUR" ROWS BETWEEN 6 PRECEDING
AND CURRENT ROW)`. Les fenêtres analytiques ne sont donc pas calculées en pandas
sur le poste, elles sont poussées dans la requête.

Il interroge ensuite l'**historique de session**, qui montre chaque requête avec
l'entrepôt virtuel qui l'a servie, sa taille, le numéro de cluster, les octets
parcourus et le temps de compilation. Le processus Python n'a fait qu'envoyer un
plan et recevoir un résultat.

C'est exactement la différence avec le PySpark local écarté le 19/08 : celui-ci
se serait exécuté sur la même machine que le script qui le pilote.

## OBS-40. Trois erreurs d'API, et la méthode qui a fini par marcher

Le script Snowpark a échoué trois fois avant de tourner.

- `information_schema.warehouses()` n'existe pas comme fonction de table.
  Requête simplifiée plutôt que remplacée par une autre supposition.
- `invalid identifier 'DAY'` : la fenêtre glissante ordonnait sur `DAY` alors
  que la colonne s'appelait `JOUR` après renommage. Snowpark diffère la
  résolution des noms, l'erreur ne survient donc qu'à l'exécution, pas à
  l'écriture du code.
- `invalid identifier 'PARTITIONS_SCANNED'` : cette colonne existe dans
  `account_usage.query_history` mais pas dans la fonction de table
  `query_history_by_session`.

La troisième fois est celle qui compte. Après deux corrections faites à
l'estime, j'ai **listé les colonnes réellement exposées** par la fonction avant
de réécrire, au lieu de tenter un troisième nom plausible. C'est ce qui a
fonctionné du premier coup, et c'est la même méthode que celle qui avait servi
à trancher INC-004 : interroger le système sur ce qu'il est, plutôt que lui
supposer une forme.

---

# Session 5, 26 août 2026

## OBS-41. Le script de schéma était une arme chargée pointée sur la démonstration

Brancher la CI sur Snowflake paraissait mécanique : ajouter un étage, déposer
des secrets, appeler les scripts existants. Le premier coup d'oeil au script de
schéma a arrêté net cette mécanique. `sql/schema_gold_snowflake.sql` contient
des `CREATE OR REPLACE TABLE gamelens.mart.dim_games`, et la base y est nommée
en dur, vingt-quatre fois. Un étage de CI qui l'aurait rejoué à chaque push
aurait vidé la couche Gold à chaque push, c'est à dire détruit les données de
soutenance sans le moindre message d'erreur, puisque `CREATE OR REPLACE`
réussit parfaitement.

La correction ne consiste pas à écrire un script de schéma distinct pour la
recette. Ce serait perdre l'essentiel : c'est le script **livré** qui doit être
mis à l'épreuve, sinon la CI valide une copie et pas le livrable. La redirection
se fait donc à l'exécution, par une option `--base` de `executer_sql.py`, avec
une substitution qui distingue la base des autres objets :

```python
MOTIF_BASE = re.compile(r"(?<![A-Za-z0-9_])gamelens(?![A-Za-z0-9_])")
```

La limite de mot n'est pas de la coquetterie. `gamelens.mart` et
`DATABASE gamelens` doivent être redirigés ; `gamelens_wh`, `gamelens_analyst`
et `gamelens_etl_service` ne doivent pas l'être, car l'entrepôt virtuel et les
rôles sont des objets de compte partagés, pas des objets de base. Vérifié sur
le fichier réel avant tout appel à Snowflake : 24 redirections, entrepôt et
rôles intacts.

**Ce qu'il faut en retenir à l'oral** : la question « pourquoi votre CI ne
touche pas à Snowflake ? » a une meilleure réponse que « je n'y avais pas
pensé ». La vraie réponse est qu'une CI branchée naïvement sur un entrepôt est
plus dangereuse que pas de CI du tout.

## OBS-42. Le garde-fou que sa propre précaution rendait inatteignable

Par prudence, la recette refuse de viser une base protégée. Le refus a été
écrit d'emblée, et la fonction qui choisit le nom de base a été écrite dans le
même mouvement :

```python
explicite = os.getenv("SNOWFLAKE_DATABASE")
if explicite and explicite not in BASES_PROTEGEES:
    return explicite
```

Deux précautions, chacune raisonnable. Ensemble, elles s'annulent : la fonction
de nommage **écartait discrètement** les noms protégés en retombant sur un nom
généré, si bien que `garde_fou()` ne recevait jamais de nom protégé et ne
pouvait jamais refuser quoi que ce soit.

Le test négatif l'a révélé, et seulement lui. Lancer la recette avec
`SNOWFLAKE_DATABASE=gamelens` aurait dû produire un refus immédiat. Elle a
tourné jusqu'au bout, sur une base jetable, et rendu 0. Un vert parfait, pour
un garde-fou mort.

Le comportement était sûr, mais il mentait. Substituer silencieusement une base
à celle qu'on a demandée, c'est exactement le défaut nommé ailleurs dans ce
journal : un composant qui réussit sans faire ce qu'on lui demande. Le nommage
rend désormais ce qu'on lui demande, et le garde-fou tranche seul. Vérifié :
refus immédiat, code de sortie 1.

**Ce qu'il faut en retenir à l'oral** : un test négatif ne sert pas à cocher une
case de méthode. Ici, il a mis au jour un dispositif de sécurité entièrement
décoratif, que trois relectures du code n'auraient pas signalé puisque les deux
morceaux sont corrects séparément.

## OBS-43. Quatre contraintes ignorées, quatre violations rattrapées

L'étape la plus parlante de la recette n'était pas prévue aussi nette. Les
insertions qui éprouvent le comportement du moteur laissent volontairement des
données invalides derrière elles. Il n'a donc pas fallu fabriquer de jeu de
données corrompu pour le test négatif des contrôles d'intégrité : les
violations sont exactement ce que le moteur vient de laisser entrer.

```
6. Mise a l'epreuve des contraintes du moteur
   [PASS] NOT NULL sur unified_name                  rejetee par le moteur
   [PASS] longueur VARCHAR(36) depassee              rejetee par le moteur
   [PASS] CHECK implicite : prix negatif             acceptee par le moteur
   [PASS] clef etrangere : game_id inexistant        acceptee par le moteur
   [PASS] clef primaire : (game_id, day) en doublon  acceptee par le moteur
   [PASS] contrainte UNIQUE : steam_appid en doublon acceptee par le moteur
   -> 2 contrainte(s) appliquee(s) par le moteur, 4 laissee(s) a l'applicatif

7. Controles d'integrite apres violations, attendus EN ECHEC
   -> 4 violation(s) detectee(s) par le filet applicatif : conforme
```

Quatre laissées à l'applicatif, quatre rattrapées. La correspondance est exacte
et se lit en dix lignes. C'est la démonstration la plus économique du choix
d'architecture du Bloc 4 : sur Snowflake, les contrôles d'intégrité ne doublent
pas le moteur, ils le remplacent.

## OBS-44. Une hypothèse d'architecture vérifiée une seule fois est une hypothèse qui périme

Le comportement des contraintes Snowflake avait été établi empiriquement le
20/08/2026 (TS-08), après un test d'abord défectueux. Ce constat porte à lui
seul une décision d'architecture lourde : reporter toute l'intégrité
relationnelle sur des tests applicatifs et dbt.

Or ce constat n'était vrai que le 20 août, sur la version du moteur de ce
jour-là. Rien ne garantit qu'il le reste, et il est probable que Snowflake
finisse par appliquer davantage. Le jour où cela arriverait, le raisonnement
entier serait à revoir, et rien n'aurait prévenu.

L'étape 6 de la recette transforme donc ce constat en test de non-régression.
Si Snowflake se met à appliquer les clefs étrangères, la CI vire au rouge avec
un message qui dit précisément quoi réexaminer :

```
Le comportement des contraintes Snowflake a change : ...
Le choix de reporter l'integrite sur des tests applicatifs doit etre reexamine.
```

**Ce qu'il faut en retenir à l'oral** : c'est probablement la réponse la plus
solide à « et si le fournisseur change de comportement ? ». La plupart des
architectures documentent leurs hypothèses ; peu les surveillent.

## OBS-45. Le coût de la recette, chiffré plutôt que supposé

Brancher la CI sur un entrepôt facturé à l'usage soulève immédiatement la
question du coût. Le chiffre réel, lu sur le compte : **0,60 crédit consommé en
30 jours**, sur les 400 dollars de l'enveloppe étudiante, pour l'ensemble du
travail de la session 4 et des sessions suivantes. Une exécution de recette
dure 36 à 43 secondes sur un entrepôt XS, soit de l'ordre de 0,01 à 0,02
crédit.

Ce n'est pas nul, et c'est ce qui justifie deux choix pris plus tôt sans les
chiffrer : le dimensionnement XS et l'auto-suspend à 60 secondes. Sans
auto-suspend, l'entrepôt resterait allumé entre deux runs et la facture serait
sans rapport avec le travail réellement effectué.

## OBS-46. L'installation des dépendances comme test de non-régression

L'étage Snowflake installe `requirements-snowflake.txt` en entier, dbt compris,
alors que la recette n'utilise que Snowpark et le connecteur. C'est délibéré et
ce n'est pas de la paresse : la résolution conjointe de Snowpark et de dbt
avait échoué à plusieurs reprises le 20/08/2026, sur `pandas` puis sur
`python-dotenv`. Refaire cette résolution à chaque run est en soi une
vérification que l'épinglage tient toujours.

Le coût est d'environ deux minutes par run, mis en cache par `actions/setup-python`.
C'est un arbitrage assumé : deux minutes de CI contre la certitude que
l'environnement d'outillage documenté est encore installable.

---

# Session 6, 27 août 2026

## OBS-47. Le tampon Kafka a rendu une collecte vieille de sept jours

Preuve non cherchée, et la meilleure de la session.

Au premier run du nouveau DAG d'ingestion, le consommateur a rapporté
`records_in = 30` alors que le producteur venait d'en publier 15. Vérification
en base :

```
      collecte       | evenements |      ecrit_le
---------------------+------------+---------------------
 2026-08-27 09:22:12 |         15 | 2026-08-27 09:22:54
 2026-08-20 12:36:09 |         15 | 2026-08-27 09:22:54
```

Quinze événements collectés le **20 août à 12h36** ont été écrits en base le
**27 août à 09h22**, sept jours plus tard. Ils étaient restés dans Kafka tout
ce temps, parce que le consommateur n'avait jamais tourné après cette collecte.
Aucun n'a été perdu.

C'est exactement ce que la documentation du DAG affirme sur le rôle du tampon,
démontré sans l'avoir organisé. La phrase « si PostgreSQL est indisponible, les
messages restent dans Kafka et le run suivant les reprend » n'est plus une
affirmation de conception : elle a été vérifiée sur une interruption réelle de
sept jours.

Note d'honnêteté : la cause de l'interruption n'était pas une panne de
PostgreSQL mais l'absence d'ordonnancement, c'est-à-dire le trou que cette
session comble. Le mécanisme démontré est le bon, la circonstance était moins
glorieuse.

## OBS-48. `--depuis-le-debut` ne veut pas dire ce que son nom suggère

Le drapeau pilote `auto_offset_reset`, que Kafka ne consulte **que** lorsque le
groupe de consommation n'a aucun offset validé. Il ne relit donc pas tout à
chaque passage : il décide seulement où commencer la toute première fois.

La conséquence pratique est inverse de l'intuition. Sans lui, la valeur par
défaut `latest` positionne un groupe neuf **après** les messages déjà présents.
Le premier run après une remise à zéro du broker publierait quinze messages,
sauterait par-dessus, et n'écrirait rien. Le DAG se terminerait en succès avec
zéro ligne.

`earliest` est donc le défaut sûr pour une chaîne qui ne doit rien perdre, et
`latest` le défaut sûr pour un tableau de bord qui ne veut que le présent. Le
nom de l'option décrit son implémentation, pas son intention.

## OBS-49. La CI ne vérifiait qu'un DAG sur trois, et personne ne l'avait vu

L'étage d'intégrité de la chaîne d'intégration continue se terminait par :

```
airflow dags list | grep -q gamelens_promotion_gold
```

Écrit à l'époque où c'était le seul DAG du projet. Depuis, `gamelens_supervision`
puis `gamelens_ingestion_temps_reel` se sont ajoutés, et **aucun des deux n'était
contrôlé**. Un DAG de supervision cassé serait passé au vert.

C'est la même famille de défaut qu'OBS-32, sous une autre forme. Là, une
assertion par comptage s'ajustait à chaque évolution et n'enregistrait plus
qu'un état. Ici, une assertion nommée est restée juste mais a cessé d'être
complète. Les deux ont la même origine : un contrôle écrit pour l'état du
projet à un instant donné, que rien n'oblige à suivre son évolution.

Corrigé par une liste explicite en variable d'environnement, et **testé en
négatif** : avec un nom de DAG inexistant, le contrôle sort en code 1 avec le
message attendu. Un contrôle qu'on étend sans vérifier qu'il sait encore
échouer n'est pas un contrôle étendu, c'est un contrôle qu'on espère.

## OBS-50. La plateforme a refermé ses cinq alertes toute seule

Enchaînement observé, sans intervention entre les étapes autres que le
déclenchement des DAG :

| Moment | Fraîcheur | Complétude | Latence p95 | Retard Gold | Alertes |
|---|---|---|---|---|---|
| Avant | 8505 min | 0 % | inconnue | 6 j | **5 ouvertes** |
| Après ingestion | 4,4 min | 100 % | 42 s | 7 j | 1 ouverte |
| Après promotion | 1,0 min | 100 % | 42 s | 0 j | **0 ouverte** |

Les quatre premières alertes se sont fermées à la seule évaluation suivante des
règles, sans action dédiée : le moteur constate le retour sous seuil et
renseigne `resolue_le`. La cinquième a suivi après la promotion.

Le journal d'alertes fournit désormais de vraies durées d'incident, ce qui
manquait pour écrire la feuille de route d'exploitation (C4.3.2) :

| Règle | Durée d'ouverture |
|---|---|
| `fraicheur_frequentation` | 6 j 20 h 26 min |
| `completude_collecte` | 1 j 00 h 34 min |
| `latence_pipeline` | 1 j 00 h 34 min |
| `composant_muet` | 1 j 00 h 34 min |

Ces chiffres ne flattent personne, et c'est ce qui les rend utilisables : ils
mesurent une plateforme réellement laissée sans surveillance, pas une
démonstration préparée.

## OBS-51. Orchestrer du temps réel commence par admettre que ce n'en est pas

La question qui bloquait cette session n'était pas technique. Elle était de
savoir ce qu'on orchestre au juste : on n'exécute pas une boucle infinie sous
un ordonnanceur batch.

Le déblocage est venu en regardant la source plutôt que l'outil.
`GetNumberOfCurrentPlayers` rend la valeur d'un compteur à l'instant de
l'appel. Il n'y a pas de flux à consommer, il y a un capteur à interroger. Le
« temps réel » de GameLens est un **échantillonnage périodique**, et un
échantillonnage périodique se planifie sans le moindre contresens.

Corollaire immédiat, qui n'était pas visible avant ce recadrage : `catchup`
devient dangereux et pas seulement inutile. Rattraper le run de 03h15
consisterait à interroger Steam maintenant et à estampiller le résultat à
03h15, c'est-à-dire à fabriquer de l'histoire fausse. Un échantillon manqué est
perdu, c'est une propriété de la donnée et non un défaut du pipeline.

La leçon est de méthode : nommer correctement ce qu'on manipule débloque des
décisions de conception que le vocabulaire hérité rendait insolubles.

## OBS-52. La supervision a validé le correctif d'INC-008 sans qu'on le lui demande

En fin de session, un dernier passage de la synthèse laissait une alerte
ouverte alors que les cinq indicateurs venaient de repasser au nominal :

```
 regle             | severite | declenchee_le       | message
-------------------+----------+---------------------+---------------------------------
 echecs_composants | critique | 2026-08-27 09:45:02 | 1 execution(s) en echec sur 24h
```

Elle est déclenchée par la panne de broker provoquée volontairement pour le
test négatif TING-04. Rien d'anormal : une exécution a bien échoué dans les
dernières 24 heures, la règle le dit.

Ce qui mérite d'être noté, c'est que **cette alerte n'aurait pas pu se
déclencher deux heures plus tôt**. La règle `echecs_composants` compte les
lignes de `speed.pipeline_runs` en statut `failed`. Avant la correction
d'INC-008, une panne de broker n'écrivait aucune ligne : la règle comptait
zéro, et une panne totale de la collecte passait sous son radar.

Le correctif n'a donc pas seulement rendu la panne traçable, il a rendu
opérante une règle de supervision qui existait déjà et ne pouvait rien voir.
On avait écrit la règle, on avait écrit le traçage, et les deux étaient
corrects. Ils n'étaient simplement jamais reliés dans le seul cas qui compte.

C'est une variante d'un motif qui revient dans ce projet : deux composants
justes pris séparément, dont la combinaison ne fait pas ce qu'on croit. Le
garde-fou inatteignable d'OBS-42 en était déjà un cas. Aucune relecture de code
ne les signale, puisqu'il n'y a rien de faux à lire. Seule une mise en
situation les révèle.

## OBS-53. Le commentaire décrivait un chemin d'erreur que Steam n'emprunte pas

`steam_producer.py` portait depuis l'origine ce commentaire :

> `result == 1` signale une réponse exploitable côté Steam ; toute autre valeur
> accompagne une réponse HTTP 200 sans donnée utile.

En éprouvant le chemin de rejet sur un identifiant volontairement inexistant,
Steam a répondu **404**, pas 200 :

```
HTTPError: 404 Client Error: Not Found for url:
https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=999999999
```

Le rejet réel passe donc par `raise_for_status()` et l'exception réseau, pas
par la branche `result != 1` que le commentaire décrivait. Cette branche
existe, elle est testée, et rien ne prouve qu'elle soit jamais empruntée en
production.

Ce n'est pas grave : les deux chemins archivent désormais. Mais le commentaire
énonçait avec assurance un comportement de fournisseur qui n'avait jamais été
vérifié, exactement le travers corrigé sur les contraintes Snowflake en
session 4. Un commentaire qui décrit le comportement d'un tiers vaut ce que
vaut la dernière fois où on l'a mis à l'épreuve.

## OBS-54. Archiver révèle ce que l'on jetait

La couche Bronze a rendu visible la perte, jusque-là invisible parce que
personne ne regardait ce qui n'existait plus. Première réponse tarifaire
archivée :

```json
{"1145360": {"data": {"price_overview": {
    "final": 2450, "initial": 2450, "currency": "EUR",
    "final_formatted": "24,50€", "discount_percent": 0,
    "initial_formatted": ""
}}, "success": true}}
```

`final_formatted` et `initial_formatted` étaient jetés. Ils ne servent à rien
aujourd'hui. Le jour où une question se pose sur l'affichage régional d'un
prix, ils auraient manqué, et personne n'aurait su qu'ils avaient existé.

C'est le renversement propre à Bronze : on ne conserve pas ce dont on a besoin,
on conserve ce dont on ignore encore avoir besoin. Tant qu'on n'archive pas, la
question « qu'est-ce qu'on perd ? » est structurellement impossible à poser.

## OBS-55. Le coût de l'archive, chiffré plutôt que redouté

L'objection réflexe à une couche Bronze est le volume. Mesuré sur les données
réelles plutôt qu'estimé :

| Source | Octets moyens par réponse |
|---|---|
| `steam_player_count` | 78 |
| `steam_appdetails` | 238 |

À la cadence en place, 15 titres toutes les 15 minutes pour la fréquentation et
une fois par jour pour les tarifs, cela donne environ **114 Ko par jour**, soit
**41 Mo par an**. Sur une base qui héberge déjà les métadonnées d'Airflow, c'est
sous le seuil du remarquable.

La conclusion utile n'est pas « c'est petit ». C'est qu'une objection de volume
formulée sans mesure ne vaut rien, et qu'il suffisait de trois minutes pour la
trancher. Le calcul est refait dans la feuille de route, où il conditionne la
politique de conservation.

## OBS-56. Une archive qu'on nettoie n'est plus une archive

Le test du chemin de rejet a laissé dans `bronze.reponses_brutes` une ligne
concernant l'appid 999999999, qui n'appartient pas au panel suivi. Elle fait
tomber le taux d'exploitabilité affiché à 96,9 % au lieu de 100 %.

Réflexe naturel : supprimer la ligne pour que la démonstration soit propre.
Décision retenue : la garder.

Trois raisons. Elle est vraie, l'appel a réellement eu lieu à cet instant. Le
schéma vient d'être écrit avec l'argument qu'une archive modifiable n'est plus
une archive, et n'accorde d'ailleurs aucun droit de suppression à
`etl_service` : contourner cette règle en tant que propriétaire pour des
raisons cosmétiques la viderait de son sens dès le premier jour. Enfin, cette
ligne est le seul exemple vivant du chemin de rejet, et un taux à 96,9 %
raconte mieux le fonctionnement de la vue qu'un 100 % lisse.

Le nettoyage de la couche Bronze est un sujet réel, mais il s'appelle politique
de conservation, il se décide à l'avance, et il s'applique par ancienneté et
non par convenance.

## OBS-57. L'entrepôt qu'on n'a pas configuré coûte presque autant que celui qu'on a optimisé

Relevé de consommation Snowflake, du 20 au 27/08/2026 :

| Entrepôt virtuel | Crédits | Part |
|---|---|---|
| `GAMELENS_WH` | 0,5805 | 57 % |
| `COMPUTE_WH` | 0,4372 | **43 %** |
| `CLOUD_SERVICES_ONLY` | 0,0004 | traces |

`GAMELENS_WH` a été dimensionné en XS avec suspension automatique à 60
secondes, choix défendu depuis le Bloc 1 comme une mesure d'économie.
`COMPUTE_WH` est l'entrepôt par défaut du compte, que personne n'a configuré et
qui sert aux sessions Snowsight ouvertes à la main. Il a consommé presque
autant.

Autrement dit, l'optimisation soignée a porté sur 57 % de la dépense, et les
43 % restants venaient d'un objet qu'on n'avait jamais regardé parce qu'on ne
l'avait pas créé.

C'est une leçon d'exploitation générale : **le poste de coût qu'on optimise
n'est pas toujours celui qui coûte**. Le réflexe à prendre est de mesurer la
répartition avant d'optimiser, pas après. Trois minutes de requête auraient
suffi et personne ne les avait passées, faute d'avoir eu la curiosité de
regarder ailleurs que sur l'objet dont on était fier.

Conséquence pratique, inscrite dans la feuille de route : la consommation n'est
de toute façon pas le facteur limitant, c'est le calendrier des 120 jours. Mais
le raisonnement, lui, se transpose partout.

## OBS-58. Le premier poste de croissance n'appartient à personne

Mesures de volumétrie du 27/08/2026 :

| Base | Taille | Contenu |
|---|---|---|
| `gamelens` | 8,6 Mo | Silver, Gold et Bronze, toute la donnée du produit |
| `airflow` | **12 Mo** | métadonnées d'orchestration, aucune donnée du produit |

La base de métadonnées d'Airflow est **plus grosse que la base métier**, et
c'est de loin le premier poste de croissance : environ 486 instances de tâches
par jour à 4,6 Ko de métadonnées chacune, soit 2,2 Mo par jour, environ 0,8 Go
par an. À comparer aux 41 Mo par an de la couche Bronze, qui avait pourtant
suscité une objection de volume.

L'intérêt de ce constat n'est pas le chiffre, il est dans la raison pour
laquelle personne ne l'avait vu : ce n'est ni de la donnée métier, ni un
composant que quelqu'un revendique. L'orchestrateur est un outil, et les
métadonnées d'un outil ne figurent sur aucune liste de ce qu'on surveille.

Le remède est banal, `airflow db clean`, et il est désormais une tâche
mensuelle. Ce qui vaut d'être retenu, c'est le mécanisme : **les postes non
attribués sont ceux qui grossissent sans témoin.**

## OBS-59. Une édition par plage de lignes a détruit une section entière

Incident d'outillage, pas de plateforme, mais assez instructif pour être noté.

En voulant remplacer un bloc de code dans la feuille de route, la recherche
s'est faite sur la première occurrence de `airflow db clean`. Or cette chaîne
apparaissait aussi, plus haut, dans une cellule de tableau décrivant la tâche
mensuelle M-1. Le remplacement a donc démarré au mauvais endroit et effacé une
section et demie.

Le fichier n'était pas encore versionné, il n'y avait donc rien à restaurer :
la section a dû être réécrite.

Deux enseignements. Le premier est banal et coûte cher quand on l'oublie :
committer un document long dès qu'il est écrit, avant de le retoucher. Le
second est plus intéressant : une ancre textuelle qui semble unique ne l'est
pas nécessairement, et le mode d'édition par plage de lignes ne prévient
jamais, contrairement au remplacement de chaîne qui échoue proprement quand la
correspondance n'est pas unique.

C'est la même famille de problème que celle qu'on traque dans le code : une
opération qui réussit silencieusement là où elle aurait dû refuser.

---

# Session 7, 27 août 2026

## OBS-60. Le générateur a mesuré l'écart avant de le combler

Avant d'écrire quoi que ce soit, une requête sur le catalogue a donné l'état
réel de la documentation des schémas :

```
19 objets commentes sur 19
7 colonnes commentees sur 126
```

Toutes les tables et vues étaient décrites, presque aucune colonne. L'écart
n'était pas visible en lisant les fichiers SQL, où les quelques commentaires
existants donnaient l'impression d'un travail fait.

C'est le premier bénéfice de la génération, et il arrive avant la première
ligne générée : **poser la question « qu'est-ce qui est documenté ? » sous forme
de requête donne une réponse chiffrée**, là où une relecture donne une
impression. La même requête a ensuite servi à trouver les quatre dernières
colonnes manquantes, toutes dans la couche Bronze écrite la veille.

État final : 78 colonnes de tables sur 78, des deux côtés, PostgreSQL et
Snowflake.

## OBS-61. Générer révèle ce qu'écrire à la main aurait masqué

Le dictionnaire Snowflake a été généré une première fois avant que les colonnes
ne soient documentées. Il a rendu ceci :

```
Colonnes de tables sans description : 24.
```

Vingt-quatre colonnes sur vingt-neuf. Le fichier de schéma
`sql/schema_gold_snowflake.sql` portait bien quelques `COMMENT` en ligne, ce qui
donnait l'impression rassurante d'un schéma documenté.

Un dictionnaire écrit à la main n'aurait jamais produit ce chiffre : on aurait
décrit les colonnes en les recopiant, et le résultat aurait paru complet sans
qu'aucun de ces textes ne se trouve dans la base. Autrement dit, la
documentation aurait existé **à côté** du schéma plutôt que dedans, et rien
n'aurait signalé la différence.

Le générateur compte ce qui manque et l'écrit en bas du fichier. Une case vide
est un manque déclaré ; une case remplie à la main dans un document séparé est
une affirmation invérifiable.

## OBS-62. Un fichier généré doit exclure sa propre date de génération

Détail de conception qui aurait fait échouer le contrôle de non-régression.

La première intention était d'horodater le dictionnaire, « généré le
27/08/2026 à 12h42 ». Or la CI régénère le fichier et le compare à celui du
dépôt : avec un horodatage, la comparaison aurait échoué **à chaque exécution**,
sans qu'aucun schéma n'ait bougé.

Un contrôle qui échoue pour une raison sans rapport avec ce qu'il vérifie finit
désactivé dans la semaine. La date est donc affichée par le programme, dans sa
sortie console, et absente du fichier.

La règle générale : **tout ce qui varie sans que le sujet varie doit sortir de
l'artefact comparé.** C'est le même raisonnement que celui qui a fait remplacer
les assertions par comptage par des vérifications d'objets nommés (OBS-32), et
il se transpose partout où l'on compare deux états.

## OBS-63. Deux documents qui se contredisaient sur la même procédure

En rédigeant la section d'installation de la documentation technique, une
contradiction est apparue avec le `README.md` : ordre inverse entre
`create_topics.py` et `seed_game_mapping.py`, et un commentaire du README
annonçant « PostgreSQL + Kafka » là où `docker compose up -d` démarre en réalité
sept conteneurs depuis l'ajout d'Airflow et de Grafana.

Aucune des deux versions n'était fausse au moment où elle avait été écrite. Le
README a simplement vieilli sans que rien ne le signale.

C'est exactement le mécanisme que la documentation technique prétend éviter, et
il s'est manifesté pendant sa rédaction. D'où la section liminaire « ce que ce
document ne contient pas, et où ça vit », qui désigne pour chaque sujet **une
seule source faisant foi**, et la règle explicite : en cas de contradiction,
c'est la source qui gagne et ce document qui se corrige.

La leçon opérationnelle : la duplication ne se combat pas par la vigilance, qui
s'épuise, mais par une règle d'arbitrage écrite et par la génération partout où
elle est possible.

# Session 8, 27 août 2026

## OBS-64. Tout était prêt sauf le projet lui-même

En ouvrant le chantier dbt, l'inventaire de l'existant a donné ceci :
`dbt-core` et `dbt-snowflake` épinglés dans `requirements-snowflake.txt` et
**installés à chaque run de CI** depuis des jours ; `.gitignore` prévoyant déjà
`dbt/target/`, `dbt/dbt_packages/` et `dbt/logs/` ; le Dockerfile d'outillage
posant `DBT_PROFILES_DIR=/projet/dbt` et installant `git` avec le commentaire
« requis par dbt pour les packages » ; `docker-compose.yml` montant `./dbt` en
écriture ; et les commentaires de colonnes de `sql/schema_gold_snowflake.sql`
nommant les tests attendus, colonne par colonne : « valeur contrôlée par test
dbt `accepted_values` », « vérifié par test dbt `expression_is_true` ».

Le répertoire `dbt/` était vide.

L'observation intéressante n'est pas l'oubli, c'est sa signature. Un composant
**annoncé mais jamais construit** laisse plus de traces qu'un composant dont
personne n'a parlé, et ces traces le font passer pour fait. Les dépendances
étaient résolues, l'image était bâtie, la CI les installait : tous les signaux
que l'on regarde d'habitude pour savoir si une brique existe étaient au vert.
Le seul contrôle qui aurait tranché, c'est celui qui manquait, à savoir
l'exécution.

C'est la même leçon qu'OBS-32, formulée autrement : ce qui n'est pas exécuté
n'est pas su. Et ici, l'écart était visible depuis le dépôt, à condition de
comparer ce que l'architecture affirme au présent avec ce que les fichiers
contiennent.

## OBS-65. Garder deux filets n'était pas de la prudence

Le choix de conserver `entrepot/verifier_gold.py` en plus des contrats dbt a
été discuté avant d'écrire quoi que ce soit. L'argument contre était solide :
deux autorités sur un même fait divergent tôt ou tard, c'est le mécanisme
d'OBS-63, et la recommandation initiale était de faire de dbt l'autorité unique.

L'arbitrage a été de garder les deux, en rendant leur accord **testé plutôt que
déclaré** : les étapes 9 et 10 de la recette les confrontent au même jeu de
données fautif et exigent que les deux tombent.

Le résultat de cette exécution n'était pas prévu. Sur les quatre violations que
Snowflake laisse entrer, le filet applicatif en rattrape **4** et dbt en
rattrape **5**.

Le cinquième est le test d'unicité posé sur la vue `v_popularity_dashboard`. Un
doublon sur `(game_id, day)` dans la table de faits ne se contente pas de
dupliquer une ligne de faits : il duplique **chaque journée au travers de la
jointure** de la vue. `verifier_gold.py` n'interroge que les tables et ne peut
pas voir ce gonflement.

Autrement dit, le test destiné à surveiller la coexistence des deux filets a
démontré au passage qu'ils n'étaient pas redondants. La décision était bonne
pour une raison que personne n'avait formulée en la prenant.

## OBS-66. Deux modes d'authentification ne tiennent pas dans un seul profil

`entrepot/connexion_snowflake.py` gère les deux façons de présenter la clé privée RSA
dans une seule fonction, par une cascade de `if` : chemin de fichier en local,
contenu PEM en intégration continue. La transposition naturelle en YAML aurait
été un bloc unique portant les deux champs, chacun renvoyant à sa variable.

Elle ne marche pas, et pour une raison qui ne saute pas aux yeux.
`dbt-snowflake` refuse `private_key` et `private_key_path` renseignés ensemble.
Or `env_var('SNOWFLAKE_PRIVATE_KEY')` sur une variable absente ne rend pas un
champ absent : il rend un champ **présent et vide**, ce qui déclenche exactement
ce refus. Un fichier de configuration déclaratif n'a pas d'équivalent du `elif`.

D'où deux cibles distinctes dans `dbt/profiles.yml`, `local` et `ci`, et une
fonction `_cible_dbt()` qui **déduit** laquelle utiliser du mode
d'authentification présent, plutôt que de laisser l'appelant la choisir. Laisser
le choix à l'appelant aurait suffi à ce qu'un jour la CI vise la cible locale et
échoue sur un fichier de clé absent, avec un message parlant de format PEM.

La leçon générale : ce qui s'exprime par une condition dans du code doit
souvent s'exprimer par une **variante nommée** dans de la configuration. Ce
n'est pas la même chose, et la traduction n'est pas mécanique.

## OBS-67. Deux pièges de dbt trouvés en une heure

Aucun des deux n'est grave, les deux coûtent du temps parce que le message
d'erreur ne désigne pas la cause.

**Un commentaire Jinja dans un appel de fonction.** Documenter chaque option à
l'intérieur du bloc `config(...)` du modèle, ce qui paraît le meilleur endroit
pour le faire, produit `invalid syntax for function call expression`. Les
commentaires doivent sortir de l'appel. La documentation est donc juste
au-dessus du code qu'elle explique, et non dedans.

**La concaténation du schéma.** Écrire `+schema: mart` dans `dbt_project.yml`
alors que la cible pointe déjà `mart` ne donne pas `mart` : dbt **concatène** le
schéma personnalisé à celui de la cible et produit `mart_mart`. Le schéma est
donc porté par le profil seul, ce qui est de toute façon plus juste : il dépend
de l'endroit où l'on se connecte, pas du modèle.

## OBS-68. Un diff de 67 lignes pour un ajout de 7

Les modifications de fichiers faites depuis Python sur ce poste ont converti
`docker/snowflake/Dockerfile` de LF vers CRLF, parce que `Path.write_text`
traduit les fins de ligne selon la plateforme. Git a présenté un fichier
entièrement réécrit, 37 ajouts et 30 suppressions, là où le changement réel
tenait en 7 lignes. Un peu plus tard, `write_bytes` a produit l'erreur inverse
sur `entrepot/recette_ci.py`.

Le dépôt n'a pas de `.gitattributes` et `core.autocrlf` vaut `false` : chaque
fichier est donc versionné avec les fins de ligne qu'il avait le jour de son
premier commit, et le dépôt en mélange les deux sortes sans que ce soit visible.

Corrigé en normalisant chaque fichier modifié sur ce que `git show HEAD:` en
contient. La conséquence pratique dépasse l'esthétique du diff : une revue qui
voit un fichier entièrement réécrit ne lit pas le changement, elle le survole.
Un bruit de cette nature n'est pas neutre, il annule la relecture.

# Session 9, 31 août 2026 : contrôle de cohérence

## OBS-69. L'obstacle que j'avais déduit n'existait pas

En cherchant pourquoi aucun DAG n'alimente la couche Gold Snowflake, la réponse
m'a paru évidente avant d'être vérifiée : DA-08 isole les jeux de dépendances,
Snowpark exige `snowflake-connector-python` 4.x qui entre en conflit avec le
reste, donc l'image Airflow ne peut pas l'embarquer, donc orchestrer la
promotion supposerait un `DockerOperator` ou une image remaniée. Un raisonnement
propre, appuyé sur un principe d'architecture réel et documenté.

Il est faux. L'image Airflow contient déjà :

| Paquet | Version |
|---|---|
| `apache-airflow-providers-snowflake` | 6.10.0 |
| `snowflake-snowpark-python` | 1.47.0 |
| `snowflake-connector-python` | 4.0.0 |
| `pandas` | 2.3.3 |
| `pyarrow` | 18.1.0 |

Aucune ligne du `Dockerfile` ne les installe. Ils viennent de l'image de base
`apache/airflow:3.1.8`, qui embarque un large jeu de fournisseurs.

Ce qui rend l'erreur intéressante, c'est sa forme. Je n'ai pas ignoré un fait :
j'ai **déduit une contrainte à partir d'un principe** au lieu de la constater.
Le principe était juste, le conflit de dépendances est réel et documenté, mais
il ne s'appliquait pas ici parce que quelqu'un d'autre l'avait déjà résolu en
amont. Une déduction correcte à partir d'une prémisse vraie peut donner un
résultat faux quand la prémisse ne couvre pas le cas.

La commande qui a tranché tient en une ligne, et elle aurait dû venir avant le
raisonnement :

```bash
docker exec gamelens-airflow-scheduler python -c "
from importlib.metadata import distributions
print([d.metadata['Name'] for d in distributions()
       if 'snowflake' in (d.metadata['Name'] or '').lower()])"
```

## OBS-70. Un mot dans un commentaire a fabriqué un angle mort

La vue `speed.v_indicateur_gold` portait ce commentaire dans le catalogue :
« Fraîcheur de **l'entrepôt**. » Et la règle d'alerte associée émettait :
« **L'entrepôt Gold** accuse N jours de retard. »

Or cette vue lit `mart.*` de **PostgreSQL**, que l'architecture désigne partout
comme le *prototype*. L'entrepôt, dans le vocabulaire du projet, c'est
Snowflake. Deux textes, écrits sans intention de tromper, ont suffi à faire
croire pendant onze jours que la couche cible était surveillée.

La démonstration est involontaire et datée. Le 31/08/2026 à 08h25, la règle
s'est déclenchée sur **4 jours** de retard côté PostgreSQL et s'est refermée
seule à 08h45. Au même instant, la couche Snowflake accusait **11 jours** de
retard. Rien ne l'a signalé : aucun indicateur ne la regarde.

Le défaut n'est pas dans le code, qui fait exactement ce qu'il dit faire. Il est
dans un nom. C'est la même famille qu'OBS-32, où une assertion par comptage
passait au vert sans rien prouver : un dispositif qui a l'air de couvrir plus
qu'il ne couvre est plus dangereux qu'un dispositif absent, parce que son
silence est lu comme une bonne nouvelle.

## OBS-71. Quatre jours d'arrêt ont produit la meilleure preuve de supervision du projet

Entre le 27/08 en fin d'après-midi et le 31/08 au matin, le poste est resté
éteint. Personne ne l'avait prévu comme un test, et c'en est un meilleur que
ceux qu'on organise : les tests provoqués ont une durée choisie et un opérateur
qui regarde.

Ce que la plateforme a fait toute seule, relevé dans `speed.alertes` :

| Heure | Événement |
|---|---|
| 08:25:07 | 5 règles se déclenchent d'un coup à la reprise |
| 08:30:01 | 4 se referment, soit **4 min 53 s** après |
| 08:45:01 | la cinquième se referme, soit **19 min 54 s** après |

La règle de fraîcheur a mesuré **5 350,1 minutes** depuis la dernière collecte,
pour un seuil de 90, soit 3 jours 17 heures. La complétude est tombée à 0 %,
deux composants ont été déclarés muets, et le retard de la couche Gold est monté
à 4 jours.

Aucune intervention humaine. Aucune commande tapée. Les alertes se sont ouvertes
sur constat et refermées sur rattrapage.

**Le détail qui apprend quelque chose**, et qui aurait été invisible dans un
test provoqué : les cinq alertes ne se referment pas ensemble. Quatre se ferment
en cinq minutes, celle du retard d'entrepôt met vingt minutes. L'écart n'est pas
un défaut, il **mesure la cadence de ce qui est surveillé** : la collecte
reprend au quart d'heure, la promotion vers Gold suit son propre rythme. Le
temps de fermeture d'une alerte renseigne donc sur la chose surveillée autant
que sur le dispositif qui surveille.

Une réserve, et elle est sérieuse : ces cinq alertes se sont ouvertes et
refermées sans que personne ne soit prévenu. Si elles ne s'étaient pas
refermées, rien n'aurait changé dans l'expérience de l'exploitant. C'est V-02,
chiffré une fois de plus.

## OBS-72. Le fichier écrit pour éviter les redécouvertes se contredisait lui-même

`CLAUDE.md` existe pour qu'on ne redécouvre pas ce qui a déjà été établi. Au
31/08, il contenait deux affirmations incompatibles, à environ quarante lignes
l'une de l'autre :

- section « Faits d'environnement » : compte Snowflake `RTZSXDV-PM63908`,
  **120 jours et 400 dollars de crédits**, en service ;
- section « Note de calendrier » : compte d'essai **à recréer**, essai de
  **30 jours**, recréation **volontairement différée** jusqu'à ce que les
  modèles dbt soient prêts.

La seconde était vraie le 19/08 et fausse depuis le 20. Elle a survécu à huit
sessions et à une dizaine de mises à jour du même fichier.

La cause est mécanique et vaut d'être retenue : **un fichier de référence ne se
lit jamais en entier.** On y ajoute une section, on corrige celle qu'on
consulte, et les paragraphes qu'on ne consulte pas vieillissent sans que rien
ne les touche. La discipline de mise à jour à chaque session, réelle ici, ne
protège que les parties qu'on relit.

C'est le même mécanisme qu'OBS-63, où deux documents décrivaient une procédure
dans deux ordres différents, et qu'OBS-64, où un composant annoncé passait pour
construit. Trois occurrences du même défaut en trois sessions, sur trois
supports différents. La réponse qui a fonctionné jusqu'ici est la génération
(DA-09) et la règle d'arbitrage écrite ; celle qui manque encore est un contrôle
mécanique de cohérence interne, du genre de ceux passés ici à la main.

**Une confirmation immédiate, pendant la correction elle-même.** `CLAUDE.md`
annonçait « `documentation_technique.md`, 600 lignes » quand le fichier en
faisait 679. Le chiffre corrigé à 679 était faux vingt minutes plus tard, à 697,
du seul fait des corrections en cours. Il a donc été **supprimé** plutôt que mis
à jour : la structure d'un document se décrit, sa taille se mesure. C'est la
règle d'OBS-62, où un fichier généré devait exclure sa propre date de
génération, appliquée cette fois à de la prose. Tout ce qui varie sans que le
sujet varie doit sortir de ce qu'on affirme.

# Session 10, 31 août 2026 : ordonnancement de la promotion Snowflake

## OBS-73. La panne n'a pas touché ce que le changement touchait

Le changement consistait à donner aux conteneurs Airflow l'accès au répertoire
`entrepot/`, pour qu'un DAG puisse appeler la promotion Snowpark. Le résultat
immédiat a été conforme : exécutée à la main dans le conteneur, la promotion a
fonctionné du premier coup, sur une version de Snowpark pourtant plus ancienne
que celle de la chaîne d'intégration.

Ce qui est tombé, douze minutes plus tard, c'est l'**interface web**.

Le module `entrepot/connexion.py`, renommé `connexion_snowflake.py` depuis,
portait le nom d'un paquet PyPI réel, `connexion`, dont Airflow se sert pour son
authentification. Les entrées de
`PYTHONPATH` passant avant `site-packages`, tout `import connexion` du
processus, y compris ceux d'Airflow, atteignait désormais notre fichier. Détail
complet en INC-009.

Trois choses valent d'être retenues, et aucune n'est le bug lui-même.

**La panne était orthogonale au changement.** Rien dans « appeler une promotion
depuis un DAG » ne laisse présager « l'interface d'administration ne démarre
plus ». Une revue de ce changement, même attentive, n'aurait pas cherché là.

**Le message d'erreur était excellent.** `cannot import name 'FlaskApi' from
'connexion' (/opt/gamelens/entrepot/connexion.py)` nomme le fichier fautif entre
parenthèses. L'investigation a duré trois commandes. Ce n'est pas toujours le
cas, et c'est ce qui a fait la différence entre un incident de dix minutes et
un après-midi perdu.

**Le traitement n'a rien vu.** Le planificateur n'a pas besoin du gestionnaire
d'authentification : le DAG a tourné, la donnée est arrivée dans l'entrepôt,
pendant que l'écran permettant de le constater refusait de s'allumer. La
supervision, construite autour des traitements, n'a évidemment rien signalé.

La règle générale qui en sort dépasse ce projet : **ajouter un répertoire au
`PYTHONPATH` n'est pas une opération additive.** Elle peut retirer l'accès à
des modules qui fonctionnaient, dans des composants sans rapport avec le
changement.

## OBS-74. Une règle d'alerte calibrée sur une cadence devient fausse pour une autre

La règle `composant_muet` vérifiait qu'aucun composant attendu n'était resté
silencieux plus de 24 heures. Elle a été écrite quand les trois composants
attendus tournaient au quart d'heure, et elle était juste.

Y ajouter `snowpark_promotion`, qui tourne une fois par jour, l'aurait rendue
fausse : deux exécutions quotidiennes successives sont espacées d'exactement
24 heures, donc la fenêtre expire juste avant que la suivante ne l'alimente. La
règle se serait déclenchée chaque matin sur un système parfaitement sain.

Le plus intéressant est la forme qu'aurait prise ce défaut. L'alerte se serait
**refermée toute seule** au bout de quelques minutes, à l'exécution suivante.
Elle aurait donc produit, chaque jour, une alerte brève et auto-résolue,
strictement indiscernable d'un vrai incident passager. Pas de fausse alerte
bruyante que l'on finit par corriger : un bruit de fond quotidien qui use
l'attention et qui, le jour d'un vrai problème, se confond avec lui.

Corrigé en portant la fenêtre sur chaque composant plutôt que sur la règle :
24 heures pour les collectes, 26 pour les traitements quotidiens. Le même
défaut existait déjà, non détecté, pour `steam_prices`, quotidien depuis la
session 6 et surveillé par une fenêtre de 24 heures.

Ce qu'il faut retenir : **un seuil de supervision porte une hypothèse implicite
sur la cadence de ce qu'il surveille.** Ajouter un composant à une règle
existante, ce n'est pas allonger une liste, c'est vérifier que l'hypothèse tient
encore pour le nouveau venu.
## OBS-75. Le contrôle de cohérence a démenti une phrase écrite deux heures plus tôt

Le DAG de promotion Snowflake a été planifié à 03h00, une demi-heure après celui
de PostgreSQL, et j'en ai tiré une conclusion écrite dans quatre fichiers : les
deux couches portant la même journée, **un écart entre elles désignerait un
défaut**.

Le contrôle de cohérence qui a suivi, deux heures après, a mesuré ceci :

| | PostgreSQL | Snowflake |
|---|---|---|
| Faits de popularité | 45 | **60** |
| Tarifs | 120 | **165** |
| Retard | 0 j | 0 j |
| Journées présentes | 20, 27, 31/08 | **19**, 20, 27, 31/08 |

Les deux couches sont à jour et ne contiennent pas la même chose. La raison est
dans la stratégie d'écriture, pas dans une panne : la promotion PostgreSQL
traite **une journée par exécution**, celle de Snowpark rejoue **tout
l'historique disponible** par MERGE. La seconde est donc rattrapante, et elle a
récupéré le 19/08, journée présente en couche Silver mais pour laquelle aucune
exécution datée n'a jamais eu lieu côté PostgreSQL.

Ce qui est instructif n'est pas l'erreur, qui est mineure et corrigée, mais son
moment. La phrase était fausse au moment où je l'écrivais, et elle était
vérifiable en deux requêtes. Elle a été écrite parce qu'elle **découlait
proprement** du raisonnement sur le décalage horaire, et un raisonnement propre
donne l'impression d'un fait établi.

C'est la même forme qu'OBS-69, où j'avais déduit d'un principe d'architecture
qu'un obstacle existait, sans le constater. Deux fois en une journée, la même
faute : **une conclusion correctement déduite prend le statut d'une observation
alors qu'elle n'en est pas une.** Le seul remède qui ait fonctionné, les deux
fois, est la commande qui mesure.

Corollaire utile pour la soutenance : les deux couches ne sont pas
interchangeables, et une question du jury du type « les deux contiennent-elles
la même chose ? » a une réponse précise et chiffrée, qui n'est pas oui.

---

# Session 11, 31 août 2026 : rapport d'analyse et remise à plat des README

Objet : écrire le rapport d'analyse A4.1, puis relire les trois fichiers qui
disent au lecteur où en est le projet.

## OBS-76. Le journal des commandes avait cessé d'être rejouable, et c'est sa seule raison d'être

INC-009 avait renommé `entrepot/connexion.py` en `connexion_snowflake.py` cinq
heures plus tôt. Le renommage a été propagé dans le code, dans les DAG et dans
la documentation technique. Trois blocs de `docs/commandes_successives.md`
portaient encore `from connexion import connexion`, dont un étiqueté **« à
rejouer avant toute démonstration »**.

Le mode de défaillance mérite d'être nommé, parce qu'il n'a rien d'accidentel :
**un document dont la valeur est la rejouabilité ne signale jamais qu'il a cessé
d'être rejouable**, précisément parce que personne ne le rejoue entre deux
besoins. Le code casse à l'exécution suivante ; une procédure écrite attend son
heure, et son heure est en général le pire moment.

Le contraste avec les dictionnaires de `docs/annexes/` est instructif. Eux non
plus ne sont pas relus, mais la CI les compare au catalogue vivant à chaque
push : ils ne peuvent pas dériver de plus d'un commit. Ce journal n'a pas
d'équivalent et n'en aura probablement pas, parce que rejouer une procédure
suppose l'infrastructure allumée.

Les trois blocs corrigés, la procédure a été rejouée pour de bon : 15 dim_games,
60 faits de popularité, 165 tarifs. Elle marche. Elle n'aurait pas marché le
jour de la soutenance.

**Règle retenue.** Ce que la CI vérifie ne périme pas ; le reste périme en
silence. Le renommage d'un module doit donc déclencher une recherche textuelle
dans les **documents**, pas seulement dans le code.

## OBS-77. Corriger une contradiction n'avait pas déclenché la recherche des autres

La session 9 avait trouvé et corrigé la note de calendrier de `CLAUDE.md`, qui
décrivait un compte Snowflake « à recréer » alors qu'il existait depuis onze
jours et que la section des faits d'environnement, quarante lignes plus haut, le
disait (OBS-72).

Cette session-ci a trouvé le même défaut dans le même fichier, ailleurs : la
section du référentiel portait encore « À faire » sur C4.2.2 et C4.2.3, deux
compétences **éliminatoires**, exécutées et vertes en CI depuis plusieurs jours,
que le tableau d'avancement donnait pour terminées quarante lignes plus bas.

Ce qui est instructif n'est pas la contradiction, c'est qu'elle a survécu à sa
propre correction. Découvrir qu'un fichier se contredit aurait dû déclencher une
question simple, « où d'autre ? », et elle n'a pas été posée. Une correction
ponctuelle traite l'instance ; elle ne traite pas la classe.

**Conséquence pratique**, appliquée depuis : quand un défaut de cohérence est
trouvé dans un document de suivi, on relit le document entier avant de
committer, pas seulement le paragraphe fautif.

---

# Session 12, 1er et 2 septembre 2026 : le support de soutenance

Objet : construire les trente minutes de présentation. **Aucune brique nouvelle**,
et c'est le point : tout ce qui doit être montré existe déjà et a été exécuté.

## OBS-78. Le projet suivait neuf compétences, la grille en compte dix

Trois documents de cadrage dormaient dans `Certification/`, deux niveaux
au-dessus du dépôt, et n'avaient jamais été ouverts en onze sessions : les
modalités d'évaluation, le règlement spécial de certification, et surtout
l'onglet « Grille Eval spé Bloc 4 » du fichier d'évaluation.

La grille liste **dix** compétences. Le projet en suivait neuf, ayant fusionné
les deux premières sous l'étiquette « A4.1 ». Or A4.1 est le nom de
l'**activité** ; le jury coche des **compétences**, et il en coche deux là où
nous en comptions une. C4.1.2, « une présentation des composants de
l'architecture DATA », n'avait jamais été nommée.

Le contenu existait : la partie 2 de `docs/rapport_analyse.md` couvre ses quatre
critères. C'est l'étiquette qui manquait, pas le travail. Mais une compétence
qu'on ne nomme pas est une compétence qu'on ne présente pas explicitement, et le
jury coche sur ce qu'il entend.

**Ce que ça dit de la méthode.** Onze sessions de travail sérieux ont été
conduites sur une lecture de seconde main du référentiel. Lire la source a coûté
quarante minutes. Ne pas la lire aurait pu coûter une compétence.

## OBS-79. Un mot de la grille déplace toute la priorité : « présentées »

Critère de C4.2.2, verbatim : « **3 méthodes de traitement de la donnée sont
présentées.** » Pas « sont réalisées », pas « existent dans le dépôt ».

La règle de travail du projet depuis la session 1 est de ne rien documenter qui
n'ait été exécuté. Elle reste juste, et elle ne suffit plus : **une brique
construite, testée et verte en CI mais non montrée pendant les trente minutes
peut être notée non acquise**, et pour C4.2.2 elle est éliminatoire.

C'est un renversement complet de priorité à dix jours de l'oral. Ce qui reste à
faire n'est pas de construire davantage, c'est de rendre visible ce qui est
construit. Toute envie de refermer un écart gelé doit être pesée contre cette
phrase.

## OBS-80. Trente minutes pour trente et un sous-critères

Les dix compétences se déploient en 31 sous-critères explicites dans la grille.
Trente minutes de présentation. **Moins d'une minute chacun.**

Cette division interdit ce que tout le monde fait spontanément : raconter le
projet dans l'ordre où il a été construit. Un récit chronologique consacre du
temps aux débuts, qui sont les moins notés, et arrive essoufflé sur les
livrables. Le support est donc organisé sur la grille, et un tableau de
traçabilité vérifie que les 31 critères ont chacun leur diapositive.

Le budget est tenu à 27:30 de contenu et 2:30 de marge, **calculé par un script**
depuis les durées déclarées diapositive par diapositive, pas estimé à vue.

## OBS-81. Le dépôt ne contenait aucune preuve montrable

La convention du projet demande depuis la session 1 de conserver « les logs et
sorties réelles des tests et des runs, ils serviront de preuve et de matière
pour le support de soutenance ». Au moment de construire ce support,
`docs/preuves/` n'existait pas. Zéro capture, zéro sortie datée.

Tout avait été **transcrit** dans les documents de `docs/`, ce qui est utile
mais n'est pas une preuve : un tableau de résultats recopié à la main a
exactement la même apparence, qu'il soit vrai ou inventé.

Le manque a été comblé par un outil plutôt que par des commandes jetables.
`outils/capturer_preuves.py` produit dix captures portant chacune en en-tête la
date, la commande exacte, le code de sortie et les critères de la grille
qu'elles servent. Elles se rejouent, ce qui les distingue d'une copie d'écran.

**Ce qui rend l'oubli intéressant** : la convention était écrite, relue à chaque
session, et jamais appliquée. Une règle qu'aucun mécanisme ne rappelle n'est pas
une règle, c'est une intention.

## OBS-82. Le garde-fou que j'avais écrit s'est déclenché contre moi

`outils/generer_schema.py` lit les contraintes à deux endroits : le catalogue
Snowflake pour ce qui est déclaré, le DDL pour les cibles des clefs étrangères
que le catalogue n'expose pas. Les deux sources sont recoupées sur le nombre de
contraintes par type, et la génération **s'arrête** si elles divergent.

Elle s'est arrêtée. La divergence venait de mon propre comptage, qui lisait les
lignes du DDL sans en retirer les commentaires SQL : une contrainte citée dans
un commentaire était comptée comme déclarée.

Deux enseignements, et le second vaut mieux que le premier. D'abord la
correction, triviale. Ensuite : **le dispositif a fonctionné exactement comme
prévu, et sa première victime a été son auteur.** C'est le meilleur signe qu'un
contrôle n'est pas décoratif. À comparer au garde-fou de la recette
d'intégration, qui n'a jamais rien refusé parce que rien ne lui parvenait.

## OBS-83. Le diagnostic du lecteur était plus juste que le mien

Premier jet du support : trente-trois diapositives de la même forme, titre plus
puces, avec une pastille « éliminatoire » tamponnée sur les diapositives
concernées. Techniquement conforme à la grille, ligne à ligne.

Le retour, mot pour mot : « C'est morne, la palette graphique est
quasi-inexistante, et tout est formel. Le document fait très v0 sans entrain, et
surtout, non destiné à un public, mais plus à un robot correcteur froid. »

La dernière partie est le diagnostic, et il est exact. J'avais construit un
support **pour la grille**, pas pour deux personnes assises trente minutes. Le
marquage de conformité s'adresse au correcteur ; le public a besoin d'autre
chose.

La refonte a produit sept formes de diapositive au lieu d'une, cinq visuels
dessinés, et surtout **deux versions du même fichier** : celle qui est projetée,
sans marquage, et celle de répétition, qui le porte en pied de page.
L'information n'est pas perdue, elle change de destinataire. Le marquage part
sur une feuille A4 remise au jury, où il rend la notation triviale au lieu de
polluer l'écran.

**Un support de data engineer sans un seul graphique se disqualifie tout seul.**
C'était le vrai reproche, et il n'avait pas besoin d'être formulé en ces termes
pour être juste.

## OBS-84. Des puces disparues sans le moindre message

Les formes à visuel occupent tout le cadre. Quand une diapositive de ce type
portait des puces dans le Markdown source, le générateur les ignorait
**silencieusement** : lues, jamais dessinées, jamais signalées.

Le contenu manquant ne laissait aucune trace. Aucune erreur, aucun
avertissement, un PPTX parfaitement valide. Très exactement le mode de
défaillance que tout le projet passe son temps à traquer ailleurs, reproduit
dans mon propre outillage.

Corrigé en versant ces puces dans les **notes de l'orateur** plutôt qu'en les
jetant, et en faisant **compter** le déplacement dans le compte rendu du
générateur. Le nombre s'affiche à chaque exécution : il devient impossible de ne
pas le voir.

## OBS-85. Une note extérieure contenait deux chiffres faux, dont un venait de moi

Une relecture des outils de génération a été confiée à une autre instance et
livrée sous forme de note à appliquer. Elle proposait de bonnes choses, et
avançait deux chiffres : « 13 points de vigilance » et « cinq hypothèses, trois
écartées ».

Le premier était périmé : deux des treize, V-12 et V-13, avaient été refermés en
session 10. Onze restent ouverts.

Le second était faux, et il venait de mon propre support : la diapositive D28
disait « trois scénarios écartés » là où l'incident en compte deux. La note
avait donc **recopié fidèlement mon erreur** et me la renvoyait avec l'autorité
d'un regard extérieur.

**Enseignement.** Une relecture par un tiers vérifie la forme et la cohérence
interne, pas les chiffres. Un chiffre faux mais cohérent traverse la relecture
intact et en ressort renforcé. Les deux ont été corrigés au lieu d'être
appliqués.

## OBS-86. La diapositive revendiquait deux critères qu'elle ne disait pas

Contrôle final du support contre la grille, avant de le déclarer complet. Les
dix livrables sont couverts, chacun avec ses diapositives et son temps.

Mais la grille attend, en plus des sous-critères, **six phrases de résultat**
distinctes : elle veut que le dispositif fonctionne, pas seulement qu'il existe.
Deux manquaient.

Le trou de D28 est le plus grave, et il est ironique. Ses métadonnées
revendiquaient les critères 30 et 31, soit la **communication aux parties
prenantes** et le **résultat obtenu**. Ses puces s'arrêtaient à l'action retenue.
La communication est très exactement le critère que `docs/plan_soutenance.md`
signale, de sa propre main, comme celui que les candidats oublient le plus
souvent.

**Ce que ça apprend sur le marquage lui-même.** Déclarer qu'une diapositive
couvre un critère est une **intention**, pas une couverture, et rien ne les
distinguait : la feuille du jury, générée depuis ces mêmes métadonnées,
affichait un critère 30 dûment traité. Le seul contrôle qui tranche est de lire
ce qui est réellement dit et de le confronter à ce qui est revendiqué.

## OBS-87. Trois sessions de retard dans un pied de page, et aucune règle ne l'attrapait

`docs/vulgarisation/` a une règle de révision écrite, et elle est bonne : les
deux documents sont relus à chaque session qui ajoute ou retire une brique, ou
qui invalide une explication qui s'y trouve. Elle autorise explicitement à ne
rien changer, à condition de le dire.

Elle n'attrape pas ce qui s'est produit : les sessions 8, 9 et 10 ont modifié
les deux documents **sans toucher à leur pied de page**, resté à « 27/08/2026,
fin de session 6 ». Un document révisé qui affiche une vieille date se lit comme
un document oublié, ce qui est le contraire exact de ce que la règle cherche à
rendre visible.

Le reste suivait : huit incidents annoncés pour neuf, 46 observations pour 75,
32 cas de recette pour 55, des volumes relevés avant que les deux promotions ne
tournent chaque nuit. **Aucun de ces chiffres n'était faux le jour où il a été
écrit**, et c'est la forme de péremption la plus difficile à voir, parce que
rien dans le texte ne la contredit.

Le manque de fond était ailleurs, et plus gênant : les deux documents énumèrent
leurs limites, et ni l'un ni l'autre ne citait le plus gros écart de la
plateforme, à savoir que rien ne porte une alerte jusqu'à un humain. Le README
du sous-dossier le signalait comme risque de lecture depuis la session 11, sans
que les documents concernés ne le disent. Signaler un risque de lecture dans un
troisième document ne le corrige pas.

---

# Session 13, 7 septembre 2026 : reprise des travaux sur la plateforme

Objet : la préparation de la soutenance est mise en pause. Retour au projet
lui-même, sur une liste de remarques du lecteur.

## OBS-88. Une contrainte contournée trois semaines plus tôt a pré-empté une dépréciation

Snowflake affiche une bannière : au **09/09/2026**, fin des connexions par mot
de passe seul et suppression du type `LEGACY_SERVICE`. « Your account currently
has users who are relying on password-only sign-ins. »

La bannière ne dit pas **lesquels**, et c'est la seule question qui compte. Un
`SHOW USERS` a tranché en une requête :

| Utilisateur | Type | Mot de passe | Clé RSA | MFA |
|---|---|---|---|---|
| `GAMELENS_SERVICE` | `SERVICE` | non | **oui** | non |
| `MAEL8ZINSOU` | non défini | **oui** | non | **non** |

**La plateforme n'était pas exposée.** Tout ce qui tourne, les 4 DAG, dbt,
Snowpark, la recette de la CI, passe par `GAMELENS_SERVICE`, dont
l'authentification par paire de clés est exactement ce que la nouvelle politique
exige.

Ce qui rend l'affaire intéressante est que **cette conformité n'a pas été
anticipée**. La décision du 20/08 de passer par une clé répondait à une
contrainte sans aucun rapport : Snowflake imposait déjà la MFA aux utilisateurs
humains, et un pipeline ne peut pas la satisfaire. Le compte de service a donc
été créé en `TYPE = SERVICE` pour contourner un obstacle du moment, et ce
contournement s'est trouvé être, trois semaines plus tard, la cible exacte d'une
politique annoncée depuis.

**La leçon vaut au-delà du cas.** Ce n'est pas de la chance, ou pas seulement :
la contrainte contournée et la dépréciation annoncée procèdent du même
mouvement du fournisseur, qui durcit l'authentification. Se plier proprement à
une contrainte du moment, plutôt que chercher à la neutraliser, aligne souvent
sur la direction que prend le fournisseur. Le raccourci qui aurait consisté à
donner un mot de passe au compte de service aurait marché en août et cassé le
09 septembre.

**Et la leçon opérationnelle, plus terre à terre.** Une annonce de dépréciation
ne dit pas ce qu'elle casse chez vous, elle dit ce qui change chez le
fournisseur. Le mouvement réflexe, lire la bannière et s'inquiéter, ne produit
rien. Le seul geste utile est d'interroger son propre compte, et il a coûté une
requête.

Le compte humain, lui, était bien concerné : mot de passe seul, ni MFA, ni clé,
ni jeton. Traité le jour même, `TYPE = PERSON` et MFA enrôlée. La perte
encourue n'était pas celle du service mais celle de Snowsight, donc de tout
accès humain, y compris pour vérifier V-01. À noter, parce que cela ferme une
porte de secours qu'on croit ouverte : **une paire de clés ne permet pas de se
connecter à Snowsight**, elle sert aux pilotes et aux connecteurs. Pour un
humain, la MFA n'était pas une option parmi d'autres, c'était la seule.

Dernier point, inconfortable et honnête : le filet de sécurité en cas de
verrouillage était **V-03**, le fait que `GAMELENS_SERVICE` tourne en
`ACCOUNTADMIN`. Ce compte aurait pu réinitialiser l'authentification du compte
humain. Un écart listé comme un manquement au moindre privilège se trouve être
la police d'assurance. Cela ne rend pas V-03 souhaitable ; cela rappelle qu'un
écart de sécurité et un point unique de défaillance ne se rangent pas sur le
même axe.
## OBS-89. Le document avait écrit la condition qui invalidait son propre arbitrage

Question du lecteur, apparemment anodine : pourquoi le navigateur n'atteint-il
pas PostgreSQL ni Kafka ? Réponse courte, ils ne parlent pas HTTP, et c'est tout
ce qu'il y avait à dire. En vérifiant, j'ai regardé une chose que la question ne
demandait pas : **sur quelles interfaces** ces ports sont publiés.

```
gamelens-postgres    0.0.0.0:5433->5432/tcp
gamelens-kafka       0.0.0.0:9092->9092/tcp
```

`0.0.0.0`, donc toutes les interfaces réseau. Les quatre lignes de
`docker-compose.yml` étaient écrites `- "5433:5432"`, sans adresse de liaison,
et Docker interprète cette absence comme « publie partout ». Personne ne l'avait
choisi : c'est la forme courte, celle de tous les tutoriels.

Le problème n'est pas le port ouvert, c'est ce qu'il y a derrière :
`gamelens_app` / `devlocal_app`, un mot de passe **présent dans le dépôt et dans
la documentation**.

**Et voici ce qui rend l'observation intéressante.** La feuille de route
d'exploitation porte une table de dette technique assumée, à trois colonnes : la
dette, pourquoi elle est acceptable ici, et **ce qui la rendrait inacceptable**.
La ligne concernée disait, mot pour mot :

| Dette | Pourquoi c'est acceptable ici | Ce qui la rendrait inacceptable |
|---|---|---|
| Mots de passe de développement dans le dépôt | Ils n'ouvrent que des conteneurs locaux | **Toute exposition réseau** |

Le document avait **écrit lui-même** la condition qui annulait son arbitrage. Et
cette condition était remplie depuis le premier jour, dans le fichier voisin,
sur quatre lignes.

C'est une forme de défaillance que ce projet a déjà rencontrée plusieurs fois,
et qui mérite d'être nommée une bonne fois : **une affirmation vraie sous une
prémisse que personne ne vérifie**. La colonne « ce qui la rendrait
inacceptable » est excellente à écrire et sans valeur si rien ne la relit. Elle
n'est pas un test, c'est une intention, exactement comme la convention de
conserver des preuves qui n'a produit aucune preuve pendant onze sessions
(OBS-81).

Je nuance ce qu'il faut nuancer : le pare-feu Windows bloque peut-être déjà ces
ports entrants, et je ne peux pas le vérifier depuis la machine elle-même.
L'exposition était **potentielle**, pas démontrée. Mais un arbitrage de sécurité
qui repose sur un réglage qu'on n'a pas choisi et qu'on ne sait pas lire n'est
pas un arbitrage.

**Corrigé le jour même**, en neuf caractères par ligne :
`- "127.0.0.1:5433:5432"`. Rien ne casse, et c'est vérifiable plutôt que
supposé : les conteneurs se joignent par le réseau Docker et non par les ports
publiés, `docker exec` ne les emprunte pas, `localhost` **est** `127.0.0.1` donc
le navigateur et la CI passent toujours. Vérifié après recréation : les deux
interfaces rendent HTTP 200, et un run d'ingestion déclenché à la main a collecté
15 relevés et en a écrit 15, la table passant de 1 275 à 1 290.

La phrase de la feuille de route est désormais vraie. Elle ne l'était pas quand
elle a été écrite.

## OBS-90. Un mot du lecteur a réglé deux points de sa propre liste

La demande était : « un message périodique qui statue sur l'état des
composants ». Le mot **périodique** n'était pas un détail de confort, et il
valait mieux que ce que j'aurais proposé spontanément.

Une notification **événementielle**, une alerte s'ouvre et un message part,
comble V-02 et laisse V-07 entier. Si le moteur d'alertes s'arrête, aucune règle
n'est évaluée, aucune alerte n'est ouverte, donc aucun message ne part, et le
silence redevient indiscernable d'une plateforme saine. C'est le défaut
d'origine déplacé d'un cran, ce qui est la manière la plus courante de croire
qu'on l'a corrigé.

Un battement **périodique** inverse la charge de la preuve : il part que tout
aille bien ou non, donc son **absence** devient le signal. Les deux points 3 et
4 de la liste du lecteur ne faisaient qu'un, à condition de le concevoir ainsi.

**Ce que j'en retiens sur la méthode.** J'avais lu la demande comme « brancher
Telegram », c'est-à-dire un problème de transport. C'était un problème de
**contrat de présence**, et le mot juste était déjà dans la phrase. Reformuler
la demande avant de la satisfaire aurait pu être vu comme une politesse ; ici
c'est ce qui a évité de livrer un dispositif qui aurait paru complet.

Corollaire de conception, retenu et écrit dans l'en-tête du DAG : **on ne
demande jamais à un dispositif de témoigner de sa propre existence, on lui
adjoint un témoin.** Et il faut décider où la chaîne s'arrête, parce que le
témoin en demande un à son tour. Ici elle s'arrête un cran plus haut, sur
l'humain qui ne reçoit pas son message de 8h.

## OBS-91. Les deux seuls défauts sont venus du premier message lu par un humain

Le canal a été livré avec 14 tests unitaires, une chaîne éprouvée sur une vraie
alerte, et la non-duplication vérifiée sur trois cycles. Puis les premiers
messages ont été **lus**, et ils ont produit deux défauts, tous deux invisibles
à tout ce qui précède.

**Le fuseau.** Un bilan composé à 23h58 heure de Paris annonçait « 21:58 ». La
base stocke en UTC, ce qui est juste, et l'affichage sortait tel quel. Aucune
assertion ne pouvait le voir : le test comparait un format à un format, et les
deux étaient corrects.

**L'échelle.** Le rendu écrasait en deux niveaux une échelle qui en porte
**trois**. `v_supervision_synthese` classe la latence en `avertissement` dès
60 s, là où la règle ne se déclenche qu'à 300 s. Cette bande intermédiaire est
délibérée, c'est une pré-alerte destinée au tableau de bord. Résultat, une
latence de 148 s, parfaitement saine au regard de la règle, était annoncée par
une croix.

Le second est le plus intéressant, parce qu'il n'était pas un bug de rendu mais
une **méconnaissance de la donnée rendue** : j'avais supposé que le champ `etat`
était binaire sans lire la vue qui le produit. Même faute que d'avoir supposé
des noms de colonnes plus tôt dans la journée, et l'antidote est le même,
interroger le système sur ce qu'il est.

**La leçon commune aux deux.** Ils portaient sur le **rendu**, la seule partie
qu'aucune assertion sur des données ne touche, et ils ne pouvaient être trouvés
que par un humain devant un vrai message. Un canal d'alerte a ceci de
particulier que son produit final n'est pas une ligne en base : c'est une
phrase lue par quelqu'un. Le tester sans la lire revient à tester une imprimante
sans regarder la feuille.

Et une conséquence qui vaut au-delà : **annoncer une panne qui n'en est pas une
coûte la crédibilité d'un canal aussi sûrement que de taire une vraie.** Un
canal qui crie pour 148 s de latence finit non lu, exactement comme un canal
muet.

## OBS-92. La conversion de fuseau avait un angle mort, et il n'aurait touché qu'un champ sur cinq

En corrigeant l'heure, j'ai posé un convertisseur unique appliqué à la
composition des messages. Propre, un seul endroit, testable sans base.

Il ratait un champ. La liste des composants sans exécution récente est formatée
par `to_char()` **dans la requête SQL**, donc dans le fuseau de la session
PostgreSQL, qui est UTC. Le convertisseur Python ne la voit jamais : il reçoit
déjà du texte.

Le mode de défaillance mérite d'être nommé, parce qu'il est pire qu'une
correction ratée : le message aurait été juste sur quatre champs et faux sur le
cinquième. **Une erreur uniforme se remarque ; une erreur partielle se lit comme
une donnée.** Personne ne soupçonne un fuseau quand les autres lignes sont à
l'heure.

La règle qui s'en dégage : **quand on centralise une conversion, la première
question est de savoir ce qui ne passe pas par le centre.** Ici, tout ce qui est
déjà formaté en amont.

## OBS-93. Le canal d'alerte aurait pu empêcher de signaler les alertes

Question de conception au moment de brancher la notification dans
`gamelens_supervision` : où placer la nouvelle tâche ?

L'enchaînement naturel, `evaluer` puis `notifier` puis `remonter`, a un défaut
qui ne se voit qu'en imaginant la panne. Si Telegram est injoignable, la tâche
de notification échoue, et `remonter_alertes_critiques` passe en
`upstream_failed` sans jamais s'exécuter. **Le composant chargé de signaler les
incidents aurait empêché de les signaler**, et précisément le jour où quelque
chose ne va pas.

Les deux tâches sont donc **parallèles**, toutes deux en aval de l'évaluation et
indépendantes l'une de l'autre. Elles lisent le même résultat et n'ont aucune
raison de dépendre l'une de l'autre.

C'est une variante d'un principe que le projet applique déjà ailleurs sans
l'avoir formulé : **un dispositif de surveillance ne doit jamais être sur le
chemin critique de ce qu'il surveille.** Le même raisonnement avait conduit à
séparer `evaluer_regles`, qui réussit toujours, de `remonter_alertes_critiques`,
qui échoue en présence d'une alerte. La notification est le troisième étage de
la même idée.

## OBS-94. L'entrée qui décrivait l'écart le minorait, et personne ne l'avait vérifiée

La liste des écarts gelés portait depuis la session 11 : « Le commentaire de
`fact_prices` annonce encore le scraping GOG. **La cible Snowflake, elle, est
juste** : c'est `sql/commentaires_gold_snowflake.sql` qui l'a corrigée de son
côté. »

La seconde phrase était fausse. `sql/commentaires_gold_snowflake.sql` ne
contenait que des `COMMENT ON COLUMN`, pas un seul `COMMENT ON TABLE`. Or les
deux commentaires fautifs sont des commentaires de **table**. Ils ne pouvaient
donc pas y avoir été corrigés, et ils remontaient identiques dans les **deux**
dictionnaires publiés en annexe.

**Comment l'erreur s'est installée.** Le fichier de commentaires existe parce
que le fichier de schéma contient des `CREATE OR REPLACE TABLE` et ne peut pas
être rejoué. Sachant cela, il était naturel de supposer qu'il couvrait tout ce
que le schéma documente. Il ne couvrait que les colonnes. La supposition était
raisonnable, et c'est bien le problème : **une supposition raisonnable écrite au
présent devient un fait pour le lecteur suivant**, et elle a réduit de moitié
l'écart perçu pendant trois semaines.

**Ce que la correction a changé de nature.** Le manque n'était pas dans un
commentaire, il était dans **l'absence de tout moyen d'en corriger un**. Les
quatre tables portent donc maintenant leur `COMMENT ON TABLE`, y compris les
deux dont le texte était déjà juste. Combler seulement les deux fautifs aurait
laissé le piège intact pour la fois suivante.

Rapprochement avec OBS-91 : là, deux défauts n'avaient été vus que par un humain
lisant un vrai message. Ici, un défaut n'a été vu qu'en allant **relire ce que
le document affirmait**, au lieu de le croire. Les deux disent la même chose de
la vérification : elle ne vaut que si elle sort du système qui l'a produite.

## OBS-95. Corriger le fichier source ne corrige rien : le générateur lit la base

Piège rencontré en corrigeant les commentaires, et qui aurait produit une
correction fantôme.

`CLAUDE.md` décrit les dictionnaires comme générés depuis « les `COMMENT ON` des
fichiers de `sql/` ». C'est vrai de l'intention, faux du mécanisme :
`outils/generer_dictionnaire.py` interroge `obj_description()` côté PostgreSQL
et `information_schema` côté Snowflake, c'est-à-dire le **catalogue vivant**.

Conséquence : éditer le `.sql` puis régénérer ne change **rien**, sans le
moindre message. Et le scénario est pire qu'inefficace, il est trompeur : le
fichier source dit désormais le vrai, l'annexe publiée dit toujours le faux, et
la CI valide, puisqu'elle compare l'annexe au catalogue et non au fichier. Un
lecteur relisant le `.sql` conclurait que la correction a été faite.

Le chemin réel est en trois temps : éditer le `.sql`, **appliquer** le
`COMMENT ON` à la base, régénérer. Consigné en phase 55 et corrigé dans les
faits d'environnement de `CLAUDE.md`.

La leçon générale : **quand une documentation est générée, la question n'est
jamais « où est écrite la vérité » mais « d'où le générateur la lit ».** Les
deux endroits se ressemblent assez pour être confondus.

## OBS-96. La faiblesse n'est pas « une seule source », c'est « un seul fournisseur »

Le lecteur a demandé pourquoi Steam est la seule source du projet. En allant
vérifier, la formulation elle-même s'est révélée trop douce.

Le projet appelle **deux** endpoints, `GetNumberOfCurrentPlayers` et
`appdetails`. Deux points d'appel, une seule société. Une décision de Valve ne
retire pas la moitié de la donnée, elle la retire **en totalité**. V-10 disait
« dépendance à une API tierce » ; il dit maintenant « fournisseur unique », ce
qui est la même chose en plus honnête et se défend mieux à l'oral que de se le
faire relever.

**La bonne raison de ce choix, meilleure que celle qui était écrite.** Le
rapport d'analyse justifiait en 4.4 par le périmètre : une chaîne complète vaut
mieux que quatre déclarées. C'est vrai mais faible. La raison forte est que
**Steam est la seule source qui réponde sans authentification et sans quota**,
sur ses deux endpoints. C'est ce qui a rendu applicable la règle du bloc :
rejouer la chaîne des dizaines de fois, en CI, sur conteneur jetable, depuis un
clone neuf, **sans jamais mettre un secret sur le chemin critique du premier
test**.

Ce n'est pas un hasard isolé mais un biais constant de la plateforme, le même
qui rend le canal Telegram facultatif ou la clef Snowflake absente en CI sans
casser l'étage `tests` : **fonctionner avec rien de configuré**. Steam est la
seule source qui satisfait cette propriété, et toutes les alternatives
examinées (Twitch, IGDB, RAWG, GG.deals, ITAD) demandent une clef ou un jeton.

**La contrepartie, à énoncer soi-même** : le projet n'a donc jamais éprouvé le
renouvellement d'un jeton sur une **source**. La paire de clefs RSA couvre
l'entrepôt, pas l'ingestion.

**Ce que l'examen des alternatives a appris.** Elles ne mesurent pas la même
chose, et n'en ajouter une n'a de valeur que si elle ajoute un **axe**. Twitch
mesure l'audience diffusée, seul indicateur avancé du lot. RAWG et IGDB
mesurent un catalogue, donc du statique. GG.deals et ITAD mesurent des tarifs
multi-boutiques, ce pour quoi `dim_stores` existe et ne tient qu'une ligne. Deux
faits vérifiés le 08/09 déplacent l'arbitrage : **IGDB s'authentifie par les
identifiants Twitch**, ce qui disqualifie RAWG par simple économie, et
**GG.deals impose une attribution avec lien actif** là où ITAD ne l'impose pas.
Enfin `all-api.fr`, cité dans la question, est un **annuaire d'API et non une
source** : il liste précisément IGDB, RAWG, Giant Bomb et Steam Store.
