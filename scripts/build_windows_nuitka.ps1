# Run on Windows with Python 3.12+ in PATH. Produces dist\converter.exe (matches CI).
# Install: pip install nuitka intelhex
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pip install --upgrade pip
python -m pip install nuitka intelhex

if (-not (Test-Path "dist")) { New-Item -ItemType Directory -Path "dist" | Out-Null }

python -m nuitka `
  .\converter.py `
  --onefile `
  --enable-plugin=tk-inter `
  --include-module=gui `
  --include-module=config_manager `
  --include-module=api_client `
  --include-data-dir=bundled_configs=bundled_configs `
  --output-dir=dist `
  --assume-yes-for-downloads `
  --windows-disable-console

Write-Host "Built: dist\converter.exe"
