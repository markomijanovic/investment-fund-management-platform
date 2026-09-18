#!/usr/bin/env bash
set -Eeuo pipefail

echo "Cekam da baze budu spremne..."
kubectl wait --for=condition=ready pod/mysql-0 -n iep --timeout=180s
kubectl wait --for=condition=ready pod/mongo-0 -n iep --timeout=180s
kubectl wait --for=condition=ready pod -l app=redis -n iep --timeout=180s

echo "Brisem podatke prethodnog prolaza profesorovih testova..."
kubectl exec mongo-0 -n iep -- mongosh \
  "mongodb://iep:iep-password@127.0.0.1:27017/investment_fund?authSource=admin" \
  --quiet --eval 'db.assets.deleteMany({}); db.processed_votes.deleteMany({});'
kubectl exec deployment/redis -n iep -- redis-cli FLUSHALL
kubectl exec mysql-0 -n iep -- mysql \
  -uiep -piep-password users \
  -e "DELETE FROM users WHERE email <> 'onlymoney@gmail.com';"

echo "Resetujem lokalni blockchain..."
kubectl rollout restart deployment/ganache -n iep
kubectl rollout status deployment/ganache -n iep --timeout=180s

echo "Test podaci su ocisceni; Kubernetes servisi nisu ruseni."
