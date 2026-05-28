import json
import sys
from pathlib import Path

import git

def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


project_root = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))
from modules.util import FileMapper


class CorrespondedLines:
    """行対応を提供するヘルパー。"""

    def __init__(self, hunks: list[dict], child_filemap: FileMapper, parent_filemap: FileMapper):
        self.corresponded_lines = self._correspond_lines(hunks, child_filemap, parent_filemap)
        self.hunks = hunks
    
    def get_parent_line(self, child_path: str, child_line: int):
        if child_path not in self.corresponded_lines.keys():
            return child_line
        if child_line not in self.corresponded_lines[child_path].keys():
            return child_line
        return self.corresponded_lines[child_path][child_line]
    
    def is_file_having_moved_lines(self, child_path):
        if child_path not in self.corresponded_lines.keys():
            return False
        if len(self.corresponded_lines[child_path].keys()) == 0:
            return False
        return True
    
    def is_line_deleted(self, parent_path: str, parent_line: int):
        for diff in self.hunks:
            if diff["parent_path"] != parent_path:
                continue
            if parent_line in diff["deleted_lines"]:
                return True
        return False
    
    def is_line_added(self, child_path: str, child_line: int):
        for diff in self.hunks:
            if diff["child_path"] != child_path:
                continue
            if child_line in diff["inserted_lines"]:
                return True
        return False
    
    def is_line_modified(self, path: str, line: int):
        for diff in self.hunks:
            if diff["child_path"] != path:
                continue
            if line in diff["modified_lines"]:
                return True
        return False
    
    def get_fragment_loc_of_parent(self, child_path: str, child_start_line: int, child_end_line: int):
        if child_path not in self.corresponded_lines.keys():
            return child_end_line - child_start_line + 1
        loc = 0
        for l in range(child_start_line, child_end_line+1):
            if l not in self.corresponded_lines[child_path].keys():
                continue
            if self.corresponded_lines[child_path][l] is not None:
                loc += 1
        return loc

    def _correspond_lines(self, hunks: list[dict], child_filemap: FileMapper, parent_filemap: FileMapper):
        result = {}
        # 1) ファイル単位に hunk 情報を集約（重複・隣接・順序に依存しないため）
        by_file: dict[tuple[str, str], dict[str, set[int]]] = {}
        for h in hunks:
            cpath = h.get("child_path")
            ppath = h.get("parent_path")
            if not cpath or not ppath:
                continue
            # リネームは考慮しないので child==parent のものだけ
            if cpath != ppath:
                continue

            ins = set(int(x) for x in h.get("inserted_lines", []) if isinstance(x, int) or str(x).isdigit())
            dele = set(int(x) for x in h.get("deleted_lines", []) if isinstance(x, int) or str(x).isdigit())
            key = (cpath, ppath)
            agg = by_file.setdefault(key, {"inserted": set(), "deleted": set()})
            agg["inserted"].update(ins)
            agg["deleted"].update(dele)

        # 2) 各ファイルについて二本ポインタで child→parent 対応を構築
        for (child_path, parent_path), diff in by_file.items():
            child_file_loc = child_filemap.get_file_loc(child_path)
            if child_file_loc == -1:
                continue
            parent_file_loc = parent_filemap.get_file_loc(parent_path)
            if parent_file_loc == -1:
                continue

            inserted = {x for x in diff["inserted"] if 1 <= x <= child_file_loc}
            deleted = {x for x in diff["deleted"] if 1 <= x <= parent_file_loc}

            lines: dict[int, int | None] = {}
            i, j = 1, 1  # i: child 行, j: parent 行 (どちらも1始まり)

            while i <= child_file_loc:
                # child 側にのみ存在する行（挿入行）は None を割り当て
                if i in inserted:
                    lines[i] = None
                    i += 1
                    continue

                # parent 側で削除された行は j をスキップ（連続削除にも対応）
                while j <= parent_file_loc and j in deleted:
                    j += 1

                if j <= parent_file_loc:
                    # 対応あり
                    lines[i] = j
                    i += 1
                    j += 1
                else:
                    # parent 側が尽きた: 以降の child 行は対応なし
                    lines[i] = None
                    i += 1
            result[child_path] = lines
        return result


