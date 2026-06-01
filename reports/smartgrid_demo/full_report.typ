#import "ensa_frontpage.typ": ensa-frontpage

#show: doc => {
  set page(margin: (x: 2.05cm, y: 1.85cm), numbering: "1")
  set text(font: "Libertinus Serif", size: 12pt)
  set par(justify: true, leading: 0.62em)
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    v(0.35cm)
    align(center)[#text(20pt, weight: "bold")[#it.body]]
    v(0.4cm)
  }
  show heading.where(level: 2): it => {
    v(0.24cm)
    text(15pt, weight: "bold")[#it.body]
    v(0.1cm)
  }
  doc
}

#let fig(path, caption, width: 100%) = figure(image(path, width: width), caption: caption)

#let note(body) = rect(width: 100%, inset: 0.62em, radius: 6pt,
  fill: rgb("#F7FBFC"), stroke: 0.7pt + rgb("#22B8C8"))[#body]

#let metric(label, value) = rect(inset: 0.55em, radius: 6pt,
  fill: rgb("#EAF8FB"), stroke: 0.6pt + rgb("#22B8C8"))[
  #text(9pt, fill: gray.darken(25%))[#label]
  #linebreak()
  #text(15pt, weight: "bold", fill: rgb("#233B7B"))[#value]
]

#let part(title) = align(center)[
  #v(1.2cm)
  #text(13pt, fill: rgb("#22B8C8"), weight: "bold")[#title]
  #v(0.2cm)
  #line(length: 38%, stroke: 1pt + rgb("#22B8C8"))
]

#ensa-frontpage(
  tp-number: "SmartGrid",
  module-name: "Smart Grid - Big Data et Intelligence Artificielle",
  report-title: [Projet SmartGrid — Rapport complet],
  report-subtitle: "Entrepôt de données, prévision de consommation et détection d'anomalies",
  student-name: [Ahmed Benahmed — Entrepôt de données#linebreak()Elwalid Aboulaakoul — Intelligence artificielle],
  supervisor-label: "Encadrement",
  supervisor-name: "Pr. Hrimech",
  report-date: "1 juin 2026",
  academic-year: "2025/2026",
  footer-note: "Rapport complet: conception de l'entrepôt de données et algorithmes IA de détection d'anomalies.",
  school-logo: "media/logo_ensab.png",
  university-logo: "media/uh1.png",
)

= Vue d'ensemble du projet

Le projet SmartGrid met en place une chaîne complète pour observer la consommation électrique de compteurs intelligents, anticiper la demande et signaler les comportements anormaux. Les compteurs produisent des séries temporelles volumineuses et hétérogènes; le projet les transforme en un flux exploitable: ingestion, stockage temporel, modélisation analytique, prévision, détection d'écarts et visualisation opérationnelle.

Le système s'articule autour de deux contributions complémentaires:

#table(
  columns: 2,
  inset: 6pt,
  align: (left, left),
  [*Contribution*], [*Périmètre*],
  [*Entrepôt de données* — Ahmed Benahmed], [Normalisation multi-source vers un schéma commun, modélisation dimensionnelle en étoile / galaxie, stockage TimescaleDB (hypertables, agrégats continus) et couches médaillon.],
  [*Intelligence artificielle* — Elwalid Aboulaakoul], [Préparation des séries, benchmark de prévision (SeasonalNaive, Prophet, LightGBM), détection d'anomalies par résidu médiane/MAD, baseline LSTM Autoencoder, évaluation précision/rappel et démonstration reproductible.],
)

La chaîne de bout en bout relie ces deux parties: les mesures arrivent par Kafka ou par chargement batch, sont normalisées et stockées dans l'entrepôt, servent de base aux modèles de prévision, puis la détection compare la valeur observée à la valeur attendue avant restitution dans Grafana et supervision par Prometheus.

