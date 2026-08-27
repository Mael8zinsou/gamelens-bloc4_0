# GameLens, expliqué simplement

## Le contrat de lecture

Je pars du principe que vous savez ce qu'est un programme, une base de données
et une API. Je ne suppose rien de plus.

Chaque fois que j'emploie un mot du métier, je l'explique au moment où je
l'emploie. Il y a un lexique à la fin, mais vous ne devriez pas en avoir besoin
pour suivre.

Le document se termine par une section inhabituelle : **la liste des endroits
où mon explication ne tient pas encore**. C'est volontaire. Quand on n'arrive
pas à expliquer quelque chose simplement, c'est en général qu'on ne l'a pas
compris, et il vaut mieux le dire que le masquer sous du vocabulaire.

---

## 1. Le problème

Imaginez un éditeur de jeux vidéo indépendant. Une quinzaine de titres, une
petite équipe. Appelons-le Kestrel Interactive, c'est le client fictif de ce
projet.

Tous les matins, les mêmes questions reviennent :

- combien de gens jouent à nos jeux en ce moment ?
- combien jouent à ceux des concurrents ?
- à quel prix sont-ils vendus, et qui a lancé une promotion cette nuit ?
- de quoi parle-t-on sur les plateformes de diffusion en direct ?

Les réponses existent, éparpillées. Steam sait combien de joueurs sont
connectés. Twitch sait qui est regardé. Un catalogue en ligne sait quels jeux
existent. Chacun met ces informations à disposition par une API, c'est-à-dire
une adresse où un programme peut aller poser une question et recevoir une
réponse.

Des entreprises vendent des outils qui font ce travail de regroupement. Ils
coûtent cher, et ils décident pour vous de ce que vous pouvez regarder.

D'où la question, qui est un classique : **on achète, ou on construit ?**
GameLens est la réponse « on construit ». C'est un système qui va chercher ces
informations en continu, les range, et les rend consultables.

Dit comme ça, ça a l'air d'un après-midi de travail. Trois adresses à
interroger, un peu de code, une base, un tableau. La suite explique pourquoi
ça ne l'est pas.

---

## 2. L'image qui va me servir de fil : une cuisine

Je vais comparer ce système à la cuisine d'un restaurant. L'analogie tient
étonnamment bien, et je vous préviendrai quand elle cessera de tenir.

Un restaurant reçoit des marchandises, les prépare, et sert des plats. Entre la
caisse de légumes qui arrive du marché et l'assiette qui part en salle, il y a
plusieurs étapes, et surtout plusieurs **états** de la même matière.

GameLens fait exactement ça avec de l'information au lieu de nourriture.

---

## 3. Les trois étages de la cuisine

Dans le métier, on appelle ça une **architecture en médaillon**, avec trois
niveaux nommés bronze, argent et or. Voilà ce que ça veut dire concrètement.

### Le quai de livraison (bronze)

Les caisses arrivent du marché. On ne touche à rien. On note ce qui est arrivé,
quand, et de quel fournisseur. Même les légumes abîmés sont conservés tels
quels.

Pourquoi garder des légumes abîmés ? Parce que le jour où un client tombe
malade, on veut pouvoir remonter à la livraison exacte. Si on a jeté les
cageots, on ne peut plus rien vérifier.

Pour les données, c'est pareil et c'est même plus important : le jour où l'on
découvre une erreur dans un calcul, on veut pouvoir **tout recommencer à partir
de la matière première**. Si on a écrasé la matière première par le résultat du
calcul, on ne peut plus rien recommencer.

Ici, chaque question posée à Steam est conservée avec la réponse exacte, y
compris **les questions qui n'ont pas obtenu de réponse utile**. Ce second
point est le moins évident et probablement le plus précieux : « on a demandé le
nombre de joueurs de ce jeu à 14h03, et on a reçu une erreur » est une
information, pas un vide. C'est le signal d'un jeu retiré de la vente, ou d'un
service qui se dégrade. Avant, ça ne laissait qu'une ligne dans un fichier de
journal, vite noyée.