def get_clone_map(clonesets: list[dict], filemap: FileMapper) -> dict[str, list[dict]]:
    """ファイルパスごとにクローンフラグメントを束ねたマップを返す。"""
    clone_map: dict[str, list[dict]] = {}
    for clone_set in clonesets:
        for index, fragment in enumerate(clone_set["fragments"]):
            fragment_path = filemap.get_file_path(fragment["file_id"])
            clone_map.setdefault(fragment_path, []).append({
                "clone_id": clone_set["clone_id"],
                "index": index,
                "file_id": fragment["file_id"],
                "start_line": fragment["start_line"],
                "end_line": fragment["end_line"],
            })
    return clone_map


def correspond_code_fragments(corresponded_lines: CorrespondedLines, child_clonesets: list[dict], parent_clonesets: list[dict], child_filemap: FileMapper, parent_filemap: FileMapper):
    """子クローンフラグメントと親フラグメントの対応を決定する。"""
    corresponded_fragments = {}
    
    # 親側のフラグメントを path ごとにまとめる
    parent_clone_map = get_clone_map(parent_clonesets, parent_filemap)
    # 例: { "path/to/file": [ {clone_id, index, start_line, end_line}, ... ] }
    
    for child_clone_set in child_clonesets:
        child_clone_id = child_clone_set["clone_id"]
    
        for index, child_fragment in enumerate(child_clone_set["fragments"]):
            child_path = child_filemap.get_file_path(child_fragment["file_id"])
            parent_path = child_path  # リネームは考慮しない仕様
            c_start = child_fragment["start_line"]
            c_end   = child_fragment["end_line"]
    
            # デフォルトは None（対応なし / 新規）
            mapped: tuple[int, int] | None = None

            # 親に同一パスのクローンが無いなら確実に新規
            parent_frags = parent_clone_map.get(parent_path)
            if not parent_frags:
                corresponded_fragments.setdefault(child_clone_id, {})[index] = None
                continue
        
            # 事前計算：端点の親行、親側での生存行数（= 対応する親行の個数）
            p_start_pred = corresponded_lines.get_parent_line(child_path, c_start)
            p_end_pred   = corresponded_lines.get_parent_line(child_path, c_end)
            # 子フラグメント内の「親行に写る行」の個数（0なら新規扱い）
            parent_loc_in_child_frag = corresponded_lines.get_fragment_loc_of_parent(child_path, c_start, c_end)
            if parent_loc_in_child_frag == 0:
                corresponded_fragments.setdefault(child_clone_id, {})[index] = None
                continue

             # 子→親・親→子の対応テーブルを一度だけ構築（子フラグメント範囲内）
            # child2parent: {child_line -> parent_line or None}
            # parent2child: {parent_line -> [child_line, ...]}
            child2parent = {}
            parent2child = {}
            for cl in range(c_start, c_end + 1):
                pl = corresponded_lines.get_parent_line(child_path, cl)
                child2parent[cl] = pl
                if pl is not None:
                    parent2child.setdefault(pl, []).append(cl)

            # 親候補を順にチェック
            for pfrag in parent_frags:
                ps, pe = pfrag["start_line"], pfrag["end_line"]

                # 1) 完全一致（境界一致）: 子端点が親端点に写っている
                if p_start_pred == ps and p_end_pred == pe:
                    mapped = (pfrag["clone_id"], pfrag["index"])
                    break

                c_len = c_end - c_start + 1
                p_len = pe - ps + 1

                # 2) 子のほうが長い（= 子に挿入がある）
                #    親端点が子フラグメント内に連続して含まれているか（先頭/末尾の挿入を許容）
                if p_len < c_len:
                    # 子の範囲内で、親の開始/終了端点に対応する子行が存在するか
                    #   - 端点が複数行に写ることは普通ないが、防御的に min/max を見る
                    c_for_ps = parent2child.get(ps, [])
                    c_for_pe = parent2child.get(pe, [])
                    if c_for_ps and c_for_pe:
                        # 端点がそれぞれ子範囲の内側にあり、親端点の順序が保たれる
                        if min(c_for_ps) >= c_start and max(c_for_pe) <= c_end and min(c_for_ps) <= max(c_for_pe):
                            mapped = (pfrag["clone_id"], pfrag["index"])
                            break
                    # 見つからなければ次候補へ
                    continue

                # 3) 親のほうが長い（= 親端での削除）
                #    親フラグメント内の「削除されていない親行」たちが、子フラグメントの端点に写っているか
                if p_len > c_len:
                    # 親側の範囲 ps..pe のうち削除されていない親行を、子フラグメント内で探す
                    # 最初に子へ写る親行 → 子側の最小行
                    c_candidates = []
                    # 端点限定でもよいが、削除がまとまっている場合に備えて全域を見る
                    for pl in range(ps, pe + 1):
                        if corresponded_lines.is_line_deleted(parent_path, pl):
                            continue
                        # この親行 pl に対応する子行（子フラグメント内）を取り出す
                        clist = parent2child.get(pl, [])
                        c_candidates.extend(clist)

                    if c_candidates:
                        c_min = min(c_candidates)
                        c_max = max(c_candidates)
                        if c_min == c_start and c_max == c_end:
                            mapped = (pfrag["clone_id"], pfrag["index"])
                            break
                    # 見つからなければ次候補へ
                    continue

                # 4) 同一長だが端点がズレている（置換＋同長差分など）は、上の境界一致で拾えない限り不一致扱い
                #    ここではスキップ
                continue

            # 見つかった/見つからなかった結果を反映
            corresponded_fragments.setdefault(child_clone_id, {})[index] = mapped

    return corresponded_fragments


