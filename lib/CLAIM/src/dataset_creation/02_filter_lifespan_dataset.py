#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to select the repos by lifespan.
"""

import csv
import time
from datetime import timedelta
from pathlib import Path

from pydriller import Repository

from src.utils.print_utils import print_major_step, print_info, print_progress
from src.config import COMMIT_THRESHOLDS, COMMIT_DEADLINE


def check_long_life_repo(url: str) -> bool:
    """
    Check the lifespan condition on a single repo.

    :param url: url of the repository
    :return: True if the repo has right lifespan, False otherwise
    """
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    print_major_step(f'## Start repo analysis ({name}) [{url}]')

    try:
        print_info('   Cloning repo')
        repository = Repository(url + ".git", to=COMMIT_DEADLINE)

        print_info('   Counting commits')
        num_of_commits = len(list(repository.traverse_commits()))

        print(f'   {num_of_commits}')
        return COMMIT_THRESHOLDS[0] <= num_of_commits <= COMMIT_THRESHOLDS[1]
    except Exception:
        raise
    finally:
        pass


def filter_long_life_dataset() -> int:
    """
    Run the detection of lifespan repo between all the repos contained in the input file

    :return: number of repos that are long-life
    """
    print_major_step("# Start dataset analysis")

    dataset_file = Path(__file__).parent / '../../data/dataset/01_filtered_multi_dev.csv'

    total_repos = -1  # We don't want to count header
    for _ in open(dataset_file):
        total_repos += 1

    count = 0
    with open(dataset_file) as dataset:
        repos = csv.DictReader(dataset, delimiter=',')

        ds_output_file = Path(__file__).parent / '../../data/dataset/02_filtered_lifespan.csv'

        with open(ds_output_file, 'w+', newline='') as ds_output:
            writer = csv.DictWriter(ds_output, ['URL'])
            writer.writeheader()
            for repo in repos:  # type: dict[str, str]
                print_progress(f'   [{repos.line_num - 1}/{total_repos}]')

                if check_long_life_repo(repo["URL"]):
                    print('   Yes')
                    count += 1
                    writer.writerow({'URL': repo["URL"]})
                else:
                    print('   No')

    return count


if __name__ == "__main__":
    print_major_step(' Start script execution')
    start_time = time.time()

    print_info(' Filtering long-life dataset')
    res = filter_long_life_dataset()

    print(f'  => {res} repositories meet the lifespan requirement')

    print_info(' Terminating script execution')
    stop_time = time.time()
    print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')