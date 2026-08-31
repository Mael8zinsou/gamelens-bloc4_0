# Dictionnaire de donnees, couches PostgreSQL

> **Fichier genere. Ne pas modifier a la main.**
> Source : les `COMMENT ON` des fichiers de `sql/`, lus dans le catalogue
> de la base. Regenerer par `python outils/generer_dictionnaire.py`.
> La chaine d'integration continue echoue si ce fichier n'est pas a jour.

## Schema `bronze`
Archive des reponses d'API telles que recues. Source de recalcul.

### `bronze.v_sante_sources` (vue)
Taux de reponses exploitables par source sur 24h. Sante des sources, pas des composants.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `source` | `text` | oui |  |  |
| `appels_24h` | `bigint` | oui |  |  |
| `exploitables` | `bigint` | oui |  |  |
| `rejets` | `bigint` | oui |  |  |
| `taux_exploitable_pct` | `numeric` | oui |  |  |
| `dernier_appel` | `timestamp with time zone` | oui |  |  |

### `bronze.reponses_brutes` (table)
Une ligne par appel d'API, abouti ou non. Jamais modifiee apres ecriture.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `reponse_id` | `bigint` | non | `nextval('bronze.reponses_brutes_reponse_` | Clef technique de l'archive, sans signification metier. |
| `source` | `text` | non |  | Point d'appel interroge, ex. steam_player_count ou steam_appdetails. |
| `identifiant` | `text` | non |  | Identifiant interroge cote source, en texte pour rester agnostique. |
| `collecte_le` | `timestamp with time zone` | non |  | Instant de l'appel, fourni par l'appelant, et non instant d'ecriture. |
| `statut_http` | `integer` | oui |  | Code HTTP de la reponse. Nul quand l'appel n'a jamais abouti (erreur reseau). |
| `exploitable` | `boolean` | non |  | Faux si la reponse ne portait pas la donnee attendue. Impose alors un motif_rejet. |
| `motif_rejet` | `text` | oui |  | Pourquoi la reponse est inexploitable. Obligatoire dans ce cas. |
| `charge` | `jsonb` | oui |  | Corps de la reponse tel quel. NULL si la reponse n'a jamais ete obtenue. |
| `archivee_le` | `timestamp with time zone` | non | `now()` | Instant de l'ecriture dans l'archive, distinct de collecte_le qui est l'instant de l'appel. |

Contraintes :

- `ck_reponses_brutes_motif` : `CHECK ((exploitable OR (motif_rejet IS NOT NULL)))`
- `reponses_brutes_pkey` : `PRIMARY KEY (reponse_id)`
- `uq_reponses_brutes_grain` : `UNIQUE (source, identifiant, collecte_le)`

## Schema `mart`
Couche Gold prototype sur PostgreSQL. La cible de production est Snowflake.

### `mart.v_popularity_dashboard` (vue)
Vue de lecture agregee pour les tableaux de bord, sans acces direct aux tables de faits sous-jacentes.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `game_id` | `uuid` | oui |  |  |
| `unified_name` | `text` | oui |  |  |
| `genre` | `text` | oui |  |  |
| `critical_tier` | `text` | oui |  |  |
| `day` | `date` | oui |  |  |
| `avg_player_count` | `numeric(12,2)` | oui |  |  |
| `avg_viewer_count` | `numeric(12,2)` | oui |  |  |

### `mart.dim_games` (table)
Referentiel unifie des jeux suivis (portefeuille Kestrel Interactive + panel concurrent). Grain : un enregistrement par jeu.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `game_id` | `uuid` | non | `gen_random_uuid()` | Clef primaire interne UUID, independante des identifiants sources (convention Bloc 2). |
| `unified_name` | `text` | non |  | Nom canonique, promu depuis speed.game_mapping. |
| `genre` | `text` | oui |  | Genre principal. Partition du classement distribue. |
| `developer` | `text` | oui |  | Studio de developpement. |
| `release_date` | `date` | oui |  | Date de sortie commerciale. Non alimentee a ce jour. |
| `metacritic_score` | `smallint` | oui |  | Note critique agregee, attendue entre 0 et 100. Bornes verifiees par controle applicatif. |
| `critical_tier` | `text` | oui |  | Acclaimed, Favorable ou Mixed. Derive de metacritic_score (Bloc 1, annexe 10). |
| `steam_appid` | `integer` | oui |  | Identifiant Steam. Clef naturelle, contrainte UNIQUE. |
| `twitch_game_id` | `text` | oui |  | Identifiant Twitch. Source non branchee a ce jour. |
| `gog_slug` | `text` | oui |  | Identifiant GOG. Conserve bien que le suivi GOG soit hors perimetre depuis le Bloc 3. |
| `rawg_id` | `integer` | oui |  | Identifiant RAWG, source catalogue. |
| `gold_loaded_at` | `timestamp with time zone` | non | `now()` | Instant de promotion vers la couche Gold. |

Contraintes :

- `dim_games_critical_tier_check` : `CHECK ((critical_tier = ANY (ARRAY['Acclaimed'::text, 'Favorable'::text, 'Mixed'::text])))`
- `dim_games_metacritic_score_check` : `CHECK (((metacritic_score >= 0) AND (metacritic_score <= 100)))`
- `dim_games_pkey` : `PRIMARY KEY (game_id)`
- `uq_dim_games_steam_appid` : `UNIQUE (steam_appid)`

### `mart.dim_stores` (table)
Boutiques suivies pour la tarification (ex : Steam, GOG).

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `store_id` | `uuid` | non | `gen_random_uuid()` | Clef primaire interne UUID. |
| `name` | `text` | non |  | Nom de la boutique. Unique. |
| `base_url` | `text` | oui |  | Adresse racine de la boutique. |
| `source_type` | `text` | non |  | api ou scraping. Valeur controlee. |

Contraintes :

- `dim_stores_source_type_check` : `CHECK ((source_type = ANY (ARRAY['api'::text, 'scraping'::text])))`
- `dim_stores_pkey` : `PRIMARY KEY (store_id)`
- `dim_stores_name_key` : `UNIQUE (name)`

### `mart.fact_popularity_history` (table)
Agregats journaliers de popularite jouee et diffusee, promus depuis la couche Silver speed (Bloc 1, 3.4).

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `game_id` | `uuid` | non |  | Jeu concerne. Clef etrangere vers dim_games. |
| `day` | `date` | non |  | Journee agregee. Avec game_id, forme la clef primaire et definit le grain journalier. |
| `avg_player_count` | `numeric(12,2)` | oui |  | Moyenne des releves de frequentation de la journee. Colonne large, pas de modele EAV. |
| `max_player_count` | `integer` | oui |  | Pic de frequentation de la journee. |
| `avg_viewer_count` | `numeric(12,2)` | oui |  | Moyenne de l'audience diffusee. Nulle tant que la source Twitch n'est pas branchee. |
| `max_viewer_count` | `integer` | oui |  | Pic d'audience diffusee. Non alimente. |

Contraintes :

- `fact_popularity_history_game_id_fkey` : `FOREIGN KEY (game_id) REFERENCES mart.dim_games(game_id)`
- `fact_popularity_history_pkey` : `PRIMARY KEY (game_id, day)`

### `mart.fact_prices` (table)
Tarifs collectes par jeu et par boutique. Alimentee par le scraping GOG et les API de tarification (Bloc 1).

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `price_id` | `uuid` | non | `gen_random_uuid()` | Clef primaire interne UUID. |
| `game_id` | `uuid` | non |  | Jeu concerne. Clef etrangere vers dim_games. |
| `store_id` | `uuid` | non |  | Boutique concernee. Clef etrangere vers dim_stores. |
| `price` | `numeric(10,2)` | non |  | Prix effectivement paye, en devise currency. Doit rester strictement positif. |
| `currency` | `character(3)` | non | `'EUR'::bpchar` | Devise ISO 4217. |
| `promotion_flag` | `boolean` | non | `false` | Vrai si le releve correspond a une remise en cours. |
| `collected_at` | `timestamp with time zone` | non |  | Instant du releve. Avec game_id et store_id, definit le grain (contrainte UNIQUE). |

Contraintes :

- `fact_prices_price_check` : `CHECK ((price > (0)::numeric))`
- `fact_prices_game_id_fkey` : `FOREIGN KEY (game_id) REFERENCES mart.dim_games(game_id)`
- `fact_prices_store_id_fkey` : `FOREIGN KEY (store_id) REFERENCES mart.dim_stores(store_id)`
- `fact_prices_pkey` : `PRIMARY KEY (price_id)`
- `uq_fact_prices_grain` : `UNIQUE (game_id, store_id, collected_at)`

## Schema `speed`
Couche Silver speed : donnee recente, nettoyee, servie en continu.

### `speed.v_daily_player_stats` (vue)
Agregat journalier de la frequentation, promu vers mart.fact_popularity_history par le DAG Airflow. observation_count sert de controle de completude.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `steam_appid` | `integer` | oui |  |  |
| `unified_name` | `text` | oui |  |  |
| `day` | `date` | oui |  |  |
| `avg_player_count` | `numeric` | oui |  |  |
| `max_player_count` | `integer` | oui |  |  |
| `min_player_count` | `integer` | oui |  |  |
| `observation_count` | `bigint` | oui |  |  |

### `speed.v_indicateur_completude` (vue)
Titres distincts collectes sur 24h rapportes aux titres actifs. Detecte une source partiellement muette.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `titres_attendus` | `bigint` | oui |  |  |
| `titres_collectes_24h` | `bigint` | oui |  |  |
| `titres_manquants` | `bigint` | oui |  |  |
| `taux_completude_pct` | `numeric` | oui |  |  |

### `speed.v_indicateur_fiabilite` (vue)
Taux de succes et duree par composant. Le compteur inachevees repere un composant interrompu avant sa fin, cas qui ne produit ni succes ni echec.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `composant` | `text` | oui |  |  |
| `executions_24h` | `bigint` | oui |  |  |
| `succes` | `bigint` | oui |  |  |
| `echecs` | `bigint` | oui |  |  |
| `inachevees` | `bigint` | oui |  |  |
| `taux_succes_pct` | `numeric` | oui |  |  |
| `duree_moyenne_s` | `numeric` | oui |  |  |
| `derniere_execution` | `timestamp with time zone` | oui |  |  |

### `speed.v_indicateur_fraicheur` (vue)
Age de la donnee la plus recente par flux. Indicateur principal de la plateforme.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `flux` | `text` | oui |  |  |
| `derniere_collecte` | `timestamp with time zone` | oui |  |  |
| `age_minutes` | `numeric` | oui |  |  |
| `evenements_24h` | `bigint` | oui |  |  |

### `speed.v_indicateur_gold` (vue)
Fraicheur de la couche Gold POSTGRESQL, et d elle seule : la couche Snowflake n a aucun indicateur (V-13). La collecte peut fonctionner alors que la promotion est en panne, les deux se surveillent separement.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `derniere_journee_promue` | `date` | oui |  |  |
| `lignes_derniere_journee` | `bigint` | oui |  |  |
| `dimensions_jeux` | `bigint` | oui |  |  |
| `retard_jours` | `integer` | oui |  |  |

### `speed.v_indicateur_latence` (vue)
Temps ecoule entre collecte et ecriture en base. Le p95 est preferable a la moyenne, qu un seul pic suffit a rendre illisible.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `echantillon_24h` | `bigint` | oui |  |  |
| `latence_moyenne_s` | `numeric` | oui |  |  |
| `latence_max_s` | `numeric` | oui |  |  |
| `latence_p95_s` | `numeric` | oui |  |  |

### `speed.v_supervision_synthese` (vue)
Etat consolide de la plateforme, un element surveille par ligne. Alimente le bandeau superieur du tableau de bord.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `element` | `text` | oui |  |  |
| `valeur` | `numeric` | oui |  |  |
| `unite` | `text` | oui |  |  |
| `etat` | `text` | oui |  |  |

### `speed.alertes` (table)
Historique des alertes declenchees. Persistees pour pouvoir mesurer la duree d un incident, pas seulement son occurrence.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `alerte_id` | `bigint` | non | `nextval('speed.alertes_alerte_id_seq'::r` | Clef technique de l'alerte. |
| `regle` | `text` | non |  | Nom de la regle declenchante, tel que defini dans supervision/regles_alertes.py. |
| `severite` | `text` | non |  | critique ou avertissement. Contraint par CHECK. |
| `message` | `text` | non |  | Message formate, valeur observee et seuil substitues. |
| `valeur` | `numeric` | oui |  | Valeur observee au declenchement. |
| `seuil` | `numeric` | oui |  | Seuil franchi. Defini en SQL, jamais dans l'outil de restitution. |
| `declenchee_le` | `timestamp with time zone` | non | `now()` | Premiere evaluation ayant constate le franchissement. |
| `resolue_le` | `timestamp with time zone` | oui |  | Evaluation ayant constate le retour sous seuil. Nul tant que l'alerte est ouverte. L'ecart avec declenchee_le mesure la duree d'incident. |

Contraintes :

- `alertes_severite_check` : `CHECK ((severite = ANY (ARRAY['critique'::text, 'avertissement'::text])))`
- `alertes_pkey` : `PRIMARY KEY (alerte_id)`

### `speed.game_mapping` (table)
Referentiel de resolution des identifiants entre plateformes (Steam, Twitch, RAWG). Alimente depuis config/watchlist.json.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `steam_appid` | `integer` | non |  | Identifiant Steam, clef naturelle du referentiel. Verifie en direct titre par titre. |
| `unified_name` | `text` | non |  | Nom canonique retenu par GameLens, arbitre entre les libelles divergents des sources. |
| `developer` | `text` | oui |  | Studio de developpement, renseigne manuellement. |
| `genre` | `text` | oui |  | Genre principal. Sert de partition au classement distribue calcule par Snowpark. |
| `steam_name` | `text` | oui |  | Libelle exact cote Steam, conserve pour tracer les ecarts avec unified_name. |
| `twitch_game_id` | `text` | oui |  | Identifiant Twitch. Nul tant que la source de popularite diffusee n'est pas branchee. |
| `rawg_id` | `integer` | oui |  | Identifiant RAWG, source catalogue. |
| `is_active` | `boolean` | non | `true` | Titre suivi par la collecte. Mis a faux plutot que supprime, pour ne pas orpheliner l'historique. |
| `updated_at` | `timestamp with time zone` | non | `now()` | Derniere modification de la ligne de correspondance. |

Contraintes :

- `game_mapping_pkey` : `PRIMARY KEY (steam_appid)`

### `speed.pipeline_runs` (table)
Journal des executions de chaque composant du pipeline. Source des indicateurs de supervision et des alertes (C4.3.1).

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `run_id` | `bigint` | non | `nextval('speed.pipeline_runs_run_id_seq'` | Clef technique de l'execution. |
| `component` | `text` | non |  | Nom du composant execute. Valeurs attendues par la regle composant_muet de la supervision. |
| `status` | `text` | non |  | started, success ou failed. Contraint par CHECK. |
| `started_at` | `timestamp with time zone` | non | `now()` | Ouverture du contexte d'execution. |
| `ended_at` | `timestamp with time zone` | oui |  | Fermeture. Nul si le processus a ete tue sans passer par son finally. |
| `records_in` | `integer` | oui |  | Enregistrements lus. Un succes avec zero lu et zero ecrit designe une execution sterile. |
| `records_written` | `integer` | oui |  | Enregistrements reellement ecrits, doublons absorbes exclus. |
| `error_message` | `text` | oui |  | Type et message de l'exception, tronques a 2000 caracteres. |

Contraintes :

- `pipeline_runs_status_check` : `CHECK ((status = ANY (ARRAY['started'::text, 'success'::text, 'failed'::text])))`
- `pipeline_runs_pkey` : `PRIMARY KEY (run_id)`

### `speed.player_count_events` (table)
Evenements unitaires de frequentation Steam (GetNumberOfCurrentPlayers), consommes depuis Kafka. Grain : un appid, un instant de collecte.

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `event_id` | `bigint` | non | `nextval('speed.player_count_events_event` | Clef technique, sans signification metier. |
| `steam_appid` | `integer` | non |  | Titre concerne. Reference game_mapping, sans clef etrangere pour ne pas bloquer l'ingestion. |
| `player_count` | `integer` | non |  | Joueurs connectes a l'instant de l'appel. Zero est une mesure valide, pas une absence. |
| `collected_at` | `timestamp with time zone` | non |  | Instant de l'appel a Steam, fourni par le producteur. Avec steam_appid, definit le grain. |
| `ingested_at` | `timestamp with time zone` | non | `now()` | Instant de l'ecriture en base. L'ecart avec collected_at mesure la latence du pipeline. |
| `kafka_partition` | `integer` | oui |  | Partition Kafka d'origine, pour tracer un rejeu. |
| `kafka_offset` | `bigint` | oui |  | Offset Kafka d'origine, pour tracer un rejeu. |

Contraintes :

- `player_count_events_player_count_check` : `CHECK ((player_count >= 0))`
- `player_count_events_steam_appid_fkey` : `FOREIGN KEY (steam_appid) REFERENCES speed.game_mapping(steam_appid)`
- `player_count_events_pkey` : `PRIMARY KEY (event_id)`
- `uq_player_count_event` : `UNIQUE (steam_appid, collected_at)`

### `speed.price_snapshots` (table)
Releves tarifaires Steam (appdetails/price_overview). Remplace le scraping GOG, sorti du perimetre par l arbitrage du Bloc 3 (3.3).

| Colonne | Type | Nul | Defaut | Description |
|---|---|---|---|---|
| `snapshot_id` | `bigint` | non | `nextval('speed.price_snapshots_snapshot_` | Clef technique, sans signification metier. |
| `steam_appid` | `integer` | non |  | Titre concerne. |
| `price_final` | `numeric(10,2)` | non |  | Prix effectivement paye, en euros. Converti depuis les centimes rendus par Steam. |
| `price_initial` | `numeric(10,2)` | oui |  | Prix avant remise. Egal a price_final hors promotion. |
| `discount_percent` | `smallint` | non | `0` | Remise en pourcentage, telle qu'annoncee par Steam. Zero hors promotion. |
| `currency` | `character(3)` | non | `'EUR'::bpchar` | Devise ISO 4217, EUR par construction (parametre cc=fr). |
| `collected_at` | `timestamp with time zone` | non |  | Instant du releve tarifaire. Avec steam_appid, definit le grain. |
| `ingested_at` | `timestamp with time zone` | non | `now()` | Instant de l'ecriture en base. |

Contraintes :

- `price_snapshots_discount_percent_check` : `CHECK (((discount_percent >= 0) AND (discount_percent <= 100)))`
- `price_snapshots_price_final_check` : `CHECK ((price_final >= (0)::numeric))`
- `price_snapshots_price_initial_check` : `CHECK ((price_initial >= (0)::numeric))`
- `price_snapshots_steam_appid_fkey` : `FOREIGN KEY (steam_appid) REFERENCES speed.game_mapping(steam_appid)`
- `price_snapshots_pkey` : `PRIMARY KEY (snapshot_id)`
- `uq_price_snapshot` : `UNIQUE (steam_appid, collected_at)`

---

Colonnes de tables sans description : **0**. Une case vide est un manque declare, pas un oubli invisible.
