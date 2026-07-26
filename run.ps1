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

$requirementsPath = Join-Path $projectRoot 'requirements.txt'
$requirementsStamp = Join-Path $projectRoot '.venv\.requirements.sha256'
$requirementsHash = (Get-FileHash -LiteralPath $requirementsPath -Algorithm SHA256).Hash
$installedHash = if (Test-Path -LiteralPath $requirementsStamp) {
    (Get-Content -LiteralPath $requirementsStamp -Raw).Trim()
} else {
    ''
}

if ($installedHash -ne $requirementsHash) {
    & $venvPython -m pip install -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    Set-Content -LiteralPath $requirementsStamp -Value $requirementsHash -Encoding ascii
}
$env:PYTHONPATH = Join-Path $projectRoot 'src'
& $venvPython -m screen_translator
