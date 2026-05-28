import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({'font.size': 20})
plt.rcParams["font.family"] = "Times New Roman"

profile = [
    np.array([]),
    np.array([]),
]


claim_file = Path(__file__).parent / f'../data/analysis/profiling.csv'

with open(claim_file) as dataset:
    repos = csv.DictReader(dataset, delimiter=';')

    for repo in repos:
        profile[0] = np.append(profile[0], float(repo["TIME_CLAIM"]))
        profile[1] = np.append(profile[1], float(repo["TIME_BARESI"]))


fig, ax = plt.subplots(figsize=(13, 6))

vplot = ax.violinplot(profile,
                      positions=[0.4, 1],
                      showmeans=False,
                      showmedians=True)
bplot = ax.boxplot(profile, positions=[0.4, 1],
                   patch_artist=True,
                   boxprops=dict(facecolor="royalblue", color="royalblue", linewidth=0),
                   whiskerprops=dict(color="royalblue"),
                   capprops=dict(color="royalblue"),
                   flierprops=dict(color="royalblue"),
                   medianprops=dict(color="darkblue", linewidth=2))
ax.set_ylabel("Seconds", fontsize=24)
ax.set_xticks([0.4, 1], labels=["CLAIM", "Baresi et al."])

for partname in ('cbars','cmins','cmaxes','cmedians'):
    vp = vplot[partname]
    if partname == "cmedians":
        vp.set_edgecolor("darkblue")
    else:
        vp.set_edgecolor("royalblue")
    vp.set_linewidth(2)


fig.suptitle("Execution time", fontsize=24, weight="bold")

plt.savefig("../data/analysis/plot/execution_time_plot.png")
plt.show()
