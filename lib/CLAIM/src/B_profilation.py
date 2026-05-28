#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to find the list of microservices in every commit, grouped by consecutive commits with same list, so
it is easy to identify the commits that have touched the microservices list.
"""

import csv
import sys
import time
import traceback

import dateutil.utils
from datetime import timedelta
from pathlib import Path

import dateutil
import git  # GitPython
from pydriller import Repository  # PyDriller

from src.claim import Microservice
from src.config import COMMIT_DEADLINE
from src.utils.print_utils import print_progress, print_major_step, print_info, printable_time
from src.utils.repo import clear_repo


KEYS = ["COMMIT", "HASH", "MICROSERVICES"]


def analyze_repo(url: str) -> list[dict[str, int | list[str] | str]]:
    """
    Run the analysis of a single repo

    :param url: url of the repository
    :return: list of chunks of consecutive commits with same docker-compose files
    """
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    print_major_step(f'## Start repo analysis ({name}) [{url}]')
    workdir = 'temp/clones/' + name

    results: list[dict[str, int | str | set[Microservice]]] = []

    try:
        print_info('   Cloning repo')
        repository = Repository(url + ".git", to=COMMIT_DEADLINE)  # Pydriller: useful to traverse commits history
        git_repo = git.Repo.clone_from(url, workdir)  # GitPython: useful to work with repo

        num_of_commits = len(list(repository.traverse_commits()))

        start_time = time.time()

        count = 0
        for commit in repository.traverse_commits():  # Apparently traverse commits returns only main branch commits
            count += 1
            print(f'\r{printable_time()}   {count}/{num_of_commits}', end="" if count != num_of_commits else "\r")

            git_repo.git.checkout(commit.hash, force=True)

            microservices = set()
            if sys.argv[2] == "claim":
                from src.claim import claim

                microservices = claim(name, workdir)
            else:
                from src.Baresi.analyze_repo import analyze_docker_compose, locate_files

                dcs = locate_files(workdir, "docker-compose.yml")
                if dcs:
                    microservices_structure = analyze_docker_compose(workdir, dcs[0])

                    for service in microservices_structure["services"]:
                        if not (len(service["dbs"]) or len(service["servers"]) or len(service["buses"]) or \
                                len(service["gates"]) or len(service["monitors"]) or len(service["discos"])):
                            microservices.add(service["name"])

            results.append({"COMMIT": count, "HASH": commit.hash, "MICROSERVICES": microservices})

        stop_time = time.time()
        print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')

        return results

    except Exception as e:
        print(traceback.format_exc())
        raise e
    finally:
        print_info('   Clearing temporary directories')
        clear_repo(Path(workdir))


def print_results(url: str, results: list[dict[str, int | str | set[Microservice]]]) -> None:
    """
    Print the results

    :param url: url of the repository
    :param results: results from analysis
    :return: None
    """
    print(f'        ---------- '
          f'[{url}] at {str(dateutil.utils.today())[0:10]} '
          f'(until {str(COMMIT_DEADLINE - timedelta(days=1))[0:10]}) '
          f'----------')

    last_set = set()
    last_hash = None
    first_index_of_chunk = 0
    for result in results:
        if result["MICROSERVICES"] != last_set:
            #if first_index_of_chunk != 0:
            print(f'')
            print(f'         • from {first_index_of_chunk} to {result["COMMIT"] - 1}')
            print(f'         |     (ends with {url}/tree/{last_hash} )')
            print(f'         |')
            print(f'         | --- MICROSERVICES ---')
            for microservice in result["MICROSERVICES"]:
                print(f'         |-> {microservice}')
            print(f'         |_')

            first_index_of_chunk = result["COMMIT"]

        last_set = result["MICROSERVICES"]
        last_hash = result["HASH"]

    print(f'')
    print(f'         • from {first_index_of_chunk} to {results[len(results)-1]["COMMIT"]}')
    print(f'         |     (ends with {url}/tree/{last_hash} )')
    print(f'         |')
    print(f'         | --- MICROSERVICES ---')
    for microservice in results[len(results)-1]["MICROSERVICES"]:
        print(f'         |-> {microservice}')
    print(f'         |_')

    print(f'        ----------  ----------')


def save_results(url: str, results: list[dict[str, int | str | set[Microservice]]]) -> None:
    """
    Save the results

    :param url: url of the repository
    :param results: results from analysis
    :return: None
    """
    name = url.split("/")[-2] + "." + url.split("/")[-1]

    results_file = Path(__file__).parent / f'../data/results/total/{"CLAIM" if sys.argv[2] == "claim" else "Baresi"}/{name}.csv'

    with open(results_file, 'w+', newline='') as results_output:
        ds_writer = csv.DictWriter(results_output, KEYS)
        ds_writer.writeheader()
        for result in results:  # type: dict[str, int | str | set[Microservice]]
            ds_writer.writerow(result)


def analyze_dataset():
    if sys.argv[1].startswith("https://github.com"):    # single repo
        print_major_step("# Start analysis")

        repo: str = sys.argv[1]

        res = analyze_repo(repo)
        print_results(repo, res)
        save_results(repo, res)


if __name__ == "__main__":
    print_major_step(' Start script execution')

    print_info(' Detecting microservices')
    analyze_dataset()

    print_info(' Terminating script execution')