#fig("media/smartgrid_architecture_ai.png", [Architecture globale du projet: sources de mesure, ingestion Kafka, entrepôt TimescaleDB, couche IA (Prophet / LightGBM / LSTM Autoencoder), détection d'anomalies, puis supervision Grafana et Prometheus.], width: 74%)

Les données suivent un découpage médaillon: bronze (mesures brutes), argent (faits nettoyés et dimensions conformes), or (agrégats, prévisions et anomalies exposés au tableau de bord). Ce découpage relie directement la partie entrepôt et la partie IA.

#fig("media/dw_medallion_flow.png", [Flux médaillon reliant les deux parties: Kafka et le batch alimentent le bronze, le silver matérialise les faits avec leurs dimensions, l'or expose agrégats, prévisions et anomalies consommés par le ML et Grafana.], width: 99%)

Toutes les sources sont ramenées au même format canonique, ce qui découple les modèles et le tableau de bord de la forme originale de chaque fichier:

```csv
time,meter_id,kwh,is_anomaly,source
```

Le reste du rapport détaille les deux parties: la Partie I présente la conception de l'entrepôt de données; la Partie II présente les algorithmes IA de prévision et de détection d'anomalies.

#part[Partie I — Conception de l'entrepôt de données]

= Schéma en étoile / galaxie

La partie entrepôt s'appuie sur des faits temporels et des dimensions conformes partagées par tous les faits. Trois faits et quatre dimensions partagées constituent une constellation de faits (galaxie), variante multi-faits du schéma en étoile. Ce n'est pas un schéma en flocon: les dimensions ne sont pas normalisées en hiérarchies, ce qui réduit les jointures pour une charge dominée par la lecture.

#fig("media/dw_star_schema.png", [Schéma en étoile / galaxie. Les dimensions conformes (bleu) `dim_meter`, `dim_source`, `dim_date`, `dim_model` sont partagées par les trois tables de faits (orange). Les agrégats continus dérivent du fait de lectures et jouent le rôle de cube.], width: 94%)

Le diagramme entité-association détaille les clés et colonnes: chaque fait référence les dimensions par clé de substitution, ce qui découple les identifiants métier de la modélisation et permet l'historisation.

#fig("media/dw_erd.png", [Modèle entité-association détaillé. Les clés de substitution (`*_key`) relient les faits aux dimensions; `dim_meter` est historisée (SCD-2) via `valid_from/valid_to/is_current`.], width: 99%)

== Dimensions conformes

#table(
  columns: 2, inset: 5pt, align: (left, left),
  [*Dimension*], [*Rôle et attributs clés*],
  [`dim_meter` (SCD-2)], [Clé de substitution `meter_key`, clé naturelle `meter_id`, profil, départ (feeder), localisation, lat/lon, fenêtre de validité `valid_from/valid_to/is_current`.],
  [`dim_source`], [Origine du jeu de données: `source_code`, pays, région, opérateur (disco).],
  [`dim_date`], [Calendrier: jour, jour de semaine, week-end, saison, jour férié, période tarifaire.],
  [`dim_model`], [Référentiel des modèles: nom, version, famille, hyperparamètres (`jsonb`), identifiant d'entraînement.],
)

== Tables de faits

#table(
  columns: 2, inset: 5pt, align: (left, left),
  [*Fait (hypertable)*], [*Grain et mesures*],
  [`fact_meter_reading`], [Grain: compteur × instant. Mesures: `kwh`, `is_anomaly`. Index unique `(meter_key, time)`.],
  [`fact_prediction`], [Grain: compteur × modèle × horizon × instant. Mesures: `kwh_pred`, `kwh_lower`, `kwh_upper`.],
  [`fact_anomaly_event`], [Grain: une détection. Mesures: `kwh_actual`, `kwh_expected`, `deviation`, `severity`, `anomaly_type`.],
)

La couche physique TimescaleDB est exploitée pleinement: hypertables sur chaque fait (chunks de 7 jours), agrégats continus (15 min / horaire / journalier), compression native des chunks anciens et politique de rétention.

