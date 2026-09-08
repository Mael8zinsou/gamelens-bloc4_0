{#-
  Vue d'acces self-service, seul objet de la couche Gold dont dbt prend la
  propriete.

  Pourquoi celui-la et pas un autre. Cette vue vivait jusqu'ici au milieu de
  sql/schema_gold_snowflake.sql, un fichier qui contient vingt-quatre
  CREATE OR REPLACE TABLE qu'il est interdit de rejouer : le remettre en
  place detruirait sans un mot toute la couche de demonstration. Autrement dit,
  corriger cette vue demandait soit d'extraire son instruction a la main, soit
  de tout raser. En modele dbt elle se reconstruit seule, par `dbt run --select
  v_popularity_dashboard`, sans toucher a une seule table.

  Second gain, moins visible : la version SQL nommait `gamelens.mart.` en dur.
  Celle-ci passe par source(), donc suit la base de la cible. C'est ce qui la
  rend eprouvable sur la base jetable de la CI, ce que l'originale n'etait pas.
-#}

{#-
  Sur les deux options passees a config(), qui ne sont ni l'une ni l'autre
  cosmetiques.

  persist_docs. Le COMMENT de la vue est lu dans le catalogue par
  outils/generer_dictionnaire.py pour produire docs/annexes/, et la CI compare
  le resultat au depot. Une vue recreee sans son commentaire ferait echouer la
  chaine sur un message parlant du dictionnaire, jamais de dbt. La description
  se trouve dans _models.yml et reproduit a l'identique celle de
  schema_gold_snowflake.sql. columns reste a false : les colonnes de la vue
  n'ont aujourd'hui aucun commentaire, en ajouter changerait le fichier genere.

  grants. Sur Snowflake, remplacer une vue detruit ses droits. Sans cette
  ligne, un dbt run retirerait silencieusement au tableau de bord l'acces
  qu'il avait, et personne ne s'en apercevrait avant que Grafana n'affiche un
  panneau vide. Les roles gamelens_* sont des objets de COMPTE et non de base :
  ils existent donc aussi lors d'un run sur une base jetable.
-#}

{{
    config(
        materialized="view",
        persist_docs={"relation": True, "columns": False},
        grants={"select": ["gamelens_dashboard_viewer"]},
    )
}}

select
    g.game_id,
    g.unified_name,
    g.genre,
    g.critical_tier,
    h.day,
    h.avg_player_count,
    h.avg_viewer_count
from {{ source('gold', 'dim_games') }} g
join {{ source('gold', 'fact_popularity_history') }} h
    on g.game_id = h.game_id
