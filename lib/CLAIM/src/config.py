#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

Global variables relatives to parameters.
"""


import datetime


""" GitHub token """
GH_TOKEN: str = ''  # FIXME insert GitHub TOKEN

""" Queries to do on GitHub """
QUERIES: list[list[str]] = [  # Split by language in order to not reach the limit of 1000 results per query
                            ["language:Java topic:microservice stars:>=20 forks:>=20",
                             "language:Python topic:microservice stars:>=20 forks:>=20",
                             "language:C# topic:microservice stars:>=20 forks:>=20",
                             "language:Go topic:microservice stars:>=20 forks:>=20",
                             "language:TypeScript topic:microservice stars:>=20 forks:>=20",
                             "language:JavaScript topic:microservice stars:>=20 forks:>=20"],
                            ["language:Java topic:microservices stars:>=20 forks:>=20",
                             "language:Python topic:microservices stars:>=20 forks:>=20",
                             "language:C# topic:microservices stars:>=20 forks:>=20",
                             "language:Go topic:microservices stars:>=20 forks:>=20",
                             "language:TypeScript topic:microservices stars:>=20 forks:>=20",
                             "language:JavaScript topic:microservices stars:>=20 forks:>=20"],
                            ["language:Java topic:microservice-architecture stars:>=20 forks:>=20",
                             "language:Python topic:microservice-architecture stars:>=20 forks:>=20",
                             "language:C# topic:microservice-architecture stars:>=20 forks:>=20",
                             "language:Go topic:microservice-architecture stars:>=20 forks:>=20",
                             "language:TypeScript topic:microservice-architecture stars:>=20 forks:>=20",
                             "language:JavaScript topic:microservice-architecture stars:>=20 forks:>=20"],
                            ["language:Java topic:microservices-architecture stars:>=20 forks:>=20",
                             "language:Python topic:microservices-architecture stars:>=20 forks:>=20",
                             "language:C# topic:microservices-architecture stars:>=20 forks:>=20",
                             "language:Go topic:microservices-architecture stars:>=20 forks:>=20",
                             "language:TypeScript topic:microservices-architecture stars:>=20 forks:>=20",
                             "language:JavaScript topic:microservices-architecture stars:>=20 forks:>=20"],
                            ["language:Java microservice stars:>=200 forks:>=200",
                             "language:Python microservice stars:>=200 forks:>=200",
                             "language:C# microservice stars:>=200 forks:>=200",
                             "language:Go microservice stars:>=200 forks:>=200",
                             "language:TypeScript microservice stars:>=200 forks:>=200",
                             "language:JavaScript microservice stars:>=200 forks:>=200"]]

""" Repo to skip for some reason """
REPO_TO_SKIP: list[str] = ['https://github.com/oracle/coherence']  # this repo make git clone crash (too big?)

""" Minimum and maximum number of commit """
COMMIT_THRESHOLDS: tuple[int, int] = (250, 1600)

""" Minimum number of contributors """
CONTRIBUTORS_THRESHOLD: tuple[int, int] = (5, 30)

""" The day until which the commits should be considered (excluded) """
COMMIT_DEADLINE: datetime = datetime.datetime(2024, 2, 3)
