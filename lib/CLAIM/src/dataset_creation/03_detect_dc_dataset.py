#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to select the repos that make use of docker-compose.
"""

import csv
import time
from datetime import timedelta
from pathlib import Path

import git

from src.claim import check_dc_presence
from src.utils.print_utils import print_major_step, print_info, print_progress
from src.utils.repo import clear_repo
from src.config import REPO_TO_SKIP, COMMIT_DEADLINE


def detect_dc_repo(url: str) -> bool:
    """
    Run the detection of docker-compose on a single repo

    :param url: url of the repository
    :return: True if the repo make use of docker-compose, False otherwise
    """
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    print_major_step(f'## Start repo analysis ({name}) [{url}]')
    workdir = str(Path(__file__).parent.joinpath('../temp/clones/' + name))

    try:
        print_info('   Cloning repo')
        repo = git.Repo.clone_from(url, workdir)

        last_commit = \
            (repo.git.execute(['git', 'log', f'--until="{COMMIT_DEADLINE}"', '--format="%H"']).splitlines())[0][1:-1]

        repo.git.checkout(last_commit)

        print_info('   Analyzing repo')
        return check_dc_presence(workdir)
    except Exception:
        raise
    finally:
        print_info('   Clearing temporary directories')
        clear_repo(Path(workdir))


def detect_dc_dataset() -> int:
    """
    Run the detection of docker-compose on all the repos contained in the input file

    :return: number of repos that make use of docker-compose
    """
    print_major_step("# Start dataset analysis")

    dataset_file = Path(__file__).parent / '../../data/dataset/02_filtered_lifespan.csv'

    total_repos = -1  # We don't want to count header
    for _ in open(dataset_file):
        total_repos += 1

    count = 0
    with open(dataset_file) as dataset:
        repos = csv.DictReader(dataset, delimiter=',')

        ds_output_file = Path(__file__).parent / '../../data/dataset/03_detected_docker.csv'

        with open(ds_output_file, 'w+', newline='') as ds_output:
            writer = csv.DictWriter(ds_output, ['URL'])
            writer.writeheader()
            for repo in repos:  # type: dict[str, str]
                if repo['URL'] in REPO_TO_SKIP:
                    continue

                print_progress(f'   [{repos.line_num - 1}/{total_repos}]')

                if detect_dc_repo(repo["URL"]):
                    print('   Yes')
                    count += 1
                    writer.writerow({'URL': repo["URL"]})
                else:
                    print('   No')

    return count


if __name__ == "__main__":
    print_major_step(' Start script execution')
    start_time = time.time()

    print_info(' Detecting docker-compose dataset')
    res = detect_dc_dataset()

    print(f'  => {res} repositories currently make use of docker-compose')

    print_info(' Terminating script execution')
    stop_time = time.time()
    print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')
