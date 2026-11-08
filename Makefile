.PHONY: install data run test lint all clean

install:
	pip install -e ".[dev]"

data:
	python -m segments.download

run:
	python -m segments.pipeline

test:
	pytest -q

lint:
	ruff check src tests

all: data run test

clean:
	rm -rf reports/*.json reports/*.md figures/*.png outputs/*
