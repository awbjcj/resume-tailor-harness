[CmdletBinding()]
param(
    [switch]$WithH1B,
    [switch]$Detach,
    [switch]$Stop,
    [switch]$Status,
    [switch]$NoBuild,
    [int]$Port = 0
)

$ErrorActionPreference = 'Stop'

function Invoke-Docker {
    param([Parameter(Mandatory)][string[]]$CommandArgs)

    & docker @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Docker command failed: docker $($CommandArgs -join ' ')"
    }
}

function Assert-DockerDesktop {
    if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker Desktop is required. Install and start it, then rerun this command.'
    }

    try {
        Invoke-Docker -CommandArgs @('version', '--format', '{{.Server.Version}}')
        Invoke-Docker -CommandArgs @('compose', 'version')
    }
    catch {
        throw 'Docker Desktop is installed but its Linux container engine is not ready. Start Docker Desktop, wait until it reports running, then retry.'
    }
}

function Initialize-H1BService {
    param([Parameter(Mandatory)][string]$RepositoryRoot)

    $serviceDirectory = Join-Path $RepositoryRoot 'services/h1b-job-search-mcp'
    if (Test-Path -LiteralPath (Join-Path $serviceDirectory 'Dockerfile')) {
        return
    }

    if ($null -eq (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'The optional H-1B service has not been initialized. Install Git for Windows, then run: git submodule update --init --recursive'
    }

    if (-not (Test-Path -LiteralPath (Join-Path $RepositoryRoot '.git'))) {
        throw 'The optional H-1B service is a Git submodule. Clone this repository with --recurse-submodules, or run the script from a Git checkout and retry.'
    }

    & git -C $RepositoryRoot submodule update --init --recursive -- services/h1b-job-search-mcp
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not initialize the optional H-1B service submodule.'
    }

    if (-not (Test-Path -LiteralPath (Join-Path $serviceDirectory 'Dockerfile'))) {
        throw 'The optional H-1B service was not initialized successfully.'
    }
}

function Get-LocalPort {
    param(
        [Parameter(Mandatory)][string]$EnvFile,
        [Parameter(Mandatory)][int]$CommandLinePort
    )

    if ($CommandLinePort -ne 0) {
        return $CommandLinePort
    }

    if (Test-Path -LiteralPath $EnvFile) {
        foreach ($line in Get-Content -LiteralPath $EnvFile) {
            if ($line -match '^\s*RESUME_TAILOR_HARNESS_PORT\s*=\s*([0-9]+)\s*$') {
                $configuredPort = [int]$Matches[1]
                if ($configuredPort -ge 1 -and $configuredPort -le 65535) {
                    return $configuredPort
                }
            }
        }
    }

    return 8000
}

if ($Stop -and $Status) {
    throw 'Choose either -Stop or -Status, not both.'
}

if ($Port -ne 0 -and ($Port -lt 1 -or $Port -gt 65535)) {
    throw '-Port must be between 1 and 65535.'
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$envFile = Join-Path $repositoryRoot '.env'
$templateFile = Join-Path $repositoryRoot '.env.example'
$hadPortOverride = Test-Path Env:RESUME_TAILOR_HARNESS_PORT
$previousPortOverride = $env:RESUME_TAILOR_HARNESS_PORT

try {
    Assert-DockerDesktop

    if ($WithH1B -and -not $Stop -and -not $Status) {
        Initialize-H1BService -RepositoryRoot $repositoryRoot
    }

    if (-not $Stop -and -not $Status -and -not (Test-Path -LiteralPath $envFile)) {
        Copy-Item -LiteralPath $templateFile -Destination $envFile
        Write-Host "Created $envFile. Add an LLM provider key there or configure one in the app after it starts."
    }

    if ($Port -ne 0) {
        $env:RESUME_TAILOR_HARNESS_PORT = [string]$Port
    }

    Set-Location -LiteralPath $repositoryRoot
    $composeArgs = @('compose', '-f', 'compose.yaml')
    if ($WithH1B) {
        $composeArgs += @('-f', 'compose.h1b.yaml', '--profile', 'h1b')
    }

    if ($Stop) {
        Invoke-Docker -CommandArgs ($composeArgs + 'down')
        return
    }

    if ($Status) {
        Invoke-Docker -CommandArgs ($composeArgs + 'ps')
        return
    }

    $composeArgs += 'up'
    if (-not $NoBuild) {
        $composeArgs += '--build'
    }
    if ($Detach) {
        $composeArgs += '--detach'
    }
    Invoke-Docker -CommandArgs $composeArgs

    if ($Detach) {
        $localPort = Get-LocalPort -EnvFile $envFile -CommandLinePort $Port
        Write-Host "Résumé Tailor Harness is starting at http://localhost:$localPort. Use -Status to inspect it or -Stop to stop it; data volumes are retained."
    }
}
finally {
    if ($hadPortOverride) {
        $env:RESUME_TAILOR_HARNESS_PORT = $previousPortOverride
    }
    else {
        Remove-Item Env:RESUME_TAILOR_HARNESS_PORT -ErrorAction SilentlyContinue
    }
}
