.PHONY: up down logs simulate ingest cluster train-lstm train-prophet detect download-data prepare-data load-data eda resample-model demo-data train-prophet-csv inject-anomalies eval-anomalies ml-demo test

MODEL_FILE ?= data/model_ready/demo_meter_readings_60m.csv
INJECTED_FILE ?= data/model_ready/demo_meter_readings_60m_injected.csv
GROUP_BY ?= meter_id
FREQ_MINUTES ?= 60
HORIZON_HOURS ?= 24

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

cluster:
	cd ml && python clustering.py

train-lstm:
	cd ml && python lstm_model.py $(CLUSTER)

train-prophet:
	cd ml && python prophet_model.py $(CLUSTER)

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
	python scripts/generate_demo_data.py --out data/processed/demo_meter_readings.csv
	python scripts/resample_for_model.py data/processed/demo_meter_readings.csv --freq-minutes 60

train-prophet-csv:
	python ml/train_prophet.py $(MODEL_FILE) --group-by $(GROUP_BY) --horizon-hours $(HORIZON_HOURS) --model seasonal_naive

inject-anomalies:
	python ml/inject_anomalies.py $(MODEL_FILE) --out $(INJECTED_FILE) --group-by $(GROUP_BY)

eval-anomalies:
	python ml/eval_anomaly_detection.py $(INJECTED_FILE) --group-by $(GROUP_BY)

ml-demo: demo-data train-prophet-csv inject-anomalies eval-anomalies

test:
	python -m unittest discover -s tests
