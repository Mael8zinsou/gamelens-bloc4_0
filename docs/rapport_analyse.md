# GameLens, rapport d'analyse et présentation des composants

**Livrable A4.1** du Bloc 4, RNCP39586. Compétence visée : C4.1.1, analyser
l'environnement du projet en recueillant les besoins métiers et les volumes de
données à traiter, en réalisant un état des lieux des composants existants, afin
d'orienter le choix de conception de l'architecture.

Commanditaire fictif : **Kestrel Interactive**, éditeur de jeux vidéo
indépendant d'une quinzaine de titres. Continuité directe des Blocs 1 à 3.

## Ce que ce document contient, et ce qu'il ne contient pas

Le référentiel attend deux livrables sous A4.1, réunis ici en deux parties.

| Critère de la grille | Où il est traité |
|---|---|
| Les besoins | partie 1, section 1 |
| Les enjeux du projet | partie 1, section 2 |
| L'état de l'existant | partie 1, section 3 |
| L'environnement | partie 1, section 4 |
| Les contraintes (coût, délais, complexité) | partie 1, section 5 |
| Présentation des composants | partie 2, sections 6 et 7 |
| Choix des langages de programmation | partie 2, section 8 |
| Points de vigilance (ex : vendor lock-in) | partie 2, section 9 |
| Estimation des coûts | partie 2, section 10 |

**Ce document répond à « pourquoi cette architecture ».** Il ne dit pas comment
elle est construite : c'est l'objet de `documentation_technique.md` (C4.3.3),
qui fait foi sur les procédures, la traçabilité champ par champ et la
configuration. En cas de contradiction entre les deux, c'est la documentation
technique qui gagne et ce rapport qui se corrige.

**Tous les chiffres portés ici sont mesurés, pas estimés**, et datés du
31/08/2026 sauf mention contraire. Les commandes qui les produisent sont dans
`commandes_successives.md`. Une projection à plus grande échelle est signalée
comme telle.

---

# Partie 1 : rapport d'analyse

## 1. Les besoins métiers

Kestrel Interactive suit aujourd'hui la performance de son catalogue à travers
des abonnements SaaS. Le recueil du besoin, mené au Bloc 1, fait ressortir trois
attentes, qui ne sont pas de même nature.

**B1. Centraliser une donnée aujourd'hui dispersée.** Le positionnement d'un
titre se lit dans un catalogue, son usage réel dans une plateforme de jeu, son
exposition médiatique dans une plateforme de diffusion, son prix dans une
boutique. Quatre sources, quatre formats, quatre cadences. Aucune ne répond
seule à la question que se pose l'éditeur : « ce titre marche-t-il, par rapport
à quoi, et pourquoi ».

**B2. Disposer d'une donnée fraîche.** La fréquentation d'un jeu à un instant
donné n'existe qu'à cet instant : personne ne la conserve. Une donnée
rafraîchie au rythme d'un fournisseur tiers ne permet pas de réagir à un pic
d'audience ou à l'effet d'une promotion concurrente.

**B3. Posséder la donnée plutôt que la louer.** C'est le besoin le plus
structurant, et le moins visible dans une démonstration. Chez un fournisseur
SaaS, la profondeur d'historique dépend du palier tarifaire, l'export est
contraint, et l'intégration au système décisionnel interne reste limitée. Une
résiliation efface l'antériorité accumulée.

### Traduction en exigences techniques

| Besoin | Exigence technique | Conséquence sur l'architecture |
|---|---|---|
| B1 | Résolution d'identifiants entre sources hétérogènes | Table `game_mapping`, clé interne UUID indépendante des identifiants sources |
| B2 | Collecte à haute fréquence, sans perte en cas de panne aval | Découplage par file d'attente, puits idempotent |
| B3 | Historisation propriétaire et rejouable | Archivage brut systématique (couche Bronze), grain journalier conservé |

