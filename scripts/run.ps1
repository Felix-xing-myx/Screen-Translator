$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    & $uv.Source run --extra dev python -m screen_translator
    exit $LASTEXITCODE
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Environment not found. Run .\scripts\bootstrap.ps1 first."
}
& $python -m screen_translator
exit $LASTEXITCODE
