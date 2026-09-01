# Schema de donnees, couche Gold

> **Fichier genere. Ne pas modifier a la main.**
> Colonnes, types, contraintes et droits lus dans le catalogue Snowflake ;
> colonnes des clefs et cibles des clefs etrangeres lues dans
> `sql/schema_gold_snowflake.sql`, les deux sources etant recoupees a
> chaque generation. Regenerer par `outils/generer_schema.py`.

Livrable du critere **C4.2.1**, qui demande un schema permettant
d'identifier le type des donnees, les modalites d'acces et l'organisation
des donnees. Les trois premieres sections repondent dans cet ordre.

## 1. Organisation des donnees

![Schema en etoile de la couche Gold](schema_donnees.png)

*Source vectorielle : [`schema_donnees.svg`](schema_donnees.svg).*

Modele en etoile : deux dimensions, deux tables de faits, une vue de
restitution. Le grain de `fact_popularity_history` est le couple
(jeu, jour) ; celui de `fact_prices` est (jeu, boutique, instant de
collecte). Colonnes larges plutot qu'un modele entite-attribut-valeur :
les indicateurs suivis sont connus et peu nombreux.

Les relations sont dessinees **en tirets**, et ce n'est pas une
convention graphique : elles sont declarees dans le schema mais le moteur
ne les applique pas. Voir la section 4.

S'y ajoute la vue `mart.v_popularity_dashboard`, seul objet visible du role de
restitution. Elle joint la dimension des jeux et les faits de
popularite, sans exposer les tables sous-jacentes.

## 2. Type des donnees

Types tels que le catalogue les porte. Le dimensionnement exact
(longueurs, precisions) figure dans `dictionnaire_gold_snowflake.md`,
qui est l'annexe faite pour cela.

### `mart.v_popularity_dashboard` (vue)

| Colonne | Type | Nul | Clef |
|---|---|---|---|
| `game_id` | `TEXT` | non |  |
| `unified_name` | `TEXT` | non |  |
| `genre` | `TEXT` | oui |  |
| `critical_tier` | `TEXT` | oui |  |
| `day` | `DATE` | non |  |
| `avg_player_count` | `NUMBER` | oui |  |
| `avg_viewer_count` | `NUMBER` | oui |  |

### `mart.dim_games` (table)

| Colonne | Type | Nul | Clef |
|---|---|---|---|
| `game_id` | `TEXT` | non | PK |
| `unified_name` | `TEXT` | non |  |
| `genre` | `TEXT` | oui |  |
| `developer` | `TEXT` | oui |  |
| `release_date` | `DATE` | oui |  |
| `metacritic_score` | `NUMBER` | oui |  |
| `critical_tier` | `TEXT` | oui |  |
| `steam_appid` | `NUMBER` | oui | UK |
| `twitch_game_id` | `TEXT` | oui |  |
| `gog_slug` | `TEXT` | oui |  |
| `rawg_id` | `NUMBER` | oui |  |
| `gold_loaded_at` | `TIMESTAMP_NTZ` | non |  |

### `mart.dim_stores` (table)

| Colonne | Type | Nul | Clef |
|---|---|---|---|
| `store_id` | `TEXT` | non | PK |
| `name` | `TEXT` | non | UK |
| `base_url` | `TEXT` | oui |  |
| `source_type` | `TEXT` | non |  |

### `mart.fact_popularity_history` (table)

| Colonne | Type | Nul | Clef |
|---|---|---|---|
| `game_id` | `TEXT` | non | FK PK |
| `day` | `DATE` | non | PK |
| `avg_player_count` | `NUMBER` | oui |  |
| `max_player_count` | `NUMBER` | oui |  |
| `avg_viewer_count` | `NUMBER` | oui |  |
| `max_viewer_count` | `NUMBER` | oui |  |

### `mart.fact_prices` (table)