### La préparation (argent)

Là, on lave, on épluche, on calibre, on jette ce qui est mauvais. À la sortie,
tout est propre, régulier, utilisable.

C'est l'étape où l'on répare les incohérences. En voici une vraie, et elle est
plus gênante qu'elle n'en a l'air.

Le même jeu ne porte pas le même nom ni le même numéro selon l'endroit où on le
regarde. Chez Steam c'est un numéro. Chez Twitch c'est un autre identifiant.
Dans le catalogue, c'est un troisième. Et le titre lui-même diffère : « Disco
Elysium » d'un côté, « Disco Elysium - The Final Cut » de l'autre.

Rien ne relie ces identités entre elles. Aucun service ne vous dit « au fait,
ces trois numéros désignent le même jeu ». Il faut construire cette table de
correspondance à la main, la vérifier, et la maintenir. C'est un des vrais
travaux de fond du projet, et c'est de la plomberie invisible : quand c'est
bien fait, personne ne le remarque.

### Le passe (or)

Les plats prêts à servir, disposés pour que le serveur les prenne sans réfléchir.

Ici, ce sont des tableaux organisés pour répondre vite à des questions
précises : « la popularité de tel jeu jour par jour », « les prix relevés par
boutique ». Ils ne sont pas rangés comme c'est pratique pour les remplir, mais
comme c'est pratique pour les **consulter**. Ce n'est pas la même chose, et
c'est tout l'art de cette dernière étape.

---

## 4. Deux services en parallèle

Un restaurant qui sert à la fois un comptoir express et un menu complet ne
fonctionne pas de la même façon des deux côtés.

Au comptoir express, on veut être servi tout de suite. On accepte que ce soit
simple.

Au menu complet, on accepte d'attendre, mais on veut que ce soit soigné et
cohérent.

GameLens a les deux, pour la même donnée, et ce n'est pas un gaspillage.

**Le chemin rapide** tourne en continu. Il interroge Steam, note ce qu'il
trouve, et le range dans une base immédiatement consultable. Il répond à
« qu'est-ce qui se passe maintenant ? ».

**Le chemin lent** se déclenche chaque nuit. Il reprend tout ce qui a été
collecté dans la journée, recalcule proprement les moyennes, et range le
résultat dans l'entrepôt. Il répond à « comment ça a évolué depuis six mois ? ».

Pourquoi ne pas en faire qu'un seul ? Parce que les deux questions ont des
exigences contraires. La première veut de la fraîcheur et tolère
l'approximation. La seconde veut de la cohérence et tolère le délai. Un système
qui essaie de faire les deux fait mal les deux.

Le prix à payer, et il faut le connaître avant de choisir : **la même règle de
calcul existe à deux endroits**. Le jour où on la change, il faut la changer
des deux côtés, sinon les deux réponses se contredisent. C'est le défaut connu
de cette organisation.

---

## 5. Cinq choses qui rendent ça plus dur qu'il n'y paraît

### La donnée fond si on ne l'attrape pas

Le nombre de joueurs connectés à 14h03 n'existe qu'à 14h03. Personne ne le
conserve pour vous. Si votre collecte s'arrête six heures, ces six heures sont
perdues définitivement.

C'est très différent d'un fichier qu'on peut relire demain. Ça change tout le
rapport à la fiabilité : il ne suffit pas que le système redémarre, il faut
qu'il n'ait pas cessé.

### Le tampon entre celui qui collecte et celui qui range

Si le programme qui collecte parle directement à celui qui range, l'arrêt du
second bloque le premier, et on perd de la donnée.

On met donc un **tampon** entre les deux : une file d'attente, comme le passe
d'une cuisine où le cuisinier dépose les plats sans attendre le serveur. Le
collecteur y dépose ce qu'il trouve. Le rangeur y puise à son rythme. Si le
rangeur s'arrête, la file se remplit, et rien n'est perdu.

