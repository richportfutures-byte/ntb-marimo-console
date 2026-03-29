[CmdletBinding()]
param(
    [string]$PythonExe = $env:NTB_BOOTSTRAP_PYTHON
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$engineRoot = (Resolve-Path (Join-Path $projectRoot "..\..\source\ntb_engine")).Path

Set-Location $projectRoot

function Resolve-BootstrapPython {
    param([string]$Requested)

    if ($Requested) {
        if (Test-Path $Requested) {
            return @{
                Kind = "python"
                Command = (Resolve-Path $Requested).Path
            }
        }

        $resolved = Get-Command $Requested -ErrorAction SilentlyContinue
        if ($null -ne $resolved) {
            $kind = if ($resolved.Name -ieq "py" -or $resolved.Name -ieq "py.exe") { "py" } else { "python" }
            return @{
                Kind = $kind
                Command = $resolved.Source
            }
        }

        throw "Requested bootstrap python was not found: $Requested"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        return @{
            Kind = "python"
            Command = $python.Source
        }
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        return @{
            Kind = "py"
            Command = $py.Source
        }
    }

    throw (
        "Could not find a Python 3.11+ interpreter. Install Python 3.11+ or rerun with " +
        "-PythonExe <full-path-to-python.exe>."
    )
}

function Invoke-BootstrapPython {
    param(
        [hashtable]$BootstrapPython,
        [string[]]$Arguments
    )

    if ($BootstrapPython.Kind -eq "py") {
        & $BootstrapPython.Command -3.11 @Arguments
    }
    else {
        & $BootstrapPython.Command @Arguments
    }
}

$bootstrapPython = Resolve-BootstrapPython -Requested $PythonExe

Invoke-BootstrapPython -BootstrapPython $bootstrapPython -Arguments @(
    "-c",
    "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
)

Invoke-BootstrapPython -BootstrapPython $bootstrapPython -Arguments @(
    "-m",
    "venv",
    "--clear",
    ".venv"
)

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Bootstrap created no virtualenv interpreter at $venvPython"
}

& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -e $engineRoot
& $venvPython -m pip install -e ".[dev,preserved_engine]"
& $venvPython scripts\bootstrap_target_paths.py
& $venvPython scripts\refresh_runtime_profile_artifacts.py
& $venvPython -c "import marimo; import ntb_marimo_console; import ninjatradebuilder; import pydantic; print('marimo', marimo.__version__); print('ntb_marimo_console', getattr(ntb_marimo_console, '__name__', 'ntb_marimo_console')); print('ninjatradebuilder', getattr(ninjatradebuilder, '__name__', 'ninjatradebuilder')); print('pydantic', pydantic.__version__)"
