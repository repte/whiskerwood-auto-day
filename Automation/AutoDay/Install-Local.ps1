param(
    [Parameter(Mandatory)][string]$PackageDirectory,
    [string]$EngineRoot = 'D:\WWEngine',
    [string]$ProjectRoot = '',
    [string]$ModsRoot = (Join-Path $env:LOCALAPPDATA 'Whiskerwood\Saved\mods')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-GameStopped {
    if (@(Get-Process -Name '*Whiskerwood*' -ErrorAction SilentlyContinue).Count) {
        throw 'Close Whiskerwood before installing AutoDay. The game will not be stopped automatically.'
    }
}

function Assert-NoAutoDayInstallation {
    if (Test-Path -LiteralPath (Join-Path $ModsRoot 'AutoDay')) {
        throw 'AutoDay already exists in the local mods directory. No files were replaced.'
    }
    if (Test-Path -LiteralPath $ModsRoot -PathType Container) {
        foreach ($file in Get-ChildItem -LiteralPath $ModsRoot -Recurse -File) {
            if ($file.Name -ieq 'AutoDay.pak' -or $file.Name -ieq 'AutoDay.uplugin') {
                throw "Duplicate AutoDay package: $($file.FullName)"
            }
            if ($file.Extension -ieq '.uplugin') {
                try { $other = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json }
                catch { continue }
                if ($other.PSObject.Properties['Name'] -and $other.Name -ieq 'AutoDay') {
                    throw "Duplicate AutoDay descriptor: $($file.FullName)"
                }
            }
        }
    }
}

Assert-GameStopped
$package = (Resolve-Path -LiteralPath $PackageDirectory).Path
$files = @(Get-ChildItem -LiteralPath $package -Force)
if ($files.Count -ne 2 -or @($files | Where-Object { $_.PSIsContainer -or $_.Name -cnotin @('AutoDay.pak', 'AutoDay.uplugin') }).Count) {
    throw 'The package directory must contain exactly AutoDay.pak and AutoDay.uplugin.'
}
$pak = Join-Path $package 'AutoDay.pak'
$descriptor = Join-Path $package 'AutoDay.uplugin'
$mod = Get-Content -LiteralPath $descriptor -Raw | ConvertFrom-Json
if ($mod.Name -cne 'AutoDay' -or $mod.Version -cne '0.1.0-preview' -or $mod.EngineVersion -cne '5.8' -or
        ($mod.PSObject.Properties['Modules'] -and $mod.Modules) -or
        ($mod.PSObject.Properties['Plugins'] -and $mod.Plugins)) {
    throw 'The AutoDay descriptor is invalid or requires a plugin/native module.'
}
$descriptorHash = (Get-FileHash -LiteralPath $descriptor -Algorithm SHA256).Hash
Assert-NoAutoDayInstallation
$verification = & (Join-Path $PSScriptRoot 'Test-Package.ps1') -PakPath $pak -EngineRoot $EngineRoot -ProjectRoot $ProjectRoot
Assert-GameStopped
Assert-NoAutoDayInstallation
$destination = Join-Path $ModsRoot 'AutoDay'
[void](New-Item -ItemType Directory -Path $destination)
Copy-Item -LiteralPath $pak -Destination (Join-Path $destination 'AutoDay.pak')
Copy-Item -LiteralPath $descriptor -Destination (Join-Path $destination 'AutoDay.uplugin')
if ((Get-FileHash -LiteralPath (Join-Path $destination 'AutoDay.pak') -Algorithm SHA256).Hash -cne $verification.SHA256 -or
        (Get-FileHash -LiteralPath (Join-Path $destination 'AutoDay.uplugin') -Algorithm SHA256).Hash -cne $descriptorHash) {
    throw "Installed copy hash mismatch; installation is incomplete: $destination"
}
Write-Output "AUTODAY_LOCAL_INSTALL_PASS: $destination"
Write-Output 'Whiskerwood was not started. AutoDay is enabled by default; disable it in the native mod settings when desired.'
