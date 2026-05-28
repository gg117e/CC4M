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


## Demo Data Shipped with This Artifact

For review, this branch bundles a small precomputed `dest/` for `FudanSELab.train-ticket`, covering every programming language detected in the repository:

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
