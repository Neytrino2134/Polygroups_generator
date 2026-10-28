# Rebuilds lib\meshoptimizer.dll used by UV Preserve Decimate (core\meshopt_simplify.py).
# Usage: scripts\build_meshoptimizer.ps1 [-Version 1.3] [-VcVars C:\BuildTools2022\VC\Auxiliary\Build\vcvars64.bat]
param(
    [string]$Version = '1.3',
    [string]$VcVars = 'C:\BuildTools2022\VC\Auxiliary\Build\vcvars64.bat'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$work = Join-Path ([System.IO.Path]::GetTempPath()) "meshoptimizer-$Version-build"
New-Item -ItemType Directory -Force $work | Out-Null
$zip = Join-Path $work "v$Version.zip"
Invoke-WebRequest "https://github.com/zeux/meshoptimizer/archive/refs/tags/v$Version.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath $work -Force
$source = Join-Path $work "meshoptimizer-$Version"
# /MT links the C runtime statically, so the DLL has no extra runtime dependencies.
cmd /c "`"$VcVars`" >nul && cd /d `"$work`" && cl /nologo /O2 /EHsc /MT /LD /DMESHOPTIMIZER_API=__declspec(dllexport) `"$source\src\*.cpp`" /Fe:meshoptimizer.dll"
if ($LASTEXITCODE -ne 0) { throw "meshoptimizer build failed" }
Copy-Item (Join-Path $work 'meshoptimizer.dll') (Join-Path $root 'lib\meshoptimizer.dll') -Force
Copy-Item (Join-Path $source 'LICENSE.md') (Join-Path $root 'lib\meshoptimizer_LICENSE.md') -Force
Write-Host "lib\meshoptimizer.dll rebuilt from meshoptimizer v$Version"
