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

$privateIcuFiles = Get-ChildItem -LiteralPath (Join-Path $BundleRoot '_internal') -Recurse -File |
    Where-Object { $_.Name -match '^icu.*\.dll$' }
if ($privateIcuFiles.Count -gt 0) {
    $paths = $privateIcuFiles | ForEach-Object { $_.FullName }
    throw "PyInstaller bundle contains incompatible private ICU DLLs; remove them so Qt uses Windows ICU: $($paths -join ', ')"
}

Write-Host "Bundle verification passed: $BundleRoot"
