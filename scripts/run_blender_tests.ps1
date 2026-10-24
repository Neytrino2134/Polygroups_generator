# Run addon regression tests with the Blender 5.2 build from Blender Launcher.
# Usage: scripts\run_blender_tests.ps1 [-Suite initial|ui-bake|queue-cutter] [-Tests a.py b.py]
param(
    [string]$Suite = 'ui-bake',
    [string[]]$Tests,
    [string]$BlenderDir = 'D:\Blender Library\Blender\daily\blender-5.2.0-stable+v52.fbe6228777e7-windows.amd64-release'
)
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $BlenderDir '5.2\python\bin\python.exe'
$arguments = @('-I', (Join-Path $root 'scripts\validate_refactor_blender.py'), (Join-Path $BlenderDir 'blender.exe'))
if ($Tests) { $arguments += '--tests'; $arguments += $Tests } else { $arguments += '--suite'; $arguments += $Suite }
& $python @arguments
exit $LASTEXITCODE
