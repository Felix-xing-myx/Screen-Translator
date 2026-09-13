param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $BundleRoot -PathType Container)) {
    throw "PyInstaller bundle directory was not found: $BundleRoot"
}

$requiredFiles = @(
    'ScreenTranslator.exe',
    '_internal\python3.dll',
    '_internal\PySide6\Qt6Core.dll',
    '_internal\PySide6\pyside6.abi3.dll',
    '_internal\shiboken6\shiboken6.abi3.dll',
    '_internal\icuuc.dll',
    '_internal\VCRUNTIME140.dll',
    '_internal\VCRUNTIME140_1.dll'
)

$missingFiles = @(
    $requiredFiles |
        Where-Object { -not (Test-Path -LiteralPath (Join-Path $BundleRoot $_) -PathType Leaf) }
)
if ($missingFiles.Count -gt 0) {
    throw "PyInstaller bundle is missing required files: $($missingFiles -join ', ')"
}

$icuData = Get-ChildItem -LiteralPath (Join-Path $BundleRoot '_internal') -File -Filter 'icudt*.dll'
if ($icuData.Count -eq 0) {
    throw 'PyInstaller bundle is missing the ICU data DLL (icudt*.dll).'
}

Write-Host "Bundle verification passed: $BundleRoot"
