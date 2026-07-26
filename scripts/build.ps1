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

Push-Location $projectRoot
try {
    $sourceRoot = Join-Path $projectRoot 'src'
    $assetsRoot = Join-Path $sourceRoot 'screen_translator\assets'
    $specRoot = Join-Path $projectRoot 'build\spec'
    $workRoot = Join-Path $projectRoot 'build\pyinstaller'
    $distRoot = Join-Path $projectRoot 'dist'
    $pyInstallerArgs = @(
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "ScreenTranslator",
        "--specpath", $specRoot,
        "--workpath", $workRoot,
        "--distpath", $distRoot,
        "--paths", $sourceRoot,
        "--icon", (Join-Path $assetsRoot 'screen_translator.ico'),
        "--add-data", "$assetsRoot;screen_translator\assets",
        "--collect-all", "dashscope",
        "--hidden-import", "pyaudiowpatch"
    )
    if ($uvCommand) {
        $hasWebRtcVAD = (& $uvCommand.Source run --extra dev python -c "import importlib.util; print(1 if importlib.util.find_spec('webrtcvad') else 0)").Trim()
    } else {
        $hasWebRtcVAD = (& $pythonExe -c "import importlib.util; print(1 if importlib.util.find_spec('webrtcvad') else 0)").Trim()
    }
    if ($hasWebRtcVAD -eq '1') {
        $pyInstallerArgs += @("--hidden-import", "webrtcvad")
    }
    if ($uvCommand) {
        & $uvCommand.Source run --extra dev python -m PyInstaller @pyInstallerArgs (Join-Path $sourceRoot 'screen_translator\__main__.py')
    } else {
        & $pythonExe -m PyInstaller @pyInstallerArgs (Join-Path $sourceRoot 'screen_translator\__main__.py')
    }
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

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
