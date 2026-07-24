$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Python was not found. A Python installation is required only for development.'
    }
    & $pythonCommand.Source -m venv (Join-Path $projectRoot '.venv')
}

& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements.txt')
$env:PYTHONPATH = Join-Path $projectRoot 'src'
& $venvPython -m screen_translator