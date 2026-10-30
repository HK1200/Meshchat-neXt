#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TARGET="${MUTMUT_TARGET:-meshchatnext.src.backend.meshchat_utils*}"
THRESHOLD="${MUTMUT_MIN_SCORE:-}"
STATS_FILE="${MUTMUT_STATS_FILE:-mutmut-cicd-stats.json}"

echo "Running mutmut on: ${TARGET}"

uv run mutmut run "${TARGET}"
# The exporter prints a status message and writes JSON to this file.
# Do not interpret its stdout as the score report.
rm -f mutants/mutmut-cicd-stats.json
uv run mutmut export-cicd-stats
test -s mutants/mutmut-cicd-stats.json
cp mutants/mutmut-cicd-stats.json "${STATS_FILE}"

if [[ -n "${THRESHOLD}" ]]; then
    uv run python scripts/ci/mutation-score-check.py \
        --mutmut-stats "${STATS_FILE}" \
        --min-score "${THRESHOLD}"
fi
