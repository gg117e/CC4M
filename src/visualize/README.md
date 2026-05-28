# 可視化モジュールの使い方

## これは何か
Dash + Plotly でマイクロサービス間コードクローンを散布図＆スニペットで可視化するツールです。エントリポイントは `visualize/scatter.py`。

## 事前準備
- Python 3.9+ 想定
- 依存インストール: `pip install -r requirements.txt`
- データ配置（いずれか）
  - 統一ローダー: `data/csv/{project}/ccfsw_<lang>.csv` または `tks_<lang>.csv`
  - JSON (no_imports 推奨): `dest/codeclones/{project}/latest/{lang}_no_imports.json` と `dest/clone_analysis/{project}/services.json`
  - プロジェクトCSV: `data/csv/{project}/ccfsw_<lang>.csv` / `tks_<lang>.csv` / `rnr_<lang>.csv` ＋ `dest/clone_analysis/{project}/services.json`
  - レガシーCSV: `visualize/csv/{project}_{commit}_{lang}_all.csv` ＋ `dest/clone_analysis/{project}/services.json`
- プロジェクトメタ（任意）: `visualize/project_summary.json` に `projects.{name}.languages.{Language}.stats.total_clones` などがあるとドロップダウンや概要カードがリッチになります。
- ソーススニペット表示用: `dest/temp/no_imports/{project}/` または `dest/temp/static/{project}/` に対応するソースを配置。

## 起動
```
python visualize/scatter.py
```
ブラウザで http://localhost:8050 を開くとダッシュボードが表示されます。インポート確認だけなら `python - <<'PY'
import visualize.scatter
print("import ok")
PY` でも可。

## よくある詰まりどころ
- services.json が無い/中身が空: サービス境界線とサービス名が描けません。
- `clone_type` 欄が無い: 検出方法フィルタ（TKS/CCFSW/RNR）が効きません。
- プロジェクトを変えてもグラフが更新されない: `dest/clone_analysis/{project}/services.json` のファイル名・パスを確認。

## 構成ざっくり
- `scatter.py`: Dash アプリのエントリポイント
- `components.py`: レイアウトと詳細ビュー生成
- `callbacks.py`: グラフ更新/クリック時の処理
- `plotting.py`: 散布図生成
- `data_loader.py`: データ読み込み（優先順位ロジック）
- `utils.py`: スニペット/ファイル取得
- `assets/`: CSS
