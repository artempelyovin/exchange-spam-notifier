.PHONY: format
format:
	uv run ruff format
	uv run ruff check --select I --fix   # fix only isort


.PHONY: lint
lint:
	uv run ruff check


.PHONY: type-check
type-check:
	poetry run ty check