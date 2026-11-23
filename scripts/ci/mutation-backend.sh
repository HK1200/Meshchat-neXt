#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

TARGET="${MUTMUT_TARGET:-meshchatnext.src.backend.meshchat_utils*}"
THRESHOLD="${MUTMUT_MIN_SCORE:-}"
STATS_FILE="${MUTMUT_STATS_FILE:-mutmut-cicd-stats.json}"

# Fork-server children may suppress their console. Keep the exact original
# baseline failure without logging expected failures from real mutants.
export MUTMUT_DIAGNOSTICS_DIR="${MUTMUT_DIAGNOSTICS_DIR:-$ROOT/temp-tests/mutation-diagnostics}"
export PYTEST_PLUGINS="${PYTEST_PLUGINS:+$PYTEST_PLUGINS,}tests.backend.mutation_failure_reports"

echo "Running mutmut on: ${TARGET}"

worker_args=()
if [[ -n "${MUTMUT_MAX_CHILDREN:-}" ]]; then
    worker_args=(--max-children "${MUTMUT_MAX_CHILDREN}")
fi
uv run mutmut run "${worker_args[@]}" "${TARGET}"
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