== Étoile ou flocon ?

#note[
*Décision: schéma en étoile.* Les dimensions du SmartGrid ont une faible cardinalité et la charge est dominée par la lecture (tableaux de bord Grafana et extraction de variables ML). Des dimensions dénormalisées réduisent les jointures et accélèrent les lectures.

*Flocon rejeté.* Normaliser les dimensions en hiérarchies (`compteur → localisation → ville → région`) n'est rentable que pour des dimensions très volumineuses ou redondantes — ce n'est pas le cas ici, et le flocon ajouterait du coût de jointure pour un gain de stockage négligeable.
]

#part[Partie II — Intelligence artificielle: prévision et détection d'anomalies]

= Sources de données et préparation

Le projet documente quatre familles de données. Morocco High-Resolution Smart Meters donne le contexte marocain et peut nécessiter une conversion depuis l'intensité électrique vers le kWh. London Smart Meters fournit des profils résidentiels riches à granularité demi-horaire. UCI Household Power sert de jeu plus léger pour les tests rapides. Nigeria Smart Meter ajoute une validation africaine complémentaire avec un comportement de consommation différent.

Toutes les sources sont ramenées vers le même format:

```csv
time,meter_id,kwh,is_anomaly,source
```

Cette normalisation est importante: le modèle et le dashboard ne doivent pas dépendre de la forme originale d'un fichier London, Morocco, Nigeria ou UCI. Le champ `source` conserve l'origine de la série et permet d'éviter une confusion entre pays, dataset et compteur individuel.

La première figure EDA vérifie l'ordre de grandeur des consommations. Elle sert à repérer les valeurs extrêmes, les zéros anormaux et les différences d'échelle entre sources avant l'entraînement.

#fig("media/merged_kwh_distribution.png", [Distribution des consommations dans le jeu préparé. Une distribution très étalée indique que le détecteur doit comparer une mesure à son contexte local plutôt qu'à une moyenne globale unique.], width: 82%)

Le profil horaire moyen montre la saisonnalité intra-journalière. C'est cette structure qui justifie les fenêtres temporelles du LSTM et les comparaisons avec les mêmes heures historiques.

#fig("media/merged_hourly_profile.png", [Profil horaire moyen par source de données. Les pics matin/soir et les creux nocturnes donnent le contexte attendu de consommation.], width: 82%)

La consommation quotidienne sert à observer les tendances plus lentes. Elle est plus adaptée à Prophet, car ce modèle cherche d'abord une tendance et des composantes saisonnières.

#fig("media/merged_daily_total.png", [Consommation quotidienne par compteur. Cette vue révèle les variations de niveau et prépare la séparation entre prévision court terme et tendance long terme.], width: 82%)

= Pipeline Machine Learning

Le pipeline ML suit directement la chronologie d'une série temporelle. Chaque source de données est d'abord nettoyée, convertie en kWh si nécessaire, puis ramenée à une cadence commune. La prévision produit ensuite une valeur attendue; la détection d'anomalies mesure l'écart entre cette valeur attendue et la valeur observée.

#fig("media/ml_pipeline_benchmark.svg", [Pipeline ML retenu: sources de données, prétraitement à 30 minutes, benchmark de prévision, calcul du résidu, sélection du seuil MAD et restitution des anomalies dans Grafana.], width: 96%)

La chaîne est volontairement séquentielle. Le prétraitement fixe la granularité et le schéma. Les modèles de prévision produisent une valeur attendue au même horizon. La détection compare ensuite le réel au prévu et transforme seulement les écarts significatifs en alertes.

== Benchmark de prévision

Le benchmark utilise quatre sources naturelles et cinq folds rolling-origin. La métrique principale est WAPE, plus stable que MAPE lorsque la consommation contient des valeurs proches de zéro. Le minimum industriel est SeasonalNaive; Prophet donne la baseline interprétable; LightGBM teste une approche tabulaire avec lags et variables calendaires.

