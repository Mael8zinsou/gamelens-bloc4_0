# Support de soutenance, Bloc 4

Soutenance du **vendredi 11/09/2026**, 30 minutes de présentation puis 15
d'échange. Dépôt sur DigiformaCertif le **mercredi 09/09**.

## Ce fichier est la source, le PPTX en est une sortie

`outils/generer_support.py` lit ce fichier et produit
`docs/support_soutenance.pptx`. L'inverse n'est pas vrai : une retouche faite
dans PowerPoint est perdue à la régénération suivante.

Deux usages, et c'est volontaire :

- **régénérer** le PPTX après une correction ici, ou après avoir déposé les
  captures d'écran manquantes dans `docs/captures/` ;
- **reconstruire** le deck entièrement à la main à partir de ce seul fichier, si
  le générateur venait à ne plus tourner ou si tu préfères finir dans
  PowerPoint. Tout ce qui est à l'écran et tout ce qui se dit est ici.

## Comment lire une diapositive

Chaque diapositive porte un bloc de métadonnées, puis ses puces, puis les notes
de ce qui se dit. Les notes atterrissent dans le volet commentaire du PPTX.

- `minute` : instant de début, cumulé depuis le début de la présentation.
- `criteres` : les numéros du tableau de traçabilité de
  `docs/plan_soutenance.md`. C'est ce que le jury coche.
- `type` : la forme de la diapositive, et donc sa mise en page.
  `couverture`, `puces`, `visuel` (image plein cadre), `capture` (emplacement
  réservé), `preuve` (sortie réelle en police fixe), `direct` (démonstration),
  `duo` (deux colonnes, chaque puce portant ses deux moitiés séparées par ` | `).
- `section` : le surtitre affiché. Il donne le rythme sans coûter de temps, là où
  des intercalaires en auraient consommé.
- `visuel` : chemin d'image sous `docs/`, ou `capture:<identifiant>` pour un
  emplacement réservé, ou `preuve:<fichier de docs/preuves>`.
- `legende` : la ligne sous l'image. Pour un `duo`, les deux titres de colonne,
  séparés par ` | `.

---

## D01. GameLens, concevoir et opérer une infrastructure data

    type: couverture
    minute: 00:00
    duree: 0:20
    competence: -
    criteres: -
    visuel: -
    legende: Une plateforme qui a tourné cette nuit à 02h30, sans personne aux commandes

### Puces

- Maël Mike ZINSOU, M2 Data Engineer, Paris YNOV Campus
- RNCP39586, Bloc 4 : concevoir et opérer une infrastructure data
- Kestrel Interactive, éditeur de jeux vidéo indépendant

### Notes

Ne pas lire la diapositive. Se présenter en une phrase et enchaîner.

Ouvrir sur la légende plutôt que sur l'identité : « cette plateforme a tourné
cette nuit à 2h30, sans personne aux commandes. Je vais vous montrer comment
elle est faite. » Vingt secondes déjà budgétées, et le registre change sans
coûter une minute.

Poser aussi l'amorce d'INC-004, sans la résoudre : « à un moment, un message
d'erreur m'a désigné un coupable qui n'avait rien à voir. J'y reviens à la
fin. » Une attente qui tient trente minutes, et qui donne à la section 10
l'attention qu'elle n'aurait pas à la vingt-cinquième minute.

---

## D02. Ce que je vais montrer, dans cet ordre

    type: puces
    section: Ouverture
    minute: 00:20
    duree: 0:30
    competence: -
    criteres: -
    visuel: -

### Puces

- 1. Le besoin, l'existant, les contraintes
- 2. Les composants retenus et leur coût
- 3. Le schéma de données
- 4. Les pipelines, trois méthodes
- 5. L'intégration et le déploiement continus
- 6. La supervision et les alertes
- 7. La feuille de route d'exploitation
- 8. La documentation technique
- 9. Le cahier de recettes
- 10. Un incident réel et sa méthode d'investigation

### Notes

Quarante secondes qui font gagner du temps au jury pendant les vingt-neuf
minutes suivantes : deux professionnels avec une grille en main peuvent cocher
au fil de l'eau au lieu de chercher. Dire explicitement : « les dix livrables
attendus, dans l'ordre de la grille ».

Trois démonstrations en direct sont annoncées ici, pour qu'elles ne surprennent
pas : le cloisonnement des rôles, l'orchestrateur, le tableau de bord.

---

## D03. Le besoin de Kestrel Interactive

    type: puces
    section: 1. Le besoin, l'existant, les contraintes
    minute: 00:50
    duree: 1:00
    competence: C4.1.1
    criteres: 1, 2
    visuel: -

### Puces

- Éditeur indépendant, une quinzaine de titres au catalogue
- B1 : suivre la popularité jouée et diffusée, jour après jour
- B2 : suivre la tarification, la sienne et celle du panel concurrent
- B3 : garder l'historique, pour comparer une sortie aux précédentes
- L'enjeu n'est pas la donnée, c'est de décider quand sortir et à quel prix

### Notes

Insister sur B3, qui est l'enjeu réel : les trois besoins se traduisent en une
exigence technique unique, disposer d'un historique que l'on possède. C'est ce
qui va tout déterminer ensuite, y compris l'arbitrage de la diapositive
suivante.

---

