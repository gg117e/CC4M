import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({'font.size': 20})
plt.rcParams["font.family"] = "Times New Roman"

detection = [
    np.array([]),
    np.array([]),
]

comm_count = 0
ms_count = 0


claim_file = Path(__file__).parent / f'../data/analysis/claim.csv'

with open(claim_file) as dataset:
    chunks = csv.DictReader(dataset, delimiter=';')

    for chunk in chunks:
        if chunk["# of microservices detected"] != "":
            comm_count += int(chunk["Commits chunk end"]) - int(chunk["Commits chunk start"]) + 1
            ms_count += (int(chunk["Commits chunk end"]) - int(chunk["Commits chunk start"]) + 1)*int(chunk["# of microservices"])
            if chunk["False positives"]:
                detection[0] = np.append(detection[0],
                          np.repeat(int(chunk["False positives"]),
                                    int(chunk["Commits chunk end"]) - int(chunk["Commits chunk start"]) + 1))
            else:
                detection[0] = np.append(detection[0],
                          np.repeat(0,
                                    int(chunk["Commits chunk end"]) - int(chunk["Commits chunk start"]) + 1))

claim_file = Path(__file__).parent / f'../data/analysis/baresi.csv'

with open(claim_file) as dataset:
    chunks = csv.DictReader(dataset, delimiter=';')

    for chunk in chunks:
        if chunk["# of microservices detected"] != "":
            if chunk["False positives"]:
                detection[1] = np.append(detection[1],
                                               np.repeat(int(chunk["False positives"]),
                                                         int(chunk["Commits chunk end"]) - int(
                                                             chunk["Commits chunk start"]) + 1))
            else:
                detection[1] = np.append(detection[1],
                                               np.repeat(0,
                                                         int(chunk["Commits chunk end"]) - int(
                                                             chunk["Commits chunk start"]) + 1))

fig, ax = plt.subplots(figsize=(13, 6))

ax.violinplot(detection, [0.4, 1])
ax.set_ylabel("Number of false positives", fontsize=24)
ax.set_xticks([0.4, 1], labels=["CLAIM", "Baresi et al."])

fig.suptitle("Microservices detection (false positives)", fontsize=24, weight="bold")

plt.savefig("../data/analysis/plot/ms_plot_false_positives.png")
plt.show()


print(comm_count)
print(ms_count)




claim_file = Path(__file__).parent / f'../data/analysis/claim.csv'

with open(claim_file) as dataset:
    chunks = csv.DictReader(dataset, delimiter=';')

    for chunk in chunks:
        if chunk["# of microservices detected"] != "":
            if chunk["False negatives"]:
                detection[0] = np.append(detection[0],
                          np.repeat(int(chunk["False negatives"]),
                                    int(chunk["Commits chunk end"]) - int(chunk["Commits chunk start"]) + 1))
            else:
                detection[0] = np.append(detection[0],
                          np.repeat(0,
                                    int(chunk["Commits chunk end"]) - int(chunk["Commits chunk start"]) + 1))

claim_file = Path(__file__).parent / f'../data/analysis/baresi.csv'

with open(claim_file) as dataset:
    chunks = csv.DictReader(dataset, delimiter=';')

    for chunk in chunks:
        if chunk["# of microservices detected"] != "":
            if chunk["False negatives"]:
                detection[1] = np.append(detection[1],
                                               np.repeat(int(chunk["False negatives"]),
                                                         int(chunk["Commits chunk end"]) - int(
                                                             chunk["Commits chunk start"]) + 1))
            else:
                detection[1] = np.append(detection[1],
                                               np.repeat(0,
                                                         int(chunk["Commits chunk end"]) - int(
                                                             chunk["Commits chunk start"]) + 1))

fig, ax = plt.subplots(figsize=(13, 6))

ax.violinplot(detection, [0.4, 1])
ax.set_ylabel("Number of false negatives", fontsize=24)
ax.set_xticks([0.4, 1], labels=["CLAIM", "Baresi et al."])

fig.suptitle("Microservices detection (false negatives)", fontsize=24, weight="bold")

plt.savefig("../data/analysis/plot/ms_plot_false_negatives.png")
plt.show()
