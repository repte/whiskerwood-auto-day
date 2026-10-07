param(
    [string]$EngineRoot = 'D:\WWEngine',
    [string]$ProjectRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $ProjectRoot) {
    $ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'Whiskerwood.uproject'))) {
        $ProjectRoot = Join-Path (Split-Path $ProjectRoot -Parent) 'Modkit'
    }
}
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor-Cmd.exe'
$uat = Join-Path $EngineRoot 'Engine\Build\BatchFiles\RunUAT.bat'
$project = Join-Path $ProjectRoot 'Whiskerwood.uproject'
$metadataPath = Join-Path $ProjectRoot 'Saved\AutoDay-PackageSetup.json'
$descriptor = Join-Path $ProjectRoot 'Content\Mods\AutoDay\AutoDay.uplugin'
foreach ($required in @($editor, $uat, $project, $descriptor,
        (Join-Path $PSScriptRoot 'prepare_package.py'), (Join-Path $PSScriptRoot 'test_all.py'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required file missing: $required" }
}
$mod = Get-Content -LiteralPath $descriptor -Raw | ConvertFrom-Json
if ($mod.Version -cne '0.1.0-preview') { throw 'Unexpected AutoDay descriptor version' }

$id = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$output = Join-Path $ProjectRoot "Saved\AutoDayBuilds\$id"
$logs = Join-Path $output 'Logs'
[void](New-Item -ItemType Directory -Path $logs -Force)
$errorPattern = '(?im)\b(?:Error|Fatal):|\bBUILD FAILED\b|Traceback \(most recent call last\):|Assertion failed:|Fatal error:|AutomationTool exiting with ExitCode=[1-9]'

function Invoke-AutoDayEditorScript {
    param([string]$Script, [string]$Marker)
    $log = Join-Path $logs "$Script.log"
    $console = Join-Path $logs "$Script-console.log"
    & $editor $project ("-ExecutePythonScript=" + (Join-Path $PSScriptRoot $Script)) `
        -unattended -nullrhi -nosound -culture=en ("-abslog=$log") -stdout -FullStdOutLogOutput *> $console
    if ($LASTEXITCODE -ne 0) { throw "AutoDay editor step failed: $console" }
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "Editor log missing: $log" }
    $text = (Get-Content -LiteralPath $log -Raw) + "`n" + (Get-Content -LiteralPath $console -Raw)
    if ($text -match $errorPattern -or $text -notmatch ([regex]::Escape($Marker))) {
        throw "AutoDay editor step not verified: $log"
    }
}

$setupStarted = [DateTime]::UtcNow
Invoke-AutoDayEditorScript -Script 'prepare_package.py' -Marker 'AUTODAY_PACKAGE_SETUP_PASS'
if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf) -or
        (Get-Item -LiteralPath $metadataPath).LastWriteTimeUtc -lt $setupStarted) {
    throw "Fresh AutoDay package metadata missing: $metadataPath"
}
$setup = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$chunk = 0
if ($setup.mod -cne 'AutoDay' -or -not [int]::TryParse([string]$setup.chunk, [ref]$chunk) -or
        $chunk -lt 1 -or $chunk -gt 300) { throw 'Invalid AutoDay chunk metadata' }
Copy-Item -LiteralPath $metadataPath -Destination (Join-Path $output 'AutoDay-PackageSetup.json')
Invoke-AutoDayEditorScript -Script 'test_all.py' -Marker 'AUTODAY_TESTS_PASS'

$cookLog = Join-Path $logs 'BuildCookRun.log'
# A full cook avoids carrying stale Blueprint data into this standalone package.
& $uat BuildCookRun ("-project=$project") -platform=Win64 -clientconfig=Shipping `
    -build -cook -stage -pak -archive ("-archivedirectory=$output") `
    -nocompileeditor -installed -nop4 -utf8output -unattended -WaitForUATMutex *> $cookLog
if ($LASTEXITCODE -ne 0) { throw "AutoDay cook/package failed: $cookLog" }
$cookText = Get-Content -LiteralPath $cookLog -Raw
if ($cookText -notmatch 'BUILD SUCCESSFUL' -or $cookText -match $errorPattern) {
    throw "AutoDay cook/package not verified: $cookLog"
}
$chunkPak = Join-Path $output "Windows\Whiskerwood\Content\Paks\pakchunk$chunk-Windows.pak"
$verification = & (Join-Path $PSScriptRoot 'Test-Package.ps1') -PakPath $chunkPak `
    -EngineRoot $EngineRoot -ProjectRoot $ProjectRoot -LogDirectory $logs
$deliveryRoot = Join-Path $output 'Delivery'
$modDirectory = Join-Path $deliveryRoot 'AutoDay'
[void](New-Item -ItemType Directory -Path $modDirectory)
$deliveryPak = Join-Path $modDirectory 'AutoDay.pak'
Copy-Item -LiteralPath $chunkPak -Destination $deliveryPak
Copy-Item -LiteralPath $descriptor -Destination (Join-Path $modDirectory 'AutoDay.uplugin')
if ((Get-FileHash -LiteralPath $deliveryPak -Algorithm SHA256).Hash -cne $verification.SHA256) {
    throw 'AutoDay delivery copy hash mismatch'
}
$verification | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $output 'package-verification.json') -Encoding utf8
Write-Output "AUTODAY_BUILD_PASS: $modDirectory"
Write-Output 'Preview package only. Gameplay validation remains manual; nothing was installed or published.'
