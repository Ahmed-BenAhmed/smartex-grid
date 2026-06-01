.PHONY: up down logs simulate ingest train-lstm train-prophet detect download-data prepare-data load-data eda resample-model demo-data train-prophet-csv ml-benchmark inject-anomalies eval-anomalies anomaly-benchmark ml-plots threshold-sweep live-replay ml-demo ml-benchmark-demo test

FREQ_MINUTES ?= 30
ML_PYTHON ?= python
MODEL_FILE ?= data/model_ready/demo_meter_readings_$(FREQ_MINUTES)m.csv
INJECTED_FILE ?= data/model_ready/demo_meter_readings_$(FREQ_MINUTES)m_injected.csv
FORECAST_FILE ?= reports/ml/forecasts/demo_meter_readings_$(FREQ_MINUTES)m_lightgbm_lag_features_forecasts.csv
DEMO_FORECAST_FILE ?= reports/ml/forecasts/demo_meter_readings_$(FREQ_MINUTES)m_forecasts.csv
GROUP_BY ?= source
HORIZON_HOURS ?= 24
CV_FOLDS ?= 5

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

simulate:
	cd simulator && pip install -r requirements.txt -q
	cd simulator && python meter_simulator.py

ingest:
	cd ingestion && pip install -r requirements.txt -q
	cd ingestion && python kafka_to_timescale.py

train-lstm:
	cd ml && python lstm_model.py

train-prophet:
	cd ml && python prophet_model.py

detect:
	cd ml && python anomaly_detector.py

incremental:
	cd ml && python incremental_train.py

download-data:
	powershell -ExecutionPolicy Bypass -File scripts/download_datasets.ps1

prepare-data:
	python scripts/prepare_datasets.py --dataset all --max-rows 100000

load-data:
	cd ingestion && pip install -r requirements.txt -q
	python ingestion/load_csv_to_timescale.py

eda:
	python scripts/generate_eda.py --max-rows 500000

resample-model:
	python scripts/resample_for_model.py --freq-minutes $(FREQ_MINUTES)

demo-data:
	$(ML_PYTHON) scripts/generate_demo_data.py --cadence-minutes $(FREQ_MINUTES) --out data/processed/demo_meter_readings.csv
	$(ML_PYTHON) scripts/resample_for_model.py data/processed/demo_meter_readings.csv --freq-minutes $(FREQ_MINUTES)

train-prophet-csv:
	$(ML_PYTHON) ml/train_prophet.py $(MODEL_FILE) --group-by $(GROUP_BY) --horizon-hours $(HORIZON_HOURS) --folds $(CV_FOLDS) --model auto

ml-benchmark:
	$(ML_PYTHON) ml/benchmark_ml.py $(MODEL_FILE) --group-by $(GROUP_BY) --freq-minutes $(FREQ_MINUTES) --horizon-hours $(HORIZON_HOURS) --folds $(CV_FOLDS) --injected-file $(INJECTED_FILE)

inject-anomalies:
	$(ML_PYTHON) ml/inject_anomalies.py $(MODEL_FILE) --out $(INJECTED_FILE) --group-by $(GROUP_BY)

eval-anomalies:
	$(ML_PYTHON) ml/eval_anomaly_detection.py $(INJECTED_FILE) --group-by $(GROUP_BY) --window 24 --forecast-file $(FORECAST_FILE)

anomaly-benchmark:
	$(ML_PYTHON) ml/evaluate_anomaly_benchmarks.py $(INJECTED_FILE) --group-by $(GROUP_BY)

ml-plots:
	$(ML_PYTHON) scripts/plot_ml_benchmark.py

threshold-sweep:
	$(ML_PYTHON) scripts/compare_anomaly_thresholds.py $(INJECTED_FILE) --group-by $(GROUP_BY) --window 24 --forecast-file $(FORECAST_FILE)

live-replay:
	uv run --with kafka-python python scripts/replay_profile_to_kafka.py

ml-demo: FORECAST_FILE = $(DEMO_FORECAST_FILE)
ml-demo: demo-data train-prophet-csv inject-anomalies eval-anomalies threshold-sweep

ml-benchmark-demo: demo-data inject-anomalies ml-benchmark threshold-sweep anomaly-benchmark ml-plots

test:
	python -m unittest discover -s tests
