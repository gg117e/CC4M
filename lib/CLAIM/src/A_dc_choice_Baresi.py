#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to find the list of docker-compose files in every commit and the chosen one (according to Baresi et
al. method), grouped by consecutive commits with same list, so it is easy to identify the commits that have touched the
position/name of docker-compose files.
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

from src.claim import locate_files, choose_dc, DOCKER_COMPOSE_NAMES
from src.Baresi.analyze_repo import locate_files as Baresi_locate_files
from src.config import COMMIT_DEADLINE
from src.utils.print_utils import print_progress, print_major_step, print_info, printable_time
from src.utils.repo import clear_repo


KEYS = ["CHUNKS_N", "CHUNKS_H", "DCFs", "DC"]


def analyze_repo(url: str) -> list[dict[str, int | list[str] | str]]:
    """
    Run the analysis of a single repo

    :param url: url of the repository
    :return: list of chunks of consecutive commits with same docker-compose files
    """
    name = url.split('/')[-2] + '.' + url.split('/')[-1]
    print_major_step(f'## Start repo analysis ({name}) [{url}]')
    workdir = 'temp/clones/' + name

    results: list[dict[str, int | list[str] | str]] = []

    try:
        print_info('   Cloning repo')
        repository = Repository(url + ".git", to=COMMIT_DEADLINE)  # Pydriller: useful to traverse commits history
        git_repo = git.Repo.clone_from(url, workdir)  # GitPython: useful to work with repo

        num_of_commits = len(list(repository.traverse_commits()))

        count = 0
        chunk_docker_composes = None
        first_chunk_commit_num, first_chunk_commit_hash = 1, None
        last_chunk_commit_hash = None
        last_docker_compose = None
        for commit in repository.traverse_commits():  # Apparently traverse commits returns only main branch commits
            count += 1
            print(f'\r{printable_time()}   {count}/{num_of_commits}', end="" if count != num_of_commits else "\r")

            git_repo.git.checkout(commit.hash, force=True)

            if count == 1:
                first_chunk_commit_hash = commit.hash

            current_docker_composes = set()
            for dc_name in DOCKER_COMPOSE_NAMES:
                current_docker_composes.update(locate_files(workdir, dc_name))

            if current_docker_composes != chunk_docker_composes:
                result = dict.fromkeys(KEYS)
                result["FROM_N"] = first_chunk_commit_num
                result["FROM_H"] = first_chunk_commit_hash
                result["TO_N"] = count - 1
                result["TO_H"] = last_chunk_commit_hash
                result["DCFs"] = chunk_docker_composes
                result["DC"] = last_docker_compose
                results.append(result)
                first_chunk_commit_num, first_chunk_commit_hash = count, commit.hash
                chunk_docker_composes = current_docker_composes

            last_chunk_commit_hash = commit.hash
            Baresi_results = Baresi_locate_files(workdir, "docker-compose.yml")
            last_docker_compose = Baresi_results[0] if Baresi_results else None

        result = dict.fromkeys(KEYS)
        result["FROM_N"] = first_chunk_commit_num
        result["FROM_H"] = first_chunk_commit_hash
        result["TO_N"] = count
        result["TO_H"] = last_chunk_commit_hash
        result["DCFs"] = chunk_docker_composes
        result["DC"] = last_docker_compose
        results.append(result)
        return results

    except Exception as e:
        print(traceback.format_exc())
        raise e
    finally:
        print_info('   Clearing temporary directories')
        clear_repo(Path(workdir))


def print_results(url: str, chunks: list[dict[str, int | list[str] | str]], group: bool = False) -> None:
    """
    Print the list of chunks of consecutive commits with same docker-compose files

    :param url: url of the repository
    :param chunks: list of chunks of consecutive commits with same docker-compose files
    :param group: True if you want to group non-consecutive chunk with the same set of docker-compose files
    :return: None
    """
    print(f'        ---------- '
          f'[{url}] at {str(dateutil.utils.today())[0:10]} '
          f'(until {str(COMMIT_DEADLINE - timedelta(days=1))[0:10]}) '
          f'----------')

    if not group:
        for chunk in chunks:
            if chunk["DCFs"] is None:
                continue

            print(f'')
            print(f'         • from {"{:5d}".format(chunk["FROM_N"])} to {"{:5d}".format(chunk["TO_N"])}:')
            print(f'         |     (ends with {url}/tree/{chunk["TO_H"]} )')
            print(f'         | {sorted(chunk["DCFs"])}')
            print(f'         |-> {chunk["DC"]}')
    else:  # group
        rows = group_chunks(chunks)

        for row in rows.values():   # type: dict[str, list[tuple] | list[str] | str]
            print(f'')
            for interval in row["CHUNKS_N"]:
                print(f'         • from {"{:5d}".format(interval[0])} to {"{:5d}".format(interval[1])}:')
            print(f'         |     (first appearance {url}/tree/{row["CHUNKS_H"][0][0]} )')
            print(f'         |     ( last appearance {url}/tree/{row["CHUNKS_H"][-1][1]} )')
            print(f'         | {sorted(row["DCFs"])}')
            print(f'         |-> {row["DC"]}')

    print(f'        ----------  ----------')


