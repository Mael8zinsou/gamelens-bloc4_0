"""Ingestion temps reel, deux sources vers Kafka vers Silver speed (C4.2.2).

Comble le trou structurel constate le 26/08/2026 : la chaine batch etait
orchestree, la chaine temps reel ne l'etait pas. `steam_producer.py` et
`kafka_to_postgres.py` n'etaient lances qu'a la main ou par la CI. La couche
Gold accusait alors six jours de retard, cinq alertes etaient ouvertes, et le
run planifie de promotion echouait sur sa porte de fraicheur. La supervision
faisait son travail ; c'est le pipeline qui ne tournait pas.

## Pourquoi un DAG planifie plutot qu'un service continu

Question legitime : on n'orchestre pas un flux sous un ordonnanceur batch.
La reponse tient a la nature de la source.

Steam n'expose pas un flux d'evenements. `GetNumberOfCurrentPlayers` rend la
valeur d'un compteur A L'INSTANT DE L'APPEL. Il n'y a rien a consommer en
continu : il y a un capteur a interroger. Le temps reel de GameLens est donc un
ECHANTILLONNAGE PERIODIQUE, et un echantillonnage periodique se planifie.
Faire tourner une boucle infinie sous Airflow serait un contresens, et se
priver d'orchestration au motif que le mot "temps reel" figure dans le nom en
serait un autre.

Cadence de 15 minutes, choisie contre le seuil de la regle d'alerte
`fraicheur_frequentation`, fixe a 90 minutes. La marge absorbe cinq cycles
manques avant qu'une alerte ne se declenche.

## Pourquoi catchup=False est ici une correction, pas un confort

Rattraper un run manque de 03h15 signifierait interroger Steam maintenant et
estampiller le resultat a 03h15. On fabriquerait de l'histoire fausse, ce qui
est pire que le trou qu'on pretend combler.

Un echantillon manque est perdu definitivement : personne ne conserve pour vous
le nombre de joueurs connectes a 14h03. Le seul rattrapage honnete est de
reprendre a l'instant present.

## Pourquoi Kafka garde son role malgre l'enchainement sequentiel

Le producteur et le consommateur tournent l'un apres l'autre dans le meme run,
ce qui peut donner l'impression que le tampon ne sert a rien. Il sert.

Le consommateur ne valide son offset qu'APRES l'ecriture en base. Si PostgreSQL
est indisponible au moment ou il tourne, la tache echoue, l'offset n'est pas
valide, et les messages restent dans Kafka. Le run suivant les reprend. Sans le
tampon, la collecte serait perdue avec l'echec de l'ecriture.

## Deux sources, dont une qui ne peut pas casser l'autre

Depuis le 08/09/2026 le DAG collecte aussi l'audience diffusee sur Twitch. Les
deux producteurs tournent EN PARALLELE, et la tache Twitch ne fait jamais
echouer le run.

Ce n'est pas de la complaisance. Twitch est une source facultative greffee sur
une chaine eliminatoire : si sa tache echouait, la consommation passerait en
upstream_failed et la collecte Steam, deja publiee sur Kafka, ne serait pas
ecrite en base. Une source d'appoint casserait la source principale. C'est le
defaut que DA-12 nomme a propos du canal de notification, un dispositif
accessoire pose sur le chemin critique de l'essentiel.

L'echec n'est pas tu pour autant. `twitch_producer.main()` ouvre `execution()`,
qui inscrit l'echec dans `speed.pipeline_runs` avant de le propager ; la regle
critique `echecs_composants` le releve au cycle de supervision suivant. La
panne est constatee la ou on la cherche, sans etre placee la ou elle nuit.

## Quatre taches, dont une porte de sortie

La derniere tache n'est pas decorative. Sans elle, un run ou le producteur
n'aurait rien collecte et le consommateur rien ecrit se terminerait en succes :
un pipeline qui reussit a ne rien faire est un pipeline qui ment. Elle verifie
un resultat attendu, y compris la trace dans `speed.pipeline_runs`, dont
l'absence avait deja produit un incident reel (INC-007).
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task

CONNEXION = "gamelens_postgres"
RACINE_INGESTION = "/opt/gamelens/ingestion"

# Fenetre d'observation du controle final. Large devant la duree d'un run
# (quelques secondes) et etroite devant la cadence de 15 minutes : elle ne peut
# donc voir que les ecritures du run en cours, pas celles du precedent.
FENETRE_CONTROLE_MIN = 10

# Aligne sur la regle d'alerte fraicheur_frequentation. Duplique volontairement
# ici : le DAG doit pouvoir constater lui-meme qu'il a bien referme ce que la
# supervision surveille.
SEUIL_FRAICHEUR_MIN = 90

# Secondes d'attente sans nouveau message avant que le consommateur ne rende la
# main. Doit couvrir la negociation d'appartenance au groupe, qui prend
# plusieurs secondes a la premiere connexion.
ATTENTE_CONSOMMATEUR_S = 30


@dag(
    dag_id="gamelens_ingestion_temps_reel",
    description="Collecte Steam cadencee, publication Kafka et ecriture en Silver speed",
    doc_md=__doc__,
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 8, 27, tz="UTC"),
    # Voir la section dediee de la documentation ci-dessus : rattraper un
    # echantillonnage manque fabriquerait de l'histoire fausse.
    catchup=False,
    # Deux collectes concurrentes interrogeraient Steam deux fois pour rien. Le
    # puits est idempotent, donc ce serait sans dommage, mais sans interet.
    max_active_runs=1,
    # Une seule reprise, rapprochee : au-dela, le run suivant arrive de toute
    # facon dans 15 minutes et collectera une valeur plus fraiche. S'acharner
    # sur un echantillon perime n'a pas de sens.
    default_args={"retries": 1, "retry_delay": pendulum.duration(minutes=2)},
    tags=["gamelens", "temps-reel", "ingestion", "c4.2.2"],
)
def ingestion_temps_reel():
    @task
    def collecter_et_publier() -> int:
        """Un cycle de collecte Steam, publie sur Kafka.

        Delegue a ingestion/steam_producer.py : le DAG orchestre, il
        n'implemente pas. C'est le meme point d'entree que celui utilise a la
        main et par la chaine d'integration continue, et c'est delibere : un
        orchestrateur qui appellerait une variante du code de production
        eprouverait autre chose que ce qui tourne.
        """
        import sys

        if RACINE_INGESTION not in sys.path:
            sys.path.insert(0, RACINE_INGESTION)
        import steam_producer

        # main() et non cycle() : main() ouvre le contexte execution(), qui
        # trace le passage dans speed.pipeline_runs. Appeler la fonction nue
        # collecterait les donnees sans laisser de trace, et rendrait la
        # collecte orchestree invisible pour la supervision (INC-007).
        code = steam_producer.main(["--once"])
        if code != 0:
            raise RuntimeError(
                f"steam_producer a rendu le code {code}. Broker injoignable ou API "
                "Steam en erreur : voir les journaux de la tache."
            )
        return code

    @task
    def collecter_audience_twitch() -> dict:
        """Un cycle de collecte Twitch. NE LEVE JAMAIS.

        Voir l'en-tete du module pour le raisonnement complet. En resume : une
        source facultative ne doit pas pouvoir empecher l'ecriture de la source
        principale, et son echec doit rester visible ailleurs, dans
        speed.pipeline_runs que la supervision interroge.

        Sans identifiants, twitch_producer rend 0 sans rien tenter : un depot
        fraichement clone et la chaine d'integration continue n'ont pas de
        compte Twitch et doivent fonctionner. Meme asymetrie que le canal de
        notification.
        """
        import sys

        if RACINE_INGESTION not in sys.path:
            sys.path.insert(0, RACINE_INGESTION)
        import twitch_producer

        try:
            code = twitch_producer.main(["--once"])
        except Exception as exc:  # noqa: BLE001 - voir la docstring
            print(
                f"Collecte Twitch en echec : {type(exc).__name__}: {exc}. "
                "Le run continue ; l'echec est trace dans speed.pipeline_runs et "
                "sera releve par la regle echecs_composants."
            )
            return {"statut": "echec", "detail": f"{type(exc).__name__}: {exc}"[:200]}
        return {"statut": "ok" if code == 0 else "echec", "detail": f"code {code}"}

    @task
    def consommer_vers_silver(amont: int, audience: dict) -> int:
        """Draine le topic vers la couche Silver speed, puis rend la main.

        Draine les DEUX topics : le consommateur est abonne a celui de la
        frequentation et a celui de l'audience, et choisit sa table sur le
        topic d'origine de chaque message.

        Les arguments `amont` et `audience` ne sont pas utilises : ils
        n'existent que pour imposer l'ordre des taches, ce qui est plus lisible
        qu'un enchainement declare separement. `audience` porte en outre le
        compte rendu de la collecte Twitch, consultable dans les journaux de la
        tache sans ouvrir ceux du producteur.

        `--depuis-le-debut` ne signifie pas "tout relire a chaque fois".
        L'option pilote `auto_offset_reset`, que Kafka ne consulte QUE lorsque
        le groupe n'a aucun offset valide. Elle dit donc : a la premiere
        connexion du groupe, commencer au debut du topic plutot que sauter ce
        qui s'y trouve deja. En regime etabli, elle n'a aucun effet. Sans elle,
        le premier run apres une remise a zero du broker publierait quinze
        messages, se positionnerait apres eux, et n'ecrirait rien.
        """
        import sys

        if RACINE_INGESTION not in sys.path:
            sys.path.insert(0, RACINE_INGESTION)
        import kafka_to_postgres

        code = kafka_to_postgres.main(
            ["--timeout", str(ATTENTE_CONSOMMATEUR_S), "--depuis-le-debut"]
        )
        if code != 0:
            raise RuntimeError(
                f"kafka_to_postgres a rendu le code {code}. Les offsets ne sont pas "
                "valides : les messages restent dans Kafka et le run suivant les reprendra."
            )
        return code

    @task
    def controler_ingestion(amont: int) -> dict:
        """Porte de sortie : verifie un resultat attendu, pas une absence d'erreur.

        Trois controles, dont aucun ne serait declenche par un plantage. Ils
        visent tous le meme mode de defaillance, le plus courant et le plus
        couteux sur ce type de chaine : le run qui se termine proprement sans
        avoir rien produit.
        """
        from airflow.providers.postgres.hooks.postgres import PostgresHook

        hook = PostgresHook(postgres_conn_id=CONNEXION)
        echecs = []

        # 1. Des evenements ont-ils reellement atterri ?
        ecrits, titres = hook.get_first(
            f"""
            SELECT count(*), count(DISTINCT steam_appid)
            FROM speed.player_count_events
            WHERE ingested_at >= now() - interval '{FENETRE_CONTROLE_MIN} minutes'
            """
        )
        print(
            f"Ecritures sur les {FENETRE_CONTROLE_MIN} dernieres minutes : {ecrits} "
            f"evenement(s) sur {titres} titre(s) distinct(s)."
        )
        if not ecrits:
            echecs.append(f"aucun evenement ecrit sur la fenetre de {FENETRE_CONTROLE_MIN} minutes")

        # 2. La fraicheur est-elle repassee sous le seuil que surveille la
        #    supervision ? C'est la question a laquelle ce DAG existe pour
        #    repondre : il ne suffit pas d'avoir ecrit, il faut avoir referme
        #    l'alerte.
        (age,) = hook.get_first(
            "SELECT age_minutes FROM speed.v_indicateur_fraicheur WHERE flux = 'frequentation'"
        )
        print(
            f"Fraicheur de la frequentation apres ce run : {age} minute(s), "
            f"seuil d'alerte {SEUIL_FRAICHEUR_MIN}."
        )
        if age is None or float(age) > SEUIL_FRAICHEUR_MIN:
            echecs.append(f"fraicheur a {age} minutes, au-dela du seuil {SEUIL_FRAICHEUR_MIN}")

        # 3. Les deux composants ont-ils laisse une trace ?
        #    Sans ce controle, le scenario d'INC-007 se rejouerait sans bruit :
        #    des collectes reelles, et une supervision qui croit le composant
        #    muet parce que rien ne s'est inscrit dans le journal.
        traces = hook.get_records(
            f"""
            SELECT component, count(*), max(status)
            FROM speed.pipeline_runs
            WHERE component IN ('steam_producer', 'kafka_to_postgres')
              AND started_at >= now() - interval '{FENETRE_CONTROLE_MIN} minutes'
            GROUP BY component
            """
        )
        vus = {ligne[0] for ligne in traces}
        for ligne in traces:
            print(f"  trace {ligne[0]:<20} {ligne[1]} execution(s), statut {ligne[2]}")
        manquants = {"steam_producer", "kafka_to_postgres"} - vus
        if manquants:
            echecs.append(
                "composants non traces dans pipeline_runs : " + ", ".join(sorted(manquants))
            )

        if echecs:
            raise ValueError(
                "Ingestion temps reel non conforme. " + " ; ".join(echecs) + ". "
                "Le run a pu se terminer sans erreur tout en ne produisant rien : "
                "c'est precisement ce que ce controle existe pour attraper."
            )

        # 4. L'audience diffusee, RAPPORTEE sans etre exigee. Le controle
        #    reste strict sur la source principale et muet sur la source
        #    facultative : exiger ici ce que la supervision surveille deja
        #    ferait echouer la chaine eliminatoire pour une panne de tiers.
        (spectateurs,) = hook.get_first(
            f"""
            SELECT count(*)
            FROM speed.viewer_count_events
            WHERE ingested_at >= now() - interval '{FENETRE_CONTROLE_MIN} minutes'
            """
        )
        print(f"Audience diffusee sur la meme fenetre : {spectateurs} releve(s).")

        print(
            f"\nIngestion conforme : {ecrits} evenement(s), {titres} titre(s), "
            f"fraicheur {age} min, deux composants traces, "
            f"{spectateurs} releve(s) d'audience."
        )
        return {
            "evenements": ecrits,
            "titres": titres,
            "fraicheur_min": float(age),
            "audience": spectateurs,
        }

    # Les deux producteurs sont PARALLELES. La tache Twitch ne levant jamais,
    # une panne de la source facultative ne peut pas empecher l'ecriture de la
    # source principale (voir l'en-tete du module).
    controler_ingestion(consommer_vers_silver(collecter_et_publier(), collecter_audience_twitch()))


ingestion_temps_reel()
