# Script de soutenance, Bloc 4

Soutenance du **vendredi 11/09/2026**. 30 minutes de présentation, puis
15 minutes d'échange avec un jury de deux professionnels.

## À quoi sert ce fichier, et à quoi il ne sert pas

Trois documents traitent de la soutenance, et ils ne se recouvrent pas.

| Fichier | Ce qu'il porte | Lecteur |
|---|---|---|
| `docs/plan_soutenance.md` | La grille, les 31 sous-critères, le budget minuté, l'ordre de sacrifice | Le candidat, à la préparation |
| `docs/support_soutenance.md` | Ce qui est **à l'écran**, diapositive par diapositive. Source du PPTX généré | Le générateur, puis le projecteur |
| **Ce fichier** | Ce qui est **dit**, mot pour mot, plus le cadrage à donner à un outil de conception externe | Le candidat, à la répétition. Et un outil de mise en forme |

Le PPTX généré par `outils/generer_support.py` reste la référence de contenu.
Ce script en est la bande son, et il est écrit pour pouvoir être versé tel quel
dans un outil de conception de présentations, gamma.app en l'occurrence.

**Règle de non-divergence** : les identifiants de diapositive, leur ordre, leurs
minutes et leurs durées sont repris de `docs/support_soutenance.md` sans
modification. Si l'un des deux change, l'autre doit suivre. La vérification
tient en une commande, elle est en fin de fichier.

---

# Partie 1. L'idée générale

## Le projet en cinq phrases

**Kestrel Interactive** est un éditeur de jeux vidéo indépendant fictif, une
quinzaine de titres au catalogue. Il suit aujourd'hui la performance de ses jeux
à travers des abonnements à des outils du marché, qui font bien leur travail
mais gardent l'historique chez eux.

**GameLens** est la plateforme de données interne construite en alternative. Elle
collecte, archive, transforme et restitue la popularité jouée, la popularité
diffusée et la tarification de **150 titres** : le catalogue de l'éditeur et son
panel concurrent.

**Ce qui est en jeu n'est pas la donnée, c'est la décision.** Quand sortir un
titre, à quel prix, et par rapport à quoi. Cela suppose un historique que l'on
possède, et c'est le seul argument qui fait pencher la balance vers construire
plutôt qu'acheter.

**L'architecture est une Medallion croisée avec une Lambda** : une couche Bronze
qui archive la réponse brute de chaque appel, une couche Silver rapide en
PostgreSQL, une couche Gold en étoile sur Snowflake, avec un prototype
PostgreSQL conservé comme repli. Cinq DAG Airflow orchestrent l'ensemble, une
chaîne d'intégration continue de six étages la vérifie à chaque poussée.

**Le Bloc 4 exige des briques réellement construites et testées**, pas une
architecture décrite. Tout ce qui est présenté a tourné, et les échecs
rencontrés sont documentés : le référentiel demande explicitement un incident
réel et sa méthode d'investigation.

## La ligne directrice du discours

Une seule idée traverse les trente minutes, et elle doit être reconnaissable
d'une diapositive à l'autre :

> **Ce qui est affirmé est mesuré, et ce qui est mesuré est daté.**

Elle se décline partout. Les coûts sont relevés dans l'historique de
facturation, pas estimés. La volumétrie est mesurée, et quand la mesure s'est
révélée mal désignée, la correction est racontée. Le cloisonnement des rôles est
prouvé par un refus à l'écran, pas par une matrice. Le calcul distribué est
prouvé par le SQL généré, pas par le nom du produit. Les contrôles sont éprouvés
en négatif, parce que vérifier qu'un contrôle passe ne prouve pas qu'il
contrôle.

Le corollaire est aussi important : **les limites sont nommées par le candidat,
pas par le jury.** Un jury de professionnels cherche à provoquer cet exercice.
Le devancer vaut mieux que le subir.

---

# Partie 2. L'objectif de la présentation

## Ce que le jury coche

Le règlement demande, mot pour mot, « à l'aide d'un support de présentation de
son choix, le candidat présente lors d'une soutenance orale de 45 min ». Un
support unique, format libre, à travers lequel dix livrables sont présentés.

La grille déploie **dix compétences en 31 sous-critères**. Trente minutes pour
31 points cochables : moins d'une minute chacun. C'est la contrainte qui
structure tout, et elle a une conséquence directe :

> Le support ne peut pas raconter le projet chronologiquement, ni suivre l'ordre
> dans lequel il a été construit. Il est organisé **sur la grille**, sinon un
> critère passe à la trappe sans que personne s'en aperçoive.

## Les trois compétences éliminatoires

| Compétence | Livrable | Où elle se joue |
|---|---|---|
| **C4.2.1** | Un schéma de données | Section 3, diapositives D09 à D11 |
| **C4.2.2** | Des pipelines de traitement, **3 méthodes distinctes** | Section 4, diapositives D12 à D17 |
| **C4.2.3** | Un pipeline CI/CD | Section 5, diapositives D18 et D19 |

Le bloc est validé si au moins 50 % des compétences sont acquises **et** si
aucune éliminatoire n'est non acquise. Avec dix compétences : au moins cinq
acquises, dont obligatoirement ces trois-là.

Elles reçoivent **11 min 40 sur 28 minutes**, soit 42 % du temps pour 30 % des
compétences. C'est délibéré.

## Le mot qui change les priorités

Critère de C4.2.2, verbatim : « **3 méthodes de traitement de la donnée sont
présentées.** » Pas « sont réalisées ». Pas « existent dans le dépôt ».

Le jury coche sur ce qui se passe pendant les trente minutes. **Une brique
construite, testée, verte en intégration continue mais non montrée peut être
notée non acquise.** L'objectif de la présentation n'est donc pas de prouver que
le travail existe : c'est de le rendre visible en trente minutes.

## Le budget, qui est la vraie contrainte

**28 minutes de contenu, 2 minutes de marge.** La marge n'est pas du vide :
c'est ce qui absorbe une question posée en cours de route, un démarrage lent, un
moment en direct qui traîne.

| Section | Durée | Fin | Compétence |
|---|---|---|---|
| Ouverture | 0:50 | 0:50 | |
| 1. Le besoin, l'existant, les contraintes | 2:30 | 3:20 | C4.1.1 |
| 2. Les composants et leur coût | 3:00 | 6:20 | C4.1.2 |
| 3. Le schéma de données | 3:00 | 9:20 | **C4.2.1** |
| 4. Les pipelines, trois méthodes | 6:10 | 15:30 | **C4.2.2** |
| 5. L'intégration et le déploiement continus | 2:30 | 18:00 | **C4.2.3** |
| 6. La supervision et les alertes | 3:00 | 21:00 | C4.3.1 |
| 7. La feuille de route d'exploitation | 2:00 | 23:00 | C4.3.2 |
| 8. La documentation technique | 1:00 | 24:00 | C4.3.3 |
| 9. Le cahier de recettes | 1:30 | 25:30 | C4.4.1 |
| 10. Un incident réel | 2:00 | 27:30 | C4.4.2 |
| 11. Les limites assumées | 0:30 | 28:00 | |
| *marge* | *2:00* | *30:00* | |

**Ordre de sacrifice si le temps déborde.** Ne jamais entamer les sections 3, 4
et 5, qui sont éliminatoires. Couper dans cet ordre : section 8, puis section 7,
puis section 1. La section 11 se dit en une phrase si nécessaire, mais elle ne se
coupe pas : c'est elle qui installe les quinze minutes d'échange.

## Les trois démonstrations en direct

Le réseau de la salle doit être traité comme indisponible. Cela partage
nettement les briques : Grafana, l'interface Airflow, les requêtes sur la couche
Gold PostgreSQL et les tests unitaires sont sûrs hors ligne ; tout ce qui vise
Snowflake ou appelle une API ne l'est pas.

Les trois moments en direct sont donc choisis dans la première liste, et chacun
a son repli capturé, sur la diapositive suivante du PPTX.

