# 作業記録 (PROGRESS)

CC4M に対して, いつ, 何を, なぜ実装, 修正したかを残す記録.
新しいエントリを上に追記する. 書式は `.github/copilot-instructions.md` の
テンプレートに従う (タスク概要, 変更ファイル, テスト結果, 判断メモ, 残課題).
仕様そのものは各 docs に書き, ここには経緯と根拠を残す.

---

## 2026-10-16: co-modification 解析の diff 解析バグ修正

### 背景

コミット間の行変更 (moving_lines) を作る `collect_datas.find_moving_lines` に,
co-modification の結果を左右する 3 つのバグがあった.
いずれも 2026-10-15 のコードレビューで見つけ, 合成リポジトリと train-ticket の実データで確認した.

1. **各ファイルの先頭 hunk しか解析していなかった.**
   `parse_diff_str` が diff 文字列を `"@@"` で split し, `[1]` (ヘッダ) と `[2]` (本文) だけを使っていた.
   3 hunk の diff を与えると 1 つ目しか拾わないことを確認した.
2. **行番号が +1 ずれていた.**
   ヘッダ行 `@@ -a,b +c,d @@ <関数名など>` の残りを context 行として数えていた.
   先頭に 3 行挿入した diff で, 挿入行が `[1,2,3]` ではなく `[2,3,4]` になった.
3. **diff の向きが逆だった.**
   `prev.diff(commit)` (新しい側 -> 古い側) を取っていたため, `+` 行は古い側の行なのに,
   新しい側 (child) の挿入行として扱っていた.

3 つが重なった結果, 先頭に 3 行挿入しただけのファイルで, 子 (新) の行と親 (旧) の行の対応が
「期待: 新1-3 -> 対応なし, 新4 -> 旧1」に対し「実際: 新1 -> 旧1, 新2 -> 旧5, 新3 -> 旧6, ...」になっていた.

あわせて次の 2 点も直した.

4. 置換行 (`modified_lines`) を, 新旧で座標の違う行番号を同じ数値として比べて判定していた.
   また親側の断片範囲を, 子側座標の `modified_lines` と比べていた.
5. `analyze_commit` が早期 return したとき, 以前の実行の `dest/modified_clones/...` が残り,
   `analyze_modification` がそれを読んでいた.

#### 影響の大きさ (train-ticket, 修正前のコード)

- merge コミットのウィンドウ 43 個で, 変更された Java ファイルの diff は 2,754 件.
  そのうち 833 件 (30%) が複数 hunk を持つ.
- hunk は全部で 4,814 個あり, 2,060 個 (43%) が解析されていなかった.
- 同梱データで「1 回以上変更された」フラグメントは 14,944 個中 174 個 (1.2%) だけだった.

#### 論文 (ICSME 2026 Tool Demo) の事例への影響

- **Scenario 2 (Order.java, 9 サービス, cmr = 0.67) は成り立たない.**
  ウィンドウ 6393011a..1c228c76 で, 9 サービスの Order.java はすべて同じ変更
  (Lombok 化に伴う import の追加と getter, setter の削除) を受けている.
  クローン範囲の中が実際に編集されたのは ts-order-service と ts-order-other-service の 2 つだけだった.
  同梱データは逆に, 範囲外で行がずれただけの 6 個を「変更あり」とし, 2 個を「変更なし」としていた.
  修正後のコードで同じウィンドウを判定させた結果は次のとおりで, git 上の事実と 9 件すべて一致した.

  | サービス | 子側の範囲 | 範囲内の編集 (git) | 修正後の判定 |
  |---|---|---|---|
  | ts-order-service | 57-73 | あり | modified |
  | ts-order-other-service | 54-68 | あり | modified |
  | 残り 7 サービス | 50-64 など | なし | stable |

- **Scenario 3 (Account.java, |CM| = 2)** は, 2 つのウィンドウとも 3 ファイルが実際に変更されていることを
  git で確認した. ただし修正後のコードでの断片単位の再判定はしていない.
- Scenario 1 は未確認.

### 変更ファイル

