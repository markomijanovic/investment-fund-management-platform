#!/usr/bin/env bash
# Pokrece Kubernetes aplikaciju. Prosledjuje opcioni --clean argument.
set -Eeuo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$PROJECT_ROOT/scripts/start_k8s.sh" "$@"
