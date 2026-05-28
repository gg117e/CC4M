"""Co-change display 機能のテスト."""

import pandas as pd
import pytest


class TestNormalizePath:
    """_normalize_path 関数のテスト."""

    def test_removes_leading_slash(self):
        """先頭のスラッシュが削除される."""
        from src.visualize.components.clone_detail import _normalize_path

        assert _normalize_path("/path/to/file.java") == "path/to/file.java"

    def test_preserves_path_without_leading_slash(self):
        """先頭にスラッシュがないパスはそのまま."""
        from src.visualize.components.clone_detail import _normalize_path

        assert _normalize_path("path/to/file.java") == "path/to/file.java"

    def test_empty_string_returns_empty(self):
        """空文字列は空文字列を返す."""
        from src.visualize.components.clone_detail import _normalize_path

        assert _normalize_path("") == ""

    def test_none_returns_empty(self):
        """Noneは空文字列を返す."""
        from src.visualize.components.clone_detail import _normalize_path

        assert _normalize_path(None) == ""


class TestSafeInt:
    """_safe_int 関数のテスト."""

    def test_int_value_returned(self):
        """整数値はそのまま返される."""
        from src.visualize.components.clone_detail import _safe_int

        assert _safe_int(42) == 42

    def test_string_int_converted(self):
        """文字列の整数は変換される."""
        from src.visualize.components.clone_detail import _safe_int

        assert _safe_int("123") == 123

    def test_none_returns_zero(self):
        """Noneは0を返す."""
        from src.visualize.components.clone_detail import _safe_int

        assert _safe_int(None) == 0

    def test_pd_na_returns_zero(self):
        """pd.NAは0を返す."""
        from src.visualize.components.clone_detail import _safe_int

        assert _safe_int(pd.NA) == 0

    def test_invalid_string_returns_zero(self):
        """変換できない文字列は0を返す."""
        from src.visualize.components.clone_detail import _safe_int

        assert _safe_int("not a number") == 0


class TestFindFragmentByLocation:
    """_find_fragment_by_location 関数のテスト."""

    def test_finds_exact_match(self):
        """完全一致するフラグメントを見つける."""
        from src.visualize.components.clone_detail import _find_fragment_by_location

        df = pd.DataFrame([
            {"file_path": "src/Main.java", "start_line": 10, "end_line": 20},
            {"file_path": "src/Main.java", "start_line": 30, "end_line": 40},
            {"file_path": "src/Util.java", "start_line": 10, "end_line": 20},
        ])

        result = _find_fragment_by_location(df, "src/Main.java", 30, 40)
        assert result is not None
        assert result["start_line"] == 30
        assert result["end_line"] == 40

    def test_finds_match_with_leading_slash_in_target(self):
        """対象パスに先頭スラッシュがあっても見つける."""
        from src.visualize.components.clone_detail import _find_fragment_by_location

        df = pd.DataFrame([
            {"file_path": "src/Main.java", "start_line": 10, "end_line": 20},
        ])

        result = _find_fragment_by_location(df, "/src/Main.java", 10, 20)
        assert result is not None

    def test_finds_match_with_leading_slash_in_df(self):
        """DataFrameのパスに先頭スラッシュがあっても見つける."""
        from src.visualize.components.clone_detail import _find_fragment_by_location

        df = pd.DataFrame([
            {"file_path": "/src/Main.java", "start_line": 10, "end_line": 20},
        ])

        result = _find_fragment_by_location(df, "src/Main.java", 10, 20)
        assert result is not None

    def test_returns_none_when_not_found(self):
        """一致しない場合はNoneを返す."""
        from src.visualize.components.clone_detail import _find_fragment_by_location

        df = pd.DataFrame([
            {"file_path": "src/Main.java", "start_line": 10, "end_line": 20},
        ])

        result = _find_fragment_by_location(df, "src/Main.java", 100, 200)
        assert result is None

    def test_returns_none_for_empty_df(self):
        """空のDataFrameはNoneを返す."""
        from src.visualize.components.clone_detail import _find_fragment_by_location

        df = pd.DataFrame()
        result = _find_fragment_by_location(df, "src/Main.java", 10, 20)
        assert result is None

    def test_returns_none_when_no_file_path_column(self):
        """file_path列がないDataFrameはNoneを返す."""
        from src.visualize.components.clone_detail import _find_fragment_by_location

        df = pd.DataFrame([{"other_col": "value"}])
        result = _find_fragment_by_location(df, "src/Main.java", 10, 20)
        assert result is None


