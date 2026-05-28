param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$PythonExe = $null
$PythonArgs = @()

function Test-PythonOk {
    param([string]$Exe, [string[]]$ExeArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @ExeArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prev
    }
}

# Try py launcher with version flags in descending order
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($ver in @("-3.14", "-3.13", "-3.12")) {
        if (Test-PythonOk -Exe "py" -ExeArgs @($ver)) {
            $PythonExe = "py"
            $PythonArgs = @($ver)
            break
        }
    }
}

# Fall back to python / python3
if (-not $PythonExe) {
    foreach ($cmd in @("python", "python3")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            if (Test-PythonOk -Exe $cmd -ExeArgs @()) {
                $PythonExe = $cmd
                $PythonArgs = @()
                break
            }
        }
    }
}

if (-not $PythonExe) {
    [Console]::Error.WriteLine("ERROR: Python 3.12 or later was not found. Install Python 3.12+, then rerun this script.")
    exit 1
}

$VenvPython = ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual environment..."
    & $PythonExe @PythonArgs -m venv .venv
    if (-not (Test-Path $VenvPython)) {
        [Console]::Error.WriteLine("ERROR: Failed to create virtual environment at .venv")
        exit 1
    }
}

& $VenvPython -m pip install -U pip setuptools wheel
if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("ERROR: pip upgrade failed"); exit 1 }

& $VenvPython -m pip install -r requirements-web.txt
if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("ERROR: pip install failed"); exit 1 }

$LinkHost = $HostName
if ($LinkHost -eq "0.0.0.0" -or $LinkHost -eq "::") {
    $LinkHost = "localhost"
}

Write-Host ""
Write-Host "CC4M Web UI is starting:"
Write-Host "  http://$LinkHost`:$Port/"
Write-Host "  http://$LinkHost`:$Port/visualize/"
Write-Host ""

& $VenvPython main.py web-ui --host $HostName --port $Port --visualize-only
