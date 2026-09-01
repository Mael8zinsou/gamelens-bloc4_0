# Plan de la soutenance, Bloc 4

Soutenance orale du **vendredi 11/09/2026**. 45 minutes : 30 de présentation,
15 d'échange avec un jury de 2 professionnels externes.

**Dépôt sur DigiformaCertif le mercredi 09/09/2026**, soit deux jours plus tôt.
C'est cette date qui contraint, pas celle de l'oral : le support est gelé quand
les dernières répétitions ont lieu.

## Ce que ce document est, et la règle qu'il applique

Ce n'est pas le support. C'est le plan sur lequel le support sera construit, et
l'instrument qui permet de vérifier qu'aucune case de la grille ne passe à la
trappe.

Il applique une règle unique, tirée du libellé de la grille elle-même. Le critère
de C4.2.2 dit « 3 méthodes de traitement de la donnée **sont présentées** », pas
« sont réalisées ». Le jury coche sur les trente minutes, pas sur le dépôt.
Autrement dit : **une brique construite, testée et verte en intégration continue
mais non montrée peut être notée non acquise.** Tout ce plan en découle.

Source des libellés cités : onglet « Grille Eval spé Bloc 4 » du fichier
`24 10 10 - Grille évaluation Ingénieur en science des données (1).xlsx`, deux
niveaux au-dessus de ce dépôt. Les critères sont recopiés mot pour mot, sans
reformulation : c'est le texte que le jury a sous les yeux.

## 1. Le cadre, tel que les documents le fixent

