.PHONY: up down logs simulate ingest cluster train-lstm train-prophet detect

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
