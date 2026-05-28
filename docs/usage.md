# Usage

| Goal | Command | Prerequisite |
|---|---|---|
| Visualization only (browse bundled results) | `sh scripts/run_web.sh` or `powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1` | Python 3.12.x |
| Visualization-only POSIX shortcut | `make web` | Python 3.12.x, `make` |
| Clone detection + visualization (analyze a repo) | `docker compose up --build web-ui` | Docker Desktop / Compose |
| Docker POSIX shortcut | `make docker-web` | Docker Desktop / Compose, `make` |

## 1. Visualization Only

Serves the Dash app from existing `dest/` artifacts. It does not clone repos or
run clone detection.

Mac / Linux:

```bash
sh scripts/run_web.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1
```

Raw Python commands, useful when scripts cannot be used:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install -r requirements-web.txt
.venv/bin/python main.py web-ui --host 127.0.0.1 --port 8000 --visualize-only
```

Then open `http://localhost:8000/visualize/`.

This repository ships a small demo dataset (`dest/` for
`FudanSELab.train-ticket`) so the scatter plot and metrics are populated
immediately. Viewing the actual source of a fragment requires the matching
source checkout under `dest/projects/`:

```bash
mkdir -p dest/projects
git clone https://github.com/FudanSELab/train-ticket dest/projects/FudanSELab.train-ticket
git -C dest/projects/FudanSELab.train-ticket checkout 813dd01eec30386f673d7340a1b7eb605fcb5def
```

The bundled demo artifacts were generated from `v0.1.0-2-g813dd01e`
(`813dd01eec30386f673d7340a1b7eb605fcb5def`), not the current default branch.

## 2. Clone Detection + Visualization

Runs the external tools (CCFinderSW, CLAIM, github-linguist) inside Docker. From
the web UI you give a repository URL and analysis options, then the clone
detection and visualization build run end to end.

```bash
docker compose up --build web-ui
```

Then open `http://localhost:8000`. The first build takes a while; later builds
use the Docker cache.

## Tests And Lint

Mac / Linux:

```bash
sh scripts/run_tests.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```

POSIX shortcuts:

```bash
make test
make lint
```

`requirements-dev.txt` pulls in `requirements-web.txt` plus `pytest` and `ruff`.


## CCFinderSW Settings

`config.py` exposes the Java heap/stack used by CCFinderSW:
`CCFINDERSW_JAVA_XMX` (default `20G`) and `CCFINDERSW_JAVA_XSS` (default
`512m`). To build the Rust `ccfindersw-parser` on the host instead of in Docker,
run `sh scripts/build_ccfindersw_parser.sh` (needs a Rust toolchain).
