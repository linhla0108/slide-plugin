[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    throw "Python 3.10+ was not found. Install it from https://www.python.org/downloads/ and rerun this script."
}

function Test-PythonModules {
    param([string]$Python)
    & $Python -c "import pptx, PIL, fitz" 2>$null
    return $LASTEXITCODE -eq 0
}

if ($Check) {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "Project virtualenv is missing at .venv\Scripts\python.exe. Run this script without -Check to create it."
    }
    if (-not (Test-PythonModules $VenvPython)) {
        throw "Project virtualenv is incomplete. Run this script without -Check to install python-pptx, Pillow, and PyMuPDF."
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js 18+ was not found. Install the LTS release from https://nodejs.org and rerun this script."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot "node_modules\playwright") -PathType Container)) {
        throw "Playwright is missing. Run this script without -Check to install the existing project requirements."
    }
    Write-Output "SUN.RISER setup check passed: $VenvPython"
    exit 0
}

$PythonCommand = Find-Python
$PythonExe = $PythonCommand[0]
$PythonArgs = @($PythonCommand | Select-Object -Skip 1)
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 18+ was not found. Install the LTS release from https://nodejs.org and rerun this script."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found with Node.js. Repair the Node.js LTS installation and rerun this script."
}

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    & $PythonExe @PythonArgs -m venv (Join-Path $RepoRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv. Verify that Python includes the venv module."
    }
}

if (-not (Test-PythonModules $VenvPython)) {
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to update pip in the project virtualenv." }
    & $VenvPython -m pip install python-pptx Pillow PyMuPDF
    if ($LASTEXITCODE -ne 0) { throw "Failed to install the existing Python requirements." }
}

if (-not (Test-Path -LiteralPath (Join-Path $RepoRoot "node_modules\playwright") -PathType Container)) {
    & npm install --prefix $RepoRoot
    if ($LASTEXITCODE -ne 0) { throw "Failed to install the existing npm requirements." }
}

& npx --prefix $RepoRoot playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Failed to install Playwright Chromium." }

Write-Output "SUN.RISER setup complete. Project Python: $VenvPython"