Cet outil s'appelle Kafka. C'est sa seule fonction ici : découpler les deux
bouts.

### Le même plat servi deux fois

Voici un problème qui paraît absurde et qui est en réalité central.

Le rangeur prend un élément dans la file, l'écrit en base, puis dit à la file
« c'est bon, celui-là est traité ». Trois opérations. Si le programme meurt
entre l'écriture et la confirmation, la file ne sait pas que l'élément a été
traité. Au redémarrage, elle le redonne, et il est écrit **une deuxième fois**.

On peut essayer de rendre ça impossible. C'est très compliqué, et les
mécanismes qui le promettent sont fragiles.

L'approche retenue est plus modeste et plus solide : **on ne cherche pas à
empêcher la répétition, on la rend sans effet**. La base connaît la règle
« un relevé, pour ce jeu, à cet instant précis, ne peut exister qu'une fois ».
Si le même relevé revient, elle l'ignore poliment.

C'est le principe d'**idempotence** : refaire l'opération ne change rien.
Appuyer deux fois sur le bouton d'un ascenseur déjà appelé.

Ce n'est pas de la théorie. On a délibérément rembobiné la file pour lui faire
redonner 15 éléments déjà traités. Résultat : **0 ajouté, 15 ignorés**, la table
n'a pas bougé.

### Le calcul se fait ailleurs que sur la machine

À un moment, il faut calculer des moyennes glissantes et des classements. Sur
15 jeux, n'importe quel ordinateur y arrive. Sur des millions de lignes, non.

La solution du métier est de faire calculer par une machinerie prévue pour, qui
répartit le travail sur plusieurs machines. C'est ce qu'on appelle du **calcul
distribué**.

Le piège, et c'est un piège très fréquent, est d'utiliser un outil de calcul
distribué **sur une seule machine**. Le code ressemble à du calcul distribué,
le vocabulaire est le bon, et rien n'est distribué du tout.

Ici on a fait autrement. Le programme n'effectue aucun calcul : il rédige la
demande et l'envoie à l'entrepôt, qui la répartit sur ses propres machines et
renvoie le résultat. Comme commander en cuisine au lieu de cuisiner soi-même.

Et on peut le prouver, ce qui est le vrai critère : l'entrepôt tient un
registre de tout ce qu'il a exécuté, avec la quantité de données parcourues et
le temps passé. Ce registre montre que le travail a bien eu lieu là-bas.

### L'entrepôt ne vérifie pas ce qu'on lui donne

C'est le point le plus surprenant du projet, et celui que je trouve le plus
intéressant à raconter.

Une base de données classique refuse les données incohérentes. Vous lui dites
« un prix ne peut pas être négatif » et « un relevé doit se rattacher à un jeu
qui existe », et elle fait la police. C'est un des grands services rendus par
ces outils depuis quarante ans.

L'entrepôt utilisé ici, Snowflake, **accepte qu'on lui écrive ces règles, et ne
les applique pas**. Il les enregistre comme des indications, pas comme des
interdictions.

On ne l'a pas lu dans un manuel, on l'a testé : six insertions volontairement
fautives, pour voir lesquelles passent. Résultat, il refuse ce qui concerne
**une case toute seule** (une case obligatoire laissée vide, un texte trop long
pour la case) et laisse passer tout ce qui concerne **une relation entre
plusieurs lignes ou plusieurs tableaux** (un prix négatif, un relevé rattaché à
un jeu inexistant, un doublon).

La raison est compréhensible : vérifier qu'un jeu existe suppose d'aller
consulter un autre tableau à chaque écriture, ce qui est incompatible avec un
outil conçu pour avaler d'énormes volumes en parallèle. C'est un choix de
conception, pas un défaut.

Mais la conséquence est directe : **si on ne vérifie pas soi-même, personne ne
le fait.** Le projet a donc son propre jeu de vérifications, exécutées après
chaque chargement. Ce ne sont pas des vérifications qui doublent l'outil, ce
sont les seules qui existent.