| Colonne | Type | Nul | Clef |
|---|---|---|---|
| `price_id` | `TEXT` | non | PK |
| `game_id` | `TEXT` | non | FK UK |
| `store_id` | `TEXT` | non | FK UK |
| `price` | `NUMBER` | non |  |
| `currency` | `TEXT` | non |  |
| `promotion_flag` | `BOOLEAN` | non |  |
| `collected_at` | `TIMESTAMP_NTZ` | non | UK |

## 3. Modalites d'acces

Lu en direct par `SHOW GRANTS`, et non recopie depuis le schema :
c'est l'etat effectif des droits sur la couche de demonstration.

| Objet | Role | Privilege |
|---|---|---|
| `mart.dim_games` | `gamelens_analyst` | `SELECT` |
| `mart.dim_games` | `gamelens_etl_service` | `INSERT` |
| `mart.dim_games` | `gamelens_etl_service` | `SELECT` |
| `mart.dim_games` | `gamelens_etl_service` | `UPDATE` |
| `mart.dim_stores` | `gamelens_analyst` | `SELECT` |
| `mart.dim_stores` | `gamelens_etl_service` | `INSERT` |
| `mart.dim_stores` | `gamelens_etl_service` | `SELECT` |
| `mart.dim_stores` | `gamelens_etl_service` | `UPDATE` |
| `mart.fact_popularity_history` | `gamelens_analyst` | `SELECT` |
| `mart.fact_popularity_history` | `gamelens_etl_service` | `INSERT` |
| `mart.fact_popularity_history` | `gamelens_etl_service` | `SELECT` |
| `mart.fact_popularity_history` | `gamelens_etl_service` | `UPDATE` |
| `mart.fact_prices` | `gamelens_analyst` | `SELECT` |
| `mart.fact_prices` | `gamelens_etl_service` | `INSERT` |
| `mart.fact_prices` | `gamelens_etl_service` | `SELECT` |
| `mart.fact_prices` | `gamelens_etl_service` | `UPDATE` |
| `mart.v_popularity_dashboard` | `gamelens_dashboard_viewer` | `SELECT` |

Le cloisonnement se lit dans ce tableau : `gamelens_etl_service`
ecrit, `gamelens_analyst` lit les tables, et
`gamelens_dashboard_viewer` ne voit que la vue. La verification par
l'echec est dans `docs/preuves/c11_cloisonnement_roles.txt`.

## 4. Ce que le moteur applique, et ce qu'il n'applique pas

Le catalogue declare les contraintes ci-dessous. **Snowflake ne les
applique pas a l'ecriture**, a l'exception de celles portees par la
colonne elle-meme (`NOT NULL`, type, longueur). `CHECK`, `FOREIGN KEY`,
`PRIMARY KEY` et `UNIQUE` sont des metadonnees, verifiees empiriquement
par `sql/verify_snowflake_constraints.sql`.

| Table | Contrainte declaree | Nombre |
|---|---|---|
| `mart.dim_games` | PRIMARY KEY | 1 |
| `mart.dim_games` | UNIQUE | 1 |
| `mart.dim_stores` | PRIMARY KEY | 1 |
| `mart.dim_stores` | UNIQUE | 1 |
| `mart.fact_popularity_history` | FOREIGN KEY | 1 |
| `mart.fact_popularity_history` | PRIMARY KEY | 1 |
| `mart.fact_prices` | FOREIGN KEY | 2 |
| `mart.fact_prices` | PRIMARY KEY | 1 |
| `mart.fact_prices` | UNIQUE | 1 |

Le diagramme montre donc des relations **voulues**, pas des relations
garanties par le moteur. Ce que le moteur ne garantit pas est porte par
deux filets rejoues a chaque push : les contrats declaratifs de
`dbt/models/gold/`, ou chaque `relationships` est exactement une des
fleches du diagramme, et les controles applicatifs de
`entrepot/verifier_gold.py`.
