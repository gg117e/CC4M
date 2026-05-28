#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to query GitHub to find all the repo corresponding to one or more query, deleting the duplicate.
"""

import csv
import time
from datetime import timedelta
from math import ceil
from pathlib import Path

import requests
from requests import Response

from src.utils.print_utils import print_major_step, print_info, print_progress, print_error
from src.config import QUERIES, GH_TOKEN


class GhApiException(Exception):
    """
    Only a wrapper class for Exception raised during the query of GitHub API
    """
    def __init__(self, response: Response):
        super()
        self.response = response


def query_github(queries: list[list[str]]) -> set[str]:
    """
    Execute queries on GitHub and return a list of results without duplicates.

    :param queries: queries to execute in GitHub API format
    :return: set of repo found
    """
    results: set[str] = set()

    try:
        for query in queries:
            for subquery in query:
                param = {
                    'q': subquery,
                    'page': 1,
                    'per_page': 100,
                    'sort': 'stars',
                    'order': 'desc'
                }

                response = github_api_search(param)  # get the first page of the query to have the total number

                number_of_results = response.json()['total_count']

                for page in range(1, ceil(number_of_results / 100) + 1):

                    for item in response.json()['items']:
                        results.add(item['html_url'])

                    # query for the next page, used in the next iteration of loop
                    param['page'] = page + 1

                    response = github_api_search(param)  # get the next page of the query

            time.sleep(60)  # to not exceed the rate limit of GitHub API of 30 search per minute

        return results
    except GhApiException as e:
        response = e.args[0]
        if response.status_code == 422:
            print_error(' GitHub API validation error: ' + response.json()['message'])
        else:  # status code 503
            print_error(' GitHub API availability error: ' + response.json()['message'])

        if 'errors' in response:
            print_error(' GitHub API error message: ' + response.json()['errors'][0]['message'])


def github_api_search(param: dict[str, str | int]) -> Response:
    """
    Perform a search query via GitHub API

    :param param: parameters of the query (query itself, page, per_page, order, sort)
    :return: the response from GitHub endpoint
    :raises Exception: if code 503 (service unavailable) or 422 (validation failed) is returned
    """
    while True:
        response = requests.get(url='https://api.github.com/search/repositories',
                                headers={'Authorization': f'Bearer {GH_TOKEN}'},
                                params=param)

        if response.status_code == 200:
            if not response.json()['incomplete_results']:
                return response
            else:  # if incomplete results
                time.sleep(10)  # wait 10 secs to have more chance to have the server less busy and retry
        elif response.status_code == 304:
            time.sleep(10)  # wait 10 secs to have more chance to have the server less busy and retry
        else:  # status code 422 or 503
            raise GhApiException(response)


def save_results(repos: set[str]) -> None:
    """
    Save search results in a csv file

    :param repos: repo to write
    :return: None
    """
    results_file = Path(__file__).parent / f'../../data/dataset/00_raw_queries_results.csv'

    with open(results_file, 'w+', newline='') as results_output:
        ds_writer = csv.DictWriter(results_output, ['URL'])
        ds_writer.writeheader()
        for repo in sorted(repos):  # type: str
            ds_writer.writerow({'URL': repo})


if __name__ == "__main__":
    print_major_step(' Start script execution')
    start_time = time.time()

    print_info(' Querying GitHub')
    res = query_github(QUERIES)

    if res:
        print(f'  => Found {len(res)} repositories')
        print_info(' Saving results')
        save_results(res)

    print_info(' Terminating script execution')
    stop_time = time.time()
    print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')
