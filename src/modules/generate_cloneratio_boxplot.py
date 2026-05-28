import sys
from pathlib import Path
import json

import matplotlib.pyplot as plt

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

import modules.calculate_clone_ratio

if __name__ == "__main__":
    dataset_file = project_root / "dataset/selected_projects.json"
    with open(dataset_file, "r") as f:
        dataset = json.load(f)
    results = {}
    for project in dataset:
        result = modules.calculate_clone_ratio.analyze_repo(project)
        for language in result:
            if language not in results:
                results[language] = {
                    "within-testing_clone_ratio": [],
                    "within-production_clone_ratio": [],
                    "across-testing_clone_ratio": [],
                    "across-production_clone_ratio": []
                }
            for mode in result[language]:
                results[language][mode].append(result[language][mode])

    # 全言語全モードの箱ひげ図を横に並べて描画
    modes = ["within-testing_clone_ratio", "within-production_clone_ratio", "across-testing_clone_ratio", "across-production_clone_ratio"]
    languages = list(results.keys())

    fig, axes = plt.subplots(1, len(modes), figsize=(3 * len(modes), 6), sharey=True)

    if len(modes) == 1:
        axes = [axes]

    for idx, mode in enumerate(modes):
        data = []
        labels = []
        for language in languages:
            data.append(results[language][mode])
            labels.append(language)
        
        # データ数を出力
        total_data_points = sum(len(d) for d in data)
        print(f"{mode}: {total_data_points}個のデータポイント")
        for i, language in enumerate(languages):
            print(f"  {language}: {len(data[i])}個")
        
        axes[idx].boxplot(data, labels=labels, showmeans=True)
        axes[idx].set_title(mode, fontsize=12)
        axes[idx].tick_params(axis='x', rotation=45)
        axes[idx].set_ylim(0, 1)

    plt.tight_layout()
    
    # PNG形式で保存
    output_path = project_root / "dest/cloneratio_boxplot.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"箱ひげ図を保存しました: {output_path}")
    plt.show()