#table(
  columns: 5, inset: 5pt, align: center,
  [*Modèle*], [*Famille*], [*Statut*], [*WAPE 1 pas*], [*WAPE 24h*],
  [SeasonalNaive], [forecast], [complété], [0.0971], [0.1259],
  [Prophet default], [forecast], [complété], [0.0594], [2.7628],
  [Prophet tuned], [forecast], [complété], [0.0597], [1.2224],
  [LightGBM lags], [forecast], [complété], [0.1148], [0.0707],
)

#fig("media/forecast_model_comparison.svg", [Comparaison WAPE sur horizon 24h. LightGBM obtient la meilleure précision brute sur ce jeu synthétique, tandis que Prophet reste le modèle le plus explicable pour raconter tendance et saisonnalité.], width: 92%)

== Prévision tendance: Prophet

Prophet modélise une série comme somme de composantes: tendance, saisonnalités et effets calendaires. Dans ce projet, il est utilisé comme baseline interprétable car ses composantes peuvent être expliquées à un opérateur. Le résultat numérique montre aussi sa limite: sur l'horizon 24h synthétique, Prophet extrapole moins bien que LightGBM. Ce n'est pas masqué; le rapport le garde comme modèle principal d'interprétation, pas comme vainqueur automatique du benchmark.

#fig("media/prophete_arch.png", [Principe Prophet: la prévision combine tendance et saisonnalités. Ce modèle complète le LSTM en donnant une lecture plus stable du comportement attendu.], width: 96%)

== Baseline séquentielle: LSTM Autoencoder

Le LSTM Autoencoder n'est pas utilisé comme classifieur supervisé, car aucun label réel d'anomalie industrielle n'est disponible. Il apprend plutôt à reconstruire des fenêtres normales et signale les reconstructions coûteuses. Dans cette expérience, il reste une baseline de recherche: F1 ligne `0.1933`, inférieur aux détecteurs résiduels sur les anomalies ponctuelles.

#fig("media/lstm_arch.png", [Architecture LSTM: les portes contrôlent la mémoire, l'oubli et la sortie. Cette structure reste utile pour une baseline séquentielle non supervisée.], width: 72%)

== Démonstration reproductible

La démonstration locale utilise quatre profils synthétiques calibrés pour représenter les sources Morocco, London, Nigeria et UCI. Chaque profil conserve un comportement horaire distinct, ce qui permet de tester la chaîne complète sans dépendre de fichiers bruts volumineux pendant la soutenance. Les sorties ML sont calculées par source avec `freq_minutes = 30`, `horizon_hours = 24`, `horizon_steps = 48` et au moins cinq folds.

= Détection d'anomalies et métriques

La détection compare la consommation réelle à la consommation prévue. Le signal utile est le résidu:

#align(center)[
  #text(13pt, weight: "bold")[résidu = |consommation réelle - consommation prévue|]
]

Une alerte est créée lorsque ce résidu dépasse un seuil statistique. La démonstration utilise une version robuste basée sur la médiane et la MAD, moins sensible aux valeurs extrêmes qu'une moyenne simple. Le seuil n'est pas une vérité fixe: c'est un réglage métier, sélectionné ici par balayage.

#grid(
  columns: (1fr, 1fr, 1fr, 1fr),
  gutter: 0.25cm,
  metric([Meilleur WAPE 24h], [0.0707]),
  metric([F1 ligne], [0.4068]),
  metric([F1 événement], [0.5000]),
  metric([Précision événement], [0.8571]),
)

Les anomalies injectées sont des labels synthétiques vrais, pas des faux positifs. Le protocole inclut quatre familles: `point_spike`, `point_drop`, `contextual_day_night_swap` et `trend_drift`. Le cas contextuel échange le segment 02:00 avec le segment 14:00: la valeur reste plausible globalement, mais devient mauvaise pour cette heure. Le drift applique une dégradation graduelle `y'_t = y_t + beta t`; un détecteur de résidu peut alors ne voir que le début, la fin, ou rien si l'évolution reste trop lisse.

