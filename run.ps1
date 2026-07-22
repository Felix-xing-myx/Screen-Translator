$ErrorActionPreference = 'Stop'

$customPython = 'E:\Python 3.14.6\python.exe'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue

if (Test-Path -LiteralPath $customPython) {
    $pythonExe = $customPython
} elseif ($pythonCommand) {
    $pythonExe = $pythonCommand.Source
} else {
    Write-Host 'Python was not found. Check the configured path or install Python and add it to PATH.' -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path -LiteralPath '.venv')) {
    & $pythonExe -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe main.py
