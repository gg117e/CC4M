#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script allows to find the list of docker-compose files in every commit and the chosen one, grouped by consecutive
commits with same list, so it is easy to identify the commits that have touched the position/name of docker-compose
files.
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
from lib.CLAIM.src.claim import locate_files, choose_dc, DOCKER_COMPOSE_NAMES
from lib.CLAIM.src.config import COMMIT_DEADLINE
from lib.CLAIM.src.utils.print_utils import print_major_step, print_info, printable_time


KEYS = ["CHUNKS_N", "CHUNKS_H", "DCFs", "DC"]


def analyze_repo(name: str, workdir: str) -> list[dict[str, int | list[str] | str]]:
    """
    Run the analysis of a single repo

    :param name: name of the repository
    :param workdir: path to the working directory of the repository
    :return: list of chunks of consecutive commits with same docker-compose files
    """
    print_major_step(f'## Start repo analysis ({name})')
    results: list[dict[str, int | list[str] | str]] = []

    try:
        repository = Repository(workdir)  # Pydriller: useful to traverse commits history
        git_repo = git.Repo(workdir)  # GitPython: useful to work with repo

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
            last_docker_compose = choose_dc(workdir)

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

        for row in rows.values():
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

    result_dir = project_root / "dest/dc_choice"
    result_dir.mkdir(parents=True, exist_ok=True)
    results_file = result_dir / f"{name}.csv"

    with open(results_file, 'w+', newline='') as results_output:

        if not group:
            ds_writer = csv.DictWriter(results_output, KEYS)
            ds_writer.writeheader()
            for chunk in chunks:
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
            for row in rows.values():

                ds_writer.writerow(row)


def group_chunks(chunks):
    """
    Group non-consecutive chunks with the same set of docker-compose files

    :param chunks: list of chunks of consecutive commits with same docker-compose files
    :return: dict of chunks with the same docker-compose files
    """
    rows: dict[frozenset, dict[str, list[tuple] | list[str] | str]] = dict()
    for chunk in chunks:
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
