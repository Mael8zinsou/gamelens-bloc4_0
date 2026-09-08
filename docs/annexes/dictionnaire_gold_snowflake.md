# Dictionnaire de donnees, couche Gold Snowflake

> **Fichier genere. Ne pas modifier a la main.**
> Source : les commentaires en ligne de `sql/schema_gold_snowflake.sql`,
> lus dans `information_schema` du compte Snowflake.
> Regenerer par `python outils/generer_dictionnaire.py --cible snowflake`.

**Avertissement d'architecture.** Snowflake declare les contraintes
relationnelles mais ne les applique pas a l'ecriture : `CHECK`,
`FOREIGN KEY`, `PRIMARY KEY` et `UNIQUE` sont des metadonnees. Seuls
`NOT NULL`, le type et la longueur sont opposables. Les contraintes ne
figurent donc pas dans ce dictionnaire : elles y seraient trompeuses.
L'integrite reelle est portee par deux filets, tous deux rejoues a chaque
push : les contrats declaratifs du projet dbt (`dbt/models/gold/`), ou
chaque `relationships` est une clef etrangere que le moteur ignore, et les
controles applicatifs de `entrepot/verifier_gold.py`. Le comportement du
moteur est lui-meme verifie a chaque push, et les deux filets sont
confrontes au meme jeu de donnees fautif pour verifier qu'ils restent
d'accord (voir `entrepot/recette_ci.py`).

### `mart.v_popularity_dashboard` (vue)
Vue de lecture agregee pour les tableaux de bord, sans acces direct aux tables de faits sous-jacentes.

| Colonne | Type | Nul | Description |
|---|---|---|---|
| `game_id` | `TEXT(36)` | non |  |
| `unified_name` | `TEXT(16777216)` | non |  |
| `genre` | `TEXT(16777216)` | oui |  |
| `critical_tier` | `TEXT(16777216)` | oui |  |
| `day` | `DATE` | non |  |
| `avg_player_count` | `NUMBER(12,2)` | oui |  |
| `avg_viewer_count` | `NUMBER(12,2)` | oui |  |

### `mart.dim_games` (table)
Referentiel unifie des jeux suivis (portefeuille Kestrel Interactive + panel concurrent). Grain : un enregistrement par jeu.

| Colonne | Type | Nul | Description |
|---|---|---|---|
| `game_id` | `TEXT(36)` | non | Clef primaire interne UUID, independante des identifiants sources (convention Bloc 2). Declaree PRIMARY KEY mais non appliquee par Snowflake. |
| `unified_name` | `TEXT(16777216)` | non | Nom canonique retenu par GameLens. NOT NULL reellement applique par le moteur. |
| `genre` | `TEXT(16777216)` | oui | Genre principal. Sert de partition au classement distribue calcule par Snowpark. |
| `developer` | `TEXT(16777216)` | oui | Studio de developpement. |
| `release_date` | `DATE` | oui | Date de sortie commerciale. Non alimentee a ce jour. |
| `metacritic_score` | `NUMBER(3,0)` | oui | Note critique agregee, attendue entre 0 et 100. Bornes verifiees par verifier_gold.py, non par le moteur. |
| `critical_tier` | `TEXT(16777216)` | oui | Acclaimed, Favorable ou Mixed. Vide a ce jour : la derivation depuis metacritic_score suppose un catalogue (RAWG ou IGDB) non branche. |
| `steam_appid` | `NUMBER(10,0)` | oui | Identifiant Steam, clef naturelle. Contrainte UNIQUE declaree mais non appliquee : le doublon est rattrape par controle applicatif. |
| `twitch_game_id` | `TEXT(16777216)` | oui | Identifiant de categorie Twitch, propage depuis speed.game_mapping. Resolu pour la totalite du panel depuis le 08/09/2026. |
| `gog_slug` | `TEXT(16777216)` | oui | Identifiant GOG. Conserve bien que le suivi GOG soit hors perimetre depuis le Bloc 3. |
| `rawg_id` | `NUMBER(10,0)` | oui | Identifiant RAWG, source catalogue. Source non branchee a ce jour. |
| `gold_loaded_at` | `TIMESTAMP_NTZ` | non | Instant de promotion vers la couche Gold. |

### `mart.dim_stores` (table)
Boutiques suivies pour la tarification. Une seule a ce jour, Steam : le suivi GOG est hors perimetre depuis l'arbitrage du Bloc 3 (3.3).

| Colonne | Type | Nul | Description |
|---|---|---|---|
| `store_id` | `TEXT(36)` | non | Clef primaire interne UUID. |
| `name` | `TEXT(16777216)` | non | Nom de la boutique. UNIQUE declare, non applique. |
| `base_url` | `TEXT(16777216)` | oui | Adresse racine de la boutique. |
| `source_type` | `TEXT(16777216)` | non | api ou scraping. Valeur controlee par test dbt accepted_values, pas par le moteur. |

### `mart.fact_popularity_history` (table)
Agregats journaliers de popularite jouee et diffusee, promus depuis la couche Silver speed (Bloc 1, 3.4).

| Colonne | Type | Nul | Description |
|---|---|---|---|
| `game_id` | `TEXT(36)` | non | Jeu concerne. REFERENCES dim_games declare, non applique. |
| `day` | `DATE` | non | Journee agregee. Avec game_id, definit le grain. Sert egalement de clef de regroupement du stockage (CLUSTER BY). |
| `avg_player_count` | `NUMBER(12,2)` | oui | Moyenne des releves de frequentation de la journee. Colonne large, pas de modele EAV. |
| `max_player_count` | `NUMBER(10,0)` | oui | Pic de frequentation de la journee. |
| `avg_viewer_count` | `NUMBER(12,2)` | oui | Moyenne journaliere de l'audience diffusee sur Twitch, somme des spectateurs des 100 streams les plus regardes. Nulle si le titre n'a pas de categorie Twitch resolue. |
| `max_viewer_count` | `NUMBER(10,0)` | oui | Pic d'audience diffusee de la journee, sur les memes releves. |

### `mart.fact_prices` (table)
Tarifs collectes par jeu et par boutique. Alimentee par l'API Steam appdetails (price_overview), qui remplace le scraping GOG sorti du perimetre par l'arbitrage du Bloc 3 (3.3).

| Colonne | Type | Nul | Description |
|---|---|---|---|
| `price_id` | `TEXT(36)` | non | Clef primaire interne UUID. |
| `game_id` | `TEXT(36)` | non | Jeu concerne. REFERENCES dim_games declare, non applique : l'orphelin est rattrape par controle applicatif. |
| `store_id` | `TEXT(36)` | non | Boutique concernee. REFERENCES dim_stores declare, non applique. |
| `price` | `NUMBER(10,2)` | non | Prix effectivement paye, en devise currency. Doit rester strictement positif ; verifie par controle applicatif. |
| `currency` | `TEXT(3)` | non | Devise ISO 4217, sur 3 caracteres. Longueur reellement appliquee. |
| `promotion_flag` | `BOOLEAN` | non | Vrai si le releve correspond a une remise en cours. |
| `collected_at` | `TIMESTAMP_NTZ` | non | Instant du releve. Avec game_id et store_id, definit le grain. |

---

Colonnes de tables sans description : **0**.
