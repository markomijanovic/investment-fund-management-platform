param([switch]$Reset)
$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "scripts\run_professor_tests.ps1") -Reset:$Reset
exit $LASTEXITCODE
