param(
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$GraderDir = Join-Path $ProjectRoot "professor_tests\iep_grader"
$GraderVenv = Join-Path $GraderDir ".venv"
$GraderPython = Join-Path $GraderVenv "Scripts\python.exe"
Set-Location $ProjectRoot

kubectl get namespace iep | Out-Null
if ($LASTEXITCODE -ne 0) {
    if ($Reset) {
        & (Join-Path $PSScriptRoot "start_k8s.ps1") -Clean
        if ($LASTEXITCODE -ne 0) { throw "Cisto Kubernetes pokretanje nije uspelo." }
    } else {
        throw "Kubernetes aplikacija nije pokrenuta. Prvo pokreni: .\start.ps1"
    }
} elseif ($Reset) {
    & (Join-Path $PSScriptRoot "reset_k8s_test_data.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Reset test podataka nije uspeo." }
}

if ((Test-Path $GraderVenv) -and -not (Test-Path $GraderPython)) {
    Write-Host "Uklanjam nekompatibilni venv kopiran sa drugog operativnog sistema..."
    Remove-Item -Recurse -Force $GraderVenv
}

if (-not (Test-Path $GraderPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonLauncher = "py"
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonLauncher = "python"
    } else {
        throw "Python 3 nije instaliran."
    }

    Write-Host "Pravim virtuelno okruzenje profesora i instaliram zavisnosti (potrebno samo prvi put)..."
    if ($PythonLauncher -eq "py") {
        & py -3 -m venv $GraderVenv
    } else {
        & python -m venv $GraderVenv
    }
    if ($LASTEXITCODE -ne 0) { throw "Kreiranje virtuelnog okruzenja nije uspelo." }
    & $GraderPython -m pip install "setuptools==70.3.0"
    if ($LASTEXITCODE -ne 0) { throw "Instalacija setuptools paketa nije uspela." }
    & $GraderPython -m pip install -r (Join-Path $GraderDir "requirements-pytest.txt")
    if ($LASTEXITCODE -ne 0) { throw "Instalacija zavisnosti profesora nije uspela." }
}

# Python 3.12 venv vise ne instalira setuptools automatski, a web3 6.5.0
# jos uvek uvozi pkg_resources iz tog paketa.
& $GraderPython -c "import pkg_resources" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $GraderPython -m pip install "setuptools==70.3.0"
    if ($LASTEXITCODE -ne 0) { throw "Instalacija setuptools paketa nije uspela." }
}

$CheckerManifest = Join-Path $ProjectRoot "scripts\professor_grader_checker.yaml"
$TestExitCode = 1
$PortForwardProcesses = @()

function Test-LocalPort([int]$Port) {
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $ConnectTask = $Client.ConnectAsync("127.0.0.1", $Port)
        return $ConnectTask.Wait(1000) -and $Client.Connected
    } catch {
        return $false
    } finally {
        $Client.Dispose()
    }
}

function Start-PortForwardIfNeeded([string]$Service, [int]$Port) {
    if (Test-LocalPort $Port) {
        Write-Host "Port $Port je vec dostupan."
        return
    }

    Write-Host "Otvaram localhost:$Port prema Kubernetes service/$Service..."
    $Process = Start-Process kubectl -ArgumentList @(
        "port-forward", "service/$Service", "${Port}:${Port}", "-n", "iep"
    ) -PassThru -NoNewWindow
    $script:PortForwardProcesses += $Process
}

try {
    Start-PortForwardIfNeeded "auth" 5000
    Start-PortForwardIfNeeded "employee" 5001
    Start-PortForwardIfNeeded "director" 5002
    Start-PortForwardIfNeeded "ganache" 8545

    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        if ((Test-LocalPort 5000) -and (Test-LocalPort 5001) -and (Test-LocalPort 5002) -and (Test-LocalPort 8545)) {
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not ((Test-LocalPort 5000) -and (Test-LocalPort 5001) -and (Test-LocalPort 5002) -and (Test-LocalPort 8545))) {
        throw "Automatski port-forward nije uspeo."
    }

    Write-Host "Pokrecem privremeni brzi checker samo za vreme profesorovih testova..."
    kubectl apply -f $CheckerManifest
    if ($LASTEXITCODE -ne 0) { throw "Privremeni checker nije pokrenut." }
    kubectl rollout status deployment/professor-grader-checker -n iep --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "Privremeni checker nije postao spreman." }

    Write-Host "Pokrecem svih 98 profesorovih testova protiv Kubernetes servisa..."
    Set-Location $GraderDir
    & $GraderPython -m pytest -q --type all `
        --authentication-url http://127.0.0.1:5000 `
        --jwt-secret replace-this-jwt-secret-before-production `
        --roles-field role `
        --employee-role employee `
        --director-role director `
        --with-authentication `
        --employee-url http://127.0.0.1:5001 `
        --director-url http://127.0.0.1:5002 `
        --with-blockchain `
        --provider-url http://127.0.0.1:8545 `
        --wait-for-services `
        --service-timeout 120 `
        --grade-report-file grade_report.json
    $TestExitCode = $LASTEXITCODE
} finally {
    Set-Location $ProjectRoot
    kubectl delete -f $CheckerManifest --ignore-not-found=true | Out-Null
    foreach ($Process in $PortForwardProcesses) {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

exit $TestExitCode
