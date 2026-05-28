#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

CLAIM: a Lightweight Approach for Identifying Microservices in Dockerized Environment

This small library allows to:

1) handle docker-compose files as if they are processed by Docker Compose and then to collect and process the services
listed in them.
This is achieved by following the included docker-compose files recursively to the "leaf" ones, by extending the
services recursively to the "base" ones (either if internal to the docker-compose or from an external docker-compose)
and by interpolating the env variables from the .env files.
All the process is made following the indication from the official Docker Compose documentation (when available, or in
very few cases, documented along the code, basing to empirical tests).
All the process is addressed to the collection of "image" and "build" information of the services, but it is extremely
easy to expand to other keys.

2) find the docker-compose files in a project accordingly to some template standard names and choose one accordingly to
some rules about the folder contained in its path and the possible prefix/suffix present in its filename.
All the rules, listed in the docstring of the functions, have the aim to choose the docker-compose file that has the
highest probability to be that one that is relative to the project in its entirety (and so lists the container of all
microservices) and not one relative only to a component or to some other aspect.
These rules have been derived from an empirical observation of a certain number of repositories, so it is not
bulletproof (even if it is quite general to select the correct docker-compose in most of the repositories).

3) detect which containers are effectively microservices and which are not accordingly some rules. All the rules are
listed and described better in the docstring of the functions, but anyway as a general idea the workflow is: if there is
a specified Dockerfile then it is a microservice; after having extracted the name of the possible microservice from the
image name first and container name then, if exists a Dockerfile that in the path has that name, then we have a match
and it is a microservice. Only Dockerfile that copied some effective user-defined code are considered (so are excluded
those that copies only .sql and .sh files for example).
These rules have been derived from an empirical observation of a certain number of repositories, so it is not
bulletproof (even if it is quite general to discern microservices in most of the repositories).

--------------------

The main method is claim(), which returns the set of identified microservices by calling:
- choose_dc() method, that chooses the more probably right docker-compose;
- process_services() method, that elaborates the selected docker-compose in order to extract the containers and their
information;
- determine_microservices() method, that determines the microservices.

