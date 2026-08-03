.PHONY: setup test lint dag-check

setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

dag-check:
	uv run python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('dags').glob('*.py')]"
