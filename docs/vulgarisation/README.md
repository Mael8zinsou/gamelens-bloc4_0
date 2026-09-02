# Vulgarisation

Ce sous-dossier n'est pas un livrable de la certification. Il existe pour une
raison plus simple : pouvoir expliquer ce projet à quelqu'un d'autre, et se
rendre compte, en essayant, de ce que l'on ne comprend pas encore soi-même.

Le reste de `docs/` est écrit pour un jury et pour un futur mainteneur. Il est
précis, mais il suppose acquis à peu près tout le vocabulaire du métier. Ces
documents-ci font l'inverse : ils partent du lecteur.

## Deux versions, deux lecteurs

| Document | Pour qui | Ce à quoi il répond | Durée |
|---|---|---|---|
| [`pour-un-junior.md`](pour-un-junior.md) | Un data engineer fraîchement diplômé. Il a le vocabulaire, il n'a pas encore l'expérience de la production. | « Pourquoi as-tu fait ça comme ça, et pas autrement ? » | ~45 min |
| [`explique-simplement.md`](explique-simplement.md) | Quelqu'un qui sait ce qu'est un programme, une base de données, une API, mais pour qui « pipeline », « idempotence » ou « couche Gold » ne veulent rien dire. | « C'est quoi, ton truc ? » | ~30 min |

Les durées sont recalculées sur le nombre de mots à chaque révision, sinon elles
vieillissent en silence : au 02/09/2026, 8 976 mots pour la version junior et
6 150 pour la version simple. Elles avaient été annoncées à 25 et 12 minutes
quand les documents faisaient à peu près la moitié de cette taille. La révision
de la session 12 les a fait grossir de 7 % et de 5 %, ce qui ne déplace ni l'une
ni l'autre une fois arrondie : le tableau reste juste, et c'est le recomptage
qui le prouve, pas l'habitude.

La ligne de partage est volontairement franche, sinon les deux documents
seraient le même à quelques mots près.

La version junior **assume le jargon** et se concentre sur les décisions et
leurs contreparties. Elle n'explique pas ce qu'est une clé étrangère, elle
explique pourquoi il n'y en a pas.

La version simple **n'assume aucun vocabulaire de la donnée**. Elle avance par
analogies, et elle se termine par une section que l'on ne trouve nulle part
ailleurs dans ce dépôt : la liste des endroits où l'explication ne tient pas
encore. C'est le coeur de la méthode Feynman, et c'est aussi la meilleure liste
de révision disponible avant une session de questions.

## Par où commencer

Si vous ne connaissez pas le projet, commencez par `explique-simplement.md`,
même si vous êtes technique. Il donne la carte. `pour-un-junior.md` donne
ensuite le détail des choix.

## Ce que ces documents ne sont pas

Ils ne remplacent rien. Quand ils simplifient, ils le disent et renvoient à la
source :

- `docs/rapport_analyse.md` pour les besoins d'origine, la comparaison avec les
  outils du marché, la dépendance fournisseur et les coûts mesurés ;
- `docs/documentation_technique.md` pour les décisions d'architecture datées et
  la traçabilité champ par champ ;
- `docs/journal_incidents.md` pour les incidents au format complet ;
- `docs/observations.md` pour les surprises et les fausses pistes ;
- `docs/cahier_recettes.md` pour les tests et leurs résultats réels ;
- `docs/commandes_successives.md` pour ce qui a été tapé, dans l'ordre ;
- `docs/feuille_route_exploitation.md` pour l'exploitation courante et les
  points de vigilance ;
- `CLAUDE.md` pour l'état d'avancement, les contraintes d'environnement et la
  liste des écarts connus laissés ouverts.

## Entretien

Ces documents **vieillissent plus vite que le code**, parce qu'ils décrivent
des intentions et pas des fichiers. Une brique ajoutée sans mise à jour d'ici
les rend faux, et un document de vulgarisation faux est pire qu'absent : il
enseigne quelque chose d'inexact avec assurance.

Règle retenue : à chaque session qui **ajoute ou retire une brique**, ou qui
**invalide une explication donnée ici**, les deux documents sont relus et mis à
jour dans la même session. Une correction de détail ne le justifie pas.

La règle a une conséquence qu'il faut assumer dans les deux sens : elle
autorise aussi à **ne rien changer**, et il faut alors le dire, sinon rien ne
distingue un document relu d'un document oublié.

### Points connus à revoir

- `GAMELENS_SERVICE` tourne en `ACCOUNTADMIN`, signalé comme une incohérence
  assumée dans les deux documents. Le jour où un rôle dédié le remplacera, ces
  passages deviendront faux. C'est V-03 sur la liste des écarts gelés.
- Le seuil de fraîcheur est écrit à deux endroits, `sql/schema_supervision.sql`
  et `supervision/regles_alertes.py`, ce que la version Feynman admet dans sa
  section finale. Vérifié encore vrai le 31/08/2026 : la valeur 90 figure bien
  aux deux endroits. Une source unique rendrait ce passage caduc.
- Aucun canal de notification n'est branché (V-02), et la supervision ne se
  surveille pas elle-même (V-07). Les deux documents le **disent** désormais,
  chiffres à l'appui : détection en 90 minutes, alerte restée ouverte 6 j 20 h.
  C'était un risque de lecture signalé ici depuis la session 11 sans que les
  documents concernés ne le portent ; il est levé. Le jour où un canal sera
  branché, ce sont ces passages-là qui deviendront faux.
