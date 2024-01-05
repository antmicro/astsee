#!/bin/bash

# ci-like settings: abort on non-zero and log each line read by bash (including comments, and blanklines)
set -e -o pipefail -o verbose

# STEP: Smoke test
astsee --help

# STEP: Regular unit tests (pytest)
tuttest README.md test | bash -o pipefail -

# STEP: Extract inputs from README
tuttest README.md a.json > a.json
tuttest README.md b.json > b.json

# STEP: Check if diffing works (doesn't crash)
tuttest README.md produce-diff | bash -o pipefail -

# STEP: Run pretty print and capture output
tuttest README.md pretty-print | bash -o pipefail - | tee actual-pretty-print-output

# STEP: Check if pretty print output matches README
diff <(tuttest README.md pretty-print-output) actual-pretty-print-output --color=always
