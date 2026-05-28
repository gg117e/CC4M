#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to find the list of microservices in every commit (according to Baresi et al. method), grouped by
consecutive commits with same list, so it is easy to identify the commits that have touched the microservices list.
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

from src.claim import (dc_collect_services, process_services, _locate_dockerfiles, _container_to_microservice, Microservice,
                   _groups_dockerfiles)
from src.Baresi.analyze_repo import analyze_docker_compose as Baresi_analyze_docker_compose
from src.config import COMMIT_DEADLINE
from src.utils.print_utils import print_progress, print_major_step, print_info, printable_time
from src.utils.repo import clear_repo


KEYS = ["CHUNKS_N", "CHUNKS_H", "uSs", "CONTAINERS", "DFs"]


def analyze_repo(url: str) -> list[dict[str, int | list[str] | str]]:
    """
    Run the analysis of a single repo

    :param url: url of the repository
    :return: list of chunks of consecutive commits with same detected microservices and unmatched containers and
    dockerfiles
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
        chunk_microservices, chunk_containers, chunk_dfs = None, None, None
        first_chunk_commit_num, first_chunk_commit_hash = 1, None
        last_chunk_commit_hash = None
        for commit in repository.traverse_commits():  # Apparently traverse commits returns only main branch commits
            count += 1
            print(f'\r{printable_time()}   {count}/{num_of_commits}', end="" if count != num_of_commits else "\r")

            git_repo.git.checkout(commit.hash, force=True)

            if count == 1:
                first_chunk_commit_hash = commit.hash

            # take the correct docker compose
            docker_compose = None

            with open(Path(__file__).parent / f'../data/dataset/dc/{name}.csv') as dataset:
                chunks = csv.DictReader(dataset, delimiter=',')

                for chunk in chunks:  # type: dict[str, str | int]
                    if eval(chunk['CHUNKS_N'])[0][0] <= count:
                        docker_compose = chunk["DC"]
                    else:
                        break

            microservices, containers, dfs = set(), set(), set()
            if docker_compose:
                microservices_structure = Baresi_analyze_docker_compose(workdir, "/" + docker_compose)

                for service in microservices_structure["services"]:
                    if not (len(service["dbs"]) or len(service["servers"]) or len(service["buses"]) or \
                            len(service["gates"]) or len(service["monitors"]) or len(service["discos"])):
                        microservices.add(service["name"])

                rslts = dc_collect_services(Path(workdir).joinpath(docker_compose))
                rslts = process_services(rslts, Path(workdir))

                if rslts:
                    rslts.sort(key=lambda x: len(x.image) if x.image is not None else len(x.container_name), reverse=True)
                    local_dfs = _locate_dockerfiles(workdir)
                    dfs = local_dfs.copy()
                    _groups_dockerfiles(dfs)
                    dfs = set(dfs)

                    for rslt in rslts:
                        containers.add(rslt)

            if microservices != chunk_microservices or containers != chunk_containers or dfs != chunk_dfs:
                result = dict.fromkeys(KEYS)
                result["FROM_N"] = first_chunk_commit_num
                result["FROM_H"] = first_chunk_commit_hash
                result["TO_N"] = count - 1
                result["TO_H"] = last_chunk_commit_hash
                result["uSs"] = chunk_microservices
                result["CONTAINERS"] = chunk_containers
                result["DFs"] = chunk_dfs
                results.append(result)
                first_chunk_commit_num, first_chunk_commit_hash = count, commit.hash
                chunk_microservices = microservices
                chunk_containers = containers
                chunk_dfs = dfs

            last_chunk_commit_hash = commit.hash

        result = dict.fromkeys(KEYS)
        result["FROM_N"] = first_chunk_commit_num
        result["FROM_H"] = first_chunk_commit_hash
        result["TO_N"] = count
        result["TO_H"] = last_chunk_commit_hash
        result["uSs"] = chunk_microservices
        result["CONTAINERS"] = chunk_containers
        result["DFs"] = chunk_dfs
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
    Print the list of chunks of consecutive commits with same detected microservices and unmatched containers and
    dockerfiles

    :param url: url of the repository
    :param chunks: list of chunks of consecutive commits with same detected microservices and unmatched containers and
    dockerfiles
    :param group: True if you want to group non-consecutive chunks with same set of detected microservices and unmatched
    containers and dockerfiles
    :return: None
    """
    print(f'        ---------- '
          f'[{url}] at {str(dateutil.utils.today())[0:10]} '
          f'(until {str(COMMIT_DEADLINE - timedelta(days=1))[0:10]}) '
          f'----------')

    if not group:
        for chunk in chunks:
            if chunk["uSs"] is None or chunk["CONTAINERS"] is None or chunk["DFs"] is None:
                continue

            print(f'')
            print(f'         • from {"{:5d}".format(chunk["FROM_N"])} to {"{:5d}".format(chunk["TO_N"])}')
            print(f'         |     (ends with {url}/tree/{chunk["TO_H"]} )')
            print(f'         |')
            print(f'         | --- DETECTED MICROSERVICES ---')
            for microservice in chunk["uSs"]:
                print(f'         |-> {microservice}')
            print(f'         |')
            print(f'         | --- ALL CONTAINERS ---')
            for container in chunk["CONTAINERS"]:
                print(f'         |-> {container}')
            print(f'         |')
            print(f'         | --- ALL DOCKERFILES ---')
            for df in chunk["DFs"]:
                print(f'         |-> {df}')
    else:
        rows = group_chunks(chunks)

        for row in rows.values():  # type: dict[str, list[tuple] | list[str] | str]
            print(f'')
            for interval in row["CHUNKS_N"]:
                print(f'         • from {"{:5d}".format(interval[0])} to {"{:5d}".format(interval[1])}:')
            print(f'         |     (first appearance {url}/tree/{row["CHUNKS_H"][0][0]} )')
            print(f'         |     ( last appearance {url}/tree/{row["CHUNKS_H"][-1][1]} )')
            print(f'         |')
            print(f'         | --- MICROSERVICES ---')
            for microservice in row["uSs"]:
                print(f'         |-> {microservice}')
            print(f'         |')
            print(f'         | --- OTHER CONTAINERS ---')
            for container in row["CONTAINERS"]:
                print(f'         |-> {container}')
            print(f'         |')
            print(f'         | --- REMAIN DOCKERFILES ---')
            for df in row["DFs"]:
                print(f'         |-> {df}')

    print(f'        ----------  ----------')


