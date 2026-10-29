# Dot-source before dependency installs, builds or tests in the Windows SSD export.
$ErrorActionPreference = 'Stop'
$NextSourceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$NextHandoffRoot = Split-Path $NextSourceRoot -Parent
if (-not (Test-Path (Join-Path $NextHandoffRoot 'WINDOWS-LOCAL-TEST.txt'))) {
    throw 'Use the Windows-readable Shared SSD handoff folder.'
}
$NextCacheRoot = Join-Path $NextHandoffRoot 'windows-caches'
$env:TEMP = Join-Path $NextCacheRoot 'tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:UV_PYTHON_INSTALL_DIR = Join-Path $NextCacheRoot 'python'
$env:COREPACK_HOME = Join-Path $NextCacheRoot 'corepack'
$env:npm_config_cache = Join-Path $NextCacheRoot 'npm'
$env:UV_CACHE_DIR = Join-Path $NextCacheRoot 'uv'
$env:PIP_CACHE_DIR = Join-Path $NextCacheRoot 'pip'
$env:npm_config_store_dir = Join-Path $NextCacheRoot 'pnpm'
$env:ELECTRON_CACHE = Join-Path $NextCacheRoot 'electron'
$env:ELECTRON_BUILDER_CACHE = Join-Path $NextCacheRoot 'electron-builder'
@($env:UV_PYTHON_INSTALL_DIR, $env:COREPACK_HOME, $env:npm_config_cache, $env:TEMP, $env:UV_CACHE_DIR, $env:PIP_CACHE_DIR, $env:npm_config_store_dir, $env:ELECTRON_CACHE, $env:ELECTRON_BUILDER_CACHE) | ForEach-Object { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
Write-Host "Local source: $NextSourceRoot"
Write-Host "Build caches: $NextCacheRoot"