class TestExtractCommonCommits:
    """extract_common_commits 関数のテスト."""

    def test_empty_inputs_returns_empty_list(self):
        """両方のJSONが空の場合、空のリストを返す."""
        from src.visualize.utils import extract_common_commits

        result = extract_common_commits("[]", "[]")
        assert result == []

    def test_no_common_commits_returns_empty_list(self):
        """共通コミットがない場合、空のリストを返す."""
        from src.visualize.utils import extract_common_commits

        mod_x = '["abc123", "def456"]'
        mod_y = '["ghi789", "jkl012"]'
        result = extract_common_commits(mod_x, mod_y)
        assert result == []

    def test_common_commits_found(self):
        """共通コミットがある場合、正しく抽出される."""
        from src.visualize.utils import extract_common_commits

        mod_x = '["abc123", "def456", "common1"]'
        mod_y = '["ghi789", "common1", "common2"]'
        result = extract_common_commits(mod_x, mod_y)
        assert result == ["common1"]

    def test_multiple_common_commits_sorted_descending(self):
        """複数の共通コミットが降順でソートされる."""
        from src.visualize.utils import extract_common_commits

        mod_x = '["aaa111", "bbb222", "ccc333"]'
        mod_y = '["bbb222", "ccc333", "ddd444"]'
        result = extract_common_commits(mod_x, mod_y)
        assert result == ["ccc333", "bbb222"]

    def test_invalid_json_x_returns_empty_list(self):
        """modification_x が不正なJSONの場合、空のリストを返す."""
        from src.visualize.utils import extract_common_commits

        result = extract_common_commits("invalid json", '["abc123"]')
        assert result == []

    def test_invalid_json_y_returns_empty_list(self):
        """modification_y が不正なJSONの場合、空のリストを返す."""
        from src.visualize.utils import extract_common_commits

        result = extract_common_commits('["abc123"]', "invalid json")
        assert result == []

    def test_none_inputs_handled(self):
        """None入力が安全に処理される."""
        from src.visualize.utils import extract_common_commits

        result = extract_common_commits(None, '["abc123"]')
        assert result == []

        result = extract_common_commits('["abc123"]', None)
        assert result == []

    def test_all_commits_common(self):
        """全てのコミットが共通の場合."""
        from src.visualize.utils import extract_common_commits

        mod_x = '["abc123", "def456"]'
        mod_y = '["def456", "abc123"]'
        result = extract_common_commits(mod_x, mod_y)
        assert sorted(result) == ["abc123", "def456"]


class TestGenerateGithubCommitUrl:
    """generate_github_commit_url 関数のテスト."""

    def test_valid_project_and_commit(self):
        """有効なプロジェクトとコミットでURLが生成される."""
        from src.visualize.components.clone_metrics import generate_github_commit_url

        url = generate_github_commit_url("owner.repo", "abc123def456")
        assert url is not None
        assert "abc123def456" in url
        assert "/commit/" in url

    def test_empty_project_returns_none(self):
        """プロジェクトが空の場合、Noneを返す."""
        from src.visualize.components.clone_metrics import generate_github_commit_url

        result = generate_github_commit_url("", "abc123def456")
        assert result is None

    def test_empty_commit_returns_none(self):
        """コミットが空の場合、Noneを返す."""
        from src.visualize.components.clone_metrics import generate_github_commit_url

        result = generate_github_commit_url("owner.repo", "")
        assert result is None

    def test_none_project_returns_none(self):
        """プロジェクトがNoneの場合、Noneを返す."""
        from src.visualize.components.clone_metrics import generate_github_commit_url

        result = generate_github_commit_url(None, "abc123def456")
        assert result is None

    def test_none_commit_returns_none(self):
        """コミットがNoneの場合、Noneを返す."""
        from src.visualize.components.clone_metrics import generate_github_commit_url

        result = generate_github_commit_url("owner.repo", None)
        assert result is None


