.PHONY: doctor test lint format check

doctor:
	uv run oc doctor

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: format lint test
