[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$Version,
 [Parameter(Mandatory=$true)][string]$Zip,
 [Parameter(Mandatory=$true)][string]$ProgramRoot,
 [string]$Config = (Join-Path $PSScriptRoot 'release-config.json'),
 [string]$ZipUrl,
 [string[]]$Notes = @()
)
$ErrorActionPreference = 'Stop'
$Python = Join-Path $ProgramRoot 'tools\python\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'KIO portable program folder is required (-ProgramRoot).' }
$Publisher = Join-Path $PSScriptRoot 'publish_windows.py'
$Arguments = @('-I','-B',$Publisher,'--config',$Config,'--version',$Version,'--zip',$Zip)
if ($ZipUrl) { $Arguments += @('--url',$ZipUrl) }
foreach ($Note in $Notes) { $Arguments += @('--note',$Note) }
# Password is entered directly into Python getpass; never passed on argv or saved.
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Release not completed. Read the error; the previous feed is preserved or restored.' }