Cette traduction est le point de bascule du projet : c'est elle, et non un
attrait pour telle ou telle technologie, qui détermine les composants retenus
en partie 2.

## 2. Les enjeux

**Enjeu économique : construire plutôt qu'acheter.** L'arbitrage n'est pas
tranché par le seul coût de licence. Un abonnement SaaS a un coût connu et une
mise en service immédiate ; une plateforme interne a un coût de construction,
un coût de maintien, et une mise en service différée. L'argument qui fait
pencher la balance est B3 : ce qui est acheté n'est pas la donnée, c'est un
accès à la donnée.

**Enjeu de dépendance.** Remplacer une dépendance à deux éditeurs SaaS par une
dépendance à quatre API tierces et à un entrepôt cloud n'est pas
mécaniquement un progrès. Le projet ne supprime pas la dépendance, il la
déplace vers des interfaces publiques documentées, dont la substitution est
possible. Cet enjeu est repris en partie 9, où il devient un point de vigilance
chiffré.

**Enjeu de crédibilité décisionnelle.** Une donnée interne n'est utile que si
elle est fiable. Sur une plateforme construite maison, personne ne garantit
l'intégrité à la place de l'équipe : c'est ce qui justifie l'effort de
vérification décrit en `cahier_recettes.md` et le double filet d'intégrité
documenté en DA-04.

## 3. L'état de l'existant

### 3.1 Ce dont dispose le commanditaire

| Élément existant | Nature | Verdict |
|---|---|---|
| Abonnements SaaS de veille (type GameDiscoverCo Pro, StreamsCharts Pro) | Vues croisées catalogue, popularité, tendances | À remplacer, c'est l'objet du projet |
| Comptes développeur sur les plateformes sources | Accès API, gratuits ou à quota | **Réutilisable en l'état** |
| Système décisionnel interne | Consommateur final des données | Contrainte d'interface, pas composant du projet |

### 3.2 Ce que les outils existants font, et ne font pas

Il serait malhonnête de présenter les solutions du marché comme insuffisantes
sur toute la ligne. Elles couvrent bien la découverte de tendances et
l'agrégation multi-plateformes, avec une qualité éditoriale qu'une équipe
interne n'atteindra pas.

Ce qu'elles ne permettent pas, et qui motive le projet : la profondeur
d'historique dépend du contrat, la donnée n'est pas exportable sans contrainte,
le périmètre suivi n'est pas librement extensible au panel concurrent choisi par
l'éditeur, et l'intégration au système décisionnel interne passe par des
exports plutôt que par une couche requêtable.

### 3.3 Ce qui existait côté technique avant le Bloc 4

Le Bloc 1 a posé la stratégie de collecte, de transformation et de sécurisation.
Le Bloc 2 a posé le modèle et les conventions de nommage. Le Bloc 3 a arbitré le
périmètre, notamment en sortant le suivi tarifaire GOG au profit de l'API Steam.

**Rien de tout cela n'était exécuté.** L'état de l'existant au démarrage du
Bloc 4 est donc : une architecture décrite, des conventions posées, et aucun
composant en fonctionnement. C'est ce qui distingue ce bloc des précédents et
qui explique le principe de travail retenu : préférer un composant modeste et
réellement exécuté à un composant ambitieux jamais lancé.

## 4. L'environnement du projet

### 4.1 Les sources, et ce que chacune impose

| Source | Accès | Contrainte imposée | Rôle retenu |
|---|---|---|---|
| RAWG | clé gratuite, 20 000 requêtes/mois | quota mensuel | Catalogue. **Non branchée à ce jour**, voir 4.4 |
| Steam Web API, `GetNumberOfCurrentPlayers` | sans authentification | rend un compteur instantané, non un flux | Popularité jouée, cœur du temps réel |
| Steam Store API, `appdetails` | sans authentification | tarifs par région | Tarification, depuis l'arbitrage du Bloc 3 |
| Twitch API | OAuth, enregistrement développeur | jeton à renouveler | Popularité diffusée. **Non branchée à ce jour** |