class TestGetGithubBaseUrl:
    """get_github_base_url 関数のテスト."""

    def test_fallback_converts_dot_to_slash(self):
        """fallbackではドットをスラッシュに変換する."""
        from src.visualize.components.clone_metrics import get_github_base_url

        # 存在しないプロジェクト → fallback が使用される
        url = get_github_base_url("FudanSELab.train-ticket-nonexistent")
        assert url == "https://github.com/FudanSELab/train-ticket-nonexistent"

    def test_fallback_only_converts_first_dot(self):
        """fallbackでは最初のドットのみスラッシュに変換する."""
        from src.visualize.components.clone_metrics import get_github_base_url

        url = get_github_base_url("owner.repo.with.dots")
        assert url == "https://github.com/owner/repo.with.dots"

    def test_commit_url_uses_correct_base(self):
        """generate_github_commit_urlが正しいベースURLを使用する."""
        from src.visualize.components.clone_metrics import generate_github_commit_url

        # fallback が適用される（存在しないプロジェクト）
        url = generate_github_commit_url("owner.repo", "abc123")
        assert url == "https://github.com/owner/repo/commit/abc123"

    def test_fudanselab_train_ticket_url(self):
        """FudanSELab.train-ticket のURLが正しく生成される."""
        from src.visualize.components.clone_metrics import generate_github_commit_url

        url = generate_github_commit_url(
            "FudanSELab.train-ticket", "abc123def456789"
        )
        # services_json に URL がある場合はそれを使用
        # ない場合は fallback でドットをスラッシュに変換
        assert url is not None
        assert "/commit/abc123def456789" in url
        # 重要: 404 にならない URL 形式であること
        assert "FudanSELab/train-ticket" in url or "FudanSELab.train-ticket" not in url

    def test_services_json_url_used_if_available(self):
        """services_json の URL が利用可能な場合、それを使用する."""
        from src.visualize.components.clone_metrics import get_github_base_url

        # FudanSELab.train-ticket は services_json に URL がある
        url = get_github_base_url("FudanSELab.train-ticket")
        assert url == "https://github.com/FudanSELab/train-ticket"

    def test_raster_foundry_url(self):
        """raster-foundry.raster-foundry のURLが正しく生成される."""
        from src.visualize.components.clone_metrics import get_github_base_url

        url = get_github_base_url("raster-foundry.raster-foundry")
        assert url == "https://github.com/raster-foundry/raster-foundry"


