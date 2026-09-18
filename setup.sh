#!/usr/bin/env bash
# Jednokratna priprema dok postoji internet. Posle ovoga start i test rade offline.
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GRADER_DIR="$PROJECT_ROOT/professor_tests/iep_grader"
GRADER_PYTHON="$GRADER_DIR/.venv/bin/python"
cd "$PROJECT_ROOT"

for command_name in docker kubectl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Nedostaje komanda: $command_name" >&2
    exit 1
  fi
done

docker info >/dev/null
kubectl cluster-info >/dev/null

echo "Preuzimam infrastrukturne image-e..."
docker pull python:3.11-slim
docker pull mysql:8.0.36
docker pull mongo:7.0.12
docker pull redis:7.2.5-alpine
docker pull trufflesuite/ganache-cli:v6.12.2

echo "Gradim aplikacione image-e..."
docker build --target auth -t iep-auth:latest .
docker build --target employee -t iep-employee:latest .
docker build --target director -t iep-director:latest .
docker build --target checker -t iep-checker:latest .

if [[ ! -x "$GRADER_PYTHON" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    HOST_PYTHON=python3.11
  elif command -v python3 >/dev/null 2>&1; then
    HOST_PYTHON=python3
  else
    echo "Python 3 nije instaliran." >&2
    exit 1
  fi
  echo "Pravim profesorov virtualni environment..."
  "$HOST_PYTHON" -m venv "$GRADER_DIR/.venv"
fi

echo "Instaliram zavisnosti profesorovog gradera..."
"$GRADER_PYTHON" -m pip install "setuptools==70.3.0"
"$GRADER_PYTHON" -m pip install -r "$GRADER_DIR/requirements-pytest.txt"

echo
echo "Priprema je zavrsena. Sledece komande vise ne zahtevaju internet:"
echo "  ./start.sh --clean"
echo "  ./test.sh --reset"