### 4.2 Une contrainte d'environnement structurante

L'endpoint de fréquentation Steam ne diffuse pas d'événements : il rend un
compteur au moment de l'appel. Il n'y a donc **rien à consommer en continu**,
seulement un capteur à interroger.

Cette observation, faite à la conception, a une conséquence directe sur
l'architecture : ce que le projet appelle « temps réel » est un
**échantillonnage périodique**, non un flux. Le nommer ainsi n'est pas une
concession, c'est ce qui rend l'ordonnancement cohérent et ce qui justifie de
refuser le rattrapage automatique des exécutions manquées, lequel fabriquerait
un historique faux.

### 4.3 Volumétrie mesurée

Le référentiel demande les volumes à traiter. Ils sont ici mesurés sur la
plateforme en fonctionnement, pas estimés.

| Grandeur | Mesure |
|---|---|
| Empreinte d'un relevé de fréquentation | **78 octets** |
| Empreinte d'un relevé tarifaire | **238 octets** |
| Couche Bronze, croissance annuelle à 15 titres | **environ 41 Mo/an** |
| Base applicative complète (Bronze + Silver + Gold) | **8,9 Mo** |
| Base de métadonnées de l'orchestrateur | **12 Mo** |
| Couche Gold Snowflake | 15 dimensions, 60 faits de popularité, 165 tarifs |

**Le fait le plus utile de ce tableau** est que la base de l'orchestrateur pèse
plus que la donnée du produit. À cette échelle, le coût de stockage n'est pas
un critère d'architecture : c'est un argument à assumer devant un jury plutôt
qu'à masquer.

**Projection à l'échelle réelle du commanditaire.** Un suivi de 200 titres,
portefeuille et panel concurrent réunis, multiplie la volumétrie par environ 13,
soit de l'ordre de **550 Mo par an**. La cadence d'appel, elle, devient le vrai
facteur limitant bien avant le stockage.

### 4.4 Une seule source, un seul fournisseur : le choix et son prix

Deux des quatre sources analysées au Bloc 1 ne sont pas raccordées, RAWG et
Twitch, et le suivi GOG est sorti du périmètre par l'arbitrage du Bloc 3. Les
colonnes correspondantes existent dans le schéma et restent nulles.

**La raison n'est pas seulement un arbitrage de périmètre.** Steam est la seule
source examinée qui réponde **sans authentification et sans quota**, sur ses
deux endpoints. C'est ce qui a rendu applicable la règle de travail du bloc :
rejouer la chaîne des dizaines de fois, dans l'intégration continue, sur
conteneur jetable, depuis un clone neuf, **sans jamais placer un secret sur le
chemin critique du premier test**.

Ce n'est pas un cas isolé mais un biais constant de la plateforme, le même qui
rend le canal de notification facultatif et qui permet à l'étage de tests de
tourner sans la clef Snowflake : **fonctionner avec rien de configuré**. Chacune
des alternatives examinées ci-dessous demande une clef ou un jeton.

**Le prix de ce choix, énoncé plutôt que subi.** Ce n'est pas une source unique,
c'est un **fournisseur unique** : les deux endpoints appartiennent à Valve, donc
une décision de Valve ne retire pas une part de la donnée mais sa totalité.
C'est le point de vigilance V-10 de la feuille de route, requalifié en ce sens.
Second effet, moins visible : la plateforme n'a jamais éprouvé le renouvellement
d'un jeton **sur une source**, la paire de clefs RSA ne couvrant que l'entrepôt.

**Les alternatives, évaluées sur l'axe qu'elles ajoutent** et non sur leur
richesse. En raccorder une ne vaut que si elle mesure autre chose.

