import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({'font.size': 20})
plt.rcParams["font.family"] = "Times New Roman"

tools = (
    "CLAIM",
    "Baresi et al.",
)
detection = {
    "Success": np.array([13245, 12669]),
    "Error": np.array([13357 - 13245, 13357 - 12669]),
}

fig, ax = plt.subplots(figsize=(13, 8))

ax.bar(tools, detection["Success"], color="#333333", width=0.4, label="Success", bottom=0)
ax.bar(tools, detection["Error"], color="#999999", width=0.4, label="Error", bottom=detection["Success"])

# Sum of values
total_values = np.add(detection["Success"], detection["Error"])

# Labels
ax.text(ax.patches[0].get_x() + ax.patches[0].get_width() / 2,
        ax.patches[0].get_height() / 2 + ax.patches[0].get_y(),
        round(ax.patches[0].get_height()), ha = 'center',
        color = 'w', weight = 'bold', size = 20)

ax.text(ax.patches[1].get_x() + ax.patches[1].get_width() / 2,
        ax.patches[1].get_height() / 2 + ax.patches[1].get_y(),
        round(ax.patches[1].get_height()), ha = 'center',
        color = 'w', weight = 'bold', size = 20)

ax.text(ax.patches[2].get_x() + ax.patches[2].get_width() / 2,
        total_values[0] + 100,
        round(ax.patches[2].get_height()), ha = 'center',
        color = '#000000', weight = 'bold', size = 20)

ax.text(ax.patches[3].get_x() + ax.patches[3].get_width() / 2,
        total_values[1] + 100,
        round(ax.patches[3].get_height()), ha = 'center',
        color = '#000000', weight = 'bold', size = 20)

ax.set_title("compose file detection", fontsize=24, weight="bold")
ax.set_ylabel("Number of commits", fontsize=24)
ax.legend(loc="upper center", fontsize=24)

plt.savefig("../data/analysis/plot/dc_plot.png")
plt.show()
