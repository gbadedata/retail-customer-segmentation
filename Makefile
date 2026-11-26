.PHONY: install install-spark data run test parity lint all clean

install:
	pip install -e ".[dev]"

install-spark:
	pip install -e ".[dev,spark]"

data:
	python -m segments.download

run:
	python -m segments.pipeline

test:
	pytest -q

parity:
	python scripts/spark_parity.py --check

lint:
	ruff check src tests scripts

all: data run test

clean:
	rm -rf reports/*.json reports/*.md figures/*.png outputs/*
