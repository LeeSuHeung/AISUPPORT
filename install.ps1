[CmdletBinding()]
param(
    [string]$Target,
    [string]$AgentsFile,
    [switch]$Verify,
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'scripts\install-aisupport.ps1'
& $installer @PSBoundParameters
exit $LASTEXITCODE