Pour rester dans la cuisine : on a loué une cuisine industrielle très puissante
qui ne contrôle pas les dates de péremption. À nous de le faire à l'entrée.

---

## 6. Comment on sait que ça marche : on essaie de le casser

Il y a une idée qui traverse tout ce projet, et c'est celle que je retiendrais
si je ne devais en retenir qu'une.

**La panne la plus dangereuse n'est pas celle qui fait du bruit.**

Un programme qui s'arrête brutalement, on le voit. On le répare. C'est
désagréable et c'est simple.

Le vrai danger, c'est le programme qui **s'exécute jusqu'au bout sans rien
faire**. Il ne signale aucune erreur. Ses journaux sont verts. Il rend
poliment la main. Et pendant trois semaines, personne ne remarque que le
tableau ne se met plus à jour.

Cette idée a une conséquence pratique. Il ne suffit pas de vérifier que les
programmes tournent. Il faut vérifier qu'ils **produisent** quelque chose.

D'où deux règles suivies dans tout le projet.

**Première règle : un test doit comparer un résultat obtenu à un résultat
attendu écrit à l'avance.** « Ça ne plante pas » n'est pas un résultat attendu.

Exemple. Pour vérifier le calcul de moyennes, on ne regarde pas si la requête
aboutit. On fabrique un petit jeu de données dont on peut calculer les
résultats de tête, on écrit ces résultats sur le papier, on lance, et on
compare. Si l'entrepôt changeait un jour sa façon de calculer une moyenne, ce
test le verrait. Un test qui vérifie seulement l'absence d'erreur ne le verrait
jamais.

**Deuxième règle : il faut vérifier qu'un dispositif de sécurité sait
échouer.** Un détecteur de fumée qui n'a jamais sonné n'est pas forcément en
bon état.

Alors on casse les choses exprès.

- On a fait tourner le traitement de nuit sur une journée **sans données**,
  pour vérifier qu'il refuse de continuer plutôt que de produire un résultat
  vide. Il a refusé, avec le bon message.
- On a testé le système d'alerte sur une plateforme **en panne**, pas seulement
  sur une plateforme qui marche.
- Les vérifications d'intégrité sont lancées **deux fois** : une fois sur des
  données saines, où elles doivent toutes passer, une fois sur des données
  volontairement corrompues, où le test **échoue si elles passent**.

Ce dernier point a une élégance que je trouve satisfaisante. Les données
corrompues ne sont pas fabriquées : ce sont exactement celles que l'entrepôt
vient de laisser entrer à l'étape précédente, puisqu'il ne vérifie rien.
Quatre règles ignorées par l'entrepôt, quatre problèmes attrapés par nos
vérifications. Ça tombe juste.

### Le test qui réussissait sans rien vérifier

Voici la meilleure histoire du lot, parce qu'elle est humiliante.

Le système de vérification automatique a le droit de créer et de détruire des
bases. Il fallait donc une sécurité : **interdiction absolue de toucher à la
base qui contient les données de démonstration.** Sans quoi une simple
distraction effacerait tout le travail.

Cette sécurité a été écrite. Puis, dans le même mouvement, la fonction qui
choisit sur quelle base travailler a été écrite pour **éviter poliment** les
bases protégées et en choisir une autre.

Deux précautions. Chacune raisonnable. Ensemble, elles s'annulent : la sécurité
ne recevait jamais de base interdite, donc elle n'avait jamais rien à refuser.
Elle était décorative.

On l'a découvert en essayant de la déclencher exprès. Le programme a tourné
jusqu'au bout, tranquillement, sur une autre base, et s'est terminé avec succès.

Le comportement était sûr. Mais il mentait. Et aucune relecture du code ne
l'aurait montré, puisque les deux morceaux, pris séparément, sont corrects.
Seul le fait d'essayer de casser la chose a révélé que le garde-fou était mort.

