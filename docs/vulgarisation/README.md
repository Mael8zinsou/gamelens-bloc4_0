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
| [`pour-un-junior.md`](pour-un-junior.md) | Un data engineer fraîchement diplômé. Il a le vocabulaire, il n'a pas encore l'expérience de la production. | « Pourquoi as-tu fait ça comme ça, et pas autrement ? » | ~25 min |
| [`explique-simplement.md`](explique-simplement.md) | Quelqu'un qui sait ce qu'est un programme, une base de données, une API, mais pour qui « pipeline », « idempotence » ou « couche Gold » ne veulent rien dire. | « C'est quoi, ton truc ? » | ~12 min |

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

- `docs/journal_incidents.md` pour les incidents au format complet ;
- `docs/observations.md` pour les surprises et les fausses pistes ;
- `docs/cahier_recettes.md` pour les tests et leurs résultats réels ;
- `docs/commandes_successives.md` pour ce qui a été tapé, dans l'ordre ;
- `docs/feuille_route_exploitation.md` pour l'exploitation courante et les
  points de vigilance ;
- `CLAUDE.md` pour l'état d'avancement et les contraintes d'environnement.

## Entretien

Ces documents **vieillissent plus vite que le code**, parce qu'ils décrivent
des intentions et pas des fichiers. Une brique ajoutée sans mise à jour d'ici
les rend faux, et un document de vulgarisation faux est pire qu'absent : il
enseigne quelque chose d'inexact avec assurance.

Règle retenue : à chaque session qui **ajoute ou retire une brique**, ou qui
**invalide une explication donnée ici**, les deux documents sont relus et mis à
jour dans la même session. Une correction de détail ne le justifie pas.

Points connus à revoir lors de la prochaine mise à jour :

- `GAMELENS_SERVICE` tourne en `ACCOUNTADMIN`, signalé comme une incohérence
  assumée dans les deux documents. Le jour où un rôle dédié le remplacera, ces
  passages deviendront faux.
- Le seuil de fraîcheur est écrit à deux endroits, ce que la version Feynman
  admet dans sa section finale. Une source unique le rendrait caduc.

Traité en session 6 (27/08/2026) : l'ingestion temps réel est désormais
planifiée, et la couche Bronze est construite. Les deux documents ont été
corrigés en conséquence plutôt que d'effacer la mention, l'écart entre le
constat et la correction faisant partie de l'histoire du projet.

Traité en session 8 (27/08/2026) : dbt est branché sur Snowflake. Le document
pour un junior gagne une décision 3.9 et perd la faiblesse « dbt installé, pas
encore branché » ; la version Feynman gagne le passage sur les deux contrôleurs
et leur mise d'accord. Même règle que ci-dessus : les mentions résolues restent,
datées.

Un manque a été **ajouté** à cette occasion plutôt que retiré :
`dim_games.critical_tier` est vide alors que le schéma annonce qu'un modèle dbt
la dérive. C'est le même écart entre l'annoncé et le réel que celui refermé
cette session, en plus petit, et il est signalé plutôt que corrigé en silence.

Revu en session 9 (31/08/2026), non pour une brique ajoutée mais pour une
explication devenue fausse, ce que la règle ci-dessus prévoit aussi. Un contrôle
de cohérence a montré que le schéma d'architecture des deux documents décrivait
l'intention et non le système : seule la couche Gold PostgreSQL est promue
automatiquement, la couche Snowflake est chargée à la main et rien ne surveille
son retard. Le schéma du document pour un junior est corrigé et porte désormais
son avertissement ; la version Feynman gagne une huitième faille, placée en tête
de sa section 9 parce que c'est la plus embarrassante des huit.

C'est exactement le cas que cette page redoutait en ouverture : un document de
vulgarisation faux est pire qu'absent, puisqu'il enseigne une chose inexacte
avec assurance. Il l'a été onze jours.

Dernière mise à jour : 31/08/2026, fin de session 9.
