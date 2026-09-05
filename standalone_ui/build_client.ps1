$ErrorActionPreference = "Stop"
$BuildRoot = Join-Path $env:TEMP "airetopo_panel_build"
$DistRoot = Join-Path $PSScriptRoot "bin"

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name airetopo_panel `
    --distpath $DistRoot `
    --workpath (Join-Path $BuildRoot "work") `
    --specpath (Join-Path $BuildRoot "spec") `
    (Join-Path $PSScriptRoot "client.py")

$Client = Join-Path $DistRoot "airetopo_panel.exe"
if (-not (Test-Path -LiteralPath $Client)) {
    throw "Client build did not produce $Client"
}

$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Client).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $DistRoot "airetopo_panel.sha256") -Value "$Hash  airetopo_panel.exe"

$LicenseRoot = Join-Path $DistRoot "licenses"
New-Item -ItemType Directory -Force -Path $LicenseRoot | Out-Null
$PythonRoot = python -c "import sys; print(sys.base_prefix)"
$TclRoot = python -c "import tkinter, pathlib; print(pathlib.Path(tkinter.Tcl().eval('info library')).parent)"
Copy-Item -LiteralPath (Join-Path $PythonRoot "LICENSE.txt") -Destination (Join-Path $LicenseRoot "PYTHON_LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $TclRoot "tk8.6\license.terms") -Destination (Join-Path $LicenseRoot "TCL_TK_LICENSE.txt") -Force
Write-Host "Built $Client"
Write-Host "SHA256 $Hash"
