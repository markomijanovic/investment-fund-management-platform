#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
GRADER_DIR="$PROJECT_ROOT/professor_tests/iep_grader"
GRADER_PYTHON="$GRADER_DIR/.venv/bin/python"
RESET=false

if [[ $# -gt 1 ]]; then
  echo "Upotreba: $0 [--reset]" >&2
  exit 2
elif [[ "${1:-}" == "--reset" ]]; then
  RESET=true
elif [[ $# -gt 0 ]]; then
  echo "Upotreba: $0 [--reset]" >&2
  exit 2
fi

if ! kubectl get namespace iep >/dev/null 2>&1; then
  if [[ "$RESET" == true ]]; then
    "$PROJECT_ROOT/scripts/start_k8s.sh" --clean
  else
    echo "Kubernetes aplikacija nije pokrenuta. Prvo pokreni: ./start.sh" >&2
    exit 1
  fi
elif [[ "$RESET" == true ]]; then
  "$PROJECT_ROOT/scripts/reset_k8s_test_data.sh"
fi

if [[ ! -x "$GRADER_PYTHON" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    HOST_PYTHON=python3.11
  elif command -v python3 >/dev/null 2>&1; then
    HOST_PYTHON=python3
  else
    echo "Python 3 nije instaliran." >&2
    exit 1
  fi
  echo "Pravim virtuelno okruzenje profesora i instaliram zavisnosti (potrebno samo prvi put)..."
  "$HOST_PYTHON" -m venv "$GRADER_DIR/.venv"
  "$GRADER_PYTHON" -m pip install "setuptools==70.3.0"
  "$GRADER_PYTHON" -m pip install -r "$GRADER_DIR/requirements-pytest.txt"
fi

# Python 3.12 venv vise ne instalira setuptools automatski, a web3 6.5.0
# jos uvek uvozi pkg_resources iz tog paketa.
if ! "$GRADER_PYTHON" -c "import pkg_resources" >/dev/null 2>&1; then
  "$GRADER_PYTHON" -m pip install "setuptools==70.3.0"
fi

PORT_FORWARD_PIDS=()
FORWARD_LOG_DIR="$(mktemp -d)"

cleanup() {
  kubectl delete -f "$PROJECT_ROOT/scripts/professor_grader_checker.yaml" --ignore-not-found=true >/dev/null 2>&1 || true
  for process_id in "${PORT_FORWARD_PIDS[@]:-}"; do
    kill "$process_id" >/dev/null 2>&1 || true
  done
  rm -rf "$FORWARD_LOG_DIR"
}
trap cleanup EXIT INT TERM

port_is_open() {
  curl --silent --show-error --max-time 2 --output /dev/null "http://127.0.0.1:$1" >/dev/null 2>&1
}

start_port_forward_if_needed() {
  local service_name="$1"
  local port="$2"
  if port_is_open "$port"; then
    echo "Port $port je vec dostupan."
    return
  fi

  echo "Otvaram localhost:$port prema Kubernetes service/$service_name..."
  kubectl port-forward "service/$service_name" "$port:$port" -n iep \
    >"$FORWARD_LOG_DIR/$service_name.out" \
    2>"$FORWARD_LOG_DIR/$service_name.err" &
  PORT_FORWARD_PIDS+=("$!")
}

start_port_forward_if_needed auth 5000
start_port_forward_if_needed employee 5001
start_port_forward_if_needed director 5002
start_port_forward_if_needed ganache 8545

for _ in {1..30}; do
  if port_is_open 5000 && port_is_open 5001 && port_is_open 5002 && port_is_open 8545; then
    break
  fi
  sleep 1
done

if ! port_is_open 5000 || ! port_is_open 5001 || ! port_is_open 5002 || ! port_is_open 8545; then
  echo "Port-forward nije uspeo:" >&2
  for error_log in "$FORWARD_LOG_DIR"/*.err; do
    [[ -e "$error_log" ]] && { echo "--- $error_log" >&2; sed -n '1,40p' "$error_log" >&2; }
  done
  exit 1
fi

echo "Pokrecem privremeni brzi checker samo za vreme profesorovih testova..."
kubectl apply -f "$PROJECT_ROOT/scripts/professor_grader_checker.yaml"
kubectl rollout status deployment/professor-grader-checker -n iep --timeout=120s

echo "Pokrecem svih 98 profesorovih testova protiv Kubernetes servisa..."
cd "$GRADER_DIR"
"$GRADER_PYTHON" -m pytest -q --type all \
  --authentication-url http://127.0.0.1:5000 \
  --jwt-secret replace-this-jwt-secret-before-production \
  --roles-field role \
  --employee-role employee \
  --director-role director \
  --with-authentication \
  --employee-url http://127.0.0.1:5001 \
  --director-url http://127.0.0.1:5002 \
  --with-blockchain \
  --provider-url http://127.0.0.1:8545 \
  --wait-for-services \
  --service-timeout 120 \
  --grade-report-file grade_report.json
