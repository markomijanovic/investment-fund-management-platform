$ErrorActionPreference = "Stop"

Write-Host "Cekam da baze budu spremne..."
kubectl wait --for=condition=ready pod/mysql-0 -n iep --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "MySQL nije spreman." }
kubectl wait --for=condition=ready pod/mongo-0 -n iep --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "MongoDB nije spreman." }
kubectl wait --for=condition=ready pod -l app=redis -n iep --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "Redis nije spreman." }

Write-Host "Brisem podatke prethodnog prolaza profesorovih testova..."
kubectl exec mongo-0 -n iep -- mongosh "mongodb://iep:iep-password@127.0.0.1:27017/investment_fund?authSource=admin" --quiet --eval 'db.assets.deleteMany({}); db.processed_votes.deleteMany({});'
if ($LASTEXITCODE -ne 0) { throw "MongoDB reset nije uspeo." }
kubectl exec deployment/redis -n iep -- redis-cli FLUSHALL
if ($LASTEXITCODE -ne 0) { throw "Redis reset nije uspeo." }
kubectl exec mysql-0 -n iep -- mysql -uiep -piep-password users -e "DELETE FROM users WHERE email <> 'onlymoney@gmail.com';"
if ($LASTEXITCODE -ne 0) { throw "MySQL reset nije uspeo." }

Write-Host "Resetujem lokalni blockchain..."
kubectl rollout restart deployment/ganache -n iep
if ($LASTEXITCODE -ne 0) { throw "Ganache restart nije uspeo." }
kubectl rollout status deployment/ganache -n iep --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "Ganache nije postao spreman." }

Write-Host "Test podaci su ocisceni; Kubernetes servisi nisu ruseni."