## D04. L'existant, et pourquoi ne pas simplement acheter

    type: duo
    minute: 01:50
    duree: 0:50
    competence: C4.1.1
    criteres: 5, 2
    visuel: -
    legende: Ce que les outils du marche font bien | Ce qu'ils ne donnent pas

### Puces

- Une couverture bien plus large que la nôtre | L'historique reste chez eux
- Une fraîcheur quotidienne, sans rien exploiter | Résilier, c'est perdre la série accumulée
- Aucune infrastructure à opérer | Aucune requête libre sur le détail
- Une équipe qui maintient les connecteurs | Un abonnement par siège, qui court

### Notes

L'arbitrage se joue sur la propriété de l'historique, pas sur le prix. C'est
la phrase à prononcer en quittant cette diapositive.

Commencer par ce que les outils du marché font **bien**. Un état de l'existant
qui ne dit que du mal n'est pas une analyse, c'est une justification.

Ne pas chiffrer la comparaison : leurs tarifs dépendent de paliers dont ce
projet n'a pas connaissance, et inventer un nombre pour faire pencher la
balance décrédibiliserait le reste. Le dire si la question vient.

---

## D05. L'environnement et les contraintes

    type: puces
    minute: 02:40
    duree: 0:40
    competence: C4.1.1
    criteres: 3, 4
    visuel: -

### Puces

- Deux fournisseurs raccordés : Steam pour la fréquentation et les tarifs, Twitch pour l'audience
- Aucun ne diffuse de flux : on échantillonne, on ne s'abonne pas
- 150 titres suivis, le catalogue de Kestrel et son panel concurrent, relevés toutes les 15 minutes
- Volumétrie mesurée : 176 octets par ligne archivée côté Steam, 3 231 côté Twitch
- Contraintes : un seul poste, aucun budget d'infrastructure, une échéance de soutenance
- Ce cadrage a décidé la suite : couche Bronze en PostgreSQL et non en stockage objet, entrepôt dimensionné XS

### Notes

La contrainte structurante n'est pas le volume, c'est que **les sources ne
diffusent pas de flux**. Le « temps réel » de ce projet est un échantillonnage
périodique, et il faut le dire soi-même avant que le jury ne le demande.

Sur le volume, assumer la révision plutôt que la taire, parce qu'elle est plus
instructive que le chiffre. Ce rapport a annoncé **41 Mo par an** pendant trois
semaines, et ce nombre a été corrigé deux fois le 08/09 : d'abord parce qu'il
désignait la taille de la charge JSON et non celle de la ligne archivée, ensuite
parce qu'une réponse Twitch décrit jusqu'à cent diffusions. La projection réelle
est de **17,5 Go par an**, dont 16 pour la seule audience.

Ce qui compte est que la conclusion tienne et que la marge ait fondu : 17,5 Go
restent tenables pour PostgreSQL, mais le point de vigilance V-05 est passé de
faible à forte. Un registre de risques se relit quand l'architecture change, pas
seulement quand un risque se matérialise.

La grille demande que ce rapport **permette de cadrer le travail de conception**.
Le dire en quittant la diapositive, avec un exemple et non en général : c'est
cette analyse qui a écarté le stockage objet, et non un arbitrage pris plus tard.

---

## D06. Les composants retenus

    type: visuel
    section: 2. Les composants et leur cout
    minute: 03:20
    duree: 1:10
    competence: C4.1.2
    criteres: 6, 7
    visuel: annexes/visuel_architecture.png
    legende: Deux fournisseurs, trois couches, deux cibles Gold, cinq chaines orchestrees.

### Puces

- Ingestion : Python, et Kafka en mode KRaft comme tampon durable
- Silver speed : PostgreSQL 16, la donnée récente et nettoyée
- Gold : Snowflake, cible de production, plus un prototype PostgreSQL gardé comme repli
- Orchestration : Airflow 3.1.8, en conteneurs
- Calcul distribué : Snowpark, et non Spark
- Transformation et contrats : dbt
- Supervision : indicateurs en SQL, Grafana pour l'affichage

### Notes

Pour chaque composant, une phrase sur l'alternative écartée. Kafka plutôt qu'une
file légère parce que le rejeu des offsets est ce qui prouve l'idempotence.
Snowpark plutôt que Spark : y revenir en section 4, ne pas s'y attarder ici.

Ne pas réciter le tableau. Le jury lit plus vite qu'on ne parle.

---

## D07. Points de vigilance : la dépendance fournisseur

    type: puces
    minute: 04:30
    duree: 0:50
    competence: C4.1.2
    criteres: 8
    visuel: -

### Puces

- Faible sur Kafka, PostgreSQL, dbt : standards ouverts, réversibles
- Modérée sur Airflow et l'intégration continue : le code est portable, pas la plomberie
- Forte sur Snowflake, et sur lui seul : SQL propriétaire, Snowpark, facturation à l'usage
- Atténuation assumée : le prototype PostgreSQL du Gold est maintenu et alimenté
- Ce n'est pas un plan de sortie, c'est un chemin de repli documenté

### Notes

Le critère nomme explicitement le vendor lock-in. Répondre composant par
composant, pas globalement : une réponse globale ne prouve pas qu'on a regardé.

La dernière puce est importante : ne pas prétendre qu'on pourrait quitter
Snowflake en une journée. Dire ce que le repli couvre et ce qu'il ne couvre pas.

---

