# CLAIM: a Lightweight Approach to Identify Microservices in Dockerized Environments
This repository is a companion page for the following publication:
> Anonymous 2024. CLAIM: a Lightweight Approach to Identify Microservices in Dockerized Environments. Submitted for 
> revision to the 28th International Conference on Evaluation and Assessment in Software Engineering (EASE)

It contains an implementation of CLAIM tool and all the material required for replicating the study, including: 
implementation of CLAIM, scripts for defining datasets, script to conduct experiment, raw data and final results.

<!--
## How to cite us
The scientific article describing design, execution, and main results of this study is available [here]().

If this study is helping your research, consider to cite it is as follows, thanks!

```
@article{claim,
  title={CLAIM: a Lightweight Approach to Identify Microservices in Dockerized Environments},
  author={Anonymous},
  journal={International Conference on Evaluation and Assessment in Software Engineering (EASE)},
  year={2024}
}
```
-->

## CLAIM documentation
Brief overview on CLAIM.

### Exposed methods

The main method is:
- <code>claim(repository name, repository base directory)</code>, which returns the set of identified microservices by 
calling:
  - <code>choose_dc(repository base directory)</code>, that chooses the right compose file;
  - <code>dc_collect_services(compose file, repository base directory)</code>, that extracts the list of Docker
services;
  - <code>process_services(list of Docker services, repository base directory)</code>, that elaborates the 
selected compose in order to extract the images, builds and containers;
  - <code>determine_microservices(repository user, repository name, repository base directory, candidate microservices
</code>, that determines the microservices.

### Configuration parameters
Here the configuration parameters used by CLAIM:
- filenames for compose file to be selected:

  ```
  *docker-compose*.yml, *docker-compose*.yaml, *compose*.yml, *compose*.yaml
  ```
  
- folder considered "neutral" for compose file to be accepted:

  ```
  docker*, *compose, swarm,
  src, services,
  dev*, test*, staging, deploy*, integration, release, prod*,
  iac, saas, devops, setup*, script*, complete, etc
  ```

- folder weights for compose file sorting (lexicographically with respect to path): same order as above, decreasing weight
- affixes considered "neutral" for compose file to be accepted:

  ```
  services, base,
  dev*, build*, stack, prod*, stable, deploy*, test*  
  ```
  
- affixes considered undesired for compose file to be discarded:

  ```
  infra*, override  
  ```

- affixes weights for compose file to be chosen: same order as above, decreasing weight

- filenames for Dockerfile to be selected:

  ```
  *Dockerfile*
  ```

- extensions for resulting files to be discarded (i.e. false positives Dockerfile):

  ```
  .sh, .ps1, .nanowin, .txt
  ```

- folder for Dockerfile to be discarded:

  ```
  vendor, external, example, demo
  ```
  

- extensions considered "configuration" when copied into filesystem of containers

  ```
  .sh, .xml, .txt, .yaml, .yml, .sql,
  .conf, .config, .cnf, .cfg, .cf, .crt, .key
  ```
  

## Quick start
Brief documentation on how to use the replication material.

### Requirements

- Python 3.10

### Preliminary

- Clone the repo in the directory you want (we refer to it as `{CLONE_DIR}`):

  ```
  git clone * {CLONE_DIR}
  ```

- Install all the Python package required:

  ```
  pip install -r src/requirements.txt
  ```

### Experiment

- Set GitHub token in <code>config.py</code>

- Run the compose file detection with CLAIM:

  ```
  python src.A_dc_choice {"dataset_real"/"dataset_ground_truth"}
  ```

- Run the compose file detection with Baresi et al.:

  ```
  python src.A_dc_choice_Baresi {"dataset_real"/"dataset_ground_truth"}
  ```
  
- Run the microservices identification with CLAIM:

  ```
  python src.A_ms_detection {"dataset_real"/"dataset_ground_truth"}
  ```

- Run the microservices identification with Baresi et al.:

  ```
  python src.A_ms_detection_Baresi {"dataset_real"/"dataset_ground_truth"}
  ```
  
- Run the profilation:

  ```
  python scalene --memory --cpu --- -m src.B_profilation {repository} {"claim"/"baresi"}
  ```


## Repository Structure
This is the root directory of the repository. The directory is structured as follows:

    CLAIM_rep-pkg
     .
     |
     |
     |--- src/                                   Source code used in the paper
     |      |
     |      |--- Baresi/                         Scripts from Baresi et al.
     |      |
     |      |--- dataset_creation/               Scripts relating to steps of the creation of dataset with manually created ground truth
     |      |
     |      |--- claim.py                        Implementation of CLAIM
     |      |
     |      |--- config.py                       Configurations
     |      |
     |      |--- 0_*                             Datasets
     |      |
     |      |--- A_*                             Experiment
     |      |
     |      |--- B_*                             Profiling (time and memory)
     |      |
     |      |--- C_*                             Result plot
     |
     |--- data/                                  Data used in the paper 
     |      |
     |      |--- dataset/                        Dataset data
     |      |
     |      |--- results/                        Experiment results
     |      |
     |      |--- analysis/                       Data input for plotting and plots

## License
The source code is licensed under the MIT license, which you can find in the [LICENSE file](LICENSE).

All graphical/text assets are licensed under the [Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