- L'expiration du compte Snowflake à la mi-décembre 2026 (V-01) est citée dans
  la version junior. La date est **attendue et non confirmée** dans Snowsight :
  si elle est démentie, ce passage l'est avec elle.

### Journal des révisions

**Session 6 (27/08/2026).** L'ingestion temps réel est désormais planifiée, et
la couche Bronze est construite. Les deux documents ont été corrigés en
conséquence plutôt que d'effacer la mention, l'écart entre le constat et la
correction faisant partie de l'histoire du projet.

**Session 8 (27/08/2026).** dbt est branché sur Snowflake. Le document pour un
junior gagne une décision 3.9 et perd la faiblesse « dbt installé, pas encore
branché » ; la version Feynman gagne le passage sur les deux contrôleurs et leur
mise d'accord. Même règle que ci-dessus : les mentions résolues restent, datées.

Un manque a été **ajouté** à cette occasion plutôt que retiré :
`dim_games.critical_tier` est vide alors que le schéma annonce qu'un modèle dbt
la dérive. C'est le même écart entre l'annoncé et le réel que celui refermé
cette session-là, en plus petit, et il est signalé plutôt que corrigé en silence.

**Sessions 9 et 10 (31/08/2026).** Révision déclenchée non par une brique
ajoutée mais par une explication devenue fausse, ce que la règle prévoit aussi.
Un contrôle de cohérence a montré que le schéma d'architecture des deux
documents décrivait l'intention et non le système : seule la couche Gold
PostgreSQL était promue automatiquement, la couche Snowflake était chargée à la
main et rien ne surveillait son retard. Corrigé le jour même : un second automate
s'en charge, et les deux documents portent désormais l'histoire complète, écart
inclus, plutôt que la seule version corrigée. Le schéma du document pour un
junior est corrigé et porte son avertissement ; la version Feynman gagne une
huitième faille, placée en tête de sa section 9 parce que c'est la plus
embarrassante des huit.

C'est exactement le cas que cette page redoutait en ouverture : un document de
vulgarisation faux est pire qu'absent, puisqu'il enseigne une chose inexacte
avec assurance. Il l'a été onze jours.

**Session 11 (31/08/2026), relu et laissé en l'état.** La session a produit le
rapport d'analyse `docs/rapport_analyse.md` et remis à plat `CLAUDE.md` et le
`README.md` de la racine. Aucune brique n'a été ajoutée ni retirée : un rapport
est un document, pas un composant. Les deux documents ont été relus contre les
mesures de coût que le rapport a produites, qu'ils ne citent nulle part, et
contre la liste des écarts gelés, qu'ils décrivent déjà correctement. Rien à
corriger, donc rien de corrigé.

Seule cette page change, sur trois points : les durées de lecture, périmées
d'un facteur deux depuis que les documents ont grossi ; le renvoi vers le
rapport d'analyse, ajouté à la liste des sources ; et l'absence de canal de
notification, ajoutée aux points à revoir parce qu'un lecteur peut déduire des
deux documents qu'une alerte prévient quelqu'un.

**Session 12 (02/09/2026).** Révision demandée par le lecteur, qui trouvait les
documents périmés. Il avait raison, et sur un point que la règle de cette page
n'attrape pas : **les deux documents se dataient encore du 27/08, fin de
session 6**, alors que les sessions 8, 9 et 10 les avaient modifiés sans jamais
toucher au pied de page. Un document révisé qui affiche une vieille date se lit
comme un document oublié, ce qui est très exactement le contraire de ce que la
règle ci-dessus cherche à rendre visible.

Trois familles de corrections, et elles ne se valent pas.

*Des chiffres devenus faux par simple écoulement du temps.* Huit incidents pour
neuf, 46 observations pour 75, 32 cas de recette pour 55, des volumes relevés
avant que les deux promotions ne tournent chaque nuit. Aucun n'était faux le
jour où il a été écrit, et c'est là toute la difficulté : un chiffre juste ne
prévient pas qu'il a cessé de l'être.

*Un schéma incomplet.* Le schéma d'architecture de la version junior ne montrait
pas la couche Bronze, alors qu'elle existe depuis le 27/08 et que le paragraphe
placé juste dessous la décrit longuement. C'est le défaut refermé en session 9,
en plus discret : une omission se remarque encore moins qu'une erreur, parce que
rien dans le texte ne la contredit.

*Un manque de fond jamais écrit.* Les deux documents énumèrent leurs limites, et
ni l'un ni l'autre ne citait le plus gros écart de la plateforme : rien ne porte
une alerte jusqu'à un humain. Cette page le signalait comme risque de lecture
depuis la session 11, sans que les documents concernés ne le disent. Chacun a
désormais sa section, chiffrée, avec la limite jumelle V-07.

À noter pour la règle elle-même : **aucune brique n'a été ajoutée ni retirée
depuis la session 11.** La session 12 a produit le support de soutenance, son
plan et la feuille remise au jury, qui sont des documents. Cette révision n'a
donc pas été déclenchée par la branche habituelle de la règle, mais par la
seconde, celle des explications devenues fausses. C'est la deuxième fois qu'elle
sert, après les sessions 9 et 10, et les deux fois ce n'est pas la construction
qui a périmé les documents, c'est le temps.

Dernière mise à jour : 02/09/2026, fin de session 12.