| Source | Axe ajouté | Accès, vérifié le 08/09/2026 |
|---|---|---|
| Twitch Helix | Audience diffusée, **seul indicateur avancé** | OAuth `client_credentials` |
| IGDB | Catalogue | **Mêmes identifiants que Twitch**, 4 req/s |
| RAWG | Catalogue | Clef propre, 20 000 requêtes par mois |
| GG.deals | Tarifs multi-boutiques | Clef gratuite, **attribution avec lien actif obligatoire** |
| IsThereAnyDeal | Tarifs multi-boutiques | Clef gratuite, 1 000 requêtes par 5 minutes |
| GOG | Tarifs | **Scraping, pas une API** : sorti du périmètre au Bloc 3 |

Deux faits orientent la suite. **IGDB s'authentifie par les identifiants
Twitch**, une seule inscription ouvrant les deux, ce qui disqualifie RAWG par
simple économie de moyens. Et Twitch est la seule à apporter un axe réellement
neuf, l'audience diffusée précédant les ventes, là où un catalogue n'apporte que
du statique. La priorité de raccordement est donc Twitch, puis IGDB, et le suivi
tarifaire multi-boutiques ensuite : `dim_stores` existe déjà pour l'accueillir
et ne porte aujourd'hui qu'une seule ligne.

L'état actuel est porté honnêtement partout où il se lit. Le cahier de recettes
liste ces sources parmi ce qui n'est pas couvert, et le dictionnaire de données
porte, colonne par colonne, la mention « source non branchée à ce jour ».

## 5. Les contraintes

### 5.1 Coût

Contrainte forte et double. Le compte Snowflake est un compte étudiant doté de
**400 dollars de crédits sur 120 jours**, expirant les 17 ou 18/12/2026. Le
poste de travail est une machine personnelle sous Windows.

Deux conséquences de conception, prises avant d'avoir consommé le premier
crédit : un entrepôt virtuel dimensionné en **XS avec suspension automatique à
60 secondes**, et l'interdiction de toute surveillance interrogeant Snowflake en
continu. Le chiffrage est en section 10.

### 5.2 Délais

Le Bloc 4 est une soutenance, non un dossier : il n'y a pas de rattrapage par la
rédaction. Un composant décrit mais jamais exécuté ne survit pas à un
« montrez-moi ». Cette contrainte a produit la règle de travail la plus
structurante du projet : **exécuter avant de documenter**, et conserver les
traces d'exécution comme preuves.

### 5.3 Complexité d'implémentation

Contrainte évaluée composant par composant en partie 2. Trois arbitrages ont été
tranchés par elle plutôt que par la performance :

- **Couche Bronze en table PostgreSQL** plutôt qu'en stockage objet. Le support
  change, la propriété recherchée (archive immuable de tout appel) est la même,
  et un service de plus n'apportait rien à cette échelle.
- **Calcul distribué délégué à l'entrepôt** plutôt qu'exécuté localement : sur
  un poste unique, un moteur distribué en mode local ne démontre rien.
- **Isolation des environnements Python** en conteneurs séparés, après un
  conflit de dépendances réel et non théorique.

### 5.4 Environnement d'exécution

Windows impose deux contraintes qui ont coûté du temps et méritent d'être
citées comme telles : l'orchestrateur ne fonctionne pas nativement, ce qui rend
la conteneurisation obligatoire et non optionnelle ; et un service PostgreSQL
natif occupe le port par défaut, ce qui a produit le premier incident majeur du
projet.

---

# Partie 2 : présentation des composants de l'architecture

## 6. Vue d'ensemble et logique d'assemblage

L'architecture croise deux modèles, chacun répondant à un besoin distinct de la
partie 1.

**Medallion** organise les couches par niveau de raffinage : Bronze conserve
l'appel brut, Silver la donnée nettoyée, Gold la donnée modélisée pour l'usage.
C'est la réponse à B3, la possession : une couche Bronze permet de rejouer une
transformation sur l'historique sans redemander la donnée à la source, ce
qu'aucun abonnement SaaS ne permet.

**Lambda** organise les chemins par cadence : un chemin rapide qui écrit en
continu, un chemin batch qui consolide chaque nuit. C'est la réponse à B2, la
fraîcheur, sans sacrifier la justesse des agrégats.

