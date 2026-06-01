# SmartGrid - Prevision energetique et detection d'anomalies

> **Projet 16** - Prevision de consommation energetique et detection d'anomalies pour Smart Grid
>
> ENSA Berrechid · Ahmed Ben Ahmed

---

## Objectif du projet

Ce projet met en place une chaine SmartGrid complete: ingestion de mesures de compteurs, stockage temporel, preparation Machine Learning, prevision de consommation, detection d'anomalies et visualisation operationnelle.

| Objectif | Implementation |
|---|---|
| Ingerer des series de compteurs intelligents | Kafka -> TimescaleDB hypertable |
| Stocker les donnees avec granularites temporelles | TimescaleDB continuous aggregates |
| Prevoir la consommation par source naturelle | SeasonalNaive, Prophet, LightGBM |
| Detecter les consommations anormales | Residus de prevision -> mediane/MAD -> flag anomalie |
| Visualiser les resultats | Grafana: consommation, previsions, anomalies, monitoring |
| Superviser l'infrastructure | Prometheus + exporters Kafka/PostgreSQL |

La logique ML principale repose sur une evaluation reproductible a cadence 30 minutes. L'horizon de prevision est de 24 heures, soit 48 pas temporels, avec validation rolling-origin et metrique WAPE.

---

## Rapport du projet

Le rapport complet du projet (architecture, benchmark ML, captures de demonstration) est disponible a la racine du depot:

- [`smartgrid_demo_report.pdf`](smartgrid_demo_report.pdf)

Les sources Typst et la version generee se trouvent dans `reports/smartgrid_demo/`.

---

## Stack technique

| Couche | Technologie |
|---|---|
| Ingestion | Kafka (Confluent CP 7.6) |
| Stockage | TimescaleDB / PostgreSQL 16 |
| Machine Learning | SeasonalNaive, Prophet, LightGBM, LSTM Autoencoder |
| Detection d'anomalies | Residus de prevision + rolling median/MAD |
| Monitoring | Prometheus + Grafana |
| Orchestration | Docker Compose |
| Rapport | Typst + PDF genere |

---

## Demarrage rapide

### Benchmark ML hors Docker

Ce chemin ne depend pas de l'infrastructure Docker. Il genere les donnees de demonstration, lance le benchmark ML et produit les artefacts de rapport.

```bash
make ml-benchmark-demo
make test
```

Artefacts principaux:

```text
reports/ml/forecast_metrics.json
reports/ml/anomaly_eval_metrics.json
reports/ml/experiment_matrix.json
reports/ml/model_comparison.md
reports/ml/benchmark_receipt.md
reports/smartgrid_demo/build/smartgrid_demo_report.pdf
```

Resultats de reference du benchmark local:

| Element | Resultat |
|---|---:|
| Meilleur WAPE 24h | 0.0707 avec LightGBM |
| F1 anomalie ligne | 0.4068 avec LightGBM + MAD |
| F1 anomalie evenement | 0.5000 avec LightGBM + MAD |
| Precision evenement | 0.8571 |

Les anomalies injectees sont des labels synthetiques vrais: pics, drops, swap contextuel `02:00 <-> 14:00` et drift progressif. Le rapport distingue le scoring ligne par ligne et le scoring evenementiel.

### Demo complete pour enregistrement

Pour lancer la pile locale, charger les donnees 30 minutes, charger les previsions/anomalies, verifier les services et afficher les liens utiles:

```bash
scripts/recording_demo_flow.sh
```

Ce script verifie:

- tests unitaires;
- compilation du rapport PDF;
- Docker Compose;
- TimescaleDB;
- Kafka UI;
- Grafana;
- Prometheus;
- chargement des lectures, previsions et anomalies.

Liens locaux:

- Grafana: <http://localhost:3001/d/smartgrid-load-map/smartgrid-e28094-load-map?orgId=1&from=1672531200000&to=1674345600000>
- Kafka UI: <http://localhost:8080>
- Prometheus: <http://localhost:9091/targets>

Identifiants locaux Grafana:

```text
admin / admin
```

---

## Donnees

Le projet documente plusieurs sources de consommation:

- Morocco High-Resolution Smart Meters;
- London Smart Meters;
- UCI Household Power;
- Nigeria Smart Meter.

Toutes les sources sont normalisees vers le schema:

```csv
time,meter_id,kwh,is_anomaly,source
```

Les fichiers lourds telecharges restent ignores par Git. Les donnees de demonstration deterministes sont generees localement par:

```bash
make demo-data
```

Pour preparer les jeux externes:

```bash
make download-data
make prepare-data
make load-data
```

Pour generer les figures EDA:

```bash
make eda
```

Les figures sont ecrites dans `reports/eda/` et reprises dans le rapport final.

---

## Structure du projet

```text
smartex-grid/
├── simulator/                  # Generateur de mesures de compteurs
├── ingestion/                  # Consumer Kafka -> TimescaleDB
├── warehouse/                  # Schema SQL + agregats temporels
├── ml/                         # Code Machine Learning
│   ├── benchmark_ml.py         # Matrice de benchmark CSV-first
│   ├── train_prophet.py        # Evaluation rolling-origin WAPE
│   ├── inject_anomalies.py     # Injection d'anomalies synthetiques
│   ├── eval_anomaly_detection.py
│   ├── evaluate_anomaly_benchmarks.py
│   ├── prophet_model.py
│   ├── lstm_model.py
│   └── incremental_train.py
├── grafana/                    # Dashboards et datasource provisioning
├── prometheus/                 # Configuration scrape
├── reports/
│   ├── ml/                     # Metriques et plots ML
│   └── smartgrid_demo/         # Rapport Typst, PDF, captures
├── scripts/                    # Scripts demo, benchmark et verification
├── docker-compose.yml
└── Makefile
```

---

## Rapport

Le rapport principal est disponible ici:

```text
reports/smartgrid_demo/build/smartgrid_demo_report.pdf
```

Pour le reconstruire:

```bash
typst compile reports/smartgrid_demo/report.typ reports/smartgrid_demo/build/smartgrid_demo_report.pdf
```

Le runbook de demonstration est ici:

```text
reports/smartgrid_demo/DEMO_RUNBOOK.md
```

---

## Lien avec SmartTex

Ce projet est autonome pour le module Smart Grid, mais il garde un lien naturel avec SmartTex:

<https://github.com/Ahmed-BenAhmed/smartex>

SmartTex mesure deja la puissance `power_watts` des metiers a tisser via capteur de courant. Dans une integration future, chaque machine textile peut devenir un compteur intelligent: un pont MQTT -> Kafka suffirait pour injecter ces mesures dans ce pipeline de prevision et de detection d'anomalies.

Voir `docs/architecture.md` pour la carte d'integration.
