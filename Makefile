SHELL := /bin/bash

.PHONY: test-and-lint
# dont stop testing/linting after error
test-and-lint:
	@$(MAKE) -k test-and-lint2

.PHONY: test-and-lint2
test-and-lint2: test lint

.PHONY: lint
lint: lint-ruff lint-pylint lint-eslint

.PHONY: lint-ruff
lint-ruff:
	ruff check .
	ruff format --check .

.PHONY: lint-pylint
lint-pylint:
	pylint astsee/ tests/

.PHONY: lint-eslint
lint-eslint:
	./node_modules/.bin/eslint astsee/*.js

.PHONY: autofix
autofix: autofix-py autofix-js

.PHONY: autofix-py
autofix-py:
	ruff check . --fix --show-fixes
	ruff format .

.PHONY: autofix-js
autofix-js:
	./node_modules/.bin/eslint astsee/*.js --fix

.PHONY: test
test: pytest readme-test

.PHONY: pytest
pytest:
	pytest

.PHONY: readme-test
readme-test:
	TMPDIR=$$(mktemp -d) && cp README.md "$$TMPDIR/" && cd "$$TMPDIR" \
	# Extract inputs from README \
	tuttest README.md a.json > a.json && tuttest README.md b.json > b.json \
	# Check if diffing works (doesn't crash) \
	tuttest README.md produce-diff | bash -o pipefail - && \
	# Run pretty print and capture output \
	tuttest README.md pretty-print | bash -o pipefail - | tee actual-pretty-print-output && \
	# Check if pretty print output matches README \
	diff <(tuttest README.md pretty-print-output) actual-pretty-print-output --color=always