Le croisement des deux donne cinq couches physiques, et non quatre : Bronze,
Silver speed, Gold prototype PostgreSQL, Gold cible Snowflake, plus la couche de
supervision. Ce sont ces couches, et non les outils, qui déterminent le choix
des composants ci-dessous.

## 7. Les composants, un par un

Chaque composant est présenté avec le rôle qu'il tient ici, l'alternative
sérieuse qui a été écartée, et la raison de l'arbitrage. Les décisions
d'architecture complètes, avec leur contrepartie, sont en `documentation_technique.md`
sous les identifiants DA-01 à DA-11.

### 7.1 Collecte : Python et `requests`

**Rôle** : interroger les API sources, archiver la réponse brute, publier la
mesure. Environ 1 400 relevés par jour à 15 titres.

**Alternative écartée** : un outil d'ingestion prêt à l'emploi de type Airbyte
ou Meltano. Écarté parce qu'aucun connecteur ne couvre `GetNumberOfCurrentPlayers`,
que le besoin tient en une centaine de lignes, et qu'un service supplémentaire
aurait coûté plus en exploitation qu'il n'aurait fait gagner en écriture.

**Ce que cela coûte** : un module à maintenir si Steam modifie son interface.
Ce risque est un point de vigilance en section 9.

### 7.2 Découplage : Apache Kafka, en mode KRaft

**Rôle** : absorber l'écart de rythme entre le collecteur et l'écrivain. Si le
second s'arrête, le premier continue et rien n'est perdu, dans la limite de la
rétention de 168 heures.

**Alternative écartée** : écrire directement en base. À 15 titres, cela
fonctionnerait, et il faut le dire franchement. Le tampon résout un problème
d'échelle que le commanditaire n'a pas encore, et il répond à une exigence
explicite du référentiel sur les pipelines temps réel.

**Ce que le tampon a réellement apporté**, et qui n'était pas prévu : lors d'un
arrêt de sept jours du poste, il a restitué à la reprise une collecte
antérieure intacte. La propriété théorique s'est vérifiée en conditions
subies.

**Choix du mode KRaft** : sans ZooKeeper. C'est bien Apache Kafka et non une
alternative allégée, ce qui rend inutile la substitution que le cadrage du
projet autorisait.

### 7.3 Couche Silver speed et Bronze : PostgreSQL 16

**Rôle** : recevoir la donnée nettoyée du chemin rapide, porter l'archive brute,
héberger les indicateurs de supervision et les métadonnées de l'orchestrateur.

**Alternative écartée pour Bronze** : un stockage objet de type S3 ou MinIO,
comme l'annonçait le Bloc 1. Écart assumé : le support change, la propriété
recherchée est identique, et à 41 Mo par an un service tiers de plus
n'apportait rien. La contrepartie, une couche Bronze qui n'est pas conçue pour
absorber des téraoctets, est explicite.

**Ce que le choix impose** : l'archive n'accorde aucun droit de modification ni
de suppression, pas même au compte qui l'alimente. Une archive modifiable n'est
plus une archive.

### 7.4 Orchestration : Apache Airflow 3.1.8

**Rôle** : quatre chaînes ordonnancées. Ingestion toutes les 15 minutes,
promotion vers PostgreSQL à 02h30, promotion vers Snowflake à 03h00,
supervision toutes les 15 minutes.

**Alternative écartée** : le planificateur du système d'exploitation. Il
déclenche, mais il ne donne ni dépendances entre tâches, ni reprises, ni
historique d'exécution, ni interface de rejeu. Ce sont ces quatre propriétés,
et non le déclenchement, qui étaient recherchées.

**Ce que cela coûte, mesuré** : la base de métadonnées de l'orchestrateur pèse
12 Mo, soit davantage que la donnée du produit, et croît d'environ 0,8 Go par
an. C'est le premier poste de croissance de la plateforme, et il n'appartient
pas au métier.