| Moment | Diapositive | Durée | Repli |
|---|---|---|---|
| Cloisonnement des rôles | D10 | ~40 s | `docs/preuves/c11_cloisonnement_roles.txt` |
| Airflow, les cinq DAG | D15 | ~60 s | `docs/preuves/c14_airflow_dags.txt` |
| Grafana, le tableau de bord | D21 | ~60 s | La capture d'écran |

**Règle de scène** : si le direct ne répond pas en dix secondes, passer au repli
sans commenter l'incident.

---

# Partie 3. Consignes pour l'outil de conception

Cette partie s'adresse à gamma.app, ou à tout outil équivalent. Elle décrit ce
que la mise en forme doit respecter, et surtout ce qu'elle ne doit pas faire.

## Le cadre

- **31 diapositives**, ni plus ni moins, dans l'ordre donné en partie 4. Chaque
  diapositive porte son identifiant `D01` à `D31`.
- **Format 16:9**, projeté en salle sur un écran dont la taille est inconnue.
  Prévoir que le jury lit à trois mètres : rien en dessous de 18 points.
- **Langue : français.** Les noms techniques restent en anglais lorsqu'ils sont
  des noms propres de produits ou d'objets du code.
- La présentation est **déposée en PDF** en plus d'être projetée. Elle doit donc
  rester lisible sans commentaire oral.

## Ce que la mise en forme doit faire

- **Sept formes de diapositive**, choisies par le rôle et non par la variété :
  couverture, puces, figure de tête, visuel plein cadre, preuve en police fixe,
  démonstration en direct, duo à deux colonnes. Le type de chaque diapositive est
  indiqué en partie 4.
- **Un bandeau de section discret** en surtitre, qui donne le rythme sans coûter
  de temps là où des intercalaires en auraient consommé.
- **Une palette sobre et validée en mode clair.** Le projet utilise trois
  teintes catégorielles, bleu, orange et aqua, sur fond très clair et encre
  presque noire. Le contraste prime sur l'élégance.
- **Les chiffres sont le sujet.** Quand une diapositive porte un nombre qui fait
  l'argument, il doit être vu avant d'être lu : gros, seul, avec sa légende
  dessous. Deux diapositives sont conçues ainsi, D24 et D30.

## Ce que la mise en forme ne doit pas faire

- **Ne pas ajouter de contenu.** Aucune icône décorative, aucune illustration
  générée, aucune photo d'ambiance, aucun visuel de banque d'images. Ce projet
  est jugé sur des preuves ; une image sans source dilue les vraies.
- **Ne pas reformuler les puces.** Elles sont calibrées pour être lues en
  quelques secondes pendant que le candidat parle d'autre chose. Les rallonger
  fait perdre du temps, les raccourcir leur fait perdre leur chiffre.
- **Ne pas tamponner de marquage de conformité** sur les diapositives projetées.
  Le jury a la grille en main ; il n'a pas besoin qu'on la lui récite à l'écran.
  La traçabilité des 31 critères est portée par une feuille A4 remise à part.
- **Ne pas mettre les notes à l'écran.** Le script de la partie 4 va dans le
  volet commentaire, jamais sur la diapositive.
- **Pas de tiret cadratin.** Convention du dossier, tenue partout.

## Les visuels déjà produits, à réutiliser tels quels

Cinq images et un diagramme existent, générés depuis les données réelles du
projet. Ils sont dans `docs/annexes/` et ne doivent pas être redessinés : leur
valeur est précisément d'être produits par un script à partir du catalogue des
bases et des mesures.

| Fichier | Diapositive | Ce qu'il montre |
|---|---|---|
| `visuel_architecture.png` | D06 | Les trois sources, les trois couches, les deux cibles Gold, les cinq chaînes orchestrées |
| `visuel_couts.png` | D08 | La consommation de crédits relevée dans l'historique de facturation |
| `schema_donnees.png` | D09 | Le schéma en étoile, **généré depuis le catalogue Snowflake** |
| `visuel_ci.png` | D18 | Les six étages, et ce que chacun détruit derrière lui |
| `visuel_recettes.png` | D26 | Les onze familles de cas de recette, les trois exigées en bleu |
| `visuel_investigation.png` | D29 | Les cinq étapes de l'investigation d'INC-004 |

Deux diapositives portent une **preuve textuelle en police fixe**, à conserver
en monospace et sans retouche : D17 (`c15_snowpark_sql_genere.txt`) et D28
(`c28_inc004_traceback.txt`). Une porte une **capture d'écran**, D19
(`docs/captures/github_actions.png`).
---

# Partie 4. Le script, diapositive par diapositive

Chaque entrée porte son identifiant, son type de mise en page, sa minute de
début, sa durée, et les sous-critères de la grille qu'elle sert. **À l'écran**
donne le contenu de la diapositive. **Dit** donne le texte parlé, calibré sur la
durée à cent cinquante mots par minute.

Le texte parlé est un script, pas une récitation. Il fixe l'ordre des idées, les
chiffres exacts et les formules à ne pas improviser. Le reste peut varier.

## D01. GameLens, concevoir et opérer une infrastructure data

`couverture` **00:00**, 0:20

**À l'écran**

- Maël Mike ZINSOU, M2 Data Engineer, Paris YNOV Campus
- RNCP39586, Bloc 4 : concevoir et opérer une infrastructure data
- Kestrel Interactive, éditeur de jeux vidéo indépendant
- *Légende* : Une plateforme qui a tourné cette nuit à 02h30, sans personne aux commandes

**Dit**

> Bonjour. Maël Mike ZINSOU, Master 2 Data Engineer à Paris YNOV Campus, pour
> le Bloc 4 : concevoir et opérer une infrastructure data.
>
> Cette plateforme a tourné cette nuit à deux heures trente, sans personne aux
> commandes. Je vais vous montrer comment elle est faite.
>
> Et j'y reviendrai à la fin : un message d'erreur m'a désigné un coupable qui
> n'avait rien à voir.

**Repères** : ne pas lire la diapositive. Ouvrir sur la légende plutôt que sur
l'identité, le registre change sans coûter une minute. L'amorce d'INC-004 crée
une attente qui tient trente minutes et donne à la section 10 l'attention
qu'elle n'aurait pas à la vingt-sixième minute.

## D02. Ce que je vais montrer, dans cet ordre

`puces` **00:20**, 0:30 . *Ouverture*

**À l'écran**

1. Le besoin, l'existant, les contraintes
2. Les composants retenus et leur coût
3. Le schéma de données
4. Les pipelines, trois méthodes
5. L'intégration et le déploiement continus
6. La supervision et les alertes
7. La feuille de route d'exploitation
8. La documentation technique
9. Le cahier de recettes
10. Un incident réel et sa méthode d'investigation

**Dit**

> Voici l'ordre. Ce sont les dix livrables attendus, dans l'ordre de la grille.
>
> Trois moments seront en direct, pour que cela ne vous surprenne pas : le
> cloisonnement des rôles, l'orchestrateur, et le tableau de bord.

**Repères** : trente secondes qui font gagner du temps au jury pendant les
vingt-huit minutes suivantes. Deux professionnels avec une grille en main
peuvent cocher au fil de l'eau au lieu de chercher.

## D03. Le besoin de Kestrel Interactive

`puces` **00:50**, 1:00 . C4.1.1, critères 1 et 2

**À l'écran**

- Éditeur indépendant, une quinzaine de titres au catalogue
- B1 : suivre la popularité jouée et diffusée, jour après jour
- B2 : suivre la tarification, la sienne et celle du panel concurrent
- B3 : garder l'historique, pour comparer une sortie aux précédentes
- L'enjeu n'est pas la donnée, c'est de décider quand sortir et à quel prix

**Dit**

> Kestrel Interactive édite une quinzaine de titres. Le recueil du besoin fait
> ressortir trois attentes, qui ne sont pas de même nature.
>
> Suivre la popularité, jouée et diffusée, jour après jour. Suivre la
> tarification, la sienne et celle du panel concurrent. Et, la plus
> structurante : garder l'historique, pour comparer une sortie aux précédentes.
>
> Ces trois besoins se traduisent en une seule exigence technique : disposer
> d'un historique que l'on possède. C'est elle qui détermine tout ce qui suit,
> à commencer par l'arbitrage de la diapositive suivante.
>
> Parce que l'enjeu n'est pas la donnée. L'enjeu, c'est de décider quand sortir
> un titre et à quel prix. La donnée n'est que le moyen.

