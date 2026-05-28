$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

$PythonExe = $null
$PythonArgs = @()

function Test-Python312 {
    param(
        [string]$Exe,
        [string[]]$Args
    )

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Exe @Args -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python312 -Exe "py" -Args @("-3.12")) {
        $PythonExe = "py"
        $PythonArgs = @("-3.12")
    }
}

if (-not $PythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python312 -Exe "python" -Args @()) {
        $PythonExe = "python"
        $PythonArgs = @()
    }
}

if (-not $PythonExe) {
    [Console]::Error.WriteLine("ERROR: Python 3.12.x was not found. Install Python 3.12.x, then rerun this script.")
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $PythonExe @PythonArgs -m venv .venv
}

.\.venv\Scripts\python -m pip install -U pip setuptools wheel
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest tests/ -q