---

## 7. Ce qui a cassé pour de vrai

Huit incidents ont été consignés au fil de la construction. Voici le plus
instructif, raconté en entier, parce qu'il montre à quoi ressemble vraiment un
diagnostic.

### L'erreur qui accusait un innocent

Un matin, le premier programme qui tente d'écrire en base échoue. Le message
est celui-ci :

> impossible de décoder l'octet 0xe9

Traduit : le programme a reçu un caractère qu'il n'a pas su lire.

Première hypothèse, très tentante : le projet est rangé dans un dossier dont le
nom contient des accents. Ça doit être ça.

C'était faux, et c'est le genre de fausse piste qui peut coûter une journée.

Voici ce qui se passait réellement, en trois maillons.

**Un.** Une base de données était déjà installée sur l'ordinateur, depuis un
projet précédent, et occupait la porte d'entrée numéro 5432.

**Deux.** Le nouveau système, lancé dans un conteneur, a demandé la même porte.
Il ne s'est pas plaint. Il a même affiché que la porte était bien à lui. Elle ne
l'était pas.

**Trois.** Le programme frappait donc à la porte de l'**ancienne** base. Celle-ci
ne le connaissait pas et a répondu, poliment, « authentification échouée ». En
français. Avec un accent sur le « é ». Et cet accent, dans un format que le
programme ne savait pas lire.

Le message utile, « authentification échouée », existait. Il était parfaitement
clair. Et il a été détruit par le mécanisme censé le transmettre. On n'a jamais
vu que le cadavre du message, pas le message.

**Ce qui a permis de trancher** n'est pas une recherche sur internet, c'est une
déduction, et je la trouve jolie.

Le conteneur du nouveau système est une version minimale qui ne parle qu'anglais.
Elle est physiquement incapable de produire un message en français accentué.

Donc : recevoir un message en français prouvait, à lui seul, que l'interlocuteur
n'était pas celui qu'on croyait. **La langue du message d'erreur a servi
d'empreinte digitale pour identifier qui répondait.**

La solution a été de donner au nouveau système une autre porte, la 5433. Les
deux coexistent. Et un commentaire a été laissé dans la configuration pour
expliquer pourquoi ce n'est pas la porte habituelle, sinon quelqu'un
« corrigerait » cette bizarrerie apparente et ferait revenir le problème.

**Ce que j'en retiens.** Quand une erreur très technique et très bas niveau
surgit au milieu d'une opération d'infrastructure, il faut se méfier : c'est
souvent le linceul d'un problème plus simple et plus haut placé, pas le
problème lui-même.

### Les autres, en bref

- **Un outil qui ne fonctionne pas sur Windows**, mais dont l'installation
  réussit sans broncher. Le problème ne serait apparu que bien plus tard.
  Enseignement : installer n'est pas faire fonctionner.
- **Un traitement de nuit qui aurait dupliqué ses lignes** si on l'avait relancé
  deux fois. Découvert sans aucune panne, simplement en essayant d'écrire la
  protection contre les doublons et en constatant qu'elle n'avait rien où
  s'accrocher.
- **Quatre collectes effectuées, une seule inscrite au registre.** Les données
  étaient bonnes, mais le carnet de bord était faux, donc la surveillance
  croyait le système quatre fois moins actif qu'il ne l'était. Personne n'aurait
  rien vu.
- **Une panne totale qui ne laissait aucune trace.** En coupant volontairement
  la file d'attente pour voir ce qui se passe, le programme a bien échoué et
  l'a bien signalé. Mais le carnet de bord, lui, est resté vide : le mécanisme
  qui note les échecs était placé juste après la ligne qui plantait, donc il
  n'était jamais atteint. La panne existait, elle était visible d'un côté et
  invisible de l'autre, précisément du côté qui sert à surveiller. Corrigé, et
  revérifié dans les mêmes conditions.

### Ce qu'on jetait sans le savoir

Une conséquence inattendue de s'être mis à tout garder.