## D08. Les coûts, mesurés et non estimés

    type: visuel
    minute: 05:20
    duree: 1:00
    competence: C4.1.2
    criteres: 9
    visuel: annexes/visuel_couts.png
    legende: Releve dans l'historique de facturation, pas estime.

### Puces

- 2,1566 crédits consommés en 12 jours, relevés dans l'historique de facturation
- gamelens_wh : 1,4663 crédit. Dimensionné XS, suspension automatique à 60 secondes
- COMPUTE_WH, l'entrepôt par défaut jamais configuré : 0,6899, soit 32 % au 31/08
- Au rythme mesuré, les 108 jours restants coûtent une vingtaine de crédits sur 400
- Ce n'est donc pas le budget qui contraint, c'est la date d'expiration du compte

### Notes

Le mot qui compte est **mesuré**. Beaucoup de candidats estiment ; l'historique
de facturation existe et se lit.

L'aveu sur COMPUTE_WH est volontaire : un entrepôt que personne n'utilise
volontairement pèse un tiers de la facture. C'est le genre de détail qui montre
qu'on a regardé pour de vrai, et il amène naturellement la feuille de route.

Citer la mesure avec sa date. Le pourcentage seul serait trompeur : la
consommation absolue de COMPUTE_WH a augmenté, c'est sa part qui recule.

---

## D09. Le schéma de données

    type: visuel
    section: 3. Le schema de donnees
    minute: 06:20
    duree: 1:10
    competence: C4.2.1
    criteres: 10, 12
    visuel: annexes/schema_donnees.png
    legende: Genere depuis le catalogue Snowflake : ce schema ne peut pas deriver du reel.

### Puces

- Modèle en étoile : deux dimensions, deux tables de faits, une vue de restitution
- Grain journalier pour la popularité, grain (jeu, boutique, instant) pour les prix
- Colonnes larges plutôt qu'un modèle entité-attribut-valeur
- Clé primaire interne en UUID, indépendante des identifiants sources
- Ce schéma est généré depuis le catalogue, il ne peut pas dériver du réel

### Notes

Compétence éliminatoire. Laisser le schéma à l'écran et le commenter, sans lire
les colonnes.

Justifier les colonnes larges : les indicateurs suivis sont connus et peu
nombreux, un EAV coûterait une jointure à chaque lecture pour une souplesse dont
personne n'a besoin ici.

La dernière puce mérite dix secondes : le diagramme est produit par
`outils/generer_schema.py` à partir du catalogue Snowflake. Un schéma dessiné à
la main ment tôt ou tard.

---

## D10. Les modalités d'accès, démontrées

    type: direct
    minute: 07:30
    duree: 0:50
    competence: C4.2.1
    criteres: 11
    visuel: direct:cloisonnement_roles

### Puces

- Quatre rôles, hérités du Bloc 1 : admin, etl_service, analyst, dashboard_viewer
- dashboard_viewer ne voit qu'une vue, jamais les tables de faits
- Démonstration : la même requête, refusée puis servie

### Notes

**DIRECT 1**, environ quarante secondes, entièrement local, aucun réseau requis.

Deux commandes préparées dans un terminal déjà ouvert, police agrandie :

1. `dashboard_viewer` interroge `mart.fact_prices` : `permission denied for
   table fact_prices`
2. le même rôle interroge `mart.v_popularity_dashboard` : trois lignes de
   données du jour

Dire pendant que ça tourne : « le cloisonnement se prouve mieux par un refus que
par une matrice de droits ».

Repli : `docs/preuves/c11_cloisonnement_roles.txt`, à la diapositive suivante du
PPTX. Si le direct ne répond pas en dix secondes, passer au repli sans commenter.

---

## D11. Ce que Snowflake n'applique pas

    type: duo
    minute: 08:20
    duree: 1:00
    competence: C4.2.1
    criteres: 10, 12
    legende: Déclaré dans le schéma | Réellement appliqué par le moteur

### Puces

- CHECK, sur une valeur | NOT NULL
- FOREIGN KEY, entre deux tables | Le type de la colonne
- PRIMARY KEY, entre lignes | La longueur de la colonne
- UNIQUE, entre lignes | Rien d'autre

### Notes

C'est le point technique le plus fort du projet. Le présenter comme un **choix
d'architecture assumé**, pas comme une découverte subie.

La règle sous-jacente, à énoncer à l'oral : Snowflake applique ce qui se vérifie
sur la colonne seule, et ignore tout ce qui suppose de regarder une autre ligne
ou une autre table.

Enchaîner sur ce que cela coûte : l'intégrité est reportée hors du moteur, sur
29 contrats déclaratifs dbt et 8 contrôles applicatifs, rejoués à chaque push et
éprouvés en négatif sur le même jeu de données fautif. Vérifié empiriquement,
pas lu dans une documentation : `sql/verify_snowflake_constraints.sql`.

Si la question « pourquoi deux filets et pas un seul ? » vient : ils ne
contrôlent pas la même chose. dbt contrôle la forme des données, déclarativement
et sur les quatre tables. `verifier_gold.py` contrôle des invariants métier que
dbt n'exprime pas, et il tourne sans dbt. La recette d'intégration continue leur
soumet le même jeu fautif pour vérifier qu'ils restent d'accord.

---

## D12. Trois méthodes de traitement, annoncées

    type: puces
    section: 4. Les pipelines, trois methodes
    minute: 09:20
    duree: 0:30
    competence: C4.2.2
    criteres: 13, 14, 15
    visuel: -

