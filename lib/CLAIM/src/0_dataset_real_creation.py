#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Author: Anonymous
Email: Anonymous

This script executes all the steps of dataset creation, from the query execution on GitHub, to the final dataset through
all the filtering steps. Some of them are manual, so the script waits for your signal to proceed to the next step.
"""
import shutil
import subprocess
from pathlib import Path

if __name__ == "__main__":
    print('\n\n########## Step 0: running query_github script ##########\n')
    subprocess.run(["python3", "-m", "src.dataset_creation.00_query_github"],
                   cwd=Path(__file__).parent.parent)

    print('\n\n########## Step 1: running filter_multi_dev_dataset script ##########\n')
    subprocess.run(["python3", "-m", "src.dataset_creation.01_filter_multi_dev_dataset"],
                   cwd=Path(__file__).parent.parent)

    print('\n\n########## Step 2: running filter_lifespan_dataset script ##########\n')
    subprocess.run(["python3", "-m", "src.dataset_creation.02_filter_lifespan_dataset"],
                   cwd=Path(__file__).parent.parent)

    print('\n\n########## Step 3: running detect_dc_dataset script ##########\n')
    subprocess.run(["python3", "-m", "src.dataset_creation.03_detect_dc_dataset"],
                   cwd=Path(__file__).parent.parent)

    print('\n\n########## Step 4: applying filter_only_msa filter ##########\n')
    input('You should filter manually the current dataset in order to keep only real MSA. All the instruction at '
          './dataset_creation/04_filter_only_msa.md \n Press enter when you have finished...')

    print('\n\n########## End: you can find the final dataset in ../data/dataset/dataset_real.csv')
    shutil.copyfile('../data/dataset/04_filtered_only_msa.csv', '../data/dataset/dataset_real.csv')