La toute première réponse tarifaire archivée contenait ceci, en plus des
chiffres qu'on utilisait déjà : le prix **tel qu'il s'affiche** pour un client
français, « 24,50 € », mise en forme comprise.

Ce champ était jeté depuis le début du projet, parce qu'on n'en avait pas
l'usage. Il ne sert toujours à rien aujourd'hui. Mais le jour où quelqu'un
demandera comment un prix apparaissait réellement dans telle région, il aurait
manqué, et personne n'aurait su qu'il avait existé.

C'est le renversement propre à ce genre d'archive : on ne conserve pas ce dont
on a besoin, on conserve **ce dont on ignore encore avoir besoin**. Tant qu'on
ne garde rien, la question « qu'est-ce qu'on perd ? » est impossible à poser,
parce qu'il n'y a rien à regarder pour y répondre.

### Le tampon qui a gardé une collecte pendant sept jours

Une histoire courte, et personne ne l'avait organisée.

Souvenez-vous du passe de la cuisine, où le cuisinier dépose les plats sans
attendre le serveur. Le 20 août, la collecte a déposé quinze relevés. Puis plus
personne n'est venu les chercher, parce que rien ne lançait le rangement.

Le 27 août, quand le nouveau programme automatique s'est mis en marche, il a
trouvé ces quinze relevés toujours là, et les a rangés. Sept jours d'attente,
zéro perte.

C'est exactement ce à quoi sert ce tampon, démontré par accident plutôt que par
une démonstration préparée. Ce qui vaut mieux.

---

## 8. Ce qui ne marche pas encore

Cette section est là par honnêteté, et parce qu'un projet dont on ne sait pas
nommer les limites est un projet mal compris.

**Corrigé le 27 août : la collecte se lance maintenant toute seule.** Cette
section disait, la veille encore, que personne ne démarrait la collecte et que
la réponse honnête à « qui la lance ? » était « moi, au clavier ». Un
programme s'en charge désormais tous les quarts d'heure.

Ce qu'il a fallu comprendre pour y arriver mérite d'être raconté, parce que le
blocage n'était pas technique. On m'aurait dit « mets un déclencheur
automatique » que j'aurais répondu, à juste titre, qu'on ne fait pas tourner
une surveillance continue sous un programmateur conçu pour des tâches
ponctuelles.

Le déblocage est venu en regardant la source plutôt que l'outil. Steam ne
diffuse pas un flux d'informations qu'il faudrait écouter en permanence : il
tient un compteur, qu'on peut aller lire quand on veut. Ce n'est donc pas une
surveillance continue, c'est un **relevé périodique**. Et un relevé périodique,
ça se programme sans le moindre problème, comme un relevé de compteur d'eau.

Le mot « temps réel » décrivait un besoin, avoir des chiffres frais. Il avait
été compris comme une obligation technique.

Conséquence immédiate, et elle est jolie : les cinq alertes qui étaient
ouvertes se sont refermées toutes seules, sans que personne ne touche à quoi
que ce soit. Le système constate que tout est rentré dans l'ordre et clôt ses
propres signalements.

Ce qui reste, plus modeste : entre deux relevés, une panne de quatorze minutes
passe inaperçue. C'est acceptable pour un relevé au quart d'heure. Ça ne le
serait pas pour une chaîne où chaque événement compte.

**Le compte de service a tous les droits.** Le programme qui écrit dans
l'entrepôt dispose des privilèges d'administrateur, alors que le projet met par
ailleurs un point d'honneur à donner à chacun le minimum nécessaire. C'est une
incohérence, elle est réparable, et elle est signalée ici plutôt que passée sous
silence.

**Les volumes sont minuscules.** Quinze jeux. Tout tient dans un mouchoir de
poche. Les vraies difficultés de la grande échelle ne se sont donc jamais
présentées : que faire d'une donnée qui arrive en retard, comment recalculer six
mois d'historique, comment réagir le jour où une source ajoute un champ. Rien de
tout cela n'est traité.

