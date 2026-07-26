param(
    [switch]$RuntimeOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    $uvArgs = @("sync")
    if (-not $RuntimeOnly) {
        $uvArgs += @("--extra", "dev")
    }
    & $uv.Source @uvArgs
    if ($LASTEXITCODE -ne 0) {
        throw "uv sync failed with exit code $LASTEXITCODE."
    }
    Write-Host "Environment ready: $projectRoot\.venv"
    exit 0
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if (-not $systemPython) {
        throw "Python was not found. Install Python 3.11-3.14 or install uv."
    }
    & $systemPython.Source -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create the project virtual environment."
    }
}

$extra = if ($RuntimeOnly) { "." } else { ".[dev]" }
& $python -m pip install --upgrade pip
& $python -m pip install -e $extra
if ($LASTEXITCODE -ne 0) {
    throw "pip editable install failed with exit code $LASTEXITCODE."
}
Write-Host "Environment ready: $projectRoot\.venv"
