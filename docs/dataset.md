# Dataset and Target Selection

## Input

CC4M can analyze a microservice project by directly providing its GitHub repository URL in the Clone Detection UI.

The target repository must define its microservice architecture with Docker Compose. CC4M uses the Docker Compose configuration to identify service boundaries before running clone detection. Therefore, repositories that do not provide Docker Compose files may not be suitable for analysis because the tool cannot reliably determine which source files belong to which microservice.

Analysis results are written under `dest/`.

## Public Microservice Dataset

A public dataset of Docker-based microservice projects is available at the following repository:

* Source: https://github.com/darioamorosodaragona-tuni/Microservices-Dataset

This dataset can be used as a source of candidate repositories for CC4M analysis. The full dataset is not bundled with this repository. If you want to run analyses based on the original dataset, fetch it separately and prepare the target project URLs as needed.

## Target-project Condition

A project is suitable for inter-service clone detection when the same programming language has code in **two or more microservices**.

Microservice boundaries are detected by CLAIM, which identifies services based on Docker Compose configurations. A project qualifies if, for at least one programming language, the number of detected services containing that language is `>= 2`. This condition is necessary because inter-service clones can only be detected when comparable code exists across multiple services.

`select_project.check_project` implements this condition and returns the per-language service map.

## Analyzed Commits

CC4M allows users to choose the commit selection strategy from the Clone Detection UI.

The available strategies are:

* **merge_commit** - analyze merge commits on the default branch.
* **tag** - analyze tagged commits, in descending order by date.
* **frequency** - analyze every N-th commit.

Additional limits can be configured in `config.py`:

* `ANALYSIS_UNTIL` limits the analysis to commits before a specified date.
* `MAX_ANALYZED_COMMITS` caps the number of analyzed commits.
* `SEARCH_DEPTH` caps the number of mined commits.

Analysis results for selected commits are stored in `dest/analyzed_commits/`.


## Analyzed Projects

CC4M is applied to a set of open-source, Docker-based microservice projects chosen to cover a range of sizes, languages, and design styles. For each project, the detection results (but **not** the source code) are versioned under `dest/`, keyed by `owner.repo` (for example, `FudanSELab.train-ticket`). Source checkouts are cloned on demand and are not committed.

`FudanSELab.train-ticket` is fully bundled today; the remaining projects are analyzed incrementally, and their result files are added under `dest/` as detection completes.

### Common Detection Settings

Unless the table notes otherwise, every project is analyzed with the same parameters:

| Setting | Value |
| --- | --- |
| Minimum Matching Tokens | 50 |
| Filter declaration lines | ON |
| Commit Selection Method | Merge Commit |

Per-project commit caps (`MAX_ANALYZED_COMMITS` in `config.py`) appear in the **Commits** column below.

### Project Overview

| Project | Languages | Commits | Notes |
| --- | --- | --- | --- |
| [FudanSELab/train-ticket](https://github.com/FudanSELab/train-ticket) | Java, JavaScript | Merge, no cap | Java results only — see note below |
| [microservices-patterns/ftgo-application](https://github.com/microservices-patterns/ftgo-application) | Java | Merge, no cap | |
| [lightstep/opentelemetry-examples](https://github.com/lightstep/opentelemetry-examples) | Python, Java, Go, JavaScript | Merge, no cap | |
| [Microservice-API-Patterns/LakesideMutual](https://github.com/Microservice-API-Patterns/LakesideMutual) | Java, JavaScript | Merge, no cap | |
| [stackroute/ibm-wave7-lifeline](https://github.com/stackroute/ibm-wave7-lifeline) | Java | Merge, no cap | |
| [tgrall/redis-microservices-demo](https://github.com/tgrall/redis-microservices-demo) | Java, JavaScript | Merge, no cap | |
| [FightPandemics/FightPandemics](https://github.com/FightPandemics/FightPandemics) | JavaScript (Node.js / React) | Merge, last 10 | ~600 merge commits, capped to the 20 most recent |

### Why These Projects

**FudanSELab/train-ticket** — The best-known and largest microservice benchmark, comprising tens of services. Ideal for evaluating how large-scale clones arise in complex systems. Only the Java results are published: the JavaScript scatter dataset is ~457 MB (bundled libraries inflate the clone count) and exceeds GitHub's per-file limit, so it is excluded from version control.

**microservices-patterns/ftgo-application** — The official reference implementation for the book *Microservices Patterns*. Built around standard, exemplary design patterns, it is well suited to analyzing the boilerplate and template code (clones) that accompany domain-driven design.

**lightstep/opentelemetry-examples** — A collection of OpenTelemetry implementation examples spanning multiple languages, with many API-call and instrumentation patterns. Similar configuration and initialization code tends to be cloned across services.

**Microservice-API-Patterns/LakesideMutual** — The official reference implementation for *Microservice API Patterns* (a simulated insurance-company system). A Spring Boot backend with a separate frontend; REST API integration and pattern implementation produce boilerplate clones that are easy to detect.

**stackroute/ibm-wave7-lifeline** — A textbook Spring Cloud microservice layout (config-server, search-service, zuul-api, and various profile-services). Ideal for clone analysis of per-service boilerplate such as configuration and error handling.

**tgrall/redis-microservices-demo** — A Redis-backed, polyglot system mixing Node.js services and a Java system. Responsibilities are split into fine-grained services within the repository (for example, DB read/write services), making it convenient for small, focused validation.

**FightPandemics/FightPandemics** — A large open-source social platform with a clearly separated backend and client. Good for observing how code clones arise in JavaScript/TypeScript projects (UI components, API routers, and the like). Because it has roughly 600 merge commits, analysis is capped to the 20 most recent.


## Demo Data Shipped with This Artifact

For review, this branch bundles a small precomputed `dest/` for `FudanSELab.train-ticket` (the first entry in [Analyzed Projects](#analyzed-projects)), covering every programming language detected in the repository:

* `dest/scatter/`
* `dest/services_json/`
* `dest/enriched_fragments/`
* `dest/clone_metrics/`
* `dest/analysis_params/`

These files are enough to populate the scatter plot and all metrics without running the pipeline. The full source checkout is not bundled. To make the source-code view line up with the bundled demo data, clone the analyzed revision:

```bash
mkdir -p dest/projects
git clone https://github.com/FudanSELab/train-ticket dest/projects/FudanSELab.train-ticket
git -C dest/projects/FudanSELab.train-ticket checkout 813dd01eec30386f673d7340a1b7eb605fcb5def
```