## D04. L'existant, et pourquoi ne pas simplement acheter

`duo` **01:50**, 0:50 . C4.1.1, critères 5 et 2

**À l'écran, deux colonnes**

| Ce que les outils du marché font bien | Ce qu'ils ne donnent pas |
|---|---|
| Une couverture bien plus large que la nôtre | L'historique reste chez eux |
| Une fraîcheur quotidienne, sans rien exploiter | Résilier, c'est perdre la série accumulée |
| Aucune infrastructure à opérer | Aucune requête libre sur le détail |
| Une équipe qui maintient les connecteurs | Un abonnement par siège, qui court |

**Dit**

> Je commence par ce que les outils du marché font bien, parce qu'un état de
> l'existant qui ne dit que du mal n'est pas une analyse, c'est une
> justification.
>
> Ils couvrent bien plus large que nous. Ils rafraîchissent quotidiennement sans
> qu'on ait rien à exploiter. Ils n'exigent aucune infrastructure, et une équipe
> maintient les connecteurs à notre place.
>
> Ce qu'ils ne donnent pas tient en un point : l'historique reste chez eux.
> Résilier, c'est perdre la série accumulée. Et il n'y a pas de requête libre
> sur le détail.
>
> L'arbitrage ne se joue donc pas sur le prix. Il se joue sur la propriété de
> l'historique.

**Repères** : ne pas chiffrer la comparaison. Leurs tarifs dépendent de paliers
dont ce projet n'a pas connaissance, et inventer un nombre pour faire pencher la
balance décrédibiliserait le reste. Le dire si la question vient.

## D05. L'environnement et les contraintes

`puces` **02:40**, 0:40 . C4.1.1, critères 3 et 4

**À l'écran**

- Deux fournisseurs raccordés : Steam pour la fréquentation et les tarifs, Twitch pour l'audience
- Aucun ne diffuse de flux : on échantillonne, on ne s'abonne pas
- 150 titres suivis, le catalogue de Kestrel et son panel concurrent, relevés toutes les 15 minutes
- Volumétrie mesurée : 176 octets par ligne archivée côté Steam, 3 231 côté Twitch
- Contraintes : un seul poste, aucun budget d'infrastructure, une échéance de soutenance
- Ce cadrage a décidé la suite : Bronze en PostgreSQL et non en stockage objet, entrepôt dimensionné XS

**Dit**

> Deux fournisseurs sont raccordés. Steam pour la fréquentation et les tarifs,
> Twitch pour l'audience diffusée. Cent cinquante titres, relevés toutes les
> quinze minutes.
>
> La contrainte structurante n'est pas le volume. C'est qu'aucune de ces sources
> ne diffuse de flux. Le temps réel de ce projet est un échantillonnage
> périodique, et je préfère le dire moi-même avant qu'on ne me le demande.
>
> Sur le volume, la mesure : cent soixante-seize octets par ligne archivée chez
> Steam, trois mille deux cent trente et un chez Twitch. J'y reviens à la fin,
> ce chiffre m'a surpris.
>
> C'est ce cadrage qui a écarté le stockage objet, et non un arbitrage pris plus
> tard.

## D06. Les composants retenus

`visuel plein cadre` : `docs/annexes/visuel_architecture.png`
**03:20**, 1:10 . C4.1.2, critères 6 et 7

**Légende** : Deux fournisseurs, trois couches, deux cibles Gold, cinq chaînes orchestrées.

**À l'écran, en appui du visuel**

- Ingestion : Python, et Kafka en mode KRaft comme tampon durable
- Silver speed : PostgreSQL 16, la donnée récente et nettoyée
- Gold : Snowflake, cible de production, plus un prototype PostgreSQL gardé comme repli
- Orchestration : Airflow 3.1.8, en conteneurs
- Calcul distribué : Snowpark, et non Spark
- Transformation et contrats : dbt
- Supervision : indicateurs en SQL, Grafana pour l'affichage

**Dit**

> Voici la chaîne complète. De gauche à droite : les sources, la couche Bronze
> qui archive chaque appel abouti ou non, Kafka comme tampon durable, la couche
> Silver rapide en PostgreSQL, puis les deux couches Gold.
>
> Pour chaque composant, l'alternative écartée. Kafka plutôt qu'une file
> légère, parce que le rejeu des offsets est ce qui prouve l'idempotence, et
> j'y reviens en section quatre. Snowflake comme cible, avec un prototype
> PostgreSQL conservé comme référence de comparaison et comme repli. Airflow en
> conteneurs. Snowpark pour le calcul distribué, et non Spark, ce que je
> défendrai en section quatre. dbt pour les contrats de données.
>
> Et la supervision, dont les indicateurs sont écrits en SQL : Grafana les
> affiche, il ne les définit pas.
>
> En bas du schéma, les cinq chaînes orchestrées, avec leur cadence.

**Repères** : ne pas réciter le tableau, le jury lit plus vite qu'on ne parle.

## D07. Points de vigilance : la dépendance fournisseur

`puces` **04:30**, 0:50 . C4.1.2, critère 8

**À l'écran**

- Faible sur Kafka, PostgreSQL, dbt : standards ouverts, réversibles
- Modérée sur Airflow et l'intégration continue : le code est portable, pas la plomberie
- Forte sur Snowflake, et sur lui seul : SQL propriétaire, Snowpark, facturation à l'usage
- Atténuation assumée : le prototype PostgreSQL du Gold est maintenu et alimenté
- Ce n'est pas un plan de sortie, c'est un chemin de repli documenté

**Dit**

> Le critère nomme explicitement la dépendance fournisseur. J'y réponds
> composant par composant, parce qu'une réponse globale ne prouverait pas que
> j'ai regardé.
>
> Faible sur Kafka, PostgreSQL et dbt : ce sont des standards ouverts, et le
> code écrit pour eux se rejoue ailleurs.
>
> Modérée sur Airflow et sur l'intégration continue : le code est portable, la
> plomberie ne l'est pas.
>
> Forte sur Snowflake, et sur lui seul : SQL propriétaire, Snowpark, facturation
> à l'usage.
>
> L'atténuation est assumée, et elle est réelle : le prototype PostgreSQL de la
> couche Gold est maintenu et alimenté chaque nuit. Mais je ne prétends pas
> pouvoir quitter Snowflake en une journée. Ce n'est pas un plan de sortie,
> c'est un chemin de repli documenté.

## D08. Les coûts, mesurés et non estimés

`visuel plein cadre` : `docs/annexes/visuel_couts.png`
**05:20**, 1:00 . C4.1.2, critère 9

**Légende** : Relevé dans l'historique de facturation, pas estimé.

**À l'écran, en appui du visuel**

- 2,1566 crédits consommés en 12 jours, relevés dans l'historique de facturation
- gamelens_wh : 1,4663 crédit. Dimensionné XS, suspension automatique à 60 secondes
- COMPUTE_WH, l'entrepôt par défaut jamais configuré : 0,6899, soit 32 % au 31/08
- Au rythme mesuré, les 108 jours restants coûtent une vingtaine de crédits sur 400
- Ce n'est donc pas le budget qui contraint, c'est la date d'expiration du compte

**Dit**

> Ces chiffres sont relevés dans l'historique de facturation. Ils ne sont pas
> estimés, et c'est le mot qui compte : beaucoup de projets estiment, alors que
> l'historique existe et se lit.
>
> Deux virgule quinze crédits en douze jours. L'entrepôt du projet en porte un
> virgule quarante-six : il est dimensionné en extra small, avec une suspension
> automatique à soixante secondes.
>
> Le reste vient de COMPUTE_WH, l'entrepôt par défaut, que personne n'utilise
> volontairement et que personne n'avait configuré. Zéro virgule soixante-neuf
> crédit, soit trente-deux pour cent de la facture au trente et un août. Je le
> dis parce que c'est le genre de détail qui montre qu'on a regardé pour de
> vrai, et parce que cela amène la feuille de route.
>
> Au rythme mesuré, les cent huit jours restants coûteront une vingtaine de
> crédits sur quatre cents. Ce n'est donc pas le budget qui contraint ce projet,
> c'est la date d'expiration du compte.

