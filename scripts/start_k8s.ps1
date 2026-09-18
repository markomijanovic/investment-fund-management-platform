param(
    [switch]$Clean,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

foreach ($CommandName in @("docker", "kubectl")) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Nedostaje komanda: $CommandName"
    }
}

docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop nije spreman." }
kubectl cluster-info | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Kubernetes klaster nije spreman." }

if ($Clean) {
    Write-Host "Brisem prethodni iep namespace i podatke radi cistog pokretanja..."
    kubectl delete namespace iep --ignore-not-found=true --wait=true
    if ($LASTEXITCODE -ne 0) { throw "Neuspesno brisanje namespace-a." }
}

$NeedBuild = $Build
foreach ($Image in @("iep-auth:latest", "iep-employee:latest", "iep-director:latest", "iep-checker:latest")) {
    docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) { $NeedBuild = $true }
}

if ($NeedBuild) {
    Write-Host "Gradim lokalne aplikacione image-e..."
    docker build --target auth -t iep-auth:latest .
    if ($LASTEXITCODE -ne 0) { throw "Build iep-auth image-a nije uspeo." }
    docker build --target employee -t iep-employee:latest .
    if ($LASTEXITCODE -ne 0) { throw "Build iep-employee image-a nije uspeo." }
    docker build --target director -t iep-director:latest .
    if ($LASTEXITCODE -ne 0) { throw "Build iep-director image-a nije uspeo." }
    docker build --target checker -t iep-checker:latest .
    if ($LASTEXITCODE -ne 0) { throw "Build iep-checker image-a nije uspeo." }
} else {
    Write-Host "Koristim vec pripremljene lokalne aplikacione image-e."
}

Write-Host "Primenjujem Kubernetes manifest..."
kubectl apply -f .\k8s\all.yaml
if ($LASTEXITCODE -ne 0) { throw "Kubernetes manifest nije primenjen." }
foreach ($Deployment in @("auth", "employee", "director")) {
    kubectl rollout restart "deployment/$Deployment" -n iep
    if ($LASTEXITCODE -ne 0) { throw "Restart deployment-a $Deployment nije uspeo." }
}

Write-Host "Cekam infrastrukturu..."
foreach ($App in @("mysql", "mongo", "redis", "ganache")) {
    kubectl wait --for=condition=ready pod -l "app=$App" -n iep --timeout=300s
    if ($LASTEXITCODE -ne 0) { throw "$App nije postao spreman." }
}

Write-Host "Cekam SQL inicijalizaciju..."
kubectl wait --for=condition=complete job/sql-init -n iep --timeout=300s
if ($LASTEXITCODE -ne 0) { throw "SQL inicijalizacija nije zavrsena." }

Write-Host "Cekam aplikacione servise..."
foreach ($Deployment in @("auth", "employee", "director")) {
    kubectl rollout status "deployment/$Deployment" -n iep --timeout=300s
    if ($LASTEXITCODE -ne 0) { throw "$Deployment nije postao spreman." }
}

kubectl get pods,services,jobs,cronjobs -n iep
Write-Host ""
Write-Host "Aplikacija je spremna:"
Write-Host "  Auth:     http://127.0.0.1:5000"
Write-Host "  Employee: http://127.0.0.1:5001"
Write-Host "  Director: http://127.0.0.1:5002"
Write-Host "  Ganache:  http://127.0.0.1:8545"
Write-Host "Test skripta automatski otvara port-forward ako LoadBalancer nije vezan za localhost."
Write-Host ""
Write-Host "Za cisto ponovno pokretanje koristi: .\start.ps1 -Clean"
Write-Host "Posle izmene izvornog koda koristi: .\start.ps1 -Build"