### Puces

- Un pipeline temps réel : Steam et Twitch vers Kafka vers PostgreSQL
- Un orchestrateur : Airflow, cinq DAG
- Un calcul distribué : Snowpark, sur le compute Snowflake

### Notes

Trente secondes d'annonce, pour que le jury sache que les trois méthodes exigées
arrivent et dans quel ordre. Compétence éliminatoire : c'est la section à ne
jamais sacrifier si le temps déborde.

---

## D13. Méthode 1, le pipeline temps réel

    type: puces
    minute: 09:50
    duree: 1:20
    competence: C4.2.2
    criteres: 13
    visuel: -

### Puces

- Deux sources, 150 titres : Steam sans authentification, Twitch en OAuth client_credentials
- Kafka en mode KRaft, sans ZooKeeper : c'est bien Apache Kafka
- Un topic par source, un seul consommateur paramétré qui choisit sa table sur le topic
- Idempotence prouvée par rejeu : 735 messages relus sur les deux topics, zéro inséré
- Orchestré toutes les quinze minutes, avec porte de sortie et reprise vérifiée

### Notes

L'idempotence est le point à défendre, et elle se prouve par le **rejeu des
offsets** : on remet le consommateur au début des deux topics, on relit
735 messages, et rien ne s'insère. Un test qui vérifie seulement que la requête
ne plante pas ne prouve rien.

Si le jury demande comment la seconde source a été absorbée : le consommateur a
été **paramétré, pas dupliqué**. Un second module aurait été plus rapide à
écrire et sans risque pour le chemin déjà éprouvé, mais il aurait figé deux
exemplaires de la garantie de livraison, donc deux endroits où la corriger le
jour où elle se révèle fausse. C'est précisément pour cela que le rejeu a été
refait après la modification, et sur un périmètre quarante-neuf fois plus large
que la preuve d'origine.

Dire honnêtement que le « temps réel » est ici un échantillonnage périodique,
puisque la source ne diffuse pas de flux. Cette honnêteté a plus de valeur que
le mot.

Le test négatif vaut d'être cité : broker coupé, le pipeline échoue proprement,
et la reprise automatique a été vérifiée.

---

## D14. Deux sources, parce qu'elles ne mesurent pas la même chose

    type: puces
    minute: 11:10
    duree: 0:40
    competence: C4.1.1
    criteres: 1, 13
    visuel: -

### Puces

- B1 demandait la popularité jouée ET diffusée : les deux moitiés sont collectées
- Steam dit qui joue, Twitch dit qui regarde, et leur rapport ne se déduit d'aucun des deux
- Le même jour, à la même heure : Rust, 0,05 spectateur par joueur. Fall Guys, 13,6
- L'audience diffusée monte avant les ventes : un indicateur d'avance, pas une redondance
- Critère de raccordement : l'axe qu'une source ajoute, jamais sa richesse

### Notes

Quarante secondes, et c'est la seule diapositive où la plateforme **répond à une
question métier** au lieu de montrer sa plomberie. La seconde source a été
raccordée le 08/09 : le dire si on le demande, ne pas l'annoncer soi-même, la
date n'ajoute rien au propos. Ne pas la sacrifier en
premier si le temps déborde, malgré son apparence de supplément.

Le chiffre à faire entendre est Fall Guys : 544 joueurs connectés et 7 408
personnes en train de le regarder. Treize fois plus de spectateurs que de
joueurs. Un éditeur qui ne suivrait que la fréquentation conclurait que ce titre
est mort, et il se tromperait.

Si le jury demande pourquoi Twitch plutôt que RAWG, IGDB ou GG.deals, la réponse
est le critère et non la source : RAWG et IGDB apportent du catalogue, donc du
statique ; GG.deals apporte des tarifs, un axe déjà couvert. Twitch était la
seule à ajouter une mesure que Steam ne donne pas. Ajouter, si la question va
plus loin, qu'IGDB serait la prochaine parce qu'elle s'authentifie avec les
**mêmes identifiants que Twitch**, déjà en place.

Répondre ici, et pas plus tard, à l'objection de dimensionnement : c'est la
diapositive qui la désamorce.

---

## D15. Méthode 2, l'orchestrateur

    type: direct
    minute: 11:50
    duree: 1:20
    competence: C4.2.2
    criteres: 14
    visuel: direct:airflow

### Puces

- Airflow 3.1.8, en conteneurs : il ne tourne pas nativement sous Windows
- Cinq DAG : ingestion toutes les 15 min, deux promotions nocturnes, supervision, battement
- Deux promotions distinctes, et non une seule : c'est un choix, pas un oubli
- Portes de fraîcheur, testées en négatif sur les deux promotions

### Notes

**DIRECT 2**, environ soixante secondes, local, aucun réseau requis.

Montrer la liste des cinq DAG, leur historique de runs, puis le graphe de
`gamelens_promotion_gold` et ses six tâches.

Le cinquième, `gamelens_battement`, mérite dix secondes : il ne produit aucune
donnée, il ne sert qu'à dénoncer l'arrêt de la supervision. Un dispositif qui se
surveille lui-même ne prouve rien ; il fallait un DAG séparé.

Expliquer les deux promotions séparées : Snowflake est un service tiers facturé
dont l'indisponibilité ne doit pas emporter la promotion locale. Les fusionner
aurait couplé un composant local à un fournisseur externe.

