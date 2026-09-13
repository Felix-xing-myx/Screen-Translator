param(
    [switch]$AllowExternalTesseract
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$buildArgs = @()
if ($AllowExternalTesseract) {
    $buildArgs += "-AllowExternalTesseract"
}
& (Join-Path $PSScriptRoot "build.ps1") @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "Application build failed with exit code $LASTEXITCODE."
}

& (Join-Path $PSScriptRoot "build-standalone.ps1") @buildArgs
if ($LASTEXITCODE -ne 0) {
    throw "Standalone application build failed with exit code $LASTEXITCODE."
}

$versionLine = Select-String -Path "pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"$' |
    Select-Object -First 1
$version = $versionLine.Matches.Groups[1].Value
if (-not $version) {
    throw "Unable to read the project version from pyproject.toml."
}

$standaloneSource = Join-Path $projectRoot "dist\standalone\ScreenTranslator-Standalone.exe"
$standaloneRelease = Join-Path $projectRoot "dist\ScreenTranslator-Standalone-v$version.exe"
Copy-Item -LiteralPath $standaloneSource -Destination $standaloneRelease -Force

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $knownPaths = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $isccPath = $knownPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($isccPath) {
        $iscc = [pscustomobject]@{ Source = $isccPath }
    }
}
if (-not $iscc) {
    throw "Inno Setup 6 was not found. Install it before building the installer."
}

& $iscc.Source (Join-Path $projectRoot "packaging\ScreenTranslator.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
}

$portableDir = Join-Path $projectRoot "dist\portable"
New-Item -ItemType Directory -Force -Path $portableDir | Out-Null
$portablePath = Join-Path $portableDir "ScreenTranslator-Portable-v$version.zip"
Compress-Archive -Path (Join-Path $projectRoot "dist\ScreenTranslator") -DestinationPath $portablePath -CompressionLevel Optimal -Force

Write-Host "Installer: $projectRoot\dist\installer"
Write-Host "Portable:  $portablePath"
