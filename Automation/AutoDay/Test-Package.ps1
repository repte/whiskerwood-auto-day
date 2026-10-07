param(
    [Parameter(Mandatory)][string]$PakPath,
    [string]$EngineRoot = 'D:\WWEngine',
    [string]$ProjectRoot = '',
    [string]$LogDirectory = ''
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
$pak = (Resolve-Path -LiteralPath $PakPath).Path
$unrealPak = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealPak.exe'
if (-not (Test-Path -LiteralPath $unrealPak -PathType Leaf)) { throw "UnrealPak missing: $unrealPak" }
$expected = @('BP_MapLoad', 'BP_MainMenuLoad')
if (-not $LogDirectory) { $LogDirectory = Join-Path $ProjectRoot 'Saved\Logs' }
[void](New-Item -ItemType Directory -Path $LogDirectory -Force)
$id = [guid]::NewGuid().ToString('N')
$csv = Join-Path $LogDirectory "AutoDay-Pak-$id.csv"
$listLog = Join-Path $LogDirectory "AutoDay-Pak-$id-list.log"
$integrityLog = Join-Path $LogDirectory "AutoDay-Pak-$id-integrity.log"
$errorPattern = '(?im)\b(?:Error|Fatal):|Assertion failed:|Fatal error:'

& $unrealPak $pak -List -ExtractToMountPoint ("-CSV=$csv") -unattended *> $listLog
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $csv -PathType Leaf) -or
        (Get-Content -LiteralPath $listLog -Raw) -match $errorPattern) {
    throw "AutoDay pak listing failed: $listLog"
}
$lines = @(Get-Content -LiteralPath $csv)
if ($lines.Count -lt 2 -or ($lines[0] -replace '\s', '') -cne 'Filename,Offset,Size,Hash,Deleted,Compressed,CompressionMethod') {
    throw "Empty or unsupported UnrealPak inventory: $csv"
}
$entries = @($lines | Select-Object -Skip 1 | ConvertFrom-Csv -Header Filename,Offset,Size,Hash,Deleted,Compressed,CompressionMethod)
$seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$assets = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($entry in $entries) {
    $path = [string]$entry.Filename
    if ($path -cnotmatch '^\.\./\.\./\.\./Whiskerwood/Content/Mods/AutoDay/([A-Za-z0-9_]+)\.(uasset|uexp|ubulk|uptnl)$') {
        throw "File outside the AutoDay runtime boundary: $path"
    }
    $name, $extension = $Matches[1], $Matches[2]
    if ($name -cnotin $expected) { throw "Unexpected AutoDay asset: $path" }
    if (-not $seen.Add($path)) { throw "Duplicate AutoDay entry: $path" }
    $size = 0L
    if (-not [long]::TryParse(([string]$entry.Size).Trim(), [ref]$size) -or $size -le 0 -or
            ([string]$entry.Deleted).Trim() -cne 'false') {
        throw "Invalid AutoDay pak entry: $path"
    }
    if ($extension -ceq 'uasset') { [void]$assets.Add($name) }
}
foreach ($name in $expected) {
    if (-not $assets.Contains($name)) { throw "Missing cooked AutoDay asset: $name" }
}

& $unrealPak $pak -Verify -unattended *> $integrityLog
if ($LASTEXITCODE -ne 0) { throw "AutoDay pak integrity failed: $integrityLog" }
$integrity = Get-Content -LiteralPath $integrityLog -Raw
if ($integrity -notmatch 'Pak file .* healthy' -or $integrity -match $errorPattern) {
    throw "AutoDay pak integrity not confirmed: $integrityLog"
}
[pscustomobject]@{
    Result = 'AUTODAY_PACKAGE_TESTS_PASS'
    Pak = $pak
    Assets = $expected.Count
    Entries = $entries.Count
    Bytes = (Get-Item -LiteralPath $pak).Length
    SHA256 = (Get-FileHash -LiteralPath $pak -Algorithm SHA256).Hash
    Inventory = $csv
    ListLog = $listLog
    IntegrityLog = $integrityLog
}
