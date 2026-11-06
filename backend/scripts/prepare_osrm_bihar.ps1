<#
.SYNOPSIS
    Dukaanly: Bihar OpenStreetMap (OSRM) Data Preparation Script (Windows PowerShell)

.DESCRIPTION
    Downloads the Bihar OSM road extract from Geofabrik and preprocesses it
    for Multi-Level Dijkstra (MLD) routing using the pinned OSRM backend container.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File backend\scripts\prepare_osrm_bihar.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$DataDir = Join-Path $RepoRoot "deploy\osrm\data"
$OsrmImage = "ghcr.io/project-osrm/osrm-backend:v5.27.1"
$PbfUrl = "https://download.geofabrik.de/asia/india/bihar-latest.osm.pbf"
$PbfFile = Join-Path $DataDir "bihar-latest.osm.pbf"
$OsrmBase = Join-Path $DataDir "bihar-latest.osrm"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "Dukaanly: Preparing Bihar Road Network for OSRM" -ForegroundColor Cyan
Write-Host "Target Directory: $DataDir" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}

# 1. Download PBF if not present
if (Test-Path $PbfFile) {
    $sizeMb = [Math]::Round((Get-Item $PbfFile).Length / 1MB, 2)
    Write-Host "==> Found existing OSM extract: $PbfFile ($sizeMb MB)" -ForegroundColor Green
} else {
    Write-Host "==> Downloading Bihar extract from Geofabrik (~65MB)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $PbfUrl -OutFile $PbfFile -UseBasicParsing
    Write-Host "==> Download complete." -ForegroundColor Green
}

# 2. Check Docker availability
try {
    docker info | Out-Null
} catch {
    Write-Error "Docker daemon is not running or accessible. Please start Docker Desktop."
    exit 1
}

# 3. Pull OSRM image
Write-Host "==> Pulling OSRM backend image ($OsrmImage)..." -ForegroundColor Yellow
docker pull $OsrmImage

# Convert Windows path to Docker volume mount format (forward slashes)
$DockerMount = ($DataDir -replace '\\', '/').TrimEnd('/')

# 4. Extract road network graph
Write-Host "==> Step 1/3: Extracting road network (osrm-extract)..." -ForegroundColor Yellow
docker run --rm -t -v "${DockerMount}:/data" $OsrmImage osrm-extract -p /opt/car.lua /data/bihar-latest.osm.pbf
if ($LASTEXITCODE -ne 0) { throw "osrm-extract failed with exit code $LASTEXITCODE" }

# 5. Partition road graph
Write-Host "==> Step 2/3: Partitioning road graph (osrm-partition)..." -ForegroundColor Yellow
docker run --rm -t -v "${DockerMount}:/data" $OsrmImage osrm-partition /data/bihar-latest.osrm
if ($LASTEXITCODE -ne 0) { throw "osrm-partition failed with exit code $LASTEXITCODE" }

# 6. Customize routing metrics
Write-Host "==> Step 3/3: Customizing routing metrics (osrm-customize)..." -ForegroundColor Yellow
docker run --rm -t -v "${DockerMount}:/data" $OsrmImage osrm-customize /data/bihar-latest.osrm
if ($LASTEXITCODE -ne 0) { throw "osrm-customize failed with exit code $LASTEXITCODE" }

# 7. Verification
$RequiredExtensions = @("", ".cells", ".partition", ".mldgr", ".ebg", ".names")
$AllPresent = $true
foreach ($ext in $RequiredExtensions) {
    $targetFile = "$OsrmBase$ext"
    if (-not (Test-Path $targetFile)) {
        Write-Warning "Missing expected artifact: $targetFile"
        $AllPresent = $false
    }
}

if ($AllPresent) {
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host "SUCCESS: Bihar OSRM routing data prepared successfully!" -ForegroundColor Green
    Write-Host "To launch the local OSRM routing container:" -ForegroundColor Green
    Write-Host "    docker compose up -d osrm" -ForegroundColor Green
    Write-Host "Healthcheck probe:" -ForegroundColor Green
    Write-Host "    curl http://127.0.0.1:5000/nearest/v1/driving/85.1158,25.6144" -ForegroundColor Green
    Write-Host "==================================================================" -ForegroundColor Green
} else {
    Write-Error "One or more routing artifacts failed to build."
    exit 1
}
