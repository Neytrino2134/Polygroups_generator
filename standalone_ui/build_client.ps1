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
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

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
$PythonLicense = Join-Path $LicenseRoot "PYTHON_LICENSE.txt"
$LicenseLines = [IO.File]::ReadAllLines($PythonLicense) | ForEach-Object { $_.TrimEnd() }
while ($LicenseLines.Count -gt 1 -and $LicenseLines[-1] -eq "") {
    $LicenseLines = $LicenseLines[0..($LicenseLines.Count - 2)]
}
[IO.File]::WriteAllText($PythonLicense, ([string]::Join("`n", $LicenseLines) + "`n"), [Text.UTF8Encoding]::new($false))
Write-Host "Built $Client"
Write-Host "SHA256 $Hash"