Repli : `docs/preuves/c14_airflow_dags.txt` et la capture d'écran.

---

## D16. Méthode 3, le calcul distribué

    type: puces
    minute: 13:10
    duree: 1:00
    competence: C4.2.2
    criteres: 15
    visuel: -

### Puces

- Snowpark, et non Spark : le référentiel cite Spark en exemple, l'exigence porte sur le distribué
- Un Spark local aurait tourné en mono-machine, sur ce poste
- Snowpark construit du SQL et le pousse sur le compute Snowflake
- MERGE idempotents, fenêtre glissante sur 7 jours, classement par genre
- Orchestré quotidiennement depuis le 31/08

### Notes

Anticiper la question « en quoi est-ce distribué ? » au lieu de l'attendre. Elle
viendra, et il vaut mieux y répondre soi-même avant.

Le raisonnement à énoncer : ce qui compte n'est pas le nom du produit mais où
s'exécute le calcul. Sur ce poste, Spark aurait tourné en local sur une machine.
Snowpark n'exécute rien ici : il transmet.

La preuve arrive à la diapositive suivante.

---

## D17. La preuve : le SQL que Snowpark génère

    type: preuve
    minute: 14:10
    duree: 1:20
    competence: C4.2.2
    criteres: 15
    visuel: preuve:c15_snowpark_sql_genere.txt
    legende: Extrait de docs/preuves/c15_snowpark_sql_genere.txt, capture du 01/09.

### Puces

