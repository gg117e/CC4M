#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to select the multi-dev repos (counting anonymous ones and bots).
"""

import csv
import time
from datetime import timedelta
from pathlib import Path

import requests
from requests import Response

from src.utils.print_utils import print_major_step, print_info, print_progress, print_error
from src.config import GH_TOKEN, CONTRIBUTORS_THRESHOLD


class GhApiException(Exception):
    """
    Only a wrapper class for Exception raised during the query of GitHub API
    """
    def __init__(self, response: Response):
        super()
        self.response = response


def check_multi_dev_repo(url: str) -> bool:
    """
    Check the multi-dev condition on a single repo.

    :param url: url of the repository
    :return: True if the repo is multi-dev, False otherwise
    """
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    print_major_step(f'## Start repo analysis ({name}) [{url}]')

    try:
        print_info('   Analyzing repo')

        response = github_api_contributors(url).json()

        user = [contrib for contrib in response if contrib["type"] == "User"]
        bot = [contrib for contrib in response if contrib["type"] == "Bot"]
        anon = [contrib for contrib in response if contrib["type"] == "Anonymous"]

        print(f'   User: {len(user)} - Bot: {len(bot)} - Anon: {len(anon)}')

        return CONTRIBUTORS_THRESHOLD[0] < len(user + anon + bot) <= CONTRIBUTORS_THRESHOLD[1]
    except GhApiException as e:
        print_error('GitHub API error')
        raise e


def github_api_contributors(url: str) -> Response:
    """
    Perform a repository contributors query via GitHub API

    :param url: url of the repo
    :return: the response from GitHub endpoint
    :raises Exception: if not code 200 is returned
    """
    while True:
        response = requests.get(
            url=f'https://api.github.com/repos/{url.split("/")[-2]}/{url.split("/")[-1]}/contributors',
            headers={'Authorization': f'Bearer {GH_TOKEN}'},
            params={'anon': 1})

        if response.status_code == 200:
            return response
        else:
            raise GhApiException(response)


def filter_multi_dev_dataset() -> int:
    """
    Run the detection of multi-dev repo between all the repos contained in the input file

    :return: number of repos that are multi-dev
    """
    print_major_step("# Start dataset analysis")

    dataset_file = Path(__file__).parent / '../../data/dataset/00_raw_queries_results.csv'

    total_repos = -1  # We don't want to count header
    for _ in open(dataset_file):
        total_repos += 1

    count = 0
    with open(dataset_file) as dataset:
        repos = csv.DictReader(dataset, delimiter=',')

        ds_output_file = Path(__file__).parent / '../../data/dataset/01_filtered_multi_dev.csv'

        with open(ds_output_file, 'w+', newline='') as ds_output:
            writer = csv.DictWriter(ds_output, ['URL'])
            writer.writeheader()
            for repo in repos:  # type: dict[str, str]
                print_progress(f'   [{repos.line_num - 1}/{total_repos}]')

                if check_multi_dev_repo(repo["URL"]):
                    print('   Yes')
                    count += 1
                    writer.writerow({'URL': repo["URL"]})
                else:
                    print('   No')

    return count


if __name__ == "__main__":
    print_major_step(' Start script execution')
    start_time = time.time()

    print_info(' Filtering multi-dev dataset')
    res = filter_multi_dev_dataset()

    print(f'  => {res} repositories meet the multi-dev requirement')

    print_info(' Terminating script execution')
    stop_time = time.time()
    print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')
