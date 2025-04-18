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
test: pytest readme-test deepnest-test

.PHONY: pytest
pytest:
	pytest

.PHONY: readme-test
readme-test:
	TMPDIR=$$(mktemp -d) && cp README.md "$$TMPDIR/" && cp -r "tests/" "$$TMPDIR/" && cd "$$TMPDIR" \
	# Extract inputs from README \
	tuttest README.md a.json > a.json && tuttest README.md b.json > b.json \
	# Check if diffing works (doesn't crash) \
	tuttest README.md produce-diff | bash -o pipefail - && \
	# Run pretty print and capture output \
	tuttest README.md pretty-print | bash -o pipefail - | tee actual-pretty-print-output && \
	# Check if pretty print output matches README \
	diff <(tuttest README.md pretty-print-output) actual-pretty-print-output --color=always && \
	# Same for verilator \
	tuttest README.md verilator-pretty-print | bash -o pipefail - | tee actual-verilator-pretty-print-output && \
	diff <(tuttest README.md verilator-pretty-print-output) actual-verilator-pretty-print-output --color=always && \
	# cleanup \
	rm -rf "$$TMPDIR"

.PHONY: clean
clean:
	rm -rf astsee.egg-info build

.PHONY: install-venv-test
install-venv-test: clean
	tuttest README.md install-venv | cat - <(echo "python -c 'import astsee'") | bash

.PHONY: install-pipx-test
install-pipx-test: clean
	export PIPX_HOME=$$(mktemp -d) && \
	export PIPX_BIN_DIR=$$PIPX_HOME/bin && \
	PATH=$$PIPX_BIN_DIR:$$PATH && \
	if echo -e "0.15\n$$(pipx --version)" | sort --version-sort --check=quiet; then \
		tuttest README.md install-pipx | bash -o pipefail; \
	else \
		pipx install astsee --spec .; \
	fi && \
	cd tests/verilator_in && astsee_verilator --html test1_a.tree.json test1_b.tree.json > /dev/null

.PHONY: install-test
install-test: install-pipx-test install-venv-test

.PHONY: deepnest-test
deepnest-test:
	# generated with:
	# awk -vNEST=3000 'BEGIN{print f()} function f() { NEST--; if(NEST==0) return "[]"; else return "[\"0123456789ABCDEFGHIJKLMNOPRSTUW\",\n" f()"]"}' > tests/deepnest.json
	astsee verilator tests/deepnest.json >/dev/null
