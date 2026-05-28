# Third-Party Notices

This repository contains CC4M's original source code together with selected
third-party tools and generated review data. The root `LICENSE` applies to
CC4M's original code and documentation. Third-party components keep their own
licenses and notices.

## Bundled Components

| Component | Local path | License notes |
|---|---|---|
| CCFinderSW | `lib/CCFinderSW-1.0/` | Upstream CCFinderSW is distributed under the MIT License. The upstream project also notes that it contains libraries distributed under Apache License 2.0. Several grammar files under `grammarsv4/` carry file-level notices, including MIT, BSD, Apache-2.0, EPL-1.0, and GPL notices. |
| CLAIM | `lib/CLAIM/` | The bundled README states that CLAIM source code is MIT-licensed and graphical/text assets are licensed under Creative Commons Attribution 4.0. |

## Build-Time Downloads

The Docker image downloads and builds additional tools that are not vendored in
this repository:

| Component | Used by | Notes |
|---|---|---|
| `ccfindersw-parser` | `Dockerfile` | Cloned during Docker build from the repository configured by `CCF_PARSER_REPO`. |
| GitHub Linguist | `Dockerfile` | Installed as a Ruby gem during Docker build. |

## Demo Data

The review demo data under `dest/` is derived from the public
`FudanSELab/train-ticket` repository at commit
`813dd01eec30386f673d7340a1b7eb605fcb5def` (`v0.1.0-2-g813dd01e`). It is
included only to let users open the visualization without running the full
clone-detection pipeline. The matching train-ticket source working tree is not
bundled; clone it on demand under `dest/projects/FudanSELab.train-ticket` if
the in-app source / full-source view is needed.
