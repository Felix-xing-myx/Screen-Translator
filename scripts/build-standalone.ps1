param(
    [switch]$AllowExternalTesseract
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not $uvCommand -and -not (Test-Path -LiteralPath $pythonExe)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Python is required on the build machine.'
    }
    $pythonExe = $pythonCommand.Source
}

$sourceRoot = Join-Path $projectRoot 'src'
$assetsRoot = Join-Path $sourceRoot 'screen_translator\assets'
$tesseractSource = Join-Path $projectRoot 'vendor\tesseract'
$tesseractExe = Join-Path $tesseractSource 'tesseract.exe'
$englishData = Join-Path $tesseractSource 'tessdata\eng.traineddata'
$distRoot = Join-Path $projectRoot 'dist\standalone'
$workRoot = Join-Path $projectRoot 'build\pyinstaller-standalone'
$specRoot = Join-Path $projectRoot 'build\spec-standalone'

if (-not ((Test-Path -LiteralPath $tesseractExe) -and
        (Test-Path -LiteralPath $englishData))) {
    if (-not $AllowExternalTesseract) {
        throw 'Bundled Tesseract is incomplete. Add vendor\tesseract or use -AllowExternalTesseract.'
    }
}

$pyInstallerArgs = @(
    '--noconfirm', '--clean', '--onefile', '--windowed',
    '--name', 'ScreenTranslator-Standalone',
    '--specpath', $specRoot,
    '--workpath', $workRoot,
    '--distpath', $distRoot,
    '--paths', $sourceRoot,
    '--icon', (Join-Path $assetsRoot 'screen_translator.ico'),
    '--add-data', "$assetsRoot;screen_translator\assets",
    '--collect-all', 'dashscope',
    '--collect-binaries', 'PySide6',
    '--collect-all', 'shiboken6',
    '--runtime-hook', (Join-Path $PSScriptRoot 'pyi_rth_qt_paths.py'),
    '--hidden-import', 'websocket',
    '--hidden-import', 'pyaudiowpatch'
)
if ((Test-Path -LiteralPath $tesseractExe) -and
    (Test-Path -LiteralPath $englishData)) {
    $pyInstallerArgs += @('--add-data', "$tesseractSource;tesseract")
}

if ($uvCommand) {
    $hasWebRtcVAD = (& $uvCommand.Source run --extra dev python -c "import importlib.util; print(1 if importlib.util.find_spec('webrtcvad') else 0)").Trim()
} else {
    $hasWebRtcVAD = (& $pythonExe -c "import importlib.util; print(1 if importlib.util.find_spec('webrtcvad') else 0)").Trim()
}
if ($hasWebRtcVAD -eq '1') {
    $pyInstallerArgs += @('--hidden-import', 'webrtcvad')
}

Push-Location $projectRoot
try {
    if ($uvCommand) {
        & $uvCommand.Source run --extra dev python -m PyInstaller @pyInstallerArgs (Join-Path $sourceRoot 'screen_translator\__main__.py')
    } else {
        & $pythonExe -m PyInstaller @pyInstallerArgs (Join-Path $sourceRoot 'screen_translator\__main__.py')
    }
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller standalone build failed with exit code $LASTEXITCODE."
    }
    Write-Host "Standalone build complete: $distRoot\ScreenTranslator-Standalone.exe"
} finally {
    Pop-Location
}
