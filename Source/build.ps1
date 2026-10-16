$ErrorActionPreference = 'Stop'
$sourceRoot = $PSScriptRoot
$buildPython = Join-Path $sourceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    throw 'Please create the project .venv first. See README.md.'
}

& $buildPython -m pip install -r (Join-Path $sourceRoot 'requirements-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }
& $buildPython (Join-Path $sourceRoot 'packaging\create_icon.py')
if ($LASTEXITCODE -ne 0) { throw 'Application icon generation failed.' }
# Dependency discovery must not pick up unrelated ICU / Windows runtime DLLs
# from image, PDF, or developer tools that happen to be on the caller's PATH.
$originalBuildPath = $env:PATH
try {
    $env:PATH = @(
        (Split-Path -Parent $buildPython),
        (Join-Path $env:SystemRoot 'System32'),
        $env:SystemRoot
    ) -join ';'
    & $buildPython -m PyInstaller --noconfirm --clean `
        --distpath (Join-Path (Split-Path -Parent $sourceRoot) 'Exe') `
        --workpath (Join-Path $sourceRoot 'build') `
        (Join-Path $sourceRoot 'packaging\ComponentDesk.spec')
    if ($LASTEXITCODE -ne 0) { throw 'Executable packaging failed.' }
} finally {
    $env:PATH = $originalBuildPath
}

Write-Host 'Build complete. The executable is in the Exe folder next to Source.'
