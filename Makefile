.PHONY: up down logs simulate ingest cluster train-lstm train-prophet detect download-data prepare-data load-data eda resample-model

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
	python scripts/resample_for_model.py --freq-minutes 60