def save_results(url: str, chunks: list[dict[str, int | list[str] | str]], group: bool = False) -> None:
    """
    Save the list of chunks of consecutive commits with same detected microservices and unmatched containers and
    dockerfiles

    :param url: url of the repository
    :param chunks: list of chunks of consecutive commits with same detected microservices and unmatched containers and
    dockerfiles
    :param group: True if you want to group non-consecutive chunks with the same detected microservices, unmatched
    containers and dockerfiles
    :return: None
    """
    name = url.split("/")[-2] + "." + url.split("/")[-1]

    results_file = Path(__file__).parent / f'../data/results/ms_detection/Baresi/{name}_Baresi.csv'

    with open(results_file, 'w+', newline='') as results_output:
        if not group:
            ds_writer = csv.DictWriter(results_output, KEYS)
            ds_writer.writeheader()
            for chunk in chunks:  # type: dict[str, int | list[str] | str]
                if chunk["uSs"] is None or chunk["CONTAINERS"] is None or chunk["DFs"] is None:
                    continue

                row = {"CHUNKS_N": [(chunk["FROM_N"], chunk["TO_N"])],
                       "CHUNKS_H": [(chunk["FROM_H"], chunk["TO_H"])],
                       "uSs": chunk["uSs"],
                       "CONTAINERS": chunk["CONTAINERS"],
                       "DFs": sorted(chunk["DFs"])}

                ds_writer.writerow(row)
        else:  # group
            rows = group_chunks(chunks)

            ds_writer = csv.DictWriter(results_output, KEYS)
            ds_writer.writeheader()
            for row in rows.values():  # type: dict[str, list[tuple] | list[str] | str]
                ds_writer.writerow(row)


def group_chunks(chunks):
    """
    Group non-consecutive chunks with the same set of detected microservices and unmatched containers and dockerfiles

    :param chunks: list of chunks of consecutive commits with same same set of detected microservices and unmatched
    containers and dockerfiles
    :return: dict of chunks with the same docker-compose files
    """
    rows: dict[tuple[frozenset, frozenset, frozenset], dict[str, list[tuple] | list[str] | str]] = dict()
    for chunk in chunks:
        if chunk["uSs"] is None or chunk["CONTAINERS"] is None or chunk["DFs"] is None:
            continue

        if (frozenset(chunk["uSs"]), frozenset(chunk["CONTAINERS"]), frozenset(chunk["DFs"])) not in rows:
            rows[(frozenset(chunk["uSs"]), frozenset(chunk["CONTAINERS"]), frozenset(chunk["DFs"]))] = {
                "CHUNKS_N": [(chunk["FROM_N"], chunk["TO_N"])],
                "CHUNKS_H": [(chunk["FROM_H"], chunk["TO_H"])],
                "uSs": chunk["uSs"],
                "CONTAINERS": chunk["CONTAINERS"],
                "DFs": sorted(chunk["DFs"])}
        else:
            rows[(frozenset(chunk["uSs"]), frozenset(chunk["CONTAINERS"]), frozenset(chunk["DFs"]))]["CHUNKS_N"].append(
                (chunk["FROM_N"], chunk["TO_N"]))
            rows[(frozenset(chunk["uSs"]), frozenset(chunk["CONTAINERS"]), frozenset(chunk["DFs"]))]["CHUNKS_H"].append(
                (chunk["FROM_H"], chunk["TO_H"]))
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

    print_info(' Detecting microservices')
    analyze_dataset()

    print_info(' Terminating script execution')
    stop_time = time.time()
    print_progress(f' Total execution time: {str(timedelta(seconds=(stop_time - start_time)))}')
