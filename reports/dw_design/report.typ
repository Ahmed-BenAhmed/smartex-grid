#import "ensa_frontpage.typ": ensa-frontpage

#show: doc => {
  set page(
    margin: (x: 2.05cm, y: 1.85cm),
    numbering: "1",
  )
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

#let fig(path, caption, width: 100%) = figure(
  image(path, width: width),
  caption: caption,
)

#let note(body) = rect(
  width: 100%,
  inset: 0.62em,
  radius: 6pt,
  fill: rgb("#F7FBFC"),
  stroke: 0.7pt + rgb("#22B8C8"),
)[#body]

#ensa-frontpage(
  tp-number: "SmartGrid",
  module-name: "Smart Grid - Big Data et Intelligence Artificielle",
  report-title: [Conception de l'entrepôt de données#linebreak()SmartGrid (schéma en étoile)],
  report-subtitle: "Modèle dimensionnel, couches médaillon et déploiement progressif",
  student-name: [Elwalid Aboulaakoul#linebreak()Ahmed Benahmed],
  supervisor-label: "Encadrement",
  supervisor-name: "Pr. Hrimech",
  report-date: "1 juin 2026",
  academic-year: "2025/2026",
  footer-note: "Conception data warehouse: dimensions conformes, faits temporels et déploiement progressif.",
  school-logo: "media/logo_ensab.png",
  university-logo: "media/uh1.png",
)

= Résumé

Ce rapport présente la conception de l'entrepôt de données (data warehouse) du projet SmartGrid: un schéma en étoile / galaxie à dimensions conformes posé sur un moteur temporel (TimescaleDB), un choix adapté à de la télémétrie de compteurs intelligents.

La conception repose sur quatre dimensions conformes (`dim_meter` en SCD-2, `dim_source`, `dim_date`, `dim_model`) partagées par trois tables de faits (`fact_meter_reading`, `fact_prediction`, `fact_anomaly_event`), organisées en couches médaillon bronze / argent / or. Le déploiement est conçu pour être progressif et sans interruption de service: le modèle est construit dans un schéma `dw` dédié, alimenté par rétro-remplissage puis par écriture, avant de basculer les lectures une fois la parité vérifiée.

= Schéma en étoile / galaxie

Le modèle s'appuie sur des faits temporels et des dimensions conformes partagées par tous les faits. Trois faits et quatre dimensions partagées constituent une constellation de faits (galaxie), variante multi-faits du schéma en étoile. Ce n'est pas un schéma en flocon: les dimensions ne sont pas normalisées en hiérarchies, ce qui réduit les jointures pour une charge dominée par la lecture.

#fig("media/dw_star_schema.png", [Schéma en étoile / galaxie. Les dimensions conformes (bleu) `dim_meter`, `dim_source`, `dim_date`, `dim_model` sont partagées par les trois tables de faits (orange). Les agrégats continus dérivent du fait de lectures et jouent le rôle de cube.], width: 96%)

Le diagramme entité-association détaille les clés et colonnes: chaque fait référence les dimensions par clé de substitution, ce qui découple les identifiants métier (par exemple `meter_id`) de la modélisation et permet l'historisation.

#fig("media/dw_erd.png", [Modèle entité-association détaillé. Les clés de substitution (`*_key`) relient les faits aux dimensions; `dim_meter` est historisée (SCD-2) via `valid_from/valid_to/is_current`.], width: 99%)

== Dimensions conformes

#table(
  columns: 2,
  inset: 5pt,
  align: (left, left),
  [*Dimension*], [*Rôle et attributs clés*],
  [`dim_meter` (SCD-2)], [Clé de substitution `meter_key`, clé naturelle `meter_id`, profil, départ (feeder), localisation, lat/lon, fenêtre de validité `valid_from/valid_to/is_current` pour conserver l'historique.],
  [`dim_source`], [Origine du jeu de données: `source_code`, pays, région, opérateur (disco).],
  [`dim_date`], [Calendrier: jour, jour de semaine, week-end, saison, jour férié, période tarifaire — utile comme variables pour la prévision.],
  [`dim_model`], [Référentiel des modèles: nom, version, famille, hyperparamètres (`jsonb`), identifiant d'entraînement.],
)

== Tables de faits

#table(
  columns: 2,
  inset: 5pt,
  align: (left, left),
  [*Fait (hypertable)*], [*Grain et mesures*],
  [`fact_meter_reading`], [Grain: compteur × instant. Mesures: `kwh`, `is_anomaly`. Partitionné par `time`, index unique `(meter_key, time)`.],
  [`fact_prediction`], [Grain: compteur × modèle × horizon × instant. Mesures: `kwh_pred`, `kwh_lower`, `kwh_upper`.],
  [`fact_anomaly_event`], [Grain: une détection. Mesures: `kwh_actual`, `kwh_expected`, `deviation`, `severity`, `anomaly_type`.],
)

La couche physique TimescaleDB est exploitée pleinement: hypertables sur chaque fait (chunks de 7 jours), agrégats continus (15 min / horaire / journalier), compression native des chunks anciens et politique de rétention.

= Couches médaillon

Le pipeline est organisé en couches bronze (brut), argent (nettoyé/typé) et or (faits, agrégats et marts) afin de séparer l'arrivée des données, leur normalisation et leur exposition.

#fig("media/dw_medallion_flow.png", [Flux médaillon: Kafka et le batch alimentent le bronze, le silver matérialise `fact_meter_reading` avec les dimensions, l'or expose l'agrégat continu, les prévisions et les anomalies consommés par le ML et Grafana.], width: 99%)

= Étoile ou flocon ?

#note[
*Décision: schéma en étoile.* Les dimensions du SmartGrid ont une faible cardinalité et la charge est dominée par la lecture (tableaux de bord Grafana et extraction de variables ML). Des dimensions dénormalisées réduisent les jointures et accélèrent les lectures.

*Flocon rejeté.* Normaliser les dimensions en hiérarchies (`compteur → localisation → ville → région`) n'est rentable que pour des dimensions très volumineuses ou redondantes, ou pour une gouvernance de normalisation stricte — ce n'est pas le cas ici. Le flocon ajouterait du coût de jointure pour un gain de stockage négligeable.
]

= Déploiement progressif (sans interruption)

Le déploiement est conçu pour préserver la continuité de service à chaque étape. Le modèle est construit dans un schéma `dw` dédié; les premières phases sont purement additives; les lectures ne basculent qu'une fois la parité vérifiée, et des vues de compatibilité aux colonnes identiques sont exposées aux consommateurs existants (tableaux de bord, scripts ML).

#fig("media/dw_migration_phases.png", [Déploiement en sept phases. Vert = additif (aucun impact), rouge = bascule. Le service reste opérationnel pendant les phases additives, puis les consommateurs sont préservés sous forme de vues lors de la bascule.], width: 92%)

#table(
  columns: 3,
  inset: 5pt,
  align: (left, left, left),
  [*Phase*], [*Action*], [*Continuité*],
  [0 — Garde-fous], [Tag git, instantané des comptages], [Aucun changement],
  [1 — Dimensions], [Créer `dw`, semer les dimensions], [Additif],
  [2 — Faits], [Créer + rétro-remplir, vérifier la parité], [Additif],
  [3 — Double écriture], [Alimenter `dw` en parallèle], [Service prioritaire],
  [4 — Bascule lectures], [Pointer Grafana/ML sur `dw.v_*`], [Réversible],
  [5 — Bascule], [Exposer les faits via vues `dw`], [Colonnes identiques],
  [6 — Nettoyage], [Retirer les artefacts transitoires], [Optionnel],
)

Chaque phase possède un retour arrière en une étape. La garantie de fond: aucune opération destructive avant que la parité ne soit prouvée, et les consommateurs existants restent servis par des vues aux colonnes identiques.

= Conclusion

La conception proposée combine des faits temporels sur TimescaleDB et des dimensions conformes (`dim_meter` SCD-2, `dim_source`, `dim_date`, `dim_model`), avec clés et contraintes, compression/rétention et un découpage médaillon clair. Le schéma en étoile est adapté à une charge de lecture analytique, et le déploiement progressif garantit la continuité de service du pipeline.