### 7.5 Entrepôt et calcul distribué : Snowflake et Snowpark

**Rôle** : porter la couche Gold cible et exécuter le calcul analytique. Le
calcul est envoyé à l'entrepôt sous forme de plan, non exécuté par le processus
Python.

**Alternative écartée** : un moteur distribué exécuté en local sur le poste.
Écarté parce qu'un moteur distribué tournant sur une seule machine ne démontre
pas le caractère distribué : il en simule l'interface. Déléguer le calcul à
l'entrepôt le rend vérifiable, et il l'est, par l'historique de requêtes du
fournisseur.

**Ce que cela impose** : un service tiers facturé à l'usage, avec une date
d'expiration. C'est le principal point de vigilance de la section 9.

### 7.6 Contrats de données : dbt

**Rôle** : 29 contrats déclaratifs sur les quatre tables de la couche Gold.

**Pourquoi ce composant existe** : Snowflake accepte la déclaration des
contraintes relationnelles et ne les applique pas à l'écriture. Vérifié
empiriquement. Sur cette plateforme, les tests d'intégrité ne doublent donc pas
le moteur, **ils le remplacent**. Chaque test de relation est une clé étrangère
écrite dans le schéma et jamais vérifiée par lui.

**Périmètre volontairement étroit** : dbt ne construit pas les tables, qui
restent produites par la promotion distribuée. Il les déclare en sources et les
teste. dbt éprouve ce que Snowpark construit.

### 7.7 Supervision : SQL et Grafana

**Rôle** : cinq vues d'indicateurs, six règles d'alerte à cycle de vie complet,
un tableau de bord provisionné comme code.

**Arbitrage structurant** : les seuils sont définis **en SQL**, pas dans l'outil
de visualisation. Grafana affiche les indicateurs, il ne les définit pas. Cela
rend les règles versionnées, testables hors interface, et remplaçables sans
perdre la logique de surveillance.

### 7.8 Intégration continue : GitHub Actions

**Rôle** : six étages, dont deux montent une infrastructure jetable, l'une en
conteneurs et l'autre sous forme d'une base Snowflake créée pour la durée du
run puis supprimée.

**Alternative écartée** : des vérifications lancées à la main avant chaque
livraison. Écarté pour une raison observée et non théorique : le premier
passage de la chaîne a échoué sur un défaut réel du contrôle lui-même, et
plusieurs défauts trouvés depuis l'ont été par la chaîne, pas par relecture.

## 8. Choix des langages de programmation

Trois langages, chacun sur le registre où il est le meilleur, et aucun choisi
par préférence.

| Langage | Périmètre | Raison du choix |
|---|---|---|
| **Python** | collecte, orchestration, promotion distribuée, outillage | Langage des bibliothèques clientes de toutes les sources, langage natif de l'orchestrateur et de l'interface distribuée de l'entrepôt. Le retenir évite une couche de traduction à chaque frontière. |
| **SQL** | schémas, agrégats, indicateurs et seuils de supervision | Là où la logique porte sur des ensembles de lignes, l'exprimer ailleurs revient à réécrire un moteur moins bon. Les seuils d'alerte en SQL sont versionnés et testables sans interface. |
| **YAML déclaratif** | composition des conteneurs, chaîne d'intégration, contrats de données | Ce qui décrit un état plutôt qu'une suite d'actions gagne à être déclaré. Un contrat d'unicité écrit en trois lignes remplace une requête d'agrégation écrite à la main. |

**Le partage entre Python et SQL n'est pas cosmétique.** Les huit contrôles
d'intégrité applicatifs sont en SQL parce qu'ils portent sur des relations entre
lignes ; la traçabilité des exécutions est en Python parce qu'elle porte sur le
déroulement d'un processus. Placer l'un dans le registre de l'autre aurait
produit du code plus long et moins juste.

## 9. Points de vigilance