Le seuil MAD retenu par balayage est `MAD = 4.0`, avec précision ligne `0.6316`, rappel ligne `0.3000` et F1 ligne `0.4068`. Au niveau événement, le même détecteur obtient précision `0.8571`, rappel `0.3529` et F1 `0.5000`. Cette différence est volontaire: le scoring événement exige `k = 5` flags pour les segments non ponctuels afin de réduire les alertes fragiles; les anomalies ponctuelles gardent `k = 1`.

#table(
  columns: 8, inset: 5pt, align: center,
  [*Seuil MAD*], [*Precision*], [*Recall*], [*F1*], [*TP*], [*FP*], [*FN*], [*TN*],
  [1.0], [0.5217], [0.3000], [0.3810], [24], [22], [56], [858],
  [2.0], [0.5333], [0.3000], [0.3840], [24], [21], [56], [859],
  [3.0], [0.5714], [0.3000], [0.3934], [24], [18], [56], [862],
  [4.0], [0.6316], [0.3000], [0.4068], [24], [14], [56], [866],
)

Le tableau ne montre que quelques points; le graphe suivant représente le balayage complet de `0.5` à `5.0`. Il montre le compromis réel: la précision monte quand le seuil se durcit, mais le rappel chute, surtout pour les anomalies contextuelles et les drifts.

#fig("media/anomaly_threshold_sweep.svg", [Balayage du seuil MAD sur les résidus LightGBM. Le seuil 4.0 est retenu comme point de fonctionnement pour préserver une précision raisonnable tout en gardant des alertes exploitables.], width: 86%)

#table(
  columns: 5, inset: 5pt, align: center,
  [*Détecteur*], [*Précision ligne*], [*Rappel ligne*], [*F1 ligne*], [*TP/FP/FN/TN*],
  [SeasonalNaive + MAD], [0.3731], [0.3247], [0.3472], [25/42/52/841],
  [Prophet default + MAD], [0.4561], [0.3377], [0.3881], [26/31/51/852],
  [Prophet tuned + MAD], [0.5102], [0.3247], [0.3968], [25/24/52/859],
  [LightGBM + MAD], [0.6316], [0.3000], [0.4068], [24/14/56/866],
  [LSTM Autoencoder], [0.1394], [0.3152], [0.1933], [29/179/63/3761],
)

#table(
  columns: 5, inset: 5pt, align: center,
  [*Détecteur*], [*Précision événement*], [*Rappel événement*], [*F1 événement*], [*TP/FP/FN év.*],
  [SeasonalNaive + MAD], [0.5000], [0.4286], [0.4615], [6/6/8],
  [Prophet default + MAD], [0.5556], [0.3571], [0.4348], [5/4/9],
  [Prophet tuned + MAD], [0.7143], [0.3571], [0.4762], [5/2/9],
  [LightGBM + MAD], [0.8571], [0.3529], [0.5000], [6/1/11],
  [LSTM Autoencoder], [0.5000], [0.4483], [0.4727], [13/13/16],
)

#fig("media/anomaly_row_vs_event_f1.svg", [Comparaison F1 ligne vs F1 événement. Le scoring événement pénalise moins les micro-fluctuations isolées, mais révèle clairement que les anomalies contextuelles 02:00/14:00 et les drifts graduels restent difficiles pour un simple résidu MAD.], width: 94%)

Pour le meilleur détecteur résiduel LightGBM, les pics et drops sont bien captés au niveau événement: F1 `0.9091` pour `point_spike` et `0.8571` pour `point_drop`. En revanche, `contextual_day_night_swap` et `trend_drift` obtiennent F1 `0.0000`. C'est un résultat utile: il montre que le benchmark ne récompense pas seulement les anomalies faciles, et qu'un détecteur contextuel explicite ou un modèle de drift est nécessaire pour couvrir ces cas.

