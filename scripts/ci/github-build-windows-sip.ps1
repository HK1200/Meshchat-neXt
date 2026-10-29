# Build and exercise the actual native SIP helper before freezing Windows packages.
$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'MSVC x64 toolchain is required' }
$developer = Join-Path $installation 'Common7/Tools/VsDevCmd.bat'
$environment = & cmd.exe /s /c "`"`"$developer`" -arch=x64 -host_arch=x64 >nul && set`""
if ($LASTEXITCODE -ne 0) { throw 'MSVC environment setup failed' }
foreach ($line in $environment) {
    if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
$cache = Join-Path $env:RUNNER_TEMP 'meshchatnext-sip-sources'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
$sources = @{
    're-4.12.0.tar.gz' = 'https://codeload.github.com/baresip/re/tar.gz/refs/tags/v4.12.0'
    'baresip-4.12.0.tar.gz' = 'https://codeload.github.com/baresip/baresip/tar.gz/refs/tags/v4.12.0'
    'opus-1.5.2.tar.gz' = 'https://downloads.xiph.org/releases/opus/opus-1.5.2.tar.gz'
    'mbedtls-3.6.7.tar.bz2' = 'https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.7/mbedtls-3.6.7.tar.bz2'
}
foreach ($name in $sources.Keys) {
    Invoke-WebRequest -Uri $sources[$name] -OutFile (Join-Path $cache $name)
}
# The builder checks all four pinned SHA256 values before extracting any archive.
uv run --frozen python scripts/build-windows-sip.py --source-cache $cache
if ($LASTEXITCODE -ne 0) { throw 'Native SIP helper build failed' }
uv run --frozen python scripts/windows/check-platform.py --sip-ipc-test
if ($LASTEXITCODE -ne 0) { throw 'Native SIP helper IPC check failed' }
uv run --frozen python -m pytest tests/backend/test_sip_desktop_engine.py tests/backend/test_sip_windows.py --basetemp=temp-tests/windows-sip-ci -q
if ($LASTEXITCODE -ne 0) { throw 'Native Windows SIP regression tests failed' }