- `src/modules/moving_lines.py` (新規) — diff 解析と moving_lines の保存, 読み込みを切り出した.
  - `parse_unified_diff`: 全 hunk を解析し, ヘッダの数値から行番号を数える.
    `-` 行の後に続く `+` 行は置換ブロックとし, 先頭から min(削除数, 挿入数) 行を置換の組にする.
  - `compute_moving_lines(parent_commit, child_commit)`: `parent_commit.diff(child_commit)` で向きを固定.
  - `save_moving_lines` / `load_moving_lines`: `{"format_version": 2, "hunks": [...]}` で保存する.
    旧形式 (リストのみ) は「未計算」として扱い, 再計算させる.

  ```python
  # 座標の約束
  # inserted_lines, modified_lines        -> 子 (新しい側) の行番号
  # deleted_lines, modified_parent_lines  -> 親 (古い側) の行番号
  ```

- `src/modules/collect_datas.py` — `parse_diff_str` を削除し, `find_moving_lines` を新モジュールの薄いラッパにした.
  キャッシュ判定を `exists()` から `load_moving_lines(...) is None` に変え, 旧形式のファイルを再計算するようにした.
- `src/modules/analyze_cc.py`
  - `CorrespondedLines` の判定を, 行ごとに hunk を線形探索する方式から, 事前に作った集合の参照に変えた.
  - 親側の置換判定 `is_parent_line_modified` を追加し, `correspond_clonesets` の親側ループで使うようにした.
  - `analyze_commit` は最初に古い出力ファイルを消すようにした. moving_lines が旧形式なら警告して処理しない.
    `print` を `logging` に置き換えた.
- `tests/test_moving_lines.py` (新規, 9 件) — 複数 hunk, ヘッダの残り, 件数 0 の hunk, 不等長の置換,
  `\ No newline` の扱い, 旧形式の読み込み, 実際の git リポジトリでの向き (slow).
- `tests/test_analyze_cc.py` (新規, 5 件) — 先頭への挿入による行のずれ, 2 番目の hunk によるずれ,
  範囲外の変更だけなら stable, 範囲内の編集や削除なら modified.
- `pyproject.toml` — pytest に `slow` マーカーを登録した.
- `docs/line_tracking.md` (新規) — 行の追跡の仕様.
- `docs/README.md`, `docs/dataset.md` — 上記へのリンクと, 同梱データについての注意を追記した.
- `docs/notices/2026-10-16_co-modification_bug.md` (新規) — CC4M のパイプラインを使った研究室メンバー向けの連絡文.

### テスト結果

- `.venv/Scripts/python.exe -m pytest -q` -> 170 passed (新規 14 件を含む).
- `ruff check` (変更ファイル) -> 新規ファイルは指摘なし.
  既存ファイルの E402 が 2 件増えたが, 既存コードと同じ `sys.path` 追加後の import によるもの.
- train-ticket の Scenario 2 のウィンドウで, 修正前と修正後のコードを比較した (上の表).
  修正前のコードに正しい親側の範囲を与えると, 9 件すべての対応付けに失敗し `added` (系譜が切れる) になった.

### 判断メモ

- 置換行を「削除 + 挿入」とみなさず組にしたのは, 断片の端点の行が書き換えられても対応付けを保ち,
  系譜が切れにくくするため. 組にした行は modified として扱われるので, 変更の検出漏れにはならない.
- moving_lines の保存形式にバージョンを付けたのは, 旧形式のキャッシュが残っていると
  `collect` ステップが再計算せず, 誤った結果を使い続けるため.
- リネームの追跡と, HEAD から遡るだけの追跡方式は, 今回の「バグ修正」の範囲を超えるので変えていない.

### 残課題

- TODO(gen): 同梱の `dest/` (7 プロジェクト分の enriched_fragments, scatter, clone_metrics) を修正後のパイプラインで再生成する.
  CCFinderSW を含む全ステップの再実行が必要 (train-ticket で約 43 分).
- TODO(gen): 再生成の前後で co-modification の件数がどう変わるかを記録する.
- TODO(gen): 先輩の SANER 投稿の研究が `collect_datas.py` / `analyze_cc.py` を使っているか確認し,
  使っていれば `docs/notices/2026-10-16_co-modification_bug.md` を共有する.
- TODO(gen): リネーム, 移動したファイルの追跡 (`git diff -M` の結果を使う).
- TODO(gen): Scenario 1, 3 を修正後のコードで再判定する.