**Repères** : citer la mesure avec sa date. Le pourcentage seul serait trompeur,
la consommation absolue de COMPUTE_WH a augmenté, c'est sa part qui recule.

## D09. Le schéma de données

`visuel plein cadre` : `docs/annexes/schema_donnees.png`
**06:20**, 1:10 . **C4.2.1, ÉLIMINATOIRE**, critères 10 et 12

**Légende** : Généré depuis le catalogue Snowflake : ce schéma ne peut pas dériver du réel.

**À l'écran, en appui du visuel**

- Modèle en étoile : deux dimensions, deux tables de faits, une vue de restitution
- Grain journalier pour la popularité, grain (jeu, boutique, instant) pour les prix
- Colonnes larges plutôt qu'un modèle entité-attribut-valeur
- Clé primaire interne en UUID, indépendante des identifiants sources
- Ce schéma est généré depuis le catalogue, il ne peut pas dériver du réel

**Dit**

> Compétence éliminatoire. Le modèle est en étoile : deux dimensions, les jeux
> et les boutiques ; deux tables de faits, la popularité et les prix ; et une
> vue de restitution.
>
> Le grain est journalier pour la popularité, et jeu, boutique, instant pour les
> prix.
>
> Deux choix à justifier. Les colonnes sont larges, plutôt qu'un modèle
> entité-attribut-valeur : les indicateurs suivis sont connus et peu nombreux,
> et un EAV coûterait une jointure à chaque lecture pour une souplesse dont
> personne n'a besoin ici.
>
> La clé primaire est un identifiant interne, indépendant des identifiants
> sources. C'est nécessaire : un même jeu porte un numéro chez Steam, un autre
> chez Twitch, et son titre lui-même diffère d'une plateforme à l'autre.
>
> Un dernier point qui mérite dix secondes. Ce diagramme est généré : les
> colonnes, les types et les contraintes sont lus dans le catalogue Snowflake
> par un script du dépôt. Il ne peut donc pas dériver de la réalité. Un schéma
> dessiné à la main ment tôt ou tard.

## D10. Les modalités d'accès, démontrées

`démonstration en direct` **07:30**, 0:50 . **C4.2.1**, critère 11

**À l'écran**

- Quatre rôles, hérités du Bloc 1 : admin, etl_service, analyst, dashboard_viewer
- dashboard_viewer ne voit qu'une vue, jamais les tables de faits
- Démonstration : la même requête, refusée puis servie

**Dit**

> Quatre rôles, hérités du Bloc 1 : admin, etl_service, analyst et
> dashboard_viewer.
>
> Je préfère vous le montrer plutôt que vous montrer une matrice de droits.
>
> *(commande 1)* Le rôle dashboard_viewer interroge une table de faits.
> Permission refusée.
>
> *(commande 2)* Le même rôle, sur la vue qui lui est ouverte. Trois lignes,
> avec la donnée du jour.
>
> Le cloisonnement se prouve mieux par un refus que par une matrice de droits.

**Repères** : **DIRECT 1**, environ quarante secondes, entièrement local, aucun
réseau requis. Deux commandes déjà saisies dans un terminal ouvert, police
agrandie. Repli sur `docs/preuves/c11_cloisonnement_roles.txt`, à la diapositive
suivante du PPTX. Si le direct ne répond pas en dix secondes, passer au repli
sans commenter.

## D11. Ce que Snowflake n'applique pas

`duo` **08:20**, 1:00 . **C4.2.1**, critères 10 et 12

**À l'écran, deux colonnes**

| Déclaré dans le schéma | Réellement appliqué par le moteur |
|---|---|
| CHECK, sur une valeur | NOT NULL |
| FOREIGN KEY, entre deux tables | Le type de la colonne |
| PRIMARY KEY, entre lignes | La longueur de la colonne |
| UNIQUE, entre lignes | Rien d'autre |

**Dit**

> C'est le point technique le plus fort du projet, et je le présente comme un
> choix d'architecture assumé, pas comme une découverte subie.
>
> À gauche, ce que le schéma déclare. À droite, ce que le moteur applique
> vraiment. CHECK, FOREIGN KEY, PRIMARY KEY et UNIQUE sont déclarées et
> ignorées.
>
> La règle sous-jacente est simple à énoncer : Snowflake applique ce qui se
> vérifie sur la colonne seule, et ignore tout ce qui suppose de regarder une
> autre ligne ou une autre table. Ce n'est pas lu dans une documentation, c'est
> vérifié empiriquement par un script du dépôt, qui tente les violations une par
> une.
>
> Ce que cela coûte : l'intégrité est reportée hors du moteur, sur deux filets
> rejoués à chaque poussée. Vingt-neuf contrats déclaratifs dbt, et huit
> contrôles applicatifs. Ils sont éprouvés en positif et en négatif, sur le même
> jeu de données fautif.

**Si la question vient, pourquoi deux filets et pas un seul** : ils ne
contrôlent pas la même chose. dbt contrôle la forme des données,
déclarativement, sur les quatre tables. Les contrôles applicatifs vérifient des
invariants métier que dbt n'exprime pas, et ils tournent sans dbt. La recette
d'intégration continue leur soumet le même jeu fautif pour vérifier qu'ils
restent d'accord.
## D12. Trois méthodes de traitement, annoncées

`puces` **09:20**, 0:30 . **C4.2.2, ÉLIMINATOIRE**, critères 13, 14 et 15

**À l'écran**

- Un pipeline temps réel : Steam et Twitch vers Kafka vers PostgreSQL
- Un orchestrateur : Airflow, cinq DAG
- Un calcul distribué : Snowpark, sur le compute Snowflake

**Dit**

> Compétence éliminatoire, et le référentiel exige trois méthodes distinctes.
> Les voici, et je les traite dans cet ordre.
>
> Un pipeline temps réel : Steam et Twitch vers Kafka vers PostgreSQL.
>
> Un orchestrateur : Airflow, cinq DAG.
>
> Un calcul distribué : Snowpark, sur le compute Snowflake.
>
> C'est la section que je ne sacrifierai pas si le temps déborde.

## D13. Méthode 1, le pipeline temps réel

`puces` **09:50**, 1:20 . **C4.2.2**, critère 13

**À l'écran**

- Deux sources, 150 titres : Steam sans authentification, Twitch en OAuth client_credentials
- Kafka en mode KRaft, sans ZooKeeper : c'est bien Apache Kafka
- Un topic par source, un seul consommateur paramétré qui choisit sa table sur le topic
- Idempotence prouvée par rejeu : 735 messages relus sur les deux topics, zéro inséré
- Orchestré toutes les quinze minutes, avec porte de sortie et reprise vérifiée

**Dit**

> Deux sources, cent cinquante titres. Steam répond sans authentification.
> Twitch demande un jeton OAuth en client credentials, un mode qui n'engage
> aucun utilisateur, et c'est le seul qu'un traitement automatique puisse
> satisfaire.
>
> Kafka tourne en mode KRaft, sans ZooKeeper. C'est bien Apache Kafka, pas un
> substitut allégé.
>
> Un topic par source, et un seul consommateur, paramétré, qui choisit sa table
> selon le topic d'origine du message. J'aurais pu écrire un second module :
> ç'aurait été plus rapide, et sans risque pour le chemin déjà éprouvé. Mais
> j'aurais figé deux exemplaires de la garantie de livraison, donc deux endroits
> où la corriger le jour où elle se révèle fausse.
>
> Le point à défendre, c'est l'idempotence, et elle se prouve par le rejeu des
> offsets. On remet le consommateur au début des deux topics, on relit sept cent
> trente-cinq messages, et rien ne s'insère. Un test qui vérifie seulement que la
> requête ne plante pas ne prouve rien.
>
> Le tout est orchestré toutes les quinze minutes, avec une porte de sortie. Test
> négatif : broker coupé, le pipeline échoue proprement, et la reprise
> automatique est vérifiée.