**Corrigé le 27 août : le quai de livraison existe maintenant.** Souvenez-vous
des cageots qu'on garde pour pouvoir tout refaire. Cette section disait la
veille encore que le projet ne les gardait pas. Il les garde désormais.

Ce n'est pas l'entrepôt séparé qui était prévu à l'origine, c'est un coin de
réserve dans la cuisine existante. Le lieu change, la propriété recherchée est
la même : on a la matière première, donc on peut tout recommencer.

Ce qui reste : personne n'a décidé combien de temps on garde les cageots. La
réserve grossit d'environ 41 mégaoctets par an, ce qui ne presse pas, mais une
réserve sans règle finit par en imposer une dans l'urgence.

---

## 9. Là où mon explication craque

Voilà l'intérêt réel de l'exercice. En essayant d'expliquer ce projet sans
jargon, certains endroits résistent. Quand une explication ne passe pas, c'est
rarement la faute du lecteur : c'est en général que la chose n'est pas
totalement comprise, ou qu'elle est moins justifiée qu'on ne le croyait.

Voici les sept endroits où je bute, énoncés franchement.

### « Pourquoi une file d'attente pour quinze jeux ? »

J'ai expliqué le tampon entre le collecteur et le rangeur avec l'image du passe
d'une cuisine. L'image est juste. Mais sur quinze jeux, le rangeur n'est jamais
débordé. Le collecteur pourrait écrire directement en base et personne ne
verrait la différence.

La justification honnête n'est donc pas « ça résout un problème que j'ai », mais
« ça résout un problème que j'aurais à plus grande échelle, et l'exercice
demande de démontrer que je sais le mettre en place ». C'est défendable, mais ce
n'est pas la même phrase, et je ne veux pas faire passer la seconde pour la
première.

### « En quoi est-ce vraiment réparti sur plusieurs machines ? »

J'ai dit que le calcul était envoyé à l'entrepôt plutôt qu'effectué sur place,
et que le registre de l'entrepôt le prouve.

Ce que ce registre prouve exactement, c'est que le calcul a eu lieu **ailleurs**.
Il ne prouve pas qu'il a été **découpé et réparti sur plusieurs machines**, parce
que sur trois jeux et huit jours il n'y a rien à répartir. L'entrepôt a très
probablement traité ça sur un seul fil d'exécution.

La formulation exacte serait donc : le mécanisme qui permet la répartition est
en place et vérifiable, la répartition elle-même n'est pas démontrée. C'est une
nuance que je préfère porter moi-même plutôt que me la faire signaler.

### « Pourquoi un entrepôt spécialisé, alors qu'une base classique suffirait ? »

À ces volumes, la base PostgreSQL utilisée pour le chemin rapide ferait
absolument tout, y compris la partie entrepôt, plus vite et gratuitement.

Les vraies raisons d'un entrepôt spécialisé (organisation du stockage par
colonnes, capacité de calcul qu'on allume et éteint à la demande, séparation
entre le stockage et le calcul) ne deviennent décisives qu'à partir de volumes
que ce projet n'atteint pas.

Je peux expliquer pourquoi c'est le bon choix **à l'échelle d'une vraie
entreprise**. Je ne peux pas démontrer qu'il est le bon choix **ici**.

### « Ce système d'organisation du stockage, il sert à quoi concrètement ? »

L'entrepôt permet de dire « range ces données en les regroupant par date », ce
qui accélère beaucoup les recherches par période sur de gros volumes.

C'est déclaré dans le projet. Sur soixante-quinze lignes, ça ne change
rigoureusement rien, et je ne peux pas montrer la différence entre l'avoir et ne
pas l'avoir. Je sais ce que c'est censé faire. Je ne l'ai pas vu faire.

### « Le double chemin, ça ne fait pas deux fois le travail ? »

Si. Et je l'ai présenté comme une force, ce qui mérite d'être nuancé.