def correspond_clonesets(
    corresponded_fragments: dict,
    corresponded_lines: CorrespondedLines,
    child_clonesets: list[dict],
    parent_clonesets: list[dict],
    child_filemap: FileMapper,
    parent_filemap: FileMapper
):
    """クローンセット間の差分をまとめて返す。"""
    """
    出力: modified_clones = [
      {
        "clone_id": <child clone id>,
        "fragments": [
          {
            "type": "added" | "modified" | "stable",
            "parent": {...} or None,
            "child": {...}
          }, ...
        ]
      }, ...
    ]
    """
    modified_clones = []

    # 1) parent clone_id -> クローンセット辞書
    parent_set_by_id = {cs["clone_id"]: cs for cs in parent_clonesets}

    for child_set in child_clonesets:
        child_clone_id = child_set["clone_id"]
        out_fragments = []

        # child セットに対応マップが無くても、各フラグメントを個別に added 扱いできる
        child_map = corresponded_fragments.get(child_clone_id, {})

        for index, child_frag in enumerate(child_set["fragments"]):
            child_file_id = child_frag["file_id"]
            child_path = child_filemap.get_file_path(child_file_id)
            c_start = child_frag["start_line"]
            c_end   = child_frag["end_line"]

            mapping = child_map.get(index)  # None or (parent_clone_id, parent_fragment_index)
            if mapping is None:
                # まるごと新規
                out_fragments.append({
                    "type": "added",
                    "parent": None,
                    "child": {
                        "clone_id": child_clone_id,
                        "index": index,
                        "file_id": child_file_id,
                        "file_path": child_path,
                        "start_line": c_start,
                        "end_line": c_end
                    }
                })
                continue

            parent_clone_id, parent_frag_index = mapping

            # 2) parent クローンセットを安全に参照
            pset = parent_set_by_id.get(parent_clone_id)
            if pset is None or not (0 <= parent_frag_index < len(pset["fragments"])):
                # 想定外（インデックス不整合）の場合は added 扱いに逃がす
                out_fragments.append({
                    "type": "added",
                    "parent": None,
                    "child": {
                        "clone_id": child_clone_id,
                        "index": index,
                        "file_id": child_file_id,
                        "file_path": child_path,
                        "start_line": c_start,
                        "end_line": c_end
                    }
                })
                continue

            parent_frag = pset["fragments"][parent_frag_index]
            parent_file_id = parent_frag["file_id"]
            parent_path = parent_filemap.get_file_path(parent_file_id)
            p_start = parent_frag["start_line"]
            p_end   = parent_frag["end_line"]

            # 3) 変更有無の判定
            # いずれか一方でも変化があれば "modified" とするのが自然
            parent_deleted = False
            parent_modified = False
            for l in range(p_start, p_end + 1):
                # 削除判定を先に見るとわかりやすい（削除は強いシグナル）
                if corresponded_lines.is_line_deleted(parent_path, l):
                    parent_deleted = True
                    break
                if corresponded_lines.is_line_modified(parent_path, l):
                    parent_modified = True
                    break

            child_added = False
            child_modified = False
            for l in range(c_start, c_end + 1):
                if corresponded_lines.is_line_added(child_path, l):
                    child_added = True
                    break
                if corresponded_lines.is_line_modified(child_path, l):
                    child_modified = True
                    break

            is_modified = parent_deleted or parent_modified or child_added or child_modified

            frag_record = {
                "parent": {
                    "clone_id": parent_clone_id,
                    "index": parent_frag_index,
                    "file_id": parent_file_id,
                    "file_path": parent_path,
                    "start_line": p_start,
                    "end_line": p_end
                },
                "child": {
                    "clone_id": child_clone_id,
                    "index": index,
                    "file_id": child_file_id,
                    "file_path": child_path,
                    "start_line": c_start,
                    "end_line": c_end
                }
            }

            out_fragments.append({
                "type": "modified" if is_modified else "stable",
                **frag_record
            })

        modified_clones.append({
            "clone_id": child_clone_id,
            "fragments": out_fragments
        })

    return modified_clones