| | |
|---|---|
| Épreuve | Orale, individuelle, 45 min (30 de présentation, 15 d'échange) |
| Jury | 2 membres professionnels externes |
| Support | « de son choix », un seul, à travers lequel 10 livrables sont présentés |
| Compétences | 10, dont **3 éliminatoires** : C4.2.1, C4.2.2, C4.2.3 |
| Validation | 50 % de compétences acquises au minimum **et** aucune éliminatoire non acquise |
| Dépôt | Livrables **et** support sur DigiformaCertif, avant la limite portée par la convocation |

Trois points de procédure qui ne dépendent pas de la qualité du travail :

- Un livrable déposé en retard est « déclaré non recevable et entraîne
  **automatiquement** une évaluation des compétences associées comme non
  acquises » (règlement général, 1.2). La date limite ne figure dans aucun
  règlement : elle est dans la convocation.
- Sans convocation **et** pièce d'identité, pas d'accès à l'épreuve
  (règlement général, 2.1).
- Seuls le candidat et les deux membres du jury sont dans la salle. Le règlement
  ne dit rien de l'équipement ni du réseau : ils sont donc à supposer absents.

## 2. Le budget de temps

Trente minutes pour **31 sous-critères** explicites, soit moins d'une minute
chacun. Cette arithmétique interdit deux choses : raconter le projet dans
l'ordre où il a été construit, et accorder le même temps à chaque compétence.
C4.3.3 porte un seul critère, C4.1.1 en porte cinq.

Le budget ci-dessous alloue **27 min 30 de contenu et garde 2 min 30 de marge**.
Un plan qui remplit les trente minutes exactement est un plan qui déborde. La
marge n'est pas du vide : c'est ce qui absorbe une question posée en cours de
route, un démarrage lent, un moment en direct qui traîne.

Les trois compétences éliminatoires reçoivent **11 minutes sur 27 min 30**, soit
40 % du temps pour 30 % des compétences. C'est délibéré.

## 3. Le déroulé minuté

| | Section | Durée | Cumul | Compétence |
|---|---|---|---|---|
| 0 | Ouverture et annonce du plan | 1:00 | 1:00 | |
| 1 | Le besoin, l'existant, les contraintes | 2:30 | 3:30 | C4.1.1 |
| 2 | Les composants retenus, et ce qu'ils coûtent | 3:00 | 6:30 | C4.1.2 |
| 3 | Le schéma de données | 3:00 | 9:30 | **C4.2.1** |
| 4 | Les pipelines, trois méthodes | 5:30 | 15:00 | **C4.2.2** |
| 5 | L'intégration et le déploiement continus | 2:30 | 17:30 | **C4.2.3** |
| 6 | La supervision et les alertes | 3:00 | 20:30 | C4.3.1 |
| 7 | La feuille de route d'exploitation | 2:00 | 22:30 | C4.3.2 |
| 8 | La documentation technique | 1:00 | 23:30 | C4.3.3 |
| 9 | Le cahier de recettes | 1:30 | 25:00 | C4.4.1 |
| 10 | L'incident et sa méthode d'investigation | 2:00 | 27:00 | C4.4.2 |
| 11 | Les limites assumées | 0:30 | 27:30 | |
| | *marge* | *2:30* | *30:00* | |

**L'ouverture annonce le plan.** Vingt secondes pour dire au jury dans quel ordre
les dix livrables vont défiler. Deux professionnels avec une grille en main
peuvent alors cocher au fil de l'eau au lieu de chercher. C'est le meilleur
retour sur investissement du support entier.

**Ordre de sacrifice si le temps déborde.** Ne jamais entamer les sections 3, 4
et 5 : elles sont éliminatoires. Couper dans cet ordre : section 8, puis
section 7, puis section 1. La section 11 se dit en une phrase si nécessaire,
mais elle ne se coupe pas : c'est elle qui installe les 15 minutes d'échange.

## 4. Traçabilité : les 31 sous-critères de la grille

Chaque ligne est un point que le jury peut cocher. La colonne « preuve » dit ce
qui est montré à l'écran à ce moment-là.

### C4.1.1, un rapport d'analyse (section 1)

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 1 | Les besoins | Les 3 besoins B1/B2/B3, traduits en exigences techniques |
| 2 | Les enjeux du projet | L'arbitrage construire ou acheter, et ce qu'il engage |
| 3 | L'environnement | 4 sources, volumétrie mesurée, contrainte d'échantillonnage |
| 4 | Les contraintes (coût, délais, complexité) | Le tableau des contraintes du rapport |
| 5 | L'état de l'existant | Ce que les outils du marché font **bien**, avant ce qu'ils font mal |

### C4.1.2, une présentation des composants (section 2)

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 6 | La liste des composants et des technologies sélectionnés | Le tableau des composants |
| 7 | Les avantages attendus | Par composant, avec l'alternative écartée |
| 8 | Les points de vigilance (ex : vendor lock-in) | Dépendance analysée composant par composant : faible, modérée, forte |
| 9 | Une estimation des coûts | 2,1566 crédits **mesurés** sur 12 jours, pas estimés |

### C4.2.1, un schéma de données (section 3), ÉLIMINATOIRE

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 10 | Le type de données | Dimensions et faits, types, grain journalier, colonnes larges et non EAV |
| 11 | Les modalités d'accès aux données | **DIRECT 1** : refus de `dashboard_viewer` sur une table de faits, puis la vue qui lui est ouverte |
| 12 | L'organisation des données | Medallion croisée Lambda, et les deux couches Gold |

C'est ici que se place le point technique le plus fort du projet : **Snowflake
n'applique pas les contraintes qui portent sur une relation entre lignes ou
entre tables.** CHECK, FOREIGN KEY, PRIMARY KEY et UNIQUE sont déclarées et
ignorées. Vérifié empiriquement, et compensé par deux filets rejoués à chaque
push. À dire comme un choix d'architecture assumé, pas comme une découverte
subie.

### C4.2.2, des pipelines de traitement (section 4), ÉLIMINATOIRE

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 13 | un pipeline temps réel (ex : SQL, Python) | Steam vers Kafka vers PostgreSQL, et le rejeu des offsets qui prouve l'idempotence |
| 14 | un orchestrateur (ex : Apache Airflow) | **DIRECT 2** : les 4 DAG et leur historique de runs |
| 15 | des calculs distribués (ex : Spark) | Snowpark, le SQL généré et l'historique de session |

Le critère cite Spark, le projet a choisi Snowpark. L'exigence porte sur le
**calcul distribué**, pas sur un produit. À dire d'emblée, sans attendre la
question : Snowpark pousse l'exécution sur le compute Snowflake là où un Spark
local aurait tourné en mono-machine. La preuve est le SQL généré.

### C4.2.3, un pipeline CI/CD (section 5), ÉLIMINATOIRE

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 16 | Le pipeline CI/CD présenté permet d'automatiser les tâches d'intégration et de déploiement continu | Capture des 6 étages verts, et le détail de l'étage qui crée puis supprime une base Snowflake jetable |

**Cette preuve vit sur github.com et ne peut pas être montrée en direct hors
ligne.** Elle doit être capturée. C'est la seule compétence éliminatoire dont la
démonstration dépend entièrement d'une capture.

### C4.3.1, une présentation du système de supervision (section 6)

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 17 | Les éléments et les indicateurs à surveiller | Les 5 vues d'indicateurs, et pourquoi celles-là |
| 18 | Les choix et la configuration des outils de supervision | Seuils portés par le SQL et non par Grafana, tableau de bord provisionné comme code |
| 19 | La visualisation des indicateurs | **DIRECT 3** : les 7 panneaux du tableau de bord |
| 20 | Le système d'alertes | 6 règles à cycle de vie complet : déclenchement, non-duplication, fermeture automatique |

### C4.3.2, une feuille de route d'exploitation (section 7)

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 21 | les tâches à réaliser | Du quotidien au trimestriel |
| 22 | les échéances | Y compris l'expiration du compte Snowflake |
| 23 | la planification de la maintenance | Fenêtres et procédures |
| 24 | les points de vigilance | 13, dont 2 datés |

### C4.3.3, une documentation technique (section 8)

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 25 | Le choix de la documentation technique présentée permet une bonne utilisation de l'infrastructure DATA | 11 décisions d'architecture datées avec leur contrepartie, et les 2 annexes **générées** depuis le catalogue, vérifiées par la CI |

Le critère porte sur le **choix** de la documentation. L'argument n'est donc pas
le volume, c'est le mécanisme : un dictionnaire de données généré ne peut pas
mentir sur le schéma, et la CI échoue s'il diverge.

### C4.4.1, un cahier de recettes et de tests (section 9)

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 26 | Le cahier de recettes et de tests reprend l'ensemble des fonctionnalités attendues | 55 cas, 0 partiel, 0 en attente |
| 27 | Les tests fonctionnels, structurels et de sécurité exécutés sont conformes au plan défini | La synthèse : 5 fonctionnels, 19 structurels, 3 de sécurité, plus les catégories propres au projet |

Le critère nomme **trois** familles de tests. Le cahier est déjà structuré sur
ces trois-là. Montrer la table de synthèse, pas un cas particulier.

### C4.4.2, une méthodologie d'investigation (section 10)

| # | Critère, verbatim | Preuve montrée |
|---|---|---|
| 28 | la nature du problème | INC-004 : le port publié sans effet |
| 29 | les actions à mettre en œuvre selon les scénarios | Les hypothèses testées, et celles qui ont été écartées |
| 30 | la communication auprès des différentes parties prenantes | Souvent oubliée par les candidats ; elle est écrite |
| 31 | les résultats attendus | Le résultat obtenu, et la durée mesurée |

## 5. Les six phrases de résultat

La grille ajoute, à six compétences, une phrase de résultat distincte des puces.
Elle demande que le dispositif **fonctionne**, pas seulement qu'il existe. Une
phrase suffit à chaque fois, mais elle doit être dite.

| Compétence | Phrase à valider |
|---|---|
| C4.1.1 | « Ce rapport d'analyse permet de cadrer le travail de conception et de déploiement » |
| C4.1.2 | « Ces composants permettent de concevoir une architecture qui répond efficacement au besoin » |
| C4.2.2 | « Les traitements présentés permettent de produire les DATA demandées » |
| C4.3.1 | « Le système de supervision permet de surveiller le bon fonctionnement de l'infrastructure » |
| C4.3.2 | « La feuille de route permet de maintenir en condition opérationnelle l'infrastructure » |
| C4.4.2 | « L'application de la méthodologie permet de résoudre l'incident technique » |

## 6. Les trois moments en direct, et leur repli

Le règlement ne garantit aucun réseau dans la salle. Tout ce qui vise Snowflake
ou une API externe est donc écarté du direct. Les trois moments retenus tournent
entièrement sur des conteneurs locaux.

| | Moment | Section | Durée | Ce qu'il coche |
|---|---|---|---|---|
| DIRECT 1 | `dashboard_viewer` refusé sur `mart.fact_prices`, puis la vue qui lui répond | 3 | ~40 s | critère 11 |
| DIRECT 2 | Airflow : les 4 DAG, l'historique des runs, le graphe d'une promotion | 4 | ~60 s | critère 14 |
| DIRECT 3 | Grafana : les 7 panneaux, avec la donnée du jour | 6 | ~60 s | critère 19 |

Vérifié le 01/09/2026 : le refus tombe bien (`ERROR: permission denied for table
fact_prices`), la vue répond, et la donnée porte la journée du jour.

**Chaque moment en direct a son repli capturé dans le support**, à la diapositive
suivante. Règle de scène : si le direct ne répond pas en dix secondes, passer au
repli sans commenter l'incident. Le jury évalue une infrastructure data, pas une
manipulation de terminal sous pression.

Trois minutes de direct sur 27 min 30. C'est peu, et c'est voulu : le direct sert
à prouver que la plateforme tourne, pas à porter la démonstration.

## 7. Les preuves à produire

Les preuves sont de **deux natures**, et les confondre sous le mot « capture »
conduit à mal les produire. Une sortie de terminal photographiée est une sortie
de terminal en moins bon : illisible au vidéoprojecteur, non sélectionnable, non
rejouable. Une interface de visualisation décrite en texte perd ce qui fait
précisément l'objet du critère.

### Sorties textuelles : produites, datées, rejouables

Le dépôt n'en conservait aucune au 01/09/2026, alors que les conventions de
travail demandaient de garder « les logs et sorties réelles des tests et des
runs » depuis la première session. Tout était transcrit dans les documents de
`docs/`, rien n'existait sous forme de sortie réelle.

`outils/capturer_preuves.py` comble ce manque et les rejoue à la demande. Neuf
captures sont dans `docs/preuves/`, chacune avec son en-tête de provenance :

| Fichier | Critères | Réseau |
|---|---|---|
| `c09_couts_snowflake.txt` | 9 | requis |
| `c10_contrats_dbt.txt` | 10, 12 | requis |
| `c11_cloisonnement_roles.txt` | 11 (repli du DIRECT 1) | non |
| `c12_integrite_gold.txt` | 10, 12 | requis |
| `c14_airflow_dags.txt` | 14 (repli du DIRECT 2) | non |
| `c15_snowpark_sql_genere.txt` | 15 | requis |
| `c16_ci_six_etages.txt` | 16 | requis |
| `c19_supervision_indicateurs.txt` | 19, 20 | non |
| `c26_tests_unitaires.txt` | 26, 27 | non |

`c15` est la plus précieuse : le `rank() OVER (PARTITION BY "GENRE" ...)` que
Snowpark construit et pousse sur le compute Snowflake. C'est la réponse
matérielle à « en quoi est-ce distribué ? », et elle ne s'improvise pas à l'oral.

`python outils/capturer_preuves.py --sans-reseau` rejoue les quatre captures
locales. À lancer le matin du 11/09 pour qu'elles portent la donnée du jour.

### Captures d'écran : quatre, à prendre à la main

Elles visent des interfaces graphiques et ne peuvent pas être automatisées ici.

| # | Où | Ce qu'il faut cadrer | Critère | Réseau |
|---|---|---|---|---|
| 1 | GitHub, onglet Actions | Les 6 étages d'un run vert | 16, **éliminatoire** | requis |
| 2 | http://localhost:8080 | Les 4 DAG, puis le graphe de `gamelens_promotion_gold` | 14, **éliminatoire** | non |
| 3 | http://localhost:3000 | Le tableau de bord entier, 7 panneaux | 19 | non |
| 4 | Snowsight, Admin puis Usage | La consommation par entrepôt | 9 | requis |

Les numéros 1 et 4 exigent le réseau : **à prendre avant le dépôt du 09/09**, pas
le jour de la soutenance.

### Reste à produire

Le schéma de données en diagramme, pour les critères 10 à 12. Hors ligne, et
c'est la dernière pièce manquante.

## 8. Les quinze minutes d'échange

Un tiers de l'épreuve. `docs/observations.md` a été tenu pour cela depuis la
première session. Les questions à attendre, et où se trouve la réponse :

| Question probable | Réponse, en une phrase |
|---|---|
| En quoi Snowpark est-il distribué ? | Le SQL généré s'exécute sur le compute Snowflake, pas sur le poste. À montrer, pas à affirmer. |
| Pourquoi pas Spark ? | Un Spark local aurait tourné en mono-machine. Le critère porte sur le calcul distribué. |
| Pourquoi deux couches Gold ? | Snowflake est un service tiers facturé ; son indisponibilité ne doit pas emporter la promotion locale. |
| Vos contraintes ne sont pas appliquées ? | Non, et c'est vérifié empiriquement. L'intégrité est reportée sur deux filets rejoués à chaque push. |
| Qui est prévenu quand une alerte se déclenche ? | Personne. C'est l'écart le plus important avec une plateforme exploitée, et il est chiffré. |
| Pourquoi Bronze en PostgreSQL et pas S3 ? | Écart assumé : le support change, la propriété recherchée est la même, 41 Mo par an. |
| Votre utilisateur de service est ACCOUNTADMIN ? | Oui. Connu, documenté, non corrigé faute de priorité. |
| Que se passe-t-il si Snowflake tombe ? | La promotion locale continue. C'est précisément pourquoi il y a deux DAG. |

Les trois dernières sont des aveux. Ils se disent mieux à la section 11, avant
que le jury ne les trouve : **nommer une limite de sa propre plateforme est un
exercice que le jury cherche à provoquer.**

## 9. Ce qui ne sera pas dit

Avec 31 critères en 27 minutes, tout ce qui n'est pas sur la grille se coupe. La
liste est écrite pour que ces sujets ne reviennent pas par la fenêtre pendant la
construction du support :

- Les huit incidents autres qu'INC-004. Un seul est demandé. Les autres restent
  disponibles pour les 15 minutes d'échange.
- Le détail du fonctionnement de dbt, de Kafka, d'Airflow. Le jury est composé
  de professionnels du domaine.
- L'historique de construction : les sessions, l'ordre des décisions, les
  fausses pistes. Sauf INC-004, qui est un livrable.
- Les documents de vulgarisation. Ils ne sont pas un livrable de la
  certification.
- Les péripéties d'outillage : fins de ligne, heredocs, chemins Windows.

## Ce qu'il reste à décider

- ~~La date limite de dépôt~~ : **mercredi 09/09/2026**, arrêtée le 01/09.
  Elle précède la soutenance de deux jours, ce qui gèle le support avant l'oral :
  les répétitions des 09 et 10/09 ne pourront plus le corriger.
- **Ce qui est déposé à côté du support** : le dépôt attend « livrable(s) **et**
  support(s) ». Les dix livrables existent dans `docs/` et dans le code.
- **Le format du support** : le règlement dit « de son choix ».