Maintenir la même règle de calcul à deux endroits est un coût permanent, et une
source classique de divergence entre deux chiffres censés dire la même chose. À
l'échelle de ce projet, avec une seule personne qui connaît les deux côtés, le
coût est invisible. Dans une équipe de dix personnes sur trois ans, c'est
exactement le genre de choix qu'on finit par regretter.

Il existe d'ailleurs des architectures qui s'en passent en ne gardant qu'un seul
chemin, plus rapide. Je sais qu'elles existent. Je ne les ai pas mises en
oeuvre, et je ne saurais pas argumenter finement pourquoi celle-ci serait
préférable dans un cas réel.

### « Et si deux collecteurs tournaient en même temps ? »

Toujours pas testé, mais la question a bougé depuis la mise en place du
déclenchement automatique.

Le programmateur a maintenant pour consigne de ne jamais lancer un relevé si le
précédent n'est pas terminé. Ça règle le cas courant. Ça ne règle pas le cas où
quelqu'un lance un relevé à la main pendant qu'un relevé automatique tourne :
là, deux collectes se croiseraient vraiment.

Le raisonnement dit que la protection anti-doublons devrait absorber les
écritures redondantes. Mais « devrait » n'est toujours pas « a été vérifié », et
tout ce document explique pourquoi cette différence compte.

### « Pourquoi le seuil d'alerte est-il écrit à deux endroits ? »

Une gêne que je préfère signaler moi-même.

Le système d'alerte considère que passé 90 minutes sans donnée, il faut
prévenir. Le programme de relevé vérifie, lui aussi, que les données ont moins
de 90 minutes avant de se déclarer satisfait.

Deux endroits, même nombre, écrit deux fois. Le jour où l'un des deux change et
pas l'autre, ils se contrediront sans que rien ne le signale. C'est exactement
le type de défaut que ce projet passe son temps à traquer ailleurs, et il est
là, assumé, avec un commentaire dans le code qui l'admet.

La bonne réponse serait une source unique que les deux consultent. Je ne l'ai
pas faite, parce que le mécanisme pour partager proprement cette valeur entre
un fichier SQL et un programme demande plus de travail que la valeur ne le
justifie aujourd'hui. C'est un arbitrage, pas un oubli, mais un arbitrage qui
vieillira mal si le projet grandit.

---

## Petit lexique

| Mot | Ce que ça veut dire ici |
|---|---|
| **API** | Une adresse où un programme va poser une question et reçoit une réponse, sans intervention humaine |
| **Pipeline** | La chaîne complète qui va de la source jusqu'au tableau consultable, avec ses étapes successives |
| **Ingestion** | L'action d'aller chercher la donnée à la source et de la faire entrer dans le système |
| **Bronze, argent, or** | Les trois états successifs de la donnée : brute conservée, nettoyée, mise en forme pour être consultée |
| **Entrepôt de données** | Une base spécialisée dans l'analyse de gros volumes, par opposition à une base faite pour enregistrer des transactions |
| **Idempotence** | Le fait que refaire une opération ne change rien. Appuyer deux fois sur le bouton d'un ascenseur déjà appelé |
| **Orchestrateur** | Le programme qui déclenche les traitements à l'heure prévue, dans le bon ordre, et qui gère les échecs |
| **Calcul distribué** | Un calcul découpé et réparti sur plusieurs machines, parce qu'il ne tiendrait pas sur une seule |
| **Conteneur** | Une boîte qui embarque un logiciel avec tout ce dont il a besoin, pour qu'il tourne identiquement partout |
| **Intégration continue** | Un dispositif qui, à chaque modification du code, rejoue automatiquement tous les tests |
| **Supervision** | Les indicateurs et les alertes qui disent si le système va bien, et préviennent quand il ne va plus |

---

Dernière mise à jour : 27/08/2026, fin de session 6.

Pour le détail technique des décisions, voir [`pour-un-junior.md`](pour-un-junior.md).