- rank() OVER (PARTITION BY genre ORDER BY joueurs_moyens DESC)
- avg() OVER (PARTITION BY jeu ORDER BY jour ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
- Aucune ligne ne transite par le poste : seul le résultat revient
- Capturé dans docs/preuves/c15_snowpark_sql_genere.txt

### Notes

C'est la réponse matérielle, et elle vaut mieux qu'un argument. Montrer le SQL
généré, pas une brochure.

Le point à faire entendre : les fonctions de fenêtrage sont exécutées par le
moteur Snowflake sur ses propres nœuds. Le programme Python décrit un calcul, il
ne l'exécute pas. C'est exactement ce que fait Spark, avec un moteur différent.

Si le jury insiste, l'historique de session Snowflake montre les requêtes reçues
côté serveur.

---

## D18. L'intégration et le déploiement continus

    type: visuel
    section: 5. Integration et deploiement continus
    minute: 15:30
    duree: 1:20
    competence: C4.2.3
    criteres: 16
    visuel: annexes/visuel_ci.png
    legende: Les etages 4 et 5 montent une infrastructure neuve, l'eprouvent, puis la detruisent.

### Puces

- Six étages, à chaque push et chaque pull request
- Qualité, tests, intégrité des DAG, intégration, recette de l'entrepôt, publication
- L'infrastructure d'intégration est créée puis détruite à chaque run
- Image Airflow publiée sur ghcr.io, étiquetée latest et par le SHA du commit

### Notes

Compétence éliminatoire, et la seule dont la preuve vit sur github.com : elle ne
peut pas être montrée en direct sans réseau. Capture obligatoire.

Le point qui distingue cette chaîne d'un simple lanceur de tests : les étages
d'intégration et de recette **montent une infrastructure neuve**, l'éprouvent,
puis la détruisent. Rien n'est testé contre un état accumulé.

Mentionner que le premier run avait échoué, et que le défaut était dans
l'assertion et non dans l'infrastructure. Un pipeline qui passe du premier coup
n'a en général rien vérifié.

---

## D19. Six étages au vert, sur le dernier run

    type: capture
    minute: 16:50
    duree: 1:10
    competence: C4.2.3
    criteres: 16
    visuel: capture:github_actions
    legende: Le dernier run de la branche principale, six etages au vert.

### Puces

- Une base Snowflake créée pour la durée du run, puis supprimée
- Le schéma livré est appliqué, le calcul distribué confronté à des valeurs calculées à la main
- Le comportement du moteur sur les contraintes est re-vérifié à chaque push
- Les deux filets d'intégrité sont éprouvés en positif ET en négatif, sur le même jeu fautif
- La couche de démonstration n'est jamais visée : le script refuse de démarrer si elle l'était

### Notes

La dernière puce est le genre de détail qu'un jury de professionnels remarque :
`entrepot/recette_ci.py` porte une liste de bases protégées et sort en erreur
plutôt que de risquer de détruire la démonstration.

L'épreuve en négatif est le point fort : vérifier qu'un contrôle passe ne prouve
pas qu'il contrôle. On lui soumet des données fautives et on exige qu'il échoue.

La clé privée n'est jamais écrite sur le disque du runner : elle transite par une
variable d'environnement, en contenu PEM.

---

## D20. La supervision : ce que l'on surveille, et pourquoi

    type: puces
    section: 6. Supervision et alertes
    minute: 18:00
    duree: 1:00
    competence: C4.3.1
    criteres: 17, 18
    visuel: -

### Puces

- Cinq indicateurs : fraîcheur, complétude, latence, fiabilité par composant, fraîcheur du Gold
- Les seuils sont définis en SQL, pas dans l'outil d'affichage
- Conséquence : ils restent interrogeables par n'importe quel client, même Grafana arrêté
- Le tableau de bord est provisionné comme code, pas cliqué dans une interface
- Grafana se connecte avec le rôle analyst, en lecture seule

### Notes

Le choix à défendre : **l'outil affiche les indicateurs, il ne les définit pas.**
Un seuil enfermé dans une interface graphique est un seuil qu'on ne peut ni
tester, ni versionner, ni interroger autrement.

C'est ce qui permet d'affirmer que la supervision survivrait à un changement
d'outil de restitution.

---

## D21. Les indicateurs, à l'écran

    type: direct
    minute: 19:00
    duree: 1:00
    competence: C4.3.1
    criteres: 19
    visuel: direct:grafana

### Puces

- Sept panneaux, vérifiés par un contrôle automatisé
- Fraîcheur par flux, complétude de la collecte, latence, fiabilité, alertes ouvertes

### Notes

**DIRECT 3**, environ soixante secondes, local, aucun réseau requis.

Ouvrir le tableau de bord et le laisser parler. Ne commenter que deux panneaux,
pas les sept.

Si la donnée du jour est présente, le dire : la plateforme a tourné cette nuit,
sans intervention. C'est plus convaincant qu'une capture.

Repli : la capture d'écran, à la diapositive suivante du PPTX.

---

## D22. Les alertes, et leur cycle de vie

    type: puces
    minute: 20:00
    duree: 1:00
    competence: C4.3.1
    criteres: 20
    visuel: -

### Puces

- Six règles, évaluées toutes les quinze minutes par un DAG
- Cycle complet : déclenchement, non-duplication, fermeture automatique
- Une alerte au plus par règle : sans cela, 96 lignes par jour pour un seul incident
- Fenêtre par composant, et non fenêtre unique : 24 h pour les collectes fréquentes, 26 h pour les quotidiennes
- Un incident réel de quatre jours a été détecté puis refermé seul, en moins de cinq minutes
- Notification Telegram immédiate des alertes critiques, mesurée à 2 secondes

### Notes

La non-duplication et la fermeture automatique sont ce qui distingue un système
d'alertes d'un simple journal d'erreurs.

La fenêtre par composant est un piège évité et qui vaut d'être raconté : une
fenêtre unique de 24 heures déclarerait muet, à chaque cycle, un composant qui ne
tourne qu'une fois par jour.

Le canal externe est récent, 07/09, et il vaut d'être présenté par le manque
qu'il comble plutôt que par la fonctionnalité : avant lui, une alerte de
fraîcheur est restée ouverte **6 jours et 20 heures** parce que personne ne la
regardait. Le système la voyait, il ne le disait à personne.

Deux propriétés à citer, parce qu'elles sont testées et contre-intuitives. Sans
jeton configuré, la notification est un no-op qui rend un succès ; avec un jeton
présent mais injoignable, elle trace un échec. Un dispositif d'alerte ne doit
jamais faire tomber la chaîne qu'il surveille, mais son propre silence ne doit
pas être silencieux.

---

## D23. La feuille de route d'exploitation

    type: puces
    section: 7. Feuille de route d'exploitation
    minute: 21:00
    duree: 1:00
    competence: C4.3.2
    criteres: 21, 22, 23
    visuel: -

### Puces

- Tâches du quotidien au trimestriel, avec leur fréquence et leur durée
- Échéances datées, dont l'expiration du compte Snowflake
- Fenêtres de maintenance, et l'ordre d'arrêt et de redémarrage des composants
- Procédures d'intervention éprouvées avant d'être prescrites, pas rédigées d'avance

### Notes

La dernière puce est le point de méthode : une procédure écrite sans avoir été
exécutée est une intention. Celles de ce document ont toutes été jouées au moins
une fois, et les durées annoncées sont mesurées.

Exemple concret si le jury veut du détail : la procédure de reprise après
coupure du broker Kafka a été exécutée, et le pipeline a repris seul.

---

## D24. Les points de vigilance

    type: chiffre
    minute: 22:00
    duree: 1:00
    competence: C4.3.2
    criteres: 24
    chiffre: 9
    legende: points de vigilance ouverts, sur quatorze numérotés et cinq refermés

### Puces

- Nommés, numérotés, et pour deux d'entre eux datés
- Cinq refermés en cours de projet, dont V-02 et V-07 le 07/09 : la feuille de route vit
- V-01, expiration du compte Snowflake : le seul réellement bloquant
- V-03, l'utilisateur de service tourne avec des droits trop larges
- V-05, la couche Bronze sans conservation définie : requalifié de faible à FORTE le 08/09
- COMPUTE_WH à réduire : mesuré à 32 % de la consommation au 31/08

### Notes

Nommer ses propres limites, avec leur numéro et leur mesure, avant que le jury ne
les cherche. C'est un exercice qu'un jury de professionnels cherche à provoquer,
et le devancer vaut mieux que le subir.

**V-05 est l'histoire à raconter, et elle tient en trois phrases.** Ce point
était classé faible depuis l'origine, et ce classement était juste au moment où
il a été posé : la couche Bronze grossissait alors de 41 Mo par an. Le
raccordement de Twitch l'a fait passer à 17,5 Go sans que personne ne touche à
V-05, parce qu'une réponse d'audience décrit jusqu'à cent diffusions là où un
compteur de joueurs tient dans un entier. Un registre de risques se relit quand
l'architecture change, pas seulement quand un risque se matérialise.

Si le jury demande pourquoi ne pas tronquer ce qu'on archive : ce serait décider
aujourd'hui de ce dont on aura besoin demain, ce que la couche Bronze existe
précisément pour éviter. C'est la durée de conservation qui doit devenir une
décision, pas le contenu.

---

## D25. La documentation technique

    type: puces
    section: 8. Documentation technique
    minute: 23:00
    duree: 1:00
    competence: C4.3.3
    criteres: 25
    visuel: -

### Puces

- Treize décisions d'architecture, datées, chacune avec sa contrepartie
- Traçabilité champ par champ, de la source à la couche Gold
- Deux annexes GÉNÉRÉES depuis le catalogue des bases, jamais écrites à la main
- L'intégration continue échoue si une annexe ne correspond plus au schéma

### Notes

Le critère porte sur le **choix** de la documentation. L'argument n'est donc pas
le volume, c'est le mécanisme : un dictionnaire de données généré ne peut pas
mentir sur le schéma, et la chaîne d'intégration refuse le push s'il diverge.

Sur les décisions d'architecture : chacune porte sa contrepartie, ce qu'elle a
coûté. Une décision sans inconvénient documenté est une décision qu'on n'a pas
vraiment prise.

---

## D26. Le cahier de recettes

    type: visuel
    section: 9. Cahier de recettes
    minute: 24:00
    duree: 0:45
    competence: C4.4.1
    criteres: 26, 27
    visuel: annexes/visuel_recettes.png
    legende: Les trois familles exigees par la grille, en bleu, et celles que le projet a ajoutees.

### Puces

- 70 cas, 0 partiel, 0 en attente
- Fonctionnels : 5. Structurels : 19. Sécurité : 3. Plus les huit catégories propres au projet
- Format retenu : PASS ou FAIL vérifié sur un résultat attendu
- Et non « la requête s'exécute sans erreur », qui ne prouve rien

### Notes

Le critère nomme trois familles : fonctionnels, structurels, de sécurité. Le
cahier est structuré sur ces trois-là. Montrer la table de synthèse.

Le format est le point de méthode : chaque cas énonce son résultat attendu avant
son résultat obtenu. Le premier cas conforme à ce format était le rejeu des
offsets Kafka, quinze relus et zéro inséré ; le même contrôle en compte
aujourd'hui 735, sur deux topics.

---

## D27. Éprouvé en négatif

    type: puces
    minute: 24:45
    duree: 0:45
    competence: C4.4.1
    criteres: 27
    visuel: -

### Puces

- Vérifier qu'un contrôle passe ne prouve pas qu'il contrôle
- Les deux filets d'intégrité sont soumis au même jeu de données fautif
- Les tests de sécurité valident aussi les refus : treize cas, en 20 cas paramétrés
- Les portes de fraîcheur ont été testées en coupant réellement la source
- Le panel : cinq identifiants Steam désignaient un autre jeu, et répondaient tous en HTTP 200

### Notes

C'est la différence entre un cahier de recettes et une liste de vœux. Trois
exemples suffisent, ne pas les énumérer tous.

Le cas du broker Kafka coupé est le plus parlant sur la reprise : on a arrêté le
conteneur, vérifié que le pipeline échouait proprement, puis qu'il reprenait
seul.

Le cas du panel est le plus parlant sur la nature d'un contrôle. En portant le
panel à 150 titres, cinq identifiants présumés désignaient un autre jeu :
`Void Bastards` pointait sur *Warhammer 40,000: Mechanicus*. Aucun n'aurait
produit d'erreur. Ils auraient collecté des données parfaitement valides sur les
mauvais jeux, indéfiniment, avec une fraîcheur bonne et des tests au vert. Ce
que le contrôle vérifie n'est donc pas l'absence d'erreur mais une
**correspondance** : le nom rendu par Steam est confronté au nom attendu.

---

## D28. Un incident réel : INC-004

    type: preuve
    section: 10. Un incident reel
    minute: 25:30
    duree: 1:00
    competence: C4.4.2
    criteres: 28
    visuel: preuve:c28_inc004_traceback.txt
    legende: Rejoué le 01/09/2026, à l'identique : même octet 0xe9, même position 103

### Puces

- Le message ne dit pas ce qui ne va pas : il dit qu'il n'a pas su lire ce qui ne va pas
- L'octet 0xe9 est le « é » de « échouée », dans un message PostgreSQL en français
- Fausse piste évidente, et coûteuse : le projet est stocké sous un chemin accentué

### Notes

L'intérêt de cet incident n'est pas sa difficulté, qui est faible. C'est que **le
message d'erreur désignait un coupable qui n'avait rien à voir avec la cause**.

L'octet 0xe9 était le « é » de « échouée », dans un message d'erreur PostgreSQL
en français. Le décodage a échoué avant que l'erreur utile ne remonte.

Raconter cet enchaînement lentement : c'est la partie que le jury retient.

---

## D29. La méthode, et ce qu'elle a donné

    type: visuel
    minute: 26:30
    duree: 1:00
    competence: C4.4.2
    criteres: 29, 30, 31
    visuel: annexes/visuel_investigation.png
    legende: Cinq étapes, deux hypothèses écartées, et celle qui a tranché

### Puces

- Ce qui a tranché : la LANGUE du message d'erreur, devenue empreinte du serveur
- Une Alpine en locale C ne peut répondre qu'en anglais ASCII : le français prouvait l'imposture
- Communication, immédiat : mention en daily, tout poste avec un PostgreSQL local se bloquera pareil
- Puis un prérequis ajouté à la procédure d'installation, et cette entrée de journal pour la trace
- Résultat vérifié par l'exécution : la chaîne complète, et le rejeu idempotent à 0 inséré

### Notes

C'est le cœur du livrable C4.4.2, et la grille y attend quatre choses : la
nature du problème, les actions selon les scénarios, **la communication aux
parties prenantes**, et les résultats. La troisième est celle que les candidats
oublient le plus souvent ; elle est ici en deux puces, immédiat puis durable.

Le raisonnement sur la langue est le moment fort. La langue d'un message d'erreur
a servi d'empreinte pour identifier quel serveur répondait. Le dire ainsi.

Fermer sur la phrase de résultat que la grille demande : **la méthode a résolu
l'incident**, et la vérification n'a pas été l'absence d'erreur mais l'exécution
réelle de la chaîne. Ajouter que le port 5433 est commenté dans
`docker-compose.yml` pour que personne ne « corrige » l'anomalie apparente et ne
réintroduise l'incident.

Les deux scénarios écartés : arrêter le service natif, ce qui casse d'autres
travaux et se refait à chaque redémarrage ; le désinstaller, disproportionné.

Sur la communication aux parties prenantes, rubrique que beaucoup oublient :
incident de poste de développement, sans impact sur un service rendu, donc aucune
remontée au commanditaire. La communication pertinente est interne et technique,
et le commentaire laissé dans `docker-compose.yml` en fait partie : il empêche un
lecteur futur de « corriger » l'anomalie apparente et de réintroduire l'incident.

---

## D30. Ce que je n'ai pas fait

    type: chiffre
    section: Cloture
    minute: 27:30
    duree: 0:30
    competence: -
    criteres: -
    chiffre: × 437
    legende: l'écart entre le volume annuel que mon rapport annonçait et celui que j'ai mesuré

### Puces

- Aucune politique de conservation, et l'assiette du risque a été multipliée par 437
- L'utilisateur de service tourne toujours en ACCOUNTADMIN
- Un seul environnement : ni recette, ni production séparées
- Tous documentés et numérotés. Deux autres y figuraient début septembre, et sont refermés

### Notes

Trente secondes, et elles ouvrent les quinze minutes d'échange bien mieux qu'une
conclusion triomphale.

Ne pas s'excuser. Énoncer, dire pourquoi ça n'a pas été traité, et s'arrêter. Un
jury de professionnels sait qu'une plateforme a toujours une dette ; ce qu'il
veut savoir, c'est si le candidat la connaît.

Le 437 est le plus honnête des trois aveux, et il se raconte en deux phrases.
Mon propre rapport d'analyse annonçait 41 Mo par an ; la mesure du 08/09 en
donne 17,5 Go. Une partie de l'écart vient d'une décision que j'ai prise, porter
le panel à 150 titres et brancher une seconde source ; l'autre vient d'une
erreur de désignation, les octets annoncés étaient ceux de la charge JSON et non
de la ligne archivée. Ni l'une ni l'autre ne se voyait dans le document.

La dernière puce est ce qui sépare une dette d'un renoncement : le canal de
notification absent et la supervision qui ne se surveillait pas figuraient sur
cette diapositive au début du mois, et ils n'y sont plus. Le dire, sans
insister, et sans donner la date de soi-même.

---

## D31. Questions

    type: couverture
    minute: 28:00
    duree: 0:00
    competence: -
    criteres: -
    visuel: -
    legende: Le depot, la documentation et les preuves sont a disposition

### Puces

- Merci
- Le dépôt, la documentation et les preuves sont à disposition

### Notes

Diapositive hors temps. Les questions probables et leurs réponses sont dans la
section 8 de `docs/plan_soutenance.md`, à relire la veille.

---

# Emplacements réservés pour les captures d'écran

Le générateur pose un cadre à la bonne place et à la bonne taille pour chacune.
Déposer les images sous ces noms exacts dans `docs/captures/`, puis régénérer :
elles remplacent le cadre automatiquement.

| Identifiant | Fichier attendu | Diapo | Où le prendre | Réseau |
|---|---|---|---|---|
| `github_actions` | `docs/captures/github_actions.png` | D19 | GitHub, onglet Actions, les 6 étages d'un run vert | requis |
| `airflow` | `docs/captures/airflow.png` | D15 | http://localhost:8080, les 5 DAG puis un graphe | non |
| `grafana` | `docs/captures/grafana.png` | D21 | http://localhost:3000, le tableau de bord entier | non |

Celle marquée « réseau requis » est à prendre **avant le dépôt du 09/09**.

La consommation de crédits ne figure plus dans ce tableau : elle est désormais
portée par un graphique généré depuis les chiffres mesurés, ce qui vaut mieux
qu'une capture de Snowsight et fait une capture de moins à prendre.

# Les trois moments en direct

Chacun est suivi, dans le PPTX, d'une diapositive de repli portant la preuve
textuelle déjà capturée. Règle de scène : si le direct ne répond pas en dix
secondes, passer au repli sans commenter l'incident.

| Identifiant | Diapo | Durée | Repli |
|---|---|---|---|
| `cloisonnement_roles` | D10 | ~40 s | `docs/preuves/c11_cloisonnement_roles.txt` |
| `airflow` | D15 | ~60 s | `docs/preuves/c14_airflow_dags.txt` et la capture |
| `grafana` | D21 | ~60 s | la capture |