Les treize points suivis figurent dans `feuille_route_exploitation.md` avec leur
échéance et leur action. Cette section retient ceux qui relèvent d'un choix
d'architecture, et non de l'exploitation courante.

### 9.1 Dépendance au fournisseur d'entrepôt

Le référentiel cite explicitement le vendor lock-in. Il mérite une analyse
composant par composant, car il n'est pas uniforme.

| Composant | Nature | Ce qui serait réellement à réécrire |
|---|---|---|
| **Snowflake** | propriétaire, facturé | **Le point le plus exposé.** Le schéma emploie des types et un partitionnement propres au moteur, et l'interface distribuée est propriétaire. Ce qui migrerait : la logique de promotion, pas la logique métier. |
| **Kafka** | libre, auto-hébergé | Faible. Protocole standard, exécution chez nous. |
| **Airflow** | libre | Modérée. Les chaînes emploient l'interface de tâches d'Airflow 3 : portables entre installations, pas vers un autre ordonnanceur. |
| **dbt** | libre | Faible. Les contrats sont déclaratifs, l'adaptateur d'entrepôt se change. |
| **GitHub Actions** | propriétaire | Modérée, sans enjeu de donnée : la syntaxe est spécifique, les étapes appellent des scripts du dépôt. |
| **PostgreSQL** | libre | Nulle. |

**Ce qui atténue le point le plus exposé** : un seul module du projet sait
comment on se connecte à l'entrepôt. Cette frontière de configuration, posée
alors que le compte n'existait pas encore, a déjà servi deux fois pour autre
chose que ce pour quoi elle avait été conçue. Elle ne supprime pas la
dépendance, elle circonscrit son coût.

**Ce qui l'aggrave** : le prototype PostgreSQL, gardé comme repli, est une
assurance réelle mais partielle. Il porte le même schéma et pas la même
profondeur d'historique : 3 journées contre 4 au 31/08/2026.

### 9.2 Absence de canal de notification

Les alertes sont persistées, horodatées, et se referment seules. **Personne
n'est prévenu.** C'est l'écart le plus important entre cette plateforme et une
plateforme exploitée, et il est chiffré : lors d'un arrêt de quatre jours, cinq
alertes se sont ouvertes puis refermées sans intervention et sans que quiconque
en soit informé. Si elles ne s'étaient pas refermées, rien n'aurait changé pour
l'exploitant.

### 9.3 Expiration du compte d'entrepôt

Le compte expire les 17 ou 18/12/2026. C'est le seul point de vigilance
bloquant du projet, et la section 10 montre que c'est bien la **date** qui
contraint, non le budget.

### 9.4 Dépendance à des interfaces tierces sans contrat

Les quatre sources sont des API publiques utilisées dans le cadre de leurs
conditions d'utilisation, sans engagement de service. Une modification, une
limitation ou une fermeture est possible sans préavis. L'archivage systématique
en couche Bronze est la seule atténuation réelle : il préserve l'historique déjà
acquis, il ne préserve pas la collecte future.

### 9.5 Un environnement unique

Pas de séparation entre développement, recette et production. L'infrastructure
jetable montée par la chaîne d'intégration en est une ébauche, pas un substitut.

## 10. Estimation des coûts

### 10.1 Coût d'exploitation mesuré

Relevé le 31/08/2026 dans l'historique de facturation du fournisseur, période du
20/08 au 31/08, soit **12 jours**.

| Entrepôt virtuel | Crédits consommés | Part |
|---|---|---|
| `GAMELENS_WH`, dimensionné XS et suspendu à 60 s | 1,4663 | 68 % |
| `COMPUTE_WH`, entrepôt par défaut jamais configuré | **0,6899** | **32 %** |
| **Total** | **2,1566** | |

**Le résultat le plus instructif est la seconde ligne.** Un entrepôt que
personne n'utilise volontairement, laissé à sa configuration d'origine, consomme
près d'un tiers du budget. Le dimensionnement soigné du premier est en partie
annulé par l'absence de configuration du second. C'est une action concrète
inscrite à la feuille de route.

