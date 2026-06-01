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

Le projet documente quatre familles de données: Morocco High-Resolution Smart Meters (contexte marocain, conversion possible depuis l'intensité vers le kWh), London Smart Meters (profils résidentiels demi-horaires), UCI Household Power (jeu léger pour tests rapides) et Nigeria Smart Meter (validation africaine complémentaire). Toutes sont ramenées au schéma canonique commun.

#fig("media/merged_kwh_distribution.png", [Distribution des consommations dans le jeu préparé. Une distribution très étalée indique que le détecteur doit comparer une mesure à son contexte local plutôt qu'à une moyenne globale unique.], width: 78%)

#fig("media/merged_hourly_profile.png", [Profil horaire moyen par source. Les pics matin/soir et les creux nocturnes donnent le contexte attendu de consommation.], width: 78%)

= Pipeline Machine Learning

Le pipeline ML suit la chronologie d'une série temporelle: chaque source est nettoyée, convertie en kWh si nécessaire, puis ramenée à une cadence commune de 30 minutes. La prévision produit une valeur attendue; la détection mesure l'écart entre cette valeur attendue et la valeur observée.

#fig("media/ml_pipeline_benchmark.svg", [Pipeline ML: sources, prétraitement à 30 minutes, benchmark de prévision, calcul du résidu, sélection du seuil MAD et restitution des anomalies dans Grafana.], width: 96%)

== Benchmark de prévision

Le benchmark utilise quatre sources naturelles et cinq folds rolling-origin sur un horizon de 24 heures (48 pas). La métrique principale est WAPE, plus stable que MAPE lorsque la consommation contient des valeurs proches de zéro.

#table(
  columns: 5, inset: 5pt, align: center,
  [*Modèle*], [*Famille*], [*Statut*], [*WAPE 1 pas*], [*WAPE 24h*],
  [SeasonalNaive], [forecast], [complété], [0.0971], [0.1259],
  [Prophet default], [forecast], [complété], [0.0594], [2.7628],
  [Prophet tuned], [forecast], [complété], [0.0597], [1.2224],
  [LightGBM lags], [forecast], [complété], [0.1148], [0.0707],
)

#fig("media/forecast_model_comparison.svg", [Comparaison WAPE sur horizon 24h. LightGBM obtient la meilleure précision brute sur ce jeu synthétique; Prophet reste le modèle le plus explicable pour raconter tendance et saisonnalité.], width: 90%)

== Prophet et LSTM Autoencoder

Prophet modélise une série comme somme de composantes (tendance, saisonnalités, effets calendaires) et sert de baseline interprétable. Le LSTM Autoencoder apprend à reconstruire des fenêtres normales et signale les reconstructions coûteuses; il reste une baseline de recherche (F1 ligne `0.1933`).

#grid(columns: (1fr, 1fr), gutter: 0.3cm,
  fig("media/prophete_arch.png", [Principe Prophet: tendance + saisonnalités.], width: 100%),
  fig("media/lstm_arch.png", [Architecture LSTM: portes mémoire / oubli / sortie.], width: 78%),
)

= Détection d'anomalies et métriques

La détection compare la consommation réelle à la consommation prévue. Le signal utile est le résidu `|réel - yhat|`; une alerte est créée lorsque ce résidu dépasse un seuil robuste médiane/MAD. Le scoring distingue lignes individuelles et événements opérationnels: un événement non ponctuel doit accumuler `k = 5` flags, les pics et drops ponctuels gardent `k = 1`.

#grid(columns: (1fr, 1fr, 1fr, 1fr), gutter: 0.25cm,
  metric([Meilleur WAPE 24h], [0.0707]),
  metric([F1 ligne], [0.4068]),
  metric([F1 événement], [0.5000]),
  metric([Précision événement], [0.8571]),
)

Les anomalies injectées sont des labels synthétiques vrais, répartis en quatre familles: `point_spike`, `point_drop`, `contextual_day_night_swap` et `trend_drift`. Le seuil MAD retenu par balayage est `4.0`.

#table(
  columns: 5, inset: 5pt, align: center,
  [*Détecteur*], [*Précision ligne*], [*Rappel ligne*], [*F1 ligne*], [*TP/FP/FN/TN*],
  [SeasonalNaive + MAD], [0.3731], [0.3247], [0.3472], [25/42/52/841],
  [Prophet tuned + MAD], [0.5102], [0.3247], [0.3968], [25/24/52/859],
  [LightGBM + MAD], [0.6316], [0.3000], [0.4068], [24/14/56/866],
  [LSTM Autoencoder], [0.1394], [0.3152], [0.1933], [29/179/63/3761],
)

#fig("media/anomaly_threshold_sweep.svg", [Balayage du seuil MAD sur les résidus LightGBM. Le seuil 4.0 est retenu pour préserver une précision raisonnable tout en gardant des alertes exploitables.], width: 84%)

#fig("media/anomaly_row_vs_event_f1.svg", [F1 ligne vs F1 événement. Le scoring événement pénalise moins les micro-fluctuations isolées, mais montre que les anomalies contextuelles et les drifts graduels restent difficiles pour un simple résidu MAD.], width: 92%)

= Ingestion, stockage et monitoring

La démonstration locale lance Kafka, Kafka UI, TimescaleDB, Prometheus, Grafana et les exporters. Le topic `smartgrid.meters.raw` est alimenté, les lectures et sorties ML sont chargées dans l'entrepôt, les agrégats rafraîchis et les services vérifiés.

#fig("screenshots/live_grafana_dashboard.png", [Grafana: dashboard SmartGrid peuplé — lectures, prévisions, anomalies, consommation par source et indicateur de monitoring.], width: 94%)

#grid(columns: (1fr, 1fr), gutter: 0.3cm,
  fig("screenshots/live_kafka_ui.png", [Kafka UI: topic `smartgrid.meters.raw` avec messages live.], width: 100%),
  fig("screenshots/live_prometheus_targets.png", [Prometheus: targets Prometheus / Kafka / TimescaleDB en état UP.], width: 100%),
)

= Conclusion

Le projet valide une chaîne SmartGrid cohérente de bout en bout. La partie entrepôt fournit un modèle dimensionnel solide — faits temporels et dimensions conformes — adapté à une charge analytique. La partie IA repose sur une idée simple et vérifiable: une anomalie est un écart significatif entre la consommation observée et la consommation prévue pour la même source. Les deux contributions se rejoignent dans le même entrepôt et le même tableau de bord, de l'ingestion jusqu'à la décision.
