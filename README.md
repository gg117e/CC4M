# CC4M: Code Clone Analysis and Visualization for Microservices

CC4M detects cross-service code clones in microservice projects and visualizes
them so that maintainers can see the potential impact scope of a change. It
runs CCFinderSW to obtain Type-1/Type-2 clones, enriches them with
service-boundary, co-modification, file-category, and metric information, and
serves an interactive scatter plot with metric-based filtering.

> **Screencast:** https://www.youtube.com/watch?v=0xOIQPFbkUg

## Quick Start

Run CC4M with Docker:

```bash
docker compose up --build web-ui
```

After the service starts, open
[http://localhost:8000](http://localhost:8000). 

This repository ships a small precomputed demo dataset for
`https://github.com/FudanSELab/train-ticket`, covering Java code in the
repository, so the visualization is populated immediately. In the UI, select
project `FudanSELab.train-ticket` and then select language `Java`.

The demo source checkout itself is not committed. If you want the source-code
pane to match the bundled demo rows, clone the exact analyzed revision:

```bash
mkdir -p dest/projects
git clone https://github.com/FudanSELab/train-ticket dest/projects/FudanSELab.train-ticket
git -C dest/projects/FudanSELab.train-ticket checkout 813dd01eec30386f673d7340a1b7eb605fcb5def
```

That revision is `v0.1.0-2-g813dd01e`, a 2021-05-21 merge commit.

The first Docker build takes a while; later builds use the Docker cache.

## Entry Points

| Goal                                          | Command                                                                                       | Prerequisite                      |
| --------------------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------- |
| Web UI only, from bundled `dest/` artifacts | `sh scripts/run_web.sh` or `powershell -ExecutionPolicy Bypass -File scripts\run_web.ps1` | Python 3.12+                      |
| Web UI only shortcut on POSIX systems         | `make web`                                                                                  | Python 3.12+,`make`             |
| Dockerized clone detection + visualization    | `docker compose up --build web-ui`                                                          | Docker Desktop / Compose          |
| Docker shortcut on POSIX systems              | `make docker-web`                                                                           | Docker Desktop / Compose,`make` |

The Docker path includes CCFinderSW, CLAIM, and GitHub Linguist in the image, so
it can run the full analysis workflow and serve the visualization from one
environment.

## Tests

Mac / Linux:

```bash
sh scripts/run_tests.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```

POSIX shortcut:

```bash
make test
make lint
```

## Documentation

| Document                                                              | Contents                                          |
| --------------------------------------------------------------------- | ------------------------------------------------- |
| [docs/architecture.md](docs/architecture.md)                             | Components, data pipeline, web stack              |
| [docs/usage.md](docs/usage.md)                                           | Entry points, tests, batch CLI, settings          |
| [docs/definitions.md](docs/definitions.md)                               | Terminology                                       |
| [docs/metrics.md](docs/metrics.md)                                       | Clone metrics verified against the code           |
| [docs/declaration_line_filtering.md](docs/declaration_line_filtering.md) | Declaration-line filtering before clone detection |
| [docs/file_classification.md](docs/file_classification.md)               | File-path / service / file-type handling          |
| [docs/dataset.md](docs/dataset.md)                                       | Dataset, target selection, demo data              |


## License

CC4M's original code and documentation are licensed under the MIT License. See
[LICENSE](LICENSE). Bundled third-party components and generated demo data are
described in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