def analyze_commit(name: str, language: str, commit: git.Commit, prev: git.Commit) -> bool:
    """単一コミット間でクローン差分を算出し保存する。"""
    workdir = project_root / "dest/projects" / name
    print(f"{commit.hexsha}-{prev.hexsha}")
    # childのCCFinderSWファイルの読み込み
    child_ccfsw_file = project_root / "dest/clones_json" / name / prev.hexsha / f"{language}.json"
    with open(child_ccfsw_file, "r") as f:
        child_ccfsw = json.load(f)
    child_filemap = FileMapper(child_ccfsw["file_data"], str(workdir))

    # parentのCCFinderSWファイルの読み込み
    parent_ccfsw_file = project_root / "dest/clones_json" / name / commit.hexsha / f"{language}.json"
    with open(parent_ccfsw_file, "r") as f:
        parent_ccfsw = json.load(f)
    parent_filemap = FileMapper(parent_ccfsw["file_data"], str(workdir))
    # コミット間のLineDiffファイルの読み込み
    line_diff_file = project_root / "dest/moving_lines" / name / f"{commit.hexsha}-{prev.hexsha}.json"
    if not line_diff_file.exists():
        return False
    with open(line_diff_file, "r") as f:
        hunks = json.load(f)
    # 修正がなければこのコミットの処理は終了
    if len(hunks) == 0:
        return False
    # CCFinderSWの対象ファイルに修正がなければ終了
    for hunk in hunks:
        if (child_filemap.get_file_loc(hunk["child_path"]) != -1) and (parent_filemap.get_file_loc(hunk["parent_path"]) != -1):
            break
    else:
        return False
    # 親コミットのファイルと子コミットのファイルの行を対応付ける．
    corresponded_lines = CorrespondedLines(hunks, child_filemap, parent_filemap)
    corresponded_fragments = correspond_code_fragments(corresponded_lines, child_ccfsw["clone_sets"], parent_ccfsw["clone_sets"], child_filemap, parent_filemap)

    # 修正を特定
    modified_clones = correspond_clonesets(corresponded_fragments, corresponded_lines, child_ccfsw["clone_sets"], parent_ccfsw["clone_sets"], child_filemap, parent_filemap)

    # 保存
    dest_dir = project_root / "dest/modified_clones" / name / f"{commit.hexsha}-{prev.hexsha}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    with open(dest_dir / f"{language}.json", "w") as f:
        json.dump(modified_clones, f, indent=4)
    
    # 成功
    return True
        

def analyze_repo(project: dict):
    """対象リポジトリの全対象コミットに対してクローン差分分析を行う。"""
    url = project["URL"]
    name = url.split("/")[-2] + "." + url.split("/")[-1]
    languages = project["languages"].keys()
    workdir = project_root / "dest/projects" / name
    git_repo = git.Repo(workdir)
    with open(project_root / "dest/analyzed_commits" / f"{name}.json", "r") as f:
        analyzed_commit_hashes = json.load(f)
    head_commit = git_repo.commit(analyzed_commit_hashes[0])
    for language in languages:
        prev = head_commit
        for commit_hash in analyzed_commit_hashes:
            if commit_hash == head_commit.hexsha:
                continue
            commit = git_repo.commit(commit_hash)
            analyze_commit(name, language, commit, prev)
            prev = commit