class TestGenerateGithubFileUrl:
    """generate_github_file_url 関数のテスト."""

    def test_generates_url_with_line_range(self):
        """行範囲付きのファイルURLが生成される."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        url = generate_github_file_url(
            "FudanSELab.train-ticket",
            "/ts-auth-service/src/main/java/auth/AuthController.java",
            10,
            20,
        )
        assert url is not None
        assert "FudanSELab/train-ticket" in url
        assert "#L10-L20" in url
        assert "/blob/" in url

    def test_generates_url_with_single_line(self):
        """単一行のファイルURLが生成される."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        url = generate_github_file_url(
            "FudanSELab.train-ticket",
            "ts-auth-service/src/main/java/auth/AuthController.java",
            15,
            15,
        )
        assert url is not None
        assert "#L15" in url
        # 同じ行の場合は L15-L15 にならない
        assert "-L15" not in url

    def test_generates_url_without_line_numbers(self):
        """行番号なしのファイルURLが生成される."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        url = generate_github_file_url(
            "FudanSELab.train-ticket",
            "ts-auth-service/src/main/java/auth/AuthController.java",
        )
        assert url is not None
        assert "#L" not in url
        assert "/blob/" in url

    def test_returns_none_for_empty_project(self):
        """プロジェクトが空の場合、Noneを返す."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        result = generate_github_file_url("", "src/Main.java", 10, 20)
        assert result is None

    def test_returns_none_for_empty_file_path(self):
        """ファイルパスが空の場合、Noneを返す."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        result = generate_github_file_url("owner.repo", "", 10, 20)
        assert result is None

    def test_strips_leading_slash_from_file_path(self):
        """ファイルパスの先頭スラッシュが削除される."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        url = generate_github_file_url(
            "FudanSELab.train-ticket", "/src/Main.java", 10, 20
        )
        assert url is not None
        # "/src/Main.java" が "src/Main.java" に変換される
        assert "/blob/master/src/Main.java" in url
        assert "//src" not in url  # 二重スラッシュがない

    def test_uses_master_as_default_branch(self):
        """デフォルトブランチとして master を使用."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        # 存在しないプロジェクト → fallback（master）
        url = generate_github_file_url(
            "unknown.project", "src/Main.java", 10, 20
        )
        assert url is not None
        assert "/blob/master/" in url

    def test_file_url_uses_services_json_base(self):
        """services_json の URL をベースに使用."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        # FudanSELab.train-ticket は services_json に URL がある
        url = generate_github_file_url(
            "FudanSELab.train-ticket",
            "ts-auth-service/src/main/java/Test.java",
            1,
            10,
        )
        assert url is not None
        assert "github.com/FudanSELab/train-ticket" in url

    def test_generate_github_file_url_with_commit_hash(self):
        """commit_hash指定時はコミットハッシュベースのURLが生成される."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        commit_hash = "1c228c76996af8e9889b353ad6a66e1ec9d9c38a"
        url = generate_github_file_url(
            "FudanSELab.train-ticket",
            "ts-auth-service/src/main/java/auth/AuthController.java",
            commit_hash=commit_hash,
        )
        assert url is not None
        # コミットハッシュがURLに含まれる
        assert f"/blob/{commit_hash}/" in url
        # ブランチ名は含まれない
        assert "/blob/master/" not in url
        assert "github.com/FudanSELab/train-ticket" in url

    def test_generate_github_file_url_with_commit_hash_and_line_range(self):
        """commit_hash + 行範囲指定時のURL生成."""
        from src.visualize.components.clone_metrics import generate_github_file_url

        commit_hash = "abc123def456"
        url = generate_github_file_url(
            "FudanSELab.train-ticket",
            "/ts-auth-service/src/main/java/auth/AuthController.java",
            10,
            20,
            commit_hash=commit_hash,
        )
        assert url is not None
        # コミットハッシュがURLに含まれる
        assert f"/blob/{commit_hash}/" in url
        # 行範囲も含まれる
        assert "#L10-L20" in url
        # 先頭スラッシュは除去される
        assert "/blob/abc123def456/ts-auth-service/" in url


class TestProjectInfoFromServicesJson:
    """_load_project_info_from_services_json 関数のテスト."""

    def test_loads_url_from_services_json(self):
        """services_json から URL を読み込む."""
        from src.visualize.components.clone_metrics import (
            _load_project_info_from_services_json,
        )

        info = _load_project_info_from_services_json("FudanSELab.train-ticket")
        assert info.url == "https://github.com/FudanSELab/train-ticket"

    def test_returns_none_for_nonexistent_project(self):
        """存在しないプロジェクトの場合、None を返す."""
        from src.visualize.components.clone_metrics import (
            _load_project_info_from_services_json,
        )

        info = _load_project_info_from_services_json("nonexistent.project")
        assert info.url is None
        assert info.default_branch is None

    def test_default_branch_is_none_when_not_present(self):
        """default_branch がない場合、None."""
        from src.visualize.components.clone_metrics import (
            _load_project_info_from_services_json,
        )

        # FudanSELab.train-ticket には default_branch がない
        info = _load_project_info_from_services_json("FudanSELab.train-ticket")
        assert info.default_branch is None


class TestBuildCochangeHistorySection:
    """build_cochange_history_section 関数のテスト."""

    def test_no_clone_id_returns_no_cochange_message(self):
        """clone_idがない場合、no co-changeメッセージを返す."""
        from src.visualize.components.clone_detail import build_cochange_history_section

        row = {"file_path_x": "test.java"}
        result = build_cochange_history_section(row, "test.project", "Java")

        # Dash HTML Div が返されることを確認
        assert result is not None
        # "No co-changes" メッセージが含まれていることを確認
        assert _contains_text(result, "No co-changes")

    def test_empty_fragments_returns_no_cochange_message(self):
        """fragmentsが空の場合、no co-changeメッセージを返す."""
        from src.visualize.components.clone_detail import build_cochange_history_section

        row = {"clone_id": "nonexistent_clone"}
        result = build_cochange_history_section(row, "nonexistent.project", "Java")

        assert result is not None
        assert _contains_text(result, "No co-changes")

    def test_row_must_have_fragment_info(self):
        """rowにフラグメント情報が必要（ない場合はno co-change）."""
        from src.visualize.components.clone_detail import build_cochange_history_section

        # clone_idはあるが、file_path_x/yなどがない場合
        row = {"clone_id": "test_clone"}
        result = build_cochange_history_section(row, "nonexistent.project", "Java")

        assert result is not None
        # fragmentsが見つからないためNo co-changes
        assert _contains_text(result, "No co-changes")

    def test_row_with_full_pair_info_structure(self):
        """rowに完全なペア情報がある場合の構造確認."""
        from src.visualize.components.clone_detail import (
            _normalize_path,
            _safe_int,
        )

        # rowからペア情報を正しく取得できることを確認
        row = {
            "clone_id": "62",
            "file_path_x": "src/Main.java",
            "file_path_y": "src/Util.java",
            "start_line_x": 10,
            "end_line_x": 20,
            "start_line_y": 30,
            "end_line_y": 40,
        }

        # 値が正しく取得できることを確認
        assert row.get("file_path_x") == "src/Main.java"
        assert row.get("file_path_y") == "src/Util.java"
        assert _safe_int(row.get("start_line_x")) == 10
        assert _safe_int(row.get("end_line_x")) == 20
        assert _safe_int(row.get("start_line_y")) == 30
        assert _safe_int(row.get("end_line_y")) == 40

    def test_uses_precomputed_comodified_commits_from_scatter_row(self, monkeypatch):
        """scatter row uses precomputed common commit hashes when available."""
        from src.visualize.components import clone_detail

        monkeypatch.setattr(
            clone_detail,
            "load_metrics_dataframes",
            lambda *args, **kwargs: pytest.fail("enriched fragments fallback used"),
        )

        row = {
            "clone_id": "62",
            "file_path_x": "src/Main.java",
            "file_path_y": "src/Util.java",
            "start_line_x": 10,
            "end_line_x": 20,
            "start_line_y": 30,
            "end_line_y": 40,
            "comodified_commits": '["commit_a", "commit_b"]',
        }

        result = clone_detail.build_cochange_history_section(
            row, "owner.repo", "Java"
        )

        assert _contains_text(result, "2 common commit(s) found")
        assert _contains_text(result, "commit_")
        assert _contains_text(result, "View Commit")

    def test_backfilled_empty_commits_fall_back_when_pair_is_comodified(self):
        """old CSV rows backfilled with [] still allow enriched-fragment fallback."""
        from src.visualize.components.clone_detail import _parse_row_comodified_commits

        row = {
            "clone_id": "62",
            "comodified": True,
            "comodified_commits": "[]",
            "comodification_count": 1,
        }

        assert _parse_row_comodified_commits(row) is None

    def test_fragment_lookup_uses_selected_pair_not_first_two(self):
        """選択されたペアを使用し、最初の2つではないことを確認."""
        from src.visualize.components.clone_detail import _find_fragment_by_location

        # clone_id=62に5つのフラグメントがある状況をシミュレート
        # ユーザーがフラグメント2(index=2)とフラグメント4(index=4)を選択
        df = pd.DataFrame([
            {"file_path": "src/File0.java", "start_line": 100, "end_line": 110, "modified_commits": '["a"]'},
            {"file_path": "src/File1.java", "start_line": 200, "end_line": 210, "modified_commits": '["b"]'},
            {"file_path": "src/File2.java", "start_line": 300, "end_line": 310, "modified_commits": '["c", "common1"]'},
            {"file_path": "src/File3.java", "start_line": 400, "end_line": 410, "modified_commits": '["d"]'},
            {"file_path": "src/File4.java", "start_line": 500, "end_line": 510, "modified_commits": '["e", "common1"]'},
        ])

        # 正しいフラグメントを見つける（index 2と4）
        frag_x = _find_fragment_by_location(df, "src/File2.java", 300, 310)
        frag_y = _find_fragment_by_location(df, "src/File4.java", 500, 510)

        assert frag_x is not None
        assert frag_y is not None
        assert frag_x["modified_commits"] == '["c", "common1"]'
        assert frag_y["modified_commits"] == '["e", "common1"]'

        # 最初の2つ（index 0と1）を取得しないことを確認
        assert frag_x["file_path"] != "src/File0.java"
        assert frag_y["file_path"] != "src/File1.java"


def _contains_text(component, text: str) -> bool:
    """Dash コンポーネント内に指定テキストが含まれるかを再帰的にチェック."""
    if isinstance(component, str):
        return text in component

    if hasattr(component, "children"):
        children = component.children
        if children is None:
            return False
        if isinstance(children, str):
            return text in children
        if isinstance(children, list):
            return any(_contains_text(child, text) for child in children)
        return _contains_text(children, text)

    return False


class TestGenerateGithubDiffUrl:
    """generate_github_diff_url 関数のテスト."""

    def test_generate_github_diff_url_basic(self):
        """基本的なdiff URL生成."""
        import hashlib
        from src.visualize.components.clone_metrics import generate_github_diff_url

        # monkeypatch get_github_base_url をモックする代わりに、
        # プロジェクト名を使用して期待されるURLを確認
        result = generate_github_diff_url(
            "FudanSELab.train-ticket",
            "1c228c7",
            "ts-auth-service/src/Main.java"
        )

        # SHA-256 ハッシュを計算
        expected_hash = hashlib.sha256(
            "ts-auth-service/src/Main.java".encode()
        ).hexdigest()

        assert result is not None
        assert "#diff-" in result
        assert expected_hash in result
        assert "1c228c7" in result

    def test_generate_github_diff_url_empty_project(self):
        """project が空なら None を返す."""
        from src.visualize.components.clone_metrics import generate_github_diff_url

        result = generate_github_diff_url("", "abc123", "path/to/file.java")
        assert result is None

    def test_generate_github_diff_url_empty_commit(self):
        """commit_hash が空なら None を返す."""
        from src.visualize.components.clone_metrics import generate_github_diff_url

        result = generate_github_diff_url("owner.repo", "", "path/to/file.java")
        assert result is None

    def test_generate_github_diff_url_empty_file_path(self):
        """file_path が空なら None を返す."""
        from src.visualize.components.clone_metrics import generate_github_diff_url

        result = generate_github_diff_url("owner.repo", "abc123", "")
        assert result is None

    def test_generate_github_diff_url_strips_leading_slash(self):
        """先頭スラッシュが削除されてハッシュ計算されること."""
        import hashlib
        from src.visualize.components.clone_metrics import generate_github_diff_url

        # 先頭スラッシュありとなしで同じ結果になることを確認
        result_with_slash = generate_github_diff_url(
            "owner.repo",
            "abc123",
            "/path/to/file.java"
        )
        result_without_slash = generate_github_diff_url(
            "owner.repo",
            "abc123",
            "path/to/file.java"
        )

        # 両方とも先頭スラッシュなしのパスでハッシュ計算される
        expected_hash = hashlib.sha256("path/to/file.java".encode()).hexdigest()

        assert result_with_slash is not None
        assert result_without_slash is not None
        assert expected_hash in result_with_slash
        assert expected_hash in result_without_slash
        # 結果が同じであることを確認
        assert result_with_slash == result_without_slash
