#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to find the list of microservices in every commit, grouped by consecutive commits with same list, so
it is easy to identify the commits that have touched the microservices list.
"""

import csv
import traceback
import sys
import dateutil.utils
from datetime import timedelta
from pathlib import Path

import dateutil
import git  # GitPython
from pydriller import Repository  # PyDriller

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))
from lib.CLAIM.src.claim import (dc_collect_services, process_services, _locate_dockerfiles, _container_to_microservice,
                       Microservice, _groups_dockerfiles)
from lib.CLAIM.src.config import COMMIT_DEADLINE
from lib.CLAIM.src.utils.print_utils import printable_time, print_major_step

KEYS = ["CHUNKS_N", "CHUNKS_H", "uSs", "CONTAINERS", "DFs"]


def analyze_repo(name: str, workdir: str) -> list[dict[str, int | list[str] | str]]:
    """
    Run the analysis of a single repo

    :param name: name of the repository
    :param workdir: path to the working directory of the repository
    :return: list of chunks of consecutive commits with same detected microservices and unmatched containers and
    dockerfiles
    """
    print_major_step(f'## Start repo analysis ({name})')
    results: list[dict[str, int | list[str] | str]] = []

    try:
        repository = Repository(workdir)  # Pydriller: useful to traverse commits history
        git_repo = git.Repo(workdir)  # GitPython: useful to work with repo

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

            with open(project_root / f'dest/dc_choice/{name}.csv') as dataset:
                chunks = csv.DictReader(dataset, delimiter=',')

                for chunk in chunks:
                    if eval(chunk['CHUNKS_N'])[0][0] <= count:
                        docker_compose = chunk["DC"]
                    else:
                        break

            microservices, containers, dfs = set(), set(), set()
            if docker_compose:
                rslts = dc_collect_services(Path(workdir).joinpath(docker_compose))
                rslts = process_services(rslts, Path(workdir))

                if rslts:
                    rslts.sort(key=lambda x: len(x.image) if x.image is not None else len(x.container_name), reverse=True)
                    local_dfs = _locate_dockerfiles(workdir)
                    dfs = local_dfs.copy()
                    _groups_dockerfiles(dfs)
                    dfs = set(dfs)

                    for rslt in rslts:
                        microservice = _container_to_microservice(rslt, name.split('.')[0], name.split('.')[1],
                                                                  workdir, local_dfs)
                        if microservice:
                            microservices.add(microservice)
                        else:
                            containers.add(rslt)

                    for microservice in microservices:
                        if microservice.confidence in [Microservice.Confidence.BUILD_VERIFIED,
                                                       Microservice.Confidence.BUILD_IMAGE_MATCHED,
                                                       Microservice.Confidence.BUILD_NAME_MATCHED]:
                            if microservice.build.dockerfile in dfs:
                                dfs.remove(microservice.build.dockerfile)

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
            print(f'         | --- MICROSERVICES ---')
            for microservice in chunk["uSs"]:
                print(f'         |-> {microservice}')
            print(f'         |')
            print(f'         | --- OTHER CONTAINERS ---')
            for container in chunk["CONTAINERS"]:
                print(f'         |-> {container}')
            print(f'         |')
            print(f'         | --- REMAIN DOCKERFILES ---')
            for df in chunk["DFs"]:
                print(f'         |-> {df}')
    else:
        rows = group_chunks(chunks)

        for row in rows.values():
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

    result_dir = project_root / "dest/ms_detection"
    result_dir.mkdir(parents=True, exist_ok=True)
    results_file = result_dir / f"{name}.csv"

    with open(results_file, 'w+', newline='') as results_output:
        if not group:
            ds_writer = csv.DictWriter(results_output, KEYS)
            ds_writer.writeheader()
            for chunk in chunks:
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
            for row in rows.values():
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