**Repères** : dire honnêtement que le temps réel est ici un échantillonnage
périodique, puisque la source ne diffuse pas de flux. Cette honnêteté a plus de
valeur que le mot.

## D14. Deux sources, parce qu'elles ne mesurent pas la même chose

`puces` **11:10**, 0:40 . C4.1.1, critères 1 et 13

**À l'écran**

- B1 demandait la popularité jouée ET diffusée : les deux moitiés sont collectées
- Steam dit qui joue, Twitch dit qui regarde, et leur rapport ne se déduit d'aucun des deux
- Le même jour, à la même heure : Rust, 0,05 spectateur par joueur. Fall Guys, 13,6
- L'audience diffusée monte avant les ventes : un indicateur d'avance, pas une redondance
- Critère de raccordement : l'axe qu'une source ajoute, jamais sa richesse

**Dit**

> Le besoin B1 demandait la popularité jouée **et** diffusée. Les deux moitiés
> sont maintenant collectées.
>
> Steam dit qui joue. Twitch dit qui regarde. Et le rapport des deux ne se déduit
> d'aucun des deux.
>
> Le même jour, à la même heure : Rust, zéro virgule zéro cinq spectateur par
> joueur. Fall Guys, treize virgule six. Cinq cent quarante-quatre joueurs
> connectés, sept mille quatre cents personnes en train de le regarder. Un
> éditeur qui ne suivrait que la fréquentation conclurait que ce titre est mort,
> et il se tromperait.
>
> Le critère qui décide du raccordement d'une source, c'est l'axe qu'elle
> ajoute, jamais sa richesse.

**Si la question vient, pourquoi Twitch plutôt que RAWG, IGDB ou GG.deals** :
RAWG et IGDB apportent du catalogue, donc du statique. GG.deals apporte des
tarifs, un axe déjà couvert. Twitch était la seule à ajouter une mesure que
Steam ne donne pas. IGDB serait la prochaine, parce qu'elle s'authentifie avec
les mêmes identifiants que Twitch, déjà en place.

## D15. Méthode 2, l'orchestrateur

`démonstration en direct` **11:50**, 1:20 . **C4.2.2**, critère 14

**À l'écran**

- Airflow 3.1.8, en conteneurs : il ne tourne pas nativement sous Windows
- Cinq DAG : ingestion toutes les 15 min, deux promotions nocturnes, supervision, battement
- Deux promotions distinctes, et non une seule : c'est un choix, pas un oubli
- Portes de fraîcheur, testées en négatif sur les deux promotions

**Dit**