#fig("screenshots/20_ml_dashboard.png", [Synthèse locale des métriques ML: WAPE, précision, F1 et comparaison entre consommation réelle et prévue.], width: 92%)

== Tests automatisés

Les tests unitaires sécurisent les briques critiques:

- erreur WAPE: vérifie le calcul utilisé pour comparer réel et prévision;
- prévision de référence: garantit que le fallback saisonnier produit des sorties exploitables;
- vérité terrain injectée: confirme que les anomalies synthétiques sont bien labellisées;
- pic évident: vérifie que le détecteur MAD signale une rupture nette;
- scoring événement: vérifie que les segments non ponctuels nécessitent plusieurs flags avant d'être comptés positifs;
- table de seuils: contrôle la génération du compromis précision/rappel;
- replay Kafka: vérifie que les messages live conservent la source et peuvent injecter une anomalie.

Ces tests valident la reproductibilité de la démonstration; l'évaluation finale sur données réelles doit ensuite ajouter des backtests par source et une analyse des faux négatifs.

= Ingestion, stockage et monitoring

La démonstration locale lance Kafka, Kafka UI, TimescaleDB, Prometheus, Grafana et les exporters Kafka/PostgreSQL. Le bootstrap prépare le topic `smartgrid.meters.raw`, charge les lectures et les sorties ML dans TimescaleDB, rafraîchit les agrégats et vérifie les services.

#fig("media/05_infrastructure.png", [Topologie Docker Compose: Kafka pour l'ingestion, TimescaleDB pour les séries temporelles, Grafana pour la visualisation et Prometheus pour la supervision technique.], width: 92%)

#fig("screenshots/live_grafana_dashboard.png", [Grafana: dashboard SmartGrid peuplé avec lectures, prévisions, anomalies, consommation par source et indicateur de monitoring.], width: 96%)

Grafana est l'écran principal de lecture métier. Il montre les volumes chargés, les prévisions, les anomalies, la consommation agrégée et la comparaison forecast/actual. La vue par source permet de lire séparément Morocco, London, Nigeria et UCI.

#fig("screenshots/live_kafka_ui.png", [Kafka UI: topic `smartgrid.meters.raw` disponible avec messages de compteur. Ce panneau prouve la couche ingestion et prépare le replay live.], width: 96%)

Le replay live suit le standard des démonstrations sans flux industriel réel: on rejoue des profils issus des données préparées, avec horodatages courants, seed déterministe et anomalies injectées. Les messages restent traçables, et la validation compare les anomalies détectées aux labels injectés.

#fig("screenshots/live_prometheus_targets.png", [Prometheus: targets Prometheus, Kafka exporter et TimescaleDB exporter en état UP. Prometheus sert à suivre l'infrastructure, pas seulement l'état fonctionnel du dashboard.], width: 96%)

La supervision Prometheus doit montrer plus qu'un simple état visuel. Les métriques importantes sont `up`, `scrape_duration_seconds`, les séries exportées par Kafka et les métriques PostgreSQL/TimescaleDB. Ces signaux répondent à la question: le pipeline est-il observable pendant une démonstration ou une exécution prolongée?

= Conclusion et perspectives

Le projet valide une chaîne SmartGrid cohérente: normalisation multi-source, entrepôt de données dimensionnel, prévision, détection d'anomalies, stockage temporel, ingestion Kafka, dashboard Grafana et supervision Prometheus. La partie entrepôt fournit un modèle dimensionnel solide — faits temporels et dimensions conformes — adapté à une charge analytique. La partie IA repose sur une idée simple et vérifiable: une anomalie est un écart significatif entre la consommation observée et la consommation prévue pour la même source.

La suite naturelle consiste à remplacer les profils synthétiques de démonstration par les fichiers réels Morocco, London, Nigeria et UCI, puis à refaire les mêmes métriques par source. Cette continuité est importante: le protocole de test reste identique, seuls les profils rejoués et les modèles entraînés changent.
