param([switch]$Clean, [switch]$Build)
$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "scripts\start_k8s.ps1") -Clean:$Clean -Build:$Build
exit $LASTEXITCODE
