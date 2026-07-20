param(
    [string]$HomePath = [Environment]::GetFolderPath("UserProfile")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$sourceRoot = Join-Path $PSScriptRoot "bundle"
$agentDestination = Join-Path $HomePath ".codex\agents"
$skillDestination = Join-Path $HomePath ".agents\skills\gupabal-game"
$hooksConfiguration = Join-Path $HomePath ".codex\hooks.json"
$globalInstructions = Join-Path $HomePath ".codex\AGENTS.md"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

$pythonLauncher = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonLauncher = @("py", "-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonLauncher = @("python")
} else {
    throw "Python 3.10 or newer is required to install and run the Gupabal game Hooks."
}

$versionCheck = @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)")
if ($pythonLauncher.Count -eq 2) {
    & $pythonLauncher[0] $pythonLauncher[1] @versionCheck
} else {
    & $pythonLauncher[0] @versionCheck
}
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.10 or newer is required to install and run the Gupabal game Hooks."
}

function Install-ManagedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $destinationDirectory = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $destinationDirectory | Out-Null

    if (Test-Path -LiteralPath $Destination) {
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash
        $destinationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash
        if ($sourceHash -eq $destinationHash) {
            Write-Host "Unchanged: $Destination"
            return
        }

        Copy-Item -LiteralPath $Destination -Destination "$Destination.backup-$timestamp"
    }

    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    Write-Host "Installed: $Destination"
}

function Remove-LegacyManagedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }

    Copy-Item -LiteralPath $Path -Destination "$Path.backup-$timestamp"
    Remove-Item -LiteralPath $Path -Force
    Write-Host "Removed legacy name: $Path"
}

$agentFiles = @(
    "gupabal_planner.toml",
    "gupabal_art_designer.toml",
    "gupabal_client.toml",
    "gupabal_server.toml"
)

foreach ($fileName in $agentFiles) {
    Install-ManagedFile `
        -Source (Join-Path $sourceRoot "agents\$fileName") `
        -Destination (Join-Path $agentDestination $fileName)
}

Install-ManagedFile `
    -Source (Join-Path $sourceRoot "skills\gupabal-game\SKILL.md") `
    -Destination (Join-Path $skillDestination "SKILL.md")

Install-ManagedFile `
    -Source (Join-Path $sourceRoot "skills\gupabal-game\agents\openai.yaml") `
    -Destination (Join-Path $skillDestination "agents\openai.yaml")

Install-ManagedFile `
    -Source (Join-Path $sourceRoot "skills\gupabal-game\references\decision-template.json") `
    -Destination (Join-Path $skillDestination "references\decision-template.json")

Install-ManagedFile `
    -Source (Join-Path $sourceRoot "skills\gupabal-game\references\decision-policy.md") `
    -Destination (Join-Path $skillDestination "references\decision-policy.md")

$mergeArguments = @(
    (Join-Path $sourceRoot "hooks\merge_hooks.py"),
    "--source", (Join-Path $sourceRoot "hooks\hooks.json"),
    "--hook-script-source", (Join-Path $sourceRoot "hooks\gupabal_hooks.py"),
    "--target", $hooksConfiguration,
    "--backup-suffix", $timestamp
)
if ($pythonLauncher.Count -eq 2) {
    & $pythonLauncher[0] $pythonLauncher[1] @mergeArguments
} else {
    & $pythonLauncher[0] @mergeArguments
}
if ($LASTEXITCODE -ne 0) {
    throw "Could not merge the Gupabal game Hooks into $hooksConfiguration"
}

$legacyAgentFiles = @(
    "game_planner.toml",
    "game_art_designer.toml",
    "game_client.toml",
    "game_server.toml"
)

foreach ($fileName in $legacyAgentFiles) {
    Remove-LegacyManagedFile -Path (Join-Path $agentDestination $fileName)
}

$legacySkillDestination = Join-Path $HomePath ".agents\skills\coordinate-game-feature-team"
Remove-LegacyManagedFile -Path (Join-Path $legacySkillDestination "SKILL.md")
Remove-LegacyManagedFile -Path (Join-Path $legacySkillDestination "agents\openai.yaml")

$startMarker = "<!-- BEGIN CODEX GAME TEAM -->"
$endMarker = "<!-- END CODEX GAME TEAM -->"
$managedInstructions = Get-Content -Raw -Encoding UTF8 (Join-Path $sourceRoot "AGENTS.md")
$managedBlock = "$startMarker`r`n$($managedInstructions.Trim())`r`n$endMarker"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $globalInstructions) | Out-Null
$existingInstructions = if (Test-Path -LiteralPath $globalInstructions) {
    Get-Content -Raw -Encoding UTF8 $globalInstructions
} else {
    ""
}

$blockPattern = [regex]::Escape($startMarker) + "[\s\S]*?" + [regex]::Escape($endMarker)
$baseInstructions = [regex]::Replace($existingInstructions, $blockPattern, "").Trim()
$legacyInstructions = $managedInstructions.Trim()
$baseInstructions = $baseInstructions.Replace($legacyInstructions, "").Trim()

if ([string]::IsNullOrWhiteSpace($baseInstructions)) {
    $updatedInstructions = "$managedBlock`r`n"
} else {
    $updatedInstructions = "$baseInstructions`r`n`r`n$managedBlock`r`n"
}

if ($updatedInstructions -ne $existingInstructions) {
    if (Test-Path -LiteralPath $globalInstructions) {
        Copy-Item -LiteralPath $globalInstructions -Destination "$globalInstructions.backup-$timestamp"
    }
    [System.IO.File]::WriteAllText(
        $globalInstructions,
        $updatedInstructions,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Updated: $globalInstructions"
} else {
    Write-Host "Unchanged: $globalInstructions"
}

Write-Host "Installation complete. Review the command Hooks in /hooks, then start a new Codex task."
