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
