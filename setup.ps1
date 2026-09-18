$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$GraderDir = Join-Path $ProjectRoot "professor_tests\iep_grader"
$GraderVenv = Join-Path $GraderDir ".venv"
$GraderPython = Join-Path $GraderVenv "Scripts\python.exe"
Set-Location $ProjectRoot

foreach ($CommandName in @("docker", "kubectl")) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Nedostaje komanda: $CommandName"
    }
}

docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop nije spreman." }
$DockerOs = docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $DockerOs.Trim() -ne "linux") {
    throw "Docker Desktop mora koristiti Linux containers."
}
kubectl cluster-info | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Kubernetes klaster nije spreman." }

Write-Host "Preuzimam infrastrukturne image-e..."
foreach ($Image in @("python:3.11-slim", "mysql:8.0.36", "mongo:7.0.12", "redis:7.2.5-alpine", "trufflesuite/ganache-cli:v6.12.2")) {
    docker pull $Image
    if ($LASTEXITCODE -ne 0) { throw "Neuspesno preuzimanje image-a $Image." }
}

Write-Host "Gradim aplikacione image-e..."
foreach ($Target in @("auth", "employee", "director", "checker")) {
    docker build --target $Target -t "iep-$Target`:latest" .
    if ($LASTEXITCODE -ne 0) { throw "Build image-a iep-$Target nije uspeo." }
}

if ((Test-Path $GraderVenv) -and -not (Test-Path $GraderPython)) {
    Write-Host "Uklanjam nekompatibilni venv kopiran sa drugog operativnog sistema..."
    Remove-Item -Recurse -Force $GraderVenv
}

if (-not (Test-Path $GraderPython)) {
    Write-Host "Pravim profesorov virtualni environment..."
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $GraderVenv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $GraderVenv
    } else {
        throw "Python 3 nije instaliran."
    }
    if ($LASTEXITCODE -ne 0) { throw "Kreiranje virtualnog environment-a nije uspelo." }
}

Write-Host "Instaliram zavisnosti profesorovog gradera..."
& $GraderPython -m pip install "setuptools==70.3.0"
if ($LASTEXITCODE -ne 0) { throw "Instalacija setuptools paketa nije uspela." }
& $GraderPython -m pip install -r (Join-Path $GraderDir "requirements-pytest.txt")
if ($LASTEXITCODE -ne 0) { throw "Instalacija profesorovih zavisnosti nije uspela." }

Write-Host ""
Write-Host "Priprema je zavrsena. Sledece komande vise ne zahtevaju internet:"
Write-Host "  .\start.ps1 -Clean"
Write-Host "  .\test.ps1 -Reset"
