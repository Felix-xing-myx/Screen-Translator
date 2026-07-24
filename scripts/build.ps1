param(
    [switch]$AllowExternalTesseract
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Python is required on the build machine.'
    }
    $pythonExe = $pythonCommand.Source
}

Push-Location $projectRoot
try {
    & $pythonExe -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name ScreenTranslator `
        --paths src `
        src\screen_translator\__main__.py

    $tesseractSource = Join-Path $projectRoot 'vendor\tesseract'
    $tesseractExe = Join-Path $tesseractSource 'tesseract.exe'
    $englishData = Join-Path $tesseractSource 'tessdata\eng.traineddata'
    if ((Test-Path -LiteralPath $tesseractExe) -and (Test-Path -LiteralPath $englishData)) {
        $tesseractTarget = Join-Path $projectRoot 'dist\ScreenTranslator\tesseract'
        New-Item -ItemType Directory -Force -Path $tesseractTarget | Out-Null
        Copy-Item -Path (Join-Path $tesseractSource '*') `
            -Destination $tesseractTarget -Recurse -Force
    } elseif ($AllowExternalTesseract) {
        Write-Warning 'Bundled Tesseract is incomplete; this development build requires an external Tesseract.'
    } else {
        throw 'Bundled Tesseract is incomplete. Add vendor\tesseract\tesseract.exe and tessdata\eng.traineddata, or use -AllowExternalTesseract for a development build.'
    }

    Write-Host "Build complete: $projectRoot\dist\ScreenTranslator"
} finally {
    Pop-Location
}