### 10.2 Décomposition et projection

La période mesurée est dominée par le **développement** : mises au point
manuelles, exécutions de la chaîne d'intégration à chaque poussée, rejeux. Le
coût de production seul est bien inférieur.

| Poste | Fréquence | Coût unitaire | Coût annuel |
|---|---|---|---|
| Promotion quotidienne vers l'entrepôt | 1/jour | environ 0,02 crédit, minimum de facturation de 60 s inclus | environ **8 crédits/an** |
| Recette d'intégration sur base jetable | 1 par poussée | environ 0,05 crédit | proportionnel à l'activité de développement |
| Contrats de données | inclus dans la recette | négligeable | |

Hypothèse à confirmer dans l'interface du fournisseur : le prix du crédit, de
l'ordre de 2 à 4 dollars selon l'édition et la région. À ce tarif, le coût de
production annuel de la plateforme se situe **entre 16 et 32 dollars**.

### 10.3 Le budget n'est pas la contrainte, la date l'est

Au rythme mesuré de **0,18 crédit par jour**, tout compris, les 108 jours restant
avant expiration consommeraient environ **19 crédits**, soit de l'ordre de 60
dollars sur les 400 disponibles.

**Conclusion opérationnelle** : la démonstration n'est pas menacée par
l'épuisement des crédits, elle l'est par l'expiration du compte. C'est ce qui
justifie que V-01 soit le seul point de vigilance qualifié de bloquant, et cela
retire toute urgence aux optimisations de consommation.

### 10.4 Coût de construction, et comparaison avec l'achat

Le coût de construction est le poste dominant, et le seul que ce projet permette
de chiffrer honnêtement : la plateforme a été conçue, construite, éprouvée et
documentée en **dix sessions de travail**.

Une comparaison chiffrée avec les abonnements du marché serait malhonnête ici :
leurs tarifs dépendent de paliers et de négociations dont ce projet n'a pas
connaissance, et inventer un chiffre pour faire pencher la balance
décrédibiliserait toute l'analyse. La comparaison qui tient est structurelle.

| | Abonnement SaaS | Plateforme interne |
|---|---|---|
| Profil de coût | récurrent, indexé sur des paliers | construction ponctuelle, exploitation faible et mesurée |
| Mise en service | immédiate | différée |
| Propriété de l'historique | conditionnée au contrat | acquise |
| Périmètre suivi | catalogue du fournisseur | choisi par l'éditeur |
| Compétence requise | aucune | une équipe data |
| Risque à l'arrêt | perte de l'antériorité | maintien de la donnée acquise |

L'arbitrage ne se joue donc pas sur la facture mensuelle mais sur la ligne
« propriété de l'historique », qui est exactement le besoin B3. C'est le seul
argument qui justifie de construire, et c'est celui à défendre.

---

## Ce que cette analyse a changé pendant le projet

Un rapport d'analyse rédigé après coup n'a aucune valeur s'il se contente de
justifier ce qui existe. Trois décisions ont réellement été prises ou révisées
sur la base des constats ci-dessus.

**La couche Bronze a été construite** parce que l'analyse du besoin B3 a montré
qu'aucune autre brique ne permettait de rejouer une transformation sur
l'historique sans redemander la donnée à la source. Elle n'existait pas au
démarrage du Bloc 4.

**Le suivi tarifaire est passé du scraping à une API** parce que l'analyse des
contraintes d'environnement a montré qu'une source fragile et juridiquement
grise était le mauvais endroit où placer une dépendance.

**La surveillance de l'entrepôt ne l'interroge pas** parce que le chiffrage de
la section 10 a montré qu'une règle évaluée toutes les quinze minutes
représenterait 96 requêtes par jour sur un service facturé à l'usage, pour
surveiller un traitement quotidien. La vérification a donc lieu au moment de la
promotion, où la connexion est déjà ouverte et le coût déjà payé.
