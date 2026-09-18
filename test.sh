#!/usr/bin/env bash
# Pokrece neizmenjen profesorov grader. Koristi --reset pre svakog punog prolaza.
set -Eeuo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$PROJECT_ROOT/scripts/run_professor_tests.sh" "$@"
