[CmdletBinding()]
param(
    [string]$Target,
    [string]$AgentsFile,
    [switch]$Verify,
    [switch]$DryRun,
    [switch]$Force,
    [switch]$WithHooks,
    [switch]$WithTelegram
)

$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'scripts\install-aisupport.ps1'
$PSBoundParameters['WithTelegram'] = $true
$PSBoundParameters['ConfigureTelegram'] = $true
& $installer @PSBoundParameters
exit $LASTEXITCODE
