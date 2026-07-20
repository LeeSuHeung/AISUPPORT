[CmdletBinding()]
param(
    [string]$Target,
    [switch]$Verify,
    [switch]$DryRun,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCommand) {
    throw 'Node.js 18 or newer is required: https://nodejs.org/'
}

$nodeMajor = [int](& $nodeCommand.Source -p "process.versions.node.split('.')[0]")
if ($LASTEXITCODE -ne 0 -or $nodeMajor -lt 18) {
    throw "Node.js 18 or newer is required. Found major version $nodeMajor."
}

$installerPath = Join-Path $PSScriptRoot 'install-caveman.mjs'
$installerArguments = @($installerPath)

if ($Target) {
    $installerArguments += @('--target', $Target)
}
if ($Verify) {
    $installerArguments += '--verify'
}
if ($DryRun) {
    $installerArguments += '--dry-run'
}
if ($Force) {
    $installerArguments += '--force'
}

& $nodeCommand.Source @installerArguments
exit $LASTEXITCODE