Other "exposed" methods are:
- check_dc_presence(), that checks the presence of at least one acceptable docker-compose;
- dc_collect_services(), that collects all the containers set by a docker-compose.
"""
import itertools
import logging
import math
import os
import re
from enum import Enum
from pathlib import Path
from typing import TypeAlias, NamedTuple
from urllib.parse import urlparse

import dockerfile
import yaml
from dotenv import dotenv_values
from parameter_expansion import expand


########################
# CONSTANTS DEFINITION #
########################

""" Docker-compose name to search for """
DOCKER_COMPOSE_NAMES: list[str] = ['*compose*.yml', '*compose*.yaml', '*docker-compose*.yml', '*docker-compose*.yaml']

""" Dockerfile name to search for """
DOCKERFILE_NAMES: list[str] = ['*Dockerfile*']

""" Key of interest for services in the docker-compose file """
KEY_OF_INTEREST: list[str] = ['image', 'build', 'container_name']

""" Prefix and suffix allowed in docker-compose files ordered by preference """
DC_AFFIXES_WHITELIST = ['services', 'base', 'dev', 'build', 'stack', 'prod', 'stable', 'deploy', 'test']

""" Prefix and suffix never allowed in docker-compose files """
DC_AFFIXES_BLACKLIST = ['infra', 'override']

""" Keyword for validating folder in which docker-compose files can be, ordered by preference """
DC_DIR_KEYWORD = ['docker', 'compose', 'swarm',  # docker
                  'src', 'services',  # code directory
                  'dev', 'test', 'staging', 'deploy', 'integration', 'release', 'prod',  # development phases
                  'iac', 'saas', 'devops', 'setup', 'script', 'complete', 'etc']  # miscellaneous

""" Folder to discard when searching Dockerfile """
DF_DIR_BLACKLIST = ['vendor', 'external', 'example', 'demo']

""" Common extension of files with "Dockerfile" substring that are not Dockerfile """
DF_EXT_BLACKLIST = ['.sh', '.ps1', '.nanowin', '.txt']

""" Common affixes for microservices container name """
SERVICE_AFFIXES = ['srv', 'microservice', 'service']

""" Common extension of configuration/script files used in Dockerfile """
CONFIG_EXT = ['.sh', '.xml', '.txt', '.yaml', '.yml', '.conf', '.config', '.cnf', '.cfg', '.cf', '.sql', '.crt', '.key']

DC_type: TypeAlias = None | bool | str | float | int | list['DC_type'] | dict[str, 'DC_type']


####################
# CLASS DEFINITION #
####################

class Build(NamedTuple):
    """ Represent a build of an image through a Dockerfile.
    The Dockerfile attribute is relative to the context (when it is not an absolute path) """
    context: str = None
    rel_dockerfile: str = 'Dockerfile'

    remote: bool = False
    absolute: bool = False

    @property
    def is_local(self) -> bool:
        """
        Check if the Dockerfile is local or remote/referenced with absolute path (so not recoverable)

        :return: True if the Dockerfile is local, False otherwise
        """
        return not self.remote and not self.absolute and not os.path.isabs(self.rel_dockerfile)

    @property
    def dockerfile(self) -> str | None:
        """
        Construct the Dockerfile path

        :return: the Dockerfile path or None if the Dockerfile is not local
        """
        if self.is_local:
            if self.context is not None:
                return str(Path(self.context).joinpath(self.rel_dockerfile))
            else:
                return self.rel_dockerfile
        else:
            return None


class Container(NamedTuple):
    """ Represent a container found in a docker-file """
    image: str = None
    build: Build = None
    container_name: str = None


class Microservice(NamedTuple):
    """ Represent a detected microservice """

    class Confidence(Enum):
        """
        Represent the level of confidence that the microservice is effectively a microservice
        """
        BUILD_VERIFIED = 1  # The microservice is built via docker-compose and the Dockerfile has been found
        BUILD_UNVERIFIED = 2  # The microservice is built via docker-compose but the Dockerfile hasn't been found
        BUILD_IMAGE_MATCHED = 4  # The microservice has been matched with a Dockerfile through its image name
        BUILD_NAME_MATCHED = 8  # The microservice has been matched with a Dockerfile through its container name

    name: str = None
    build: Build = None
    confidence: Confidence = None


##################
# HELPER METHODS #
##################

def locate_files(curr_folder: str, filename: str) -> list[str]:
    """
    Locate all the non-empty files corresponding to a given filename in a folder's subtree

    :param curr_folder: folder where to look for the file(s)
    :param filename: name of the file to find
    :return: the path of all the found files relative to the current folder
    """
    files = []
    try:
        for df in Path(curr_folder).rglob(filename):
            if df.is_file():
                if df.stat().st_size > 1:  # if it is not empty (N.B. some empty files weights 1 byte)
                    files.append((str(df).split(curr_folder)[-1])[1:])
    except OSError:
        # from Path documentation:
        # Many of these methods can raise an OSError if a system call fails (for example because the path doesn't exist)
        pass

    return files


####################################
# DOCKER-COMPOSE SELECTION METHODS #
####################################

def choose_dc(repo: str) -> str | None:
    """
    Select in a project the best docker-compose file (if an acceptable one exists) for its analysis.
    The aim is to select a docker-compose that is used to run all the microservices and not one that is used, for
    example to run a single components or only the technological infrastructure.

    1) As first step all the docker-compose in the repo with a "default" name (according to the docker documentation)
    possibly integrated with some prefix/suffix
    2) As second step all the found docker-compose are grouped and ordered by preferable path (according to a set of
    rules listed in the documentation of "_dcs_filter_group_order_by_path" function)
    3) As third step all the docker-composes groups with same path are processed in order until an acceptable
    docker-compose is found and in case of siblings docker-composes acceptable, is taken that one that accordingly a set
    of rules (listed in ...) has more chance to be the most preferable one

    :param repo: repository base directory
    :return: the docker-compose file selected for analysis or None if none is acceptable
    """
    dcs = []
    for dc_name in DOCKER_COMPOSE_NAMES:
        dcs.extend(locate_files(repo, dc_name))

    if not len(dcs):
        return None

    for sibling_dcs in _dcs_filter_group_order_by_path(dcs):
        max_priority = _dc_priority_by_filename(min(sibling_dcs, key=_dc_priority_by_filename))

        if max_priority is math.inf:
            continue  # no acceptable docker-compose, go to the next groups of sibling dcs

        preferred_dcs = [dc for dc in sibling_dcs if _dc_priority_by_filename(dc) == max_priority]

        if len(preferred_dcs) == 1:
            return preferred_dcs[0]
        else:
            return str(min(preferred_dcs, key=len))  # if equality persists, take the shortest one deterministically
            # src/docker-compose.base.yml > src/docker-compose.base.mysql.yml

    return None  # no acceptable docker-compose found


def _dcs_filter_group_order_by_path(dcs: list[str]) -> list[list[str]]:
    """
    Some paths are preferred to others (e.g. docker-compose.yml > dev/docker-compose.yml > deploy/doker-compose.yml).
    This function give a priority to each path of a list and groups the docker-compose files with the same directories
    path, returning a list of groups of docker-compose files.
    The docker-compose should have a path containing only folders with "standard" names (like "docker", "deploy", etc.),
    so every docker-compose that is contained in a folder that doesn't contain (as case-insensitive substring) any
    keyword, is discarded. This allows to ignore docker-compose files that are not related to the whole project, but
    only to a parts (e.g. a single microservice), that is a quite widespread habit.

    e.g. deploy/docker/docker-compose.yml (YES)     | src/microservice_name/docker-compose.yml (NO)
         microservices_name/docker-compose.yml (NO) | .docker-compose/docker-compose.yml (YES)

    The priority is assigned starting from the most significant folder to the lowest one in the path and then all the
    paths are ordered following a lexicographic order (so can happen that a longer path came before a shorter one)

    The keyword priorities are the following (in order of decreasing priority):
     - docker related keyword: docker, compose and swarm (N.B. they implicitly  include also docker-compose)
     - code directory: src and services (N.B. they implicitly  include also microservices)
     - development phases (from the earliest to the latest): dev, test, staging, deploy, integration, release and prod
     (N.B. they implicitly include also development, testing, integration test, deployment(s), continuous integration
     and production)
     - miscellaneous keyword: iac (infrastructure-as-code), saas (software-as-a-service), setup, script, devops,
     complete and "etc"

    :param dcs: list of docker-compose files
    :return: docker-compose files grouped by path and ordered by most priority path
    """
    groups = {}

    for dc in dcs:
        code_path = ''
        folders = dc.split(os.sep)[0:-1]

        for depth, folder in enumerate(folders):
            for index, keyword in enumerate(DC_DIR_KEYWORD):
                if keyword in folder.lower():
                    code_path += chr(ord('a') + index)
                    break  # stop looking for keys in folder

            if len(code_path) != depth + 1:
                break  # at least one folder hasn't any keyword

        else:  # the path is good
            if code_path not in groups:
                groups[code_path] = []

            groups[code_path].append(dc)

    return [groups[code] for code in sorted(groups.keys())]


def _dc_priority_by_filename(dc: str) -> float:
    """
    In the same path (i.e. siblings docker-compose files), some are preferred to others. This function give to a
    docker-compose file a priority (less is preferable) basing on the prefix/suffix that it presents in the filename.
    The affix can be separated from the main part of the name (i.e. compose or docker-compose) with a dot, a dash, an
    underscore or even nothing, since it is only controlled the presence of the substring in the name. And more: this
    function is case-insensitive.

    Priority levels:
     - 0: docker-compose
     - 1: docker-compose_microservices | docker-compose_services
     - 2: docker-compose_base
     - 3: docker-compose_dev | docker-compose_development
     - 4: docker-compose_build
     - 5: docker-compose_stack
     - 6: docker-compose_prod | docker-compose_production
     - 7: docker-compose_stable
     - 8: docker-compose_deploy | docker-compose_deployment
     - 9: docker-compose_test | docker-compose_testing

     - ∞: docker-composes with every other affixes and with keywords from the blacklist (override, infra,
     infrastructure)even if they have keywords from the whitelist (e.g. docker-compose_base_override or
     docker-compose_microservices_infrastructure)

     (N.B. all the examples are lowercase and underscore-separated, but it is not relevant)

    :param dc: docker-compose filename or path
    :return: the priority level (less is preferable)
    """
    dc_name = dc.split(os.sep)[-1].lower()

    if dc_name in [name.replace('*', '') for name in DOCKER_COMPOSE_NAMES]:  # e.g. docker-compose.yaml
        return 0

    if any(affix in dc_name for affix in DC_AFFIXES_BLACKLIST):
        return math.inf  # unacceptable docker-compose files (e.g. docker-compose.override.yaml)

    for index, affix in enumerate(DC_AFFIXES_WHITELIST):
        if affix in dc_name:  # e.g. docker-compose.prod.yml|docker-compose-dev.yml|compose_test.yml|base-compose.yml
            return index + 1  # e.g. docker-compose.base.yml < compose.prod.yaml

    return math.inf  # every other (unacceptable) docker-compose files (e.g. docker-compose.example.yaml)


def check_dc_presence(repo: str) -> bool:
    """
    Check if in a project there is an acceptable docker-compose file

    :param repo: repository base directory
    :return: True if there is an acceptable docker-compose, False otherwise
    """

    return True if choose_dc(repo) else False


###############################################
# DOCKER-COMPOSE CONTAINER EXTRACTION METHODS #
###############################################

def dc_collect_services(dc_path: Path, proj_dir: Path = None, env_files: list[Path] | str = None) -> list[dict] | None:
    """
    Collect docker-compose services (intended as docker nodes) walking across all included docker-composes recursively
    and resolving all the occurrences of environment variables

    :param dc_path: docker-compose file's path
    :param proj_dir: base path to resolve relative paths presents in the docker-compose file
    :param env_files: .env files to use
    :return: list of the services (as dicts with all their infos); return None if something goes wrong durin the
    collection of services, e.g. is impossible to extends a service or the docker-compose file is not a valid YAML file
    """
    if env_files is None:  # if not set, set to default
        env_files = ['.env']
    elif isinstance(env_files, str):    # if only one, listify it
        env_files = [env_files]

    if proj_dir is None:  # if not set, set to default
        proj_dir = dc_path.parent

    services = []
    with open(dc_path) as dc_file:
        try:
            dc = yaml.load(dc_file, Loader=yaml.FullLoader)  # load docker-compose file

            if not dc:
                return None

            # Step 1: get the env variables
            # [https://docs.docker.com/compose/environment-variables/env-file/]
            env: dict = {}  # dictionary of env variables
            for env_file in env_files:
                if Path.exists(proj_dir.joinpath(env_file)):
                    env.update(
                        dotenv_values(proj_dir.joinpath(env_file))  # read the env files
                    )

            # Step 2: substitute the env variables
            if env:
                dc = _interpolate_with_env(dc, env)

            # Step 3: recurse on inclusions (recursion step)
            # [https://docs.docker.com/compose/compose-file/14-include/]
            # [https://docs.docker.com/compose/multiple-compose-files/include/]
            if 'include' in dc:
                for incl in dc['include']:
                    if isinstance(incl, str):  # short syntax case
                        services.extend(  # iterate
                            dc_collect_services(proj_dir.joinpath(incl))
                        )
                    if isinstance(incl, dict):  # long syntax case
                        incl_proj_dir = \
                            proj_dir.joinpath(incl['project_directory']) if 'project_directory' in incl else None
                        incl_env_files = incl['env_file'] if 'env_file' in incl else None

                        if isinstance(incl['path'], str):
                            services.extend(  # iterate
                                dc_collect_services(proj_dir.joinpath(incl['path']), incl_proj_dir, incl_env_files)
                            )
                        if isinstance(incl['path'], list):
                            for sub_incl in incl['path']:
                                services.extend(  # iterate
                                    dc_collect_services(proj_dir.joinpath(sub_incl), incl_proj_dir, incl_env_files)
                                )

            # Step 4: collect services (step 0 of recursion)
            if 'services' in dc:
                for name, service in dc['services'].items():
                    # resolve service extension
                    extended_service = _extends_service(service, proj_dir, dc)

                    # remove keys that are not of interest
                    collectable_service = {k: v for k, v in extended_service.items() if k in KEY_OF_INTEREST}

                    # add information about docker-compose project directory and service name
                    collectable_service['proj_dir'] = str(proj_dir)
                    collectable_service['service_name'] = name

                    # collect
                    services.append(collectable_service)

        except Exception as e:
            logging.info("Error during collection of docker-compose services", exc_info=e)
            return None

    return services


def _extends_service(service: dict[DC_type], proj_dir: Path, dc: DC_type) -> dict[DC_type]:
    """
    If the service inherit from another service, complete the service definition with the information from the inherited
    service (internal to the docker-compose or from an external one). The extension is recursive in order to explicit
    all the information.

    This extension respect the rules listed at https://docs.docker.com/compose/multiple-compose-files/extends/ and
    https://docs.docker.com/compose/compose-file/05-services/#extends

    :param service: service to extend
    :param proj_dir: current project directory respect to which resolve the relative path
    :param dc: current docker-compose content
    :return: extended service
    :raise Exception: if it is impossible to extend a service because: i) the target base service doesn't exist, ii) the
    referenced external docker-compose doesn't exist or iii) the external docker-compose is referenced with an absolute
    path
    """
    extended_service = service.copy()
    if 'extends' in service:
        # Apparently base services can be taken only from the same docker-compose or an explicit specified
        # docker-compose (in other words they cannot be taken implicitly from one of the included docker-compose).
        # It doesn't exist an explicit documentation of this because the "include" feature is quite new (this statement
        # derive from empirical tests) and for the same reason, this aspect could change in the future.
        # Anyway this function, in this form, does not consider this case.
        try:
            if 'file' in service['extends']:  # external docker-compose
                if not os.path.isabs(service['extends']['file']):  # relative path
                    with (open(proj_dir.joinpath(service['extends']['file'])) as dc_file):
                        dc = yaml.load(dc_file, Loader=yaml.FullLoader)  # load docker-compose file

                        if 'services' in dc and service['extends']['service'] in dc['services']:
                            target_service = dc['services'][service['extends']['service']]
                            extended_target_service = \
                                _extends_service(target_service, proj_dir.joinpath(service['extends']['file']), dc)
                            extended_service = _merge_services(service, extended_target_service)
                        else:  # target base service not found
                            raise Exception(f'Target base service "{service["extends"]["service"]}" cannot be found in '
                                            f'{proj_dir.joinpath(service["extends"]["file"])}')
                else:  # absolute path
                    raise Exception(f'Absolute path for external docker-compose are not supported')
            else:  # self docker-compose
                if service['extends']['service'] in dc['services']:
                    target_service = dc['services'][service['extends']['service']]
                    extended_target_service = _extends_service(target_service, proj_dir, dc)
                    extended_service = _merge_services(service, extended_target_service)
                else:  # target base service not found
                    raise Exception(f'Target base service "{service["extends"]["service"]}" cannot be found in the '
                                    f'current docker-compose {proj_dir.joinpath("docker-compose*")}')

        except Exception as e:
            logging.info("Error during the extension of a service", exc_info=e)
            raise e

    return extended_service


def _merge_services(main_service: dict[DC_type], referenced_service: dict[DC_type]) -> dict[DC_type]:
    """
    Merge the definition of two services following the rules listed at
    https://docs.docker.com/compose/compose-file/05-services/#extends

    :param main_service: main service to merge with referenced service
    :param referenced_service: referenced service to merge in main service
    :return: the merging result service
    """
    merged_service = main_service.copy()
    for key, ref_value in referenced_service.items():
        if isinstance(ref_value, dict):  # mapping case from documentation
            if key not in main_service:
                merged_service[key] = ref_value.copy()
            else:
                # in case of double key definition, maps are merged and
                # in case of key duplication main has the precedence over referenced
                main_value = main_service[key]
                merged_service[key] = main_value.copy()
                merged_service[key].update({item_key: item_value for item_key, item_value in ref_value.items() if
                                            item_key not in main_value})

        elif key in ['devices', 'volumes']:  # special case documented in which sequence is treated as map
            # FIXME not clear what happens when volumes are specified with long syntax, so let's consider them sequences
            if key not in main_service:
                merged_service[key] = ref_value.copy()
            else:
                # in case of double key definition, lists are merged and
                # in case of target path duplication main has the precedence over referenced
                main_value = main_service[key]
                merged_service[key] = main_value.copy()
                main_targets = [target.split(':')[1] for target in main_value]
                for elem in ref_value:  
                    if elem.split(':')[1] not in main_targets:
                        merged_service[key].append(elem)

        elif isinstance(ref_value, list):  # sequence case from documentation
            if key not in main_service:
                merged_service[key] = ref_value.copy()
            else:  # in case of double key definition lists are merged with main values coming first
                main_value = main_service[key]
                merged_service[key] = main_value.copy()
                if key not in ['dns', 'dns_search', 'env_file', 'tmpfs']:  # standard behavior
                    merged_service[key].extend(item for item in ref_value if item not in main_value)
                else:  # special case documented in documentation for dns, dns_search, env_file, tmpfs
                    merged_service[key].append(ref_value)

        else:  # scalar case from documentation
            if key not in main_service:  # in case of double key definition main has the precedence over referenced
                merged_service[key] = ref_value.copy()

    merged_service.pop('extends', None)  # remove extends because no longer needed
    return merged_service


def _interpolate_with_env(data: DC_type, env: dict[str, str]) -> DC_type:
    """
    Given a JSON object interpolate it in every component with the values of env variables passed.

    This interpolation respects the rules listed at https://docs.docker.com/compose/compose-file/12-interpolation/

    :param data: JSON object to interpolate
    :param env: dictionary of env variables
    :return: JSON object interpolated
    """
    if isinstance(data, str):
        if '$$' in data:  # parameter_expansion.expand doesn't consider $$, so this workaround handles this situation
            meta_env_vars = re.findall("\$\$[A-Z0-9_]+", data)
            data_fragments = re.split("\$\$[A-Z0-9_]+", data)
            interpolated_data = [''] * (len(meta_env_vars) + len(data_fragments))
            interpolated_data[::2] = [expand(data_fragment, env) for data_fragment in data_fragments]
            interpolated_data[1::2] = [meta_env_var[1:] for meta_env_var in meta_env_vars]

            return ''.join(interpolated_data)
        else:
            return expand(data, env)
    elif isinstance(data, dict):
        return {k: _interpolate_with_env(v, env) for k, v in data.items()}
    elif isinstance(data, list):
        return [_interpolate_with_env(v, env) for v in data]
    else:
        return data


def process_services(services: list[DC_type] | None, proj_base_dir: Path) -> list[Container] | None:
    """
    Process collected services in order to collect only infos of interest regarding "image", "build" and "name" parts:
     - of the image will be removed tag and digest;
     - of the build information will be reconstructed the context and Dockerfile path respect to the project base dir
     (it support the specification of an external Dockerfile, but not yet the inline specification of Dockerfile)
     - the container_name is taken as it is if it is present, otherwise the name of the docker service is taken

    This processing follow the rules described at https://docs.docker.com/compose/compose-file/05-services/#image and
    https://docs.docker.com/compose/compose-file/build/

    :param services: collection of services to process
    :param proj_base_dir: project base directory, relative to which make all build path
    :return: collection of processed containers; None if None has passed as services or some info can't be processed
    """
    if services is None:
        return None

    containers: list[Container] = []
    try:
        for service in services:
            image, name, build = None, None, None

            if 'image' in service and service['image'] is not None:  # process image
                image = service['image'].split(':')[0]

            if 'container_name' in service and service['container_name'] is not None:  # process container name
                name = service['container_name']
            else:
                name = service['service_name']

            if 'build' in service and service['build'] is not None:  # process build
                if isinstance(service['build'], str):
                    if urlparse(service['build']).scheme:  # URL
                        build = Build(service['build'], remote=True)
                    elif os.path.isabs(service['build']):  # absolute path
                        build = Build(service['build'], absolute=True)
                    else:  # relative path
                        # join it the project base dir, then remove project base dir prefix
                        build = Build(os.path.relpath(
                            Path(service['proj_dir']).joinpath(service['build']), proj_base_dir))
                else:
                    docker_file = service['build']['dockerfile'] if 'dockerfile' in service['build'] else 'Dockerfile'

                    if 'context' in service['build']:
                        if urlparse(service['build']['context']).scheme:  # URL
                            build = Build(service['build'], docker_file, remote=True)
                        elif os.path.isabs(service['build']['context']):  # absolute path
                            build = Build(service['build'], docker_file, absolute=True)
                        else:  # relative path
                            build = Build(
                                        os.path.relpath(Path(service['proj_dir']).joinpath(service['build']['context']),
                                                        proj_base_dir),
                                        docker_file)
                    else:  # default context
                        build = Build(os.path.relpath(Path(service['proj_dir']).joinpath('..'), proj_base_dir),
                                      docker_file)

            containers.append(Container(image, build, name))

        return containers

    except Exception as e:
        logging.info("Error during processing of docker-compose services", exc_info=e)
        return None


##################################
# MICROSERVICE DETECTION METHODS #
##################################

def determine_microservices(user: str, repo: str, repo_path: str, containers: list[Container],
                            confidence: Microservice.Confidence = Microservice.Confidence.BUILD_NAME_MATCHED) \
        -> set[Microservice]:
    """
    Given a list of containers filter and transform them in order to return a list of the microservices contained.

    :param user: repo's user owner
    :param repo: repo's name
    :param repo_path: repository base directory
    :param containers: list of containers to analyze
    :param confidence: level of confidence wanted in the detection of microservices. Default is all available levels
    until NAME_MATCHED
    :return: the set of detected microservices
    """
    microservices: set[Microservice] = set()

    dockerfiles = _locate_dockerfiles(repo_path)

    if containers is not None:
        # order containers by image name/container name in order to start from the longest one to prevent possible
        # indecision if some of them are substring of others (thanks to the fact that once a dockerfile is matched, it
        # will be removed from the list)
        containers.sort(key=lambda x: len(x.image) if x.image is not None else len(x.container_name), reverse=True)

        for container in containers:
            microservice = _container_to_microservice(container, user, repo, repo_path, dockerfiles, confidence)
            if microservice is not None:
                microservices.add(microservice)

    return microservices


def _container_to_microservice(container: Container, user: str, repo: str, repo_path: str, dockerfiles: list[str],
                               confidence: Microservice.Confidence = Microservice.Confidence.BUILD_NAME_MATCHED) \
        -> Microservice | None:
    """
    Check if a container is a microservice or not.
    A container is considered a microservice if:
     - it explicits the Dockerfile and this copies user defined code into the container
     - it explicits the Dockerfile, but this is not in the repository
     - it does not explicit the Dockerfile, but it has been matched with one (that copies user defined code into the
     container) basing on the image's name
     - it does not explicit the Dockerfile, but it has been matched with one (that copies user defined code into the
     container) basing on the container's name

    :param container:
    :param repo_path:
    :param dockerfiles: list of available dockerfiles
    :param confidence: level of confidence wanted in the detection of microservices. Default is all available levels
    until NAME_MATCHED
    :return: the microservice if the container is a microservice (basing on the rules), None otherwise
    """
    local_dockerfiles = dockerfiles.copy()

    if confidence.value >= Microservice.Confidence.BUILD_VERIFIED.value:
        if container.build is not None and container.build.is_local:  # explicit Dockerfile build
            build = container.build
            verified = True if container.build.dockerfile in local_dockerfiles else False
            name = container.container_name

            if verified:
                if _check_code_presence_df(repo_path + '/' + container.build.dockerfile):
                    dockerfiles.remove(container.build.dockerfile)
                    return Microservice(name, build, Microservice.Confidence.BUILD_VERIFIED)
            else:
                if confidence.value >= Microservice.Confidence.BUILD_UNVERIFIED.value:
                    return Microservice(name, build, Microservice.Confidence.BUILD_UNVERIFIED)
        else:
            if confidence.value >= Microservice.Confidence.BUILD_IMAGE_MATCHED.value:
                _groups_dockerfiles(local_dockerfiles)

                if container.image is not None and len(local_dockerfiles):  # it's a real ("not abstract") container
                    ms_candidate_names = _get_ms_from_image(container.image, user, repo)

                    matched_df = _match_ms_df(repo_path, ms_candidate_names, local_dockerfiles)
                    if matched_df:
                        dockerfiles.remove(matched_df)
                        return Microservice(container.container_name, Build(rel_dockerfile=matched_df),
                                            Microservice.Confidence.BUILD_IMAGE_MATCHED)
                    else:
                        if confidence.value >= Microservice.Confidence.BUILD_NAME_MATCHED.value:
                            ms_name = _get_ms_from_name(container.container_name)

                            matched_df = _match_ms_df(repo_path, ms_name, local_dockerfiles)
                            if matched_df:
                                dockerfiles.remove(matched_df)
                                return Microservice(container.container_name, Build(rel_dockerfile=matched_df),
                                                    Microservice.Confidence.BUILD_NAME_MATCHED)

    return None


def _match_ms_df(repo_path: str, ms_names: set[str], dockerfiles: list[str]) -> str | None:
    """
    Match a microservice to a Dockerfile in a set of Dockerfiles basing on the presence in the path of one from a set
    of possible name for the microservice.

    :param repo_path: repository base directory
    :param ms_names: list of possible microservice's name
    :param dockerfiles: list of available dockerfiles
    :return: the path of the matched Dockerfile if it has been possible to do a unique match, None otherwise
    """
    # sort possible names by length, so starting from the longest ones we prevent possible multiple match with the
    # shortest ones.
    # e.g. "RepoName-api" will match with "src/RepoName-api/Dockerfile" before than "api" have indecision
    # between "src/RepoName-api/Dockerfile" and "mysql/api/Dockerfile"
    ms_names = list(ms_names)
    ms_names.sort(key=len, reverse=True)

    for ms_name in ms_names:
        candidate_dockerfiles = [df for df in dockerfiles if ms_name in df.lower().rsplit('/', 1)[0]]

        if len(candidate_dockerfiles) == 1:  # no doubt
            if _check_code_presence_df(repo_path + '/' + candidate_dockerfiles[0]):
                return candidate_dockerfiles[0]

    return None


def _get_ms_from_image(image: str, user: str, repo: str) -> set[str]:
    """
    Get a set of possible names of a microservice from the image, even if the image is in a form that include user's
    name, repo's name or registry.
    It can extract microservice's name from image in the form:
    ({registry or dockerHubUser}/)?(user[-_/])?(repo[-_/])?microservice

    :param image: image's name
    :param user: user's name
    :param repo: repo's name
    :return: microservices name extrapolated
    """
    image = image.lower()
    user = user.lower()
    repo = repo.lower()

    names = set()

    if '/' in image:
        image = image.split('/', 1)[1]

    names.add(image)

    if user in image:
        names.add(re.sub(f'{user}[-_/]', '', image))

    if repo in image:
        names.add(re.sub(f'{repo}[-_/]', '', image))

    if user in image and repo in image:
        names.add(re.sub(f'{user}[-_/]', '', re.sub(f'{repo}[-_/]', '', image)))

    return names


def _get_ms_from_name(name: str) -> set[str]:
    """
    Get a set of possible names of a microservice from the container name, even if the name include generic suffix.
    It can extract microservice's name from name in the form:
    ({srv, service, microservice}[-_/])?microservice([-_/]{srv, service, microservice})?

    :param name: container's name
    :return: microservices name extrapolated
    """
    name = name.lower()

    names = set()

    names.add(name)

    for affix in SERVICE_AFFIXES:
        if name.startswith(affix):
            name = re.sub(f'{affix}[-_/]', '', name)
            names.add(name)
            return names

    for affix in SERVICE_AFFIXES:
        if name.endswith(affix):
            name = re.sub(f'[-_/]{affix}', '', name)
            names.add(name)
            return names

    return names


def _locate_dockerfiles(repo: str) -> list[str]:
    """
    Locate all the Dockerfile in the repository used to build real container with code copied into.
    The steps it runs are:
    - It searches for Dockerfile with standard name and possible affixes: *Dockerfile*.
    - In order to filter possible non-Dockerfile files that include this pattern, it will delete the common files that
    have common extensions like .sh, .ps1, .nanowin, .txt
    - It removes Dockerfile surely relative to external services based on their path (if they are contained in folder
    like 'vendor' or 'external')
    - It removes Dockerfile surely relative to example/demo based on their path (if they are contained in folder
    like 'example' or 'demo')

    :param repo: base dir f the repository
    :return: list of Dockerfiles
    """
    dockerfiles: list[str] = []

    for dockerfile_name in DOCKERFILE_NAMES:
        dockerfiles.extend(locate_files(repo, dockerfile_name))

    # Filter false Dockerfile
    dockerfiles = [df for df in dockerfiles if not df.endswith(tuple(DF_EXT_BLACKLIST))]

    # Filter Dockerfile relative to external services
    dockerfiles = [df for df in dockerfiles if not any(df_dir for df_dir in DF_DIR_BLACKLIST if df_dir in df)]

    return dockerfiles


def _groups_dockerfiles(dockerfiles: list[str]):
    """
    Remove siblings Dockerfiles keeping only one of them (the one with the shortest filename, so if it is present
    'Dockerfile' without affixes are kept)

    :param dockerfiles: list of Dockerfiles
    """
    if len(dockerfiles):
        for df1, df2 in itertools.combinations(dockerfiles.copy(), 2):
            if df1.split('/')[0:-1] == df2.split('/')[0:-1]:
                to_remove = str(max(df1, df2, key=len))
                if to_remove in dockerfiles:
                    dockerfiles.remove(to_remove)


def _check_code_presence_df(df_path: str) -> bool:
    """
    Verify if a container contains user defined code basing on what is copied into during build phase from a Dockerfile.

    :param df_path: path of the Dockerfile
    :return: True if it contains user defined code, False otherwise
    """
    cmds = dockerfile.parse_file(df_path)
    # filter the COPY and ADD commands that copies from context (not from previous build stage):
    # --from indicates that the source of copy is in the filesystem of a previous build stage
    cmds = list(filter(
        lambda command: command.cmd in ['COPY', 'ADD'] and not command.value[0].startswith('--from'), cmds))
    if not len(cmds):
        return False
    for cmd in cmds:
        # last element is the destination and --* are arguments
        for entry in [entry for entry in cmd.value[:len(cmd.value) - 1] if not entry.startswith('--')]:
            if not urlparse(entry).scheme and not entry.endswith(tuple(CONFIG_EXT)) and 'script' not in entry:
                return True

    return False


#####################
# CLAIM MAIN METHOD #
#####################

def claim(name: str, workdir: str) -> set[Microservice]:
    """
    Performs the analysis of the repository with the CLAIM approach.

    :param name: name of the repository
    :param workdir: directory of the repository
    :return: set of detected microservices
    """
    dc = choose_dc(workdir)

    if dc:
        containers = process_services(dc_collect_services(Path(workdir).joinpath(dc)), Path(workdir))
        microservices = determine_microservices(name.split('.')[0], name.split('.')[1], workdir, containers)

        return microservices
    else:
        return set()
