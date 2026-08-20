.PHONY: setup test lint dag-check score site site-check

setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

dag-check:
	uv run python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('dags').glob('*.py')]"

# Score the log against the market baseline. Recomputable; writes nothing back.
score:
	uv run python3 -m edgeledger.scoring.score --data-dir data

# Regenerate the learning pages from docs/learning/*.md (the source of truth).
site:
	uv run python3 site/build_learning.py

# Fail if the generated pages are invalid or stale relative to docs/learning/*.md.
site-check: site
	uv run --quiet --with html5lib python3 site/validate.py
	@git diff --quiet -- site/ || (echo "site/ is stale — 'make site' changed files; commit them" && exit 1)