def save_results(url: str, chunks: list[dict[str, int | list[str] | str]], group: bool = False) -> None:
    """
    Save the list of chunks of consecutive commits with same docker-compose files to a csv file

    :param url: url of the repository
    :param chunks: list of chunks of consecutive commits with same docker-compose files
    :param group: True if you want to group non-consecutive chunk with the same set of docker-compose files
    :return: None
    """
    name = url.split("/")[-2] + "." + url.split("/")[-1]

    results_file = Path(__file__).parent / f'../data/results/dc_choice/Baresi/{name}_Baresi.csv'

    with open(results_file, 'w+', newline='') as results_output:

        if not group:
            ds_writer = csv.DictWriter(results_output, KEYS)
            ds_writer.writeheader()
            for chunk in chunks:  # type: dict[str, int | list[str] | str]
                if chunk["DCFs"] is None:
                    continue

                row = {"CHUNKS_N": [(chunk["FROM_N"], chunk["TO_N"])],
                       "CHUNKS_H": [(chunk["FROM_H"], chunk["TO_H"])],
                       "DCFs": sorted(chunk["DCFs"]),
                       "DC": chunk["DC"]}

                ds_writer.writerow(row)
        else:  # group
            rows = group_chunks(chunks)

            ds_writer = csv.DictWriter(results_output, KEYS)
            ds_writer.writeheader()
            for row in rows.values():  # type: dict[str, list[tuple] | list[str] | str]

                ds_writer.writerow(row)


def group_chunks(chunks):
    """
    Group non-consecutive chunks with the same set of docker-compose files

    :param chunks: list of chunks of consecutive commits with same docker-compose files
    :return: dict of chunks with the same docker-compose files
    """
    rows: dict[frozenset, dict[str, list[tuple] | list[str] | str]] = dict()
    for chunk in chunks:  # type: dict[str, int | list[str] | str]
        if chunk["DCFs"] is None:
            continue

        if frozenset(chunk["DCFs"]) not in rows:
            rows[frozenset(chunk["DCFs"])] = {"CHUNKS_N": [(chunk["FROM_N"], chunk["TO_N"])],
                                              "CHUNKS_H": [(chunk["FROM_H"], chunk["TO_H"])],
                                              "DCFs": sorted(chunk["DCFs"]),
                                              "DC": chunk["DC"]}
        else:
            rows[frozenset(chunk["DCFs"])]["CHUNKS_N"].append((chunk["FROM_N"], chunk["TO_N"]))
            rows[frozenset(chunk["DCFs"])]["CHUNKS_H"].append((chunk["FROM_H"], chunk["TO_H"]))
    return rows


def analyze_dataset():
    if sys.argv[1].startswith("https://github.com"):    # single repo
        print_major_step("# Start analysis")

        repo: str = sys.argv[1]

        res = analyze_repo(repo)
        print_results(repo, res)
        save_results(repo, res)
    else:   # dataset
        print_major_step("# Start dataset analysis")

        dataset_file = Path(__file__).parent / f'../data/dataset/{sys.argv[1]}.csv'

        total_repos = -1  # We don't want to count header
        for _ in open(dataset_file):
            total_repos += 1

        with open(dataset_file) as dataset:
            repos = csv.DictReader(dataset, delimiter=',')

            for repo in repos:  # type: dict[str, str]
                print_progress(f'   [{repos.line_num - 1}/{total_repos}]')

                res = analyze_repo(repo["URL"])
                print_results(repo["URL"], res, eval(sys.argv[2]))
                save_results(repo["URL"], res, eval(sys.argv[2]))


if __name__ == "__main__":
    print_major_step(' Start script execution')
    start_time = time.time()

    print_info(' Locating docker-compose files')
    analyze_dataset()

    print_info(' Terminating script execution')
    stop_time = time.time()
    print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')
