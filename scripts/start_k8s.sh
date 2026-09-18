#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CLEAN=false
FORCE_BUILD=false
for argument in "$@"; do
  case "$argument" in
    --clean) CLEAN=true ;;
    --build) FORCE_BUILD=true ;;
    *) echo "Upotreba: $0 [--clean] [--build]" >&2; exit 2 ;;
  esac
done

for command_name in docker kubectl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Nedostaje komanda: $command_name" >&2
    exit 1
  fi
done

docker info >/dev/null
kubectl cluster-info >/dev/null

if [[ "$CLEAN" == true ]]; then
  echo "Brisem prethodni iep namespace i podatke radi cistog pokretanja..."
  kubectl delete namespace iep --ignore-not-found=true --wait=true
fi

NEED_BUILD="$FORCE_BUILD"
for image_name in iep-auth:latest iep-employee:latest iep-director:latest iep-checker:latest; do
  if ! docker image inspect "$image_name" >/dev/null 2>&1; then
    NEED_BUILD=true
  fi
done

if [[ "$NEED_BUILD" == true ]]; then
  echo "Gradim lokalne aplikacione image-e..."
  docker build --target auth -t iep-auth:latest .
  docker build --target employee -t iep-employee:latest .
  docker build --target director -t iep-director:latest .
  docker build --target checker -t iep-checker:latest .
else
  echo "Koristim vec pripremljene lokalne aplikacione image-e."
fi

echo "Primenjujem Kubernetes manifest..."
kubectl apply -f k8s/all.yaml
kubectl rollout restart deployment/auth deployment/employee deployment/director -n iep

echo "Cekam infrastrukturu..."
kubectl wait --for=condition=ready pod -l app=mysql -n iep --timeout=300s
kubectl wait --for=condition=ready pod -l app=mongo -n iep --timeout=300s
kubectl wait --for=condition=ready pod -l app=redis -n iep --timeout=300s
kubectl wait --for=condition=ready pod -l app=ganache -n iep --timeout=300s

echo "Cekam SQL inicijalizaciju..."
kubectl wait --for=condition=complete job/sql-init -n iep --timeout=300s

echo "Cekam aplikacione servise..."
kubectl rollout status deployment/auth -n iep --timeout=300s
kubectl rollout status deployment/employee -n iep --timeout=300s
kubectl rollout status deployment/director -n iep --timeout=300s

kubectl get pods,services,jobs,cronjobs -n iep
echo
echo "Aplikacija je spremna:"
echo "  Auth:     http://127.0.0.1:5000"
echo "  Employee: http://127.0.0.1:5001"
echo "  Director: http://127.0.0.1:5002"
echo "  Ganache:  http://127.0.0.1:8545"
echo "Test skripta automatski otvara port-forward ako LoadBalancer nije vezan za localhost."
echo
echo "Za cisto ponovno pokretanje koristi: $0 --clean"
echo "Posle izmene izvornog koda koristi: $0 --build"
