PYTHON ?= .venv/bin/python
CONFIG ?= configs/batch_12.yaml
RUN_ID ?=
FROM ?=
REVIEW ?=
EXISTING ?=

.DEFAULT_GOAL := help
.PHONY: help setup install test history plan run collect resume review export

help:
	@echo "Comandos disponibles:"
	@echo "  make setup                       Crea .venv e instala dependencias"
	@echo "  make install                     Instala dependencias de desarrollo"
	@echo "  make test                        Ejecuta las pruebas"
	@echo "  make history                     Muestra el contador de corridas"
	@echo "  make plan                        Valida el batch de 12 sin usar la API"
	@echo "  make run [RUN_ID=nombre] [EXISTING=ruta.xlsx]"
	@echo "  make resume FROM=ruta.csv        Retoma una corrida parcial"
	@echo "  make review RUN_ID=nombre        Crea la hoja CSV de revisión"
	@echo "  make export REVIEW=ruta.csv      Exporta el corpus binario real"

setup:
	python3 -m venv .venv
	$(MAKE) install

install:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest -q -p no:cacheprovider

history:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/00_show_run_history.py

plan:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/01_collect_newsdata_urls.py --config $(CONFIG) --dry-run

collect:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/01_collect_newsdata_urls.py --config $(CONFIG) $(if $(RUN_ID),--run-id $(RUN_ID),) $(if $(EXISTING),--exclude-record-ids "$(EXISTING)",)

run: collect

resume:
	@if [ -z "$(FROM)" ]; then echo "Uso: make resume FROM=data/01_candidates/<run_id>.csv"; exit 2; fi
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/01_collect_newsdata_urls.py --config $(CONFIG) --resume-from "$(FROM)" $(if $(RUN_ID),--run-id $(RUN_ID),)

review:
	@if [ -z "$(RUN_ID)" ]; then echo "Uso: make review RUN_ID=<run_id>"; exit 2; fi
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/02_create_manual_review.py --input "data/01_candidates/$(RUN_ID).csv"

export:
	@if [ -z "$(REVIEW)" ]; then echo "Uso: make export REVIEW=data/02_review/<run_id>_manual_review.csv"; exit 2; fi
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/03_export_training_csv.py --input "$(REVIEW)"