> Airflow trois point un point huit, en conteneurs, parce qu'il ne tourne pas
> nativement sous Windows.
>
> *(montrer la liste)* Voici les cinq DAG. L'ingestion toutes les quinze
> minutes, deux promotions nocturnes, la supervision, et le battement.
>
> *(ouvrir l'historique, puis le graphe de la promotion PostgreSQL)* Voici les
> runs, et le graphe de la promotion vers la couche Gold : six tâches, avec une
> porte de fraîcheur qui a été testée en négatif.
>
> Deux promotions distinctes plutôt qu'une seule, c'est un choix. Snowflake est
> un service tiers facturé, dont l'indisponibilité ne doit pas emporter la
> promotion locale. Les fusionner aurait couplé un composant local à un
> fournisseur externe.
>
> Le cinquième DAG, le battement, ne produit aucune donnée. Il ne sert qu'à
> dénoncer l'arrêt de la supervision. Un dispositif qui se surveille lui-même ne
> prouve rien : il fallait un DAG séparé.

**Repères** : **DIRECT 2**, environ soixante secondes, local, aucun réseau
requis. Repli sur `docs/preuves/c14_airflow_dags.txt`.

## D16. Méthode 3, le calcul distribué

`puces` **13:10**, 1:00 . **C4.2.2**, critère 15

**À l'écran**

- Snowpark, et non Spark : le référentiel cite Spark en exemple, l'exigence porte sur le distribué
- Un Spark local aurait tourné en mono-machine, sur ce poste
- Snowpark construit du SQL et le pousse sur le compute Snowflake
- MERGE idempotents, fenêtre glissante sur 7 jours, classement par genre
- Orchestré quotidiennement depuis le 31/08

**Dit**

> Le référentiel cite Spark en exemple. L'exigence porte sur le calcul
> distribué, pas sur un produit, et j'ai choisi Snowpark.
>
> La question va venir, alors je la pose moi-même : en quoi est-ce distribué ?
>
> Ce qui compte n'est pas le nom du produit, c'est l'endroit où le calcul
> s'exécute. Sur ce poste, un Spark local aurait tourné en mono-machine, sur une
> seule machine, la mienne. C'est exactement ce que le critère cherche à
> écarter. Snowpark, lui, n'exécute rien ici : il construit du SQL et le pousse
> sur le compute Snowflake.
>
> Ce qu'il calcule : des MERGE idempotents, une moyenne glissante sur sept
> jours, et un classement par genre.
>
> C'est orchestré quotidiennement depuis le trente et un août. Et la preuve
> arrive à la diapositive suivante.

## D17. La preuve : le SQL que Snowpark génère

`preuve en police fixe` : `docs/preuves/c15_snowpark_sql_genere.txt`
**14:10**, 1:20 . **C4.2.2**, critère 15

**Légende** : Extrait de `docs/preuves/c15_snowpark_sql_genere.txt`, capture du 01/09.

**À l'écran**

- `rank() OVER (PARTITION BY genre ORDER BY joueurs_moyens DESC)`
- `avg() OVER (PARTITION BY jeu ORDER BY jour ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)`
- Aucune ligne ne transite par le poste : seul le résultat revient
- Capturé dans `docs/preuves/c15_snowpark_sql_genere.txt`

**Dit**

> Voici le SQL que le programme Python a généré. Il est capturé dans le dépôt,
> daté, et rejouable.
>
> Deux fonctions de fenêtrage. Un rang, partitionné par genre. Et une moyenne
> mobile sur les six lignes précédentes plus la courante, partitionnée par jeu.
>
> Le point à faire entendre : ces fonctions sont exécutées par le moteur
> Snowflake, sur ses propres nœuds. Le programme Python décrit un calcul, il ne
> l'exécute pas. C'est exactement ce que fait Spark, avec un moteur différent.
>
> Et la conséquence se lit dans la trace : aucune ligne ne transite par ce
> poste. Seul le résultat revient.
>
> C'est la réponse matérielle, et elle vaut mieux qu'un argument. Si vous voulez
> aller plus loin, l'historique de session côté Snowflake montre les requêtes
> reçues côté serveur, avec leur durée et leur entrepôt d'exécution.

## D18. L'intégration et le déploiement continus

`visuel plein cadre` : `docs/annexes/visuel_ci.png`
**15:30**, 1:20 . **C4.2.3, ÉLIMINATOIRE**, critère 16

**Légende** : Les étages 4 et 5 montent une infrastructure neuve, l'éprouvent, puis la détruisent.

**À l'écran, en appui du visuel**

- Six étages, à chaque push et chaque pull request
- Qualité, tests, intégrité des DAG, intégration, recette de l'entrepôt, publication
- L'infrastructure d'intégration est créée puis détruite à chaque run
- Image Airflow publiée sur ghcr.io, étiquetée latest et par le SHA du commit

**Dit**

> Compétence éliminatoire. Six étages, à chaque poussée et à chaque demande de
> fusion : la qualité du code, les tests unitaires, l'intégrité des DAG,
> l'intégration, la recette de l'entrepôt, et la publication de l'image.
>
> Ce qui distingue cette chaîne d'un simple lanceur de tests, ce sont les deux
> étages du milieu. Ils **montent une infrastructure neuve**, l'éprouvent, puis
> la détruisent. Rien n'est testé contre un état accumulé.
>
> À la fin, l'image Airflow est publiée sur le registre, étiquetée à la fois
> latest et par l'empreinte du commit, pour qu'on puisse toujours revenir à une
> version précise.
>
> Un mot sur le premier run : il avait échoué. Le défaut était dans mon
> assertion, pas dans l'infrastructure. Un pipeline qui passe du premier coup
> n'a en général rien vérifié.

## D19. Six étages au vert, sur le dernier run

`capture d'écran` : `docs/captures/github_actions.png`
**16:50**, 1:10 . **C4.2.3**, critère 16

**Légende** : Le dernier run de la branche principale, six étages au vert.

**À l'écran, en appui de la capture**

- Une base Snowflake créée pour la durée du run, puis supprimée
- Le schéma livré est appliqué, le calcul distribué confronté à des valeurs calculées à la main
- Le comportement du moteur sur les contraintes est re-vérifié à chaque push
- Les deux filets d'intégrité sont éprouvés en positif ET en négatif, sur le même jeu fautif
- La couche de démonstration n'est jamais visée : le script refuse de démarrer si elle l'était

**Dit**

> Voici le dernier run de la branche principale. Six étages au vert, quatre
> minutes quinze.
>
> Je m'arrête sur l'étage de recette, parce que c'est celui qui va le plus loin.
> Une base Snowflake est créée pour la durée du run. Le schéma livré y est
> appliqué. Le calcul distribué est confronté à des valeurs que j'ai calculées à
> la main. Le comportement du moteur sur les contraintes est re-vérifié. Puis la
> base est supprimée.
>
> L'épreuve en négatif est le point fort : vérifier qu'un contrôle passe ne
> prouve pas qu'il contrôle. On lui soumet des données fautives et on exige
> qu'il échoue.
>
> Et un détail que vous remarquerez peut-être : le script de recette porte une
> liste de bases protégées et sort en erreur plutôt que de risquer de détruire
> la couche de démonstration.
>
> Enfin, la clé privée n'est jamais écrite sur le disque du runner : elle
> transite par une variable d'environnement, en contenu PEM.

**Repères** : c'est la seule compétence éliminatoire dont la preuve vit sur
github.com et ne peut pas être montrée en direct sans réseau. La capture est
donc obligatoire, et elle est prise.

## D20. La supervision : ce que l'on surveille, et pourquoi

`puces` **18:00**, 1:00 . C4.3.1, critères 17 et 18

**À l'écran**

- Cinq indicateurs : fraîcheur, complétude, latence, fiabilité par composant, fraîcheur du Gold
- Les seuils sont définis en SQL, pas dans l'outil d'affichage
- Conséquence : ils restent interrogeables par n'importe quel client, même Grafana arrêté
- Le tableau de bord est provisionné comme code, pas cliqué dans une interface
- Grafana se connecte avec le rôle analyst, en lecture seule

**Dit**

> Cinq indicateurs : la fraîcheur de la donnée, la complétude de la collecte, la
> latence du pipeline, la fiabilité par composant, et la fraîcheur de la couche
> Gold.
>
> Le choix que je défends ici tient en une phrase : **l'outil affiche les
> indicateurs, il ne les définit pas.** Les seuils sont écrits en SQL, dans le
> dépôt, pas dans Grafana.
>
> La conséquence est concrète : ils restent interrogeables par n'importe quel
> client, même Grafana arrêté. Un seuil enfermé dans une interface graphique est
> un seuil qu'on ne peut ni tester, ni versionner, ni interroger autrement. Et
> c'est ce qui me permet d'affirmer que la supervision survivrait à un
> changement d'outil de restitution.
>
> Le tableau de bord lui-même est provisionné comme code, pas cliqué dans une
> interface. Et Grafana s'y connecte avec le rôle analyst, en lecture seule.

## D21. Les indicateurs, à l'écran

`démonstration en direct` **19:00**, 1:00 . C4.3.1, critère 19

**À l'écran**

- Sept panneaux, vérifiés par un contrôle automatisé
- Fraîcheur par flux, complétude de la collecte, latence, fiabilité, alertes ouvertes

**Dit**

> *(ouvrir le tableau de bord)*
>
> Sept panneaux, dont la présence est vérifiée par un contrôle automatisé, pour
> qu'un panneau supprimé par inadvertance ne passe pas inaperçu.
>
> *(commenter deux panneaux, pas les sept)* La fraîcheur par flux, ici. Et les
> alertes ouvertes, là.
>
> La donnée du jour est présente : la plateforme a tourné cette nuit, sans
> intervention. C'est plus convaincant qu'une capture d'écran.

**Repères** : **DIRECT 3**, environ soixante secondes, local, aucun réseau
requis. Ne commenter que deux panneaux. Repli sur la capture, à la diapositive
suivante du PPTX.
## D22. Les alertes, et leur cycle de vie

`puces` **20:00**, 1:00 . C4.3.1, critère 20

**À l'écran**

- Six règles, évaluées toutes les quinze minutes par un DAG
- Cycle complet : déclenchement, non-duplication, fermeture automatique
- Une alerte au plus par règle : sans cela, 96 lignes par jour pour un seul incident
- Fenêtre par composant, et non fenêtre unique : 24 h pour les collectes fréquentes, 26 h pour les quotidiennes
- Un incident réel de quatre jours a été détecté puis refermé seul, en moins de cinq minutes
- Notification Telegram immédiate des alertes critiques, mesurée à 2 secondes

**Dit**

> Six règles, évaluées toutes les quinze minutes par un DAG.
>
> Ce qui distingue un système d'alertes d'un simple journal d'erreurs, c'est le
> cycle de vie complet : déclenchement sur seuil, non-duplication tant que la
> condition dure, et fermeture automatique au retour à la normale. Sans la
> non-duplication, un seul incident produirait quatre-vingt-seize lignes par
> jour.
>
> Un piège évité mérite d'être raconté. La fenêtre de détection d'un composant
> muet est portée **par composant**, et non unique : vingt-quatre heures pour
> les collectes fréquentes, vingt-six pour celles qui ne tournent qu'une fois
> par jour. Avec une fenêtre unique de vingt-quatre heures, un composant
> quotidien serait déclaré muet à chaque cycle.
>
> Depuis le sept septembre, les alertes critiques partent aussi sur un canal
> externe. Deux secondes mesurées entre le déclenchement et la réception. Avant
> lui, le système voyait les alertes mais ne les disait à personne : une alerte
> de fraîcheur est restée ouverte six jours et vingt heures.

**Si la question vient sur la robustesse du canal** : il est facultatif. Sans
jeton configuré, la notification ne fait rien et rend un succès. Avec un jeton
présent mais injoignable, elle trace un échec. L'asymétrie est voulue et testée :
un dispositif d'alerte ne doit jamais faire tomber la chaîne qu'il surveille,
mais son propre silence ne doit pas être silencieux.

## D23. La feuille de route d'exploitation

`puces` **21:00**, 1:00 . C4.3.2, critères 21, 22 et 23

**À l'écran**

- Tâches du quotidien au trimestriel, avec leur fréquence et leur durée
- Échéances datées, dont l'expiration du compte Snowflake
- Fenêtres de maintenance, et l'ordre d'arrêt et de redémarrage des composants
- Procédures d'intervention éprouvées avant d'être prescrites, pas rédigées d'avance

**Dit**

> La feuille de route couvre les tâches du quotidien au trimestriel, avec leur
> fréquence et leur durée. Elle porte des échéances datées, dont l'expiration du
> compte Snowflake. Elle décrit les fenêtres de maintenance, et l'ordre dans
> lequel les composants s'arrêtent et redémarrent.
>
> Le point de méthode est dans la dernière ligne. Une procédure écrite sans
> avoir été exécutée est une intention, pas une procédure. Celles de ce document
> ont toutes été jouées au moins une fois, et les durées annoncées sont
> mesurées, pas estimées.
>
> Un exemple si vous voulez du concret : la reprise après coupure du broker
> Kafka. J'ai arrêté le conteneur, vérifié que le pipeline échouait proprement,
> puis qu'il reprenait seul. C'est ce qui est écrit dans la procédure, parce que
> c'est ce qui s'est passé.

## D24. Les points de vigilance

`chiffre` : **9**
**22:00**, 1:00 . C4.3.2, critère 24

**Légende** : points de vigilance ouverts, sur quatorze numérotés et cinq refermés

**À l'écran**

- Nommés, numérotés, et pour deux d'entre eux datés
- Cinq refermés en cours de projet, dont V-02 et V-07 le 07/09 : la feuille de route vit
- V-01, expiration du compte Snowflake : le seul réellement bloquant
- V-03, l'utilisateur de service tourne avec des droits trop larges
- V-05, la couche Bronze sans conservation définie : requalifié de faible à FORTE le 08/09
- COMPUTE_WH à réduire : mesuré à 32 % de la consommation au 31/08

**Dit**

> Quatorze points de vigilance numérotés, neuf ouverts, cinq refermés en cours
> de projet. Une feuille de route dont rien ne se referme n'est pas une feuille
> de route, c'est une liste de regrets.
>
> Le seul réellement bloquant est V-01, l'expiration du compte Snowflake à la
> mi-décembre. Ce n'est pas le budget qui contraint, c'est la date.
>
> Mais celui que je veux raconter est V-05, la couche Bronze sans politique de
> conservation. Il était classé **faible** depuis l'origine, et ce classement
> était juste au moment où il a été posé : la couche grossissait alors de
> quarante et un mégaoctets par an.
>
> Le raccordement de Twitch l'a fait passer à dix-sept virgule cinq gigaoctets
> **sans que personne ne touche à V-05**. Parce qu'une réponse d'audience décrit
> jusqu'à cent diffusions, là où un compteur de joueurs tient dans un entier.
>
> Ce que j'en retiens : un registre de risques se relit quand l'architecture
> change, pas seulement quand un risque se matérialise.

**Si la question vient, pourquoi ne pas tronquer ce qu'on archive** : ce serait
décider aujourd'hui de ce dont on aura besoin demain, précisément ce que la
couche Bronze existe pour éviter. C'est la durée de conservation qui doit
devenir une décision, pas le contenu.

## D25. La documentation technique

`puces` **23:00**, 1:00 . C4.3.3, critère 25

**À l'écran**

- Treize décisions d'architecture, datées, chacune avec sa contrepartie
- Traçabilité champ par champ, de la source à la couche Gold
- Deux annexes GÉNÉRÉES depuis le catalogue des bases, jamais écrites à la main
- L'intégration continue échoue si une annexe ne correspond plus au schéma

**Dit**

> Le critère porte sur le **choix** de la documentation présentée. Mon argument
> n'est donc pas le volume, c'est le mécanisme.
>
> Treize décisions d'architecture, datées, et chacune porte sa contrepartie, ce
> qu'elle a coûté. Une décision sans inconvénient documenté est une décision
> qu'on n'a pas vraiment prise.
>
> Une traçabilité champ par champ, de la source à la couche Gold.
>
> Et deux annexes qui ne sont pas écrites : elles sont **générées** depuis le
> catalogue des bases. Un dictionnaire de données généré ne peut pas mentir sur
> le schéma. Mieux : la chaîne d'intégration régénère l'annexe à chaque poussée
> et refuse le commit si elle diverge de ce qui est versionné.
>
> C'est ce qui distingue une garantie d'une consigne. « Penser à régénérer après
> modification du schéma » n'est pas un mécanisme, c'est un espoir.

## D26. Le cahier de recettes

`visuel plein cadre` : `docs/annexes/visuel_recettes.png`
**24:00**, 0:45 . C4.4.1, critères 26 et 27

**Légende** : Les trois familles exigées par la grille, en bleu, et celles que le projet a ajoutées.

**À l'écran, en appui du visuel**

- 70 cas, 0 partiel, 0 en attente
- Fonctionnels : 5. Structurels : 19. Sécurité : 3. Plus les huit catégories propres au projet
- Format retenu : PASS ou FAIL vérifié sur un résultat attendu
- Et non « la requête s'exécute sans erreur », qui ne prouve rien

**Dit**

> Soixante-dix cas, aucun partiel, aucun en attente.
>
> Le critère nomme trois familles : fonctionnels, structurels, de sécurité. Elles
> sont en bleu. Les autres sont propres au projet.
>
> Le point de méthode est le format. Chaque cas énonce son **résultat attendu**
> avant son résultat obtenu, et le verdict porte sur la comparaison des deux. Et
> non sur « la requête s'exécute sans erreur », qui ne prouve rien du tout.
>
> Le premier cas conforme à ce format était le rejeu des offsets Kafka, quinze
> messages relus et zéro inséré. Le même contrôle en compte aujourd'hui sept cent
> trente-cinq, sur deux topics.

## D27. Éprouvé en négatif

`puces` **24:45**, 0:45 . C4.4.1, critère 27

**À l'écran**

- Vérifier qu'un contrôle passe ne prouve pas qu'il contrôle
- Les deux filets d'intégrité sont soumis au même jeu de données fautif
- Les tests de sécurité valident aussi les refus : treize cas, en 20 cas paramétrés
- Les portes de fraîcheur ont été testées en coupant réellement la source
- Le panel : cinq identifiants Steam désignaient un autre jeu, et répondaient tous en HTTP 200

**Dit**

> C'est la différence entre un cahier de recettes et une liste de vœux.
> Vérifier qu'un contrôle passe ne prouve pas qu'il contrôle.
>
> Trois exemples. Les deux filets d'intégrité sont soumis au même jeu de données
> fautif, et on exige qu'ils échouent. Les portes de fraîcheur ont été testées
> en coupant réellement la source.
>
> Et le meilleur cas du cahier, je crois. En portant le panel à cent cinquante
> titres, cinq identifiants Steam que je croyais justes désignaient un autre jeu.
> Aucun n'aurait produit d'erreur : ils auraient collecté des données
> parfaitement valides sur les mauvais jeux, indéfiniment, avec une fraîcheur
> bonne et des tests au vert.
>
> Ce que le contrôle vérifie n'est donc pas l'absence d'erreur, c'est une
> **correspondance** : le nom rendu par Steam est confronté au nom attendu.

## D28. Un incident réel : INC-004

`preuve en police fixe` : `docs/preuves/c28_inc004_traceback.txt`
**25:30**, 1:00 . **C4.4.2**, critère 28

**Légende** : Rejoué le 01/09/2026, à l'identique : même octet 0xe9, même position 103.

**À l'écran**

- Le message ne dit pas ce qui ne va pas : il dit qu'il n'a pas su lire ce qui ne va pas
- L'octet 0xe9 est le « é » de « échouée », dans un message PostgreSQL en français
- Fausse piste évidente, et coûteuse : le projet est stocké sous un chemin accentué

**Dit**

> Voici l'incident que j'ai retenu, et je l'ai rejoué le premier septembre pour
> obtenir cette trace à l'identique.
>
> Lisez le message. Il ne dit pas ce qui ne va pas. Il dit qu'il **n'a pas su
> lire** ce qui ne va pas : un décodage a échoué sur l'octet 0xe9, en
> position 103.
>
> La fausse piste était évidente, et j'y suis allé : ce projet est stocké sous
> un chemin qui contient des accents et des espaces. Un octet 0xe9, c'est un
> « é ». Le coupable semblait désigné.
>
> Il n'avait rien à voir. L'octet 0xe9 était le « é » de « échouée », dans un
> message d'erreur PostgreSQL rédigé en français. Le décodage a échoué avant que
> l'erreur utile ne remonte.
>
> L'intérêt de cet incident n'est pas sa difficulté, qui est faible. C'est que le
> message d'erreur désignait un coupable sans rapport avec la cause.

**Repères** : raconter cet enchaînement lentement. C'est la partie que le jury
retient.

## D29. La méthode, et ce qu'elle a donné

`visuel plein cadre` : `docs/annexes/visuel_investigation.png`
**26:30**, 1:00 . **C4.4.2**, critères 29, 30 et 31

**Légende** : Cinq étapes, deux hypothèses écartées, et celle qui a tranché.

**À l'écran, en appui du visuel**

- Ce qui a tranché : la LANGUE du message d'erreur, devenue empreinte du serveur
- Une Alpine en locale C ne peut répondre qu'en anglais ASCII : le français prouvait l'imposture
- Communication, immédiat : mention en daily, tout poste avec un PostgreSQL local se bloquera pareil
- Puis un prérequis ajouté à la procédure d'installation, et cette entrée de journal pour la trace
- Résultat vérifié par l'exécution : la chaîne complète, et le rejeu idempotent à 0 inséré

**Dit**

> Cinq étapes, deux hypothèses écartées, et celle qui a tranché.
>
> Ce qui a tranché, c'est la **langue** du message d'erreur. Le conteneur
> PostgreSQL est une image Alpine en locale C : il ne peut répondre qu'en anglais
> ASCII. Un message en français prouvait donc que ce n'était pas lui qui
> répondait. La langue d'un message d'erreur a servi d'empreinte pour identifier
> quel serveur était au bout du port.
>
> C'était un service PostgreSQL natif de Windows, qui occupait le port et que
> Docker n'avait pas pu prendre, sans message d'erreur.
>
> Sur la communication aux parties prenantes, rubrique souvent oubliée : incident
> de poste de développement, sans impact sur un service rendu, donc aucune
> remontée au commanditaire. La communication pertinente est interne et
> technique. Immédiat, une mention en point quotidien : tout poste avec un
> PostgreSQL local se bloquera de la même façon. Durable, un prérequis ajouté à
> la procédure d'installation, et cette entrée de journal pour la trace.
>
> Et le résultat n'a pas été vérifié par l'absence d'erreur, mais par
> l'exécution : la chaîne complète a tourné, et le rejeu a inséré zéro ligne.

**Repères** : les deux scénarios écartés, si le jury creuse : arrêter le service
natif, ce qui casse d'autres travaux et se refait à chaque redémarrage ; le
désinstaller, disproportionné. Ajouter que le port 5433 est commenté dans
`docker-compose.yml` pour que personne ne corrige l'anomalie apparente et ne
réintroduise l'incident : ce commentaire fait partie de la communication.

## D30. Ce que je n'ai pas fait

`chiffre` : **× 437**
**27:30**, 0:30 . *Clôture*

**Légende** : l'écart entre le volume annuel que mon rapport annonçait et celui que j'ai mesuré

**À l'écran**

- Aucune politique de conservation, et l'assiette du risque a été multipliée par 437
- L'utilisateur de service tourne toujours en ACCOUNTADMIN
- Un seul environnement : ni recette, ni production séparées
- Tous documentés et numérotés. Deux autres y figuraient début septembre, et sont refermés

**Dit**

> Trois choses que je n'ai pas faites.
>
> Aucune politique de conservation sur la couche brute. Mon propre rapport
> annonçait quarante et un mégaoctets par an ; la mesure en donne dix-sept
> virgule cinq gigaoctets. Un facteur quatre cent trente-sept, que je n'avais
> pas vu venir.
>
> L'utilisateur de service tourne toujours avec des droits trop larges. Et il
> n'y a qu'un seul environnement : ni recette, ni production séparées.
>
> Les trois sont documentés et numérotés. Deux autres figuraient ici au début du
> mois. Ils n'y sont plus.

**Si la question vient sur le 437** : une partie de l'écart vient d'une
décision que j'ai prise, porter le panel à 150 titres et brancher une seconde
source. L'autre vient d'une erreur de désignation : les octets annoncés étaient
ceux de la charge JSON, pas ceux de la ligne archivée. Ni l'une ni l'autre ne se
voyait dans le document.

**Repères** : ne pas s'excuser. Énoncer, dire pourquoi ça n'a pas été traité, et
s'arrêter. Un jury de professionnels sait qu'une plateforme a toujours une
dette ; ce qu'il veut savoir, c'est si le candidat la connaît. Ces trente
secondes ouvrent les quinze minutes d'échange bien mieux qu'une conclusion
triomphale.

## D31. Questions

`couverture` **28:00**, hors temps

**Légende** : Le dépôt, la documentation et les preuves sont à disposition.

**À l'écran**

- Merci
- Le dépôt, la documentation et les preuves sont à disposition

**Dit**

> Merci de votre attention. Le dépôt, la documentation et les preuves capturées
> sont à votre disposition, et je peux montrer n'importe laquelle en direct.

---

# Le calibrage du texte parlé

Le texte parlé est écrit **à cent cinquante mots par minute**, qui est un débit
d'oral posé. Le total fait **3 882 mots pour 28 minutes**, soit 139 mots par
minute : le script est donc légèrement sous son budget, ce qui est le bon sens
de l'écart.

Trois familles de diapositives s'en écartent volontairement, et il faut le
savoir avant de s'en inquiéter en répétant.

- **Les trois démonstrations en direct**, D10, D15 et D21, sont très en dessous.
  L'essentiel de leur temps est de la manipulation, pas de la parole.
- **Les diapositives à preuve ou à figure**, D02, D17 et D18, sont en dessous
  aussi. Le jury lit pendant qu'on parle, et couvrir un visuel de commentaire le
  rend illisible.
- **D01 est au-dessus**, d'environ six secondes. C'est assumé : une ouverture se
  dit plus lentement, et la marge de deux minutes l'absorbe. Si la répétition
  montre que ça coince, la phrase à retirer est l'amorce de l'incident, qui sera
  reprise en section 10 de toute façon.

Contrôle, à rejouer après toute réécriture du texte parlé :

```bash
python - <<'FIN'
import re
from pathlib import Path
script  = Path("docs/script_soutenance.md").read_text(encoding="utf-8")
support = Path("docs/support_soutenance.md").read_text(encoding="utf-8")
durees = {}
for i, ch in re.findall(r"## (D\d\d)\..*?\n\n(    type:.*?\n(?:    .*\n)*)", support):
    m = re.search(r"^    duree: (\d+):(\d\d)$", ch, re.M)
    durees[i] = int(m.group(1)) * 60 + int(m.group(2)) if m else 0
blocs = re.split(r"^## (D\d\d)\.", script, flags=re.M)
mots = secondes = 0
for k in range(1, len(blocs), 2):
    dit = re.search(r"\*\*Dit\*\*\n\n((?:> .*\n|>\n|\n(?=> ))*)", blocs[k + 1])
    mots += len(re.findall(r"\w+", dit.group(1))) if dit else 0
    secondes += durees.get(blocs[k], 0)
print(f"{mots} mots pour {secondes//60}:{secondes%60:02d}, "
      f"soit {mots/(secondes/60):.0f} mots par minute")
FIN
```

Résultat attendu au 08/09/2026 : **3 882 mots pour 28:00, soit 139 mots par
minute.**

# Vérifier que ce script n'a pas divergé du support

À rejouer après toute modification de `docs/support_soutenance.md` ou de ce
fichier. Le contrôle porte sur les identifiants, leur ordre, et le budget.

```bash
python - <<'PY'
import re
from pathlib import Path

def ids(chemin, motif):
    return re.findall(motif, Path(chemin).read_text(encoding="utf-8"), re.M)

support = ids("docs/support_soutenance.md", r"^## (D\d\d)\.")
script   = ids("docs/script_soutenance.md",  r"^## (D\d\d)\.")
print(f"support : {len(support)} diapositives, script : {len(script)}")
print("identiques et dans le meme ordre :", support == script)
if support != script:
    print("  dans le support seul :", [d for d in support if d not in script])
    print("  dans le script seul  :", [d for d in script if d not in support])
PY
```

Résultat attendu, au 08/09/2026 : **31 diapositives de part et d'autre,
identiques et dans le même ordre**.

Le budget, lui, n'est saisi qu'une fois. Il vit dans les champs `duree` de
`docs/support_soutenance.md`, et `outils/generer_support.py` en rend la somme à
chaque génération : **28:00 sur 30:00**. Les minutes reprises ici en sont la
somme cumulée ; si le générateur annonce autre chose, c'est ce fichier qui a
tort.
