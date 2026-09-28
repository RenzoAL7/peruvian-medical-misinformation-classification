PYTHON ?= .venv/bin/python
CONFIG ?= configs/batch_12.yaml
RUN_ID ?=
EXISTING ?=

.DEFAULT_GOAL := help
.PHONY: help setup install test plan run collect

help:
	@echo "Comandos disponibles:"
	@echo "  make setup                       Crea .venv e instala dependencias"
	@echo "  make install                     Instala dependencias de desarrollo"
	@echo "  make test                        Ejecuta las pruebas"
	@echo "  make plan                        Valida el batch de 12 sin usar la API"
	@echo "  make run [RUN_ID=nombre] [EXISTING=ruta.xlsx]"

setup:
	python3 -m venv .venv
	$(MAKE) install

install:
	$(PYTHON) -m pip install -e '.[dev]'

test:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B -m pytest -q -p no:cacheprovider

plan:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/01_collect_newsdata_urls.py --config $(CONFIG) --dry-run

collect:
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -B scripts/01_collect_newsdata_urls.py --config $(CONFIG) --rotate-queries $(if $(RUN_ID),--run-id $(RUN_ID),) $(if $(EXISTING),--exclude-record-ids "$(EXISTING)",)

run: collect
