from __future__ import annotations

import re
from pathlib import Path


SLASH_COMMENT_LANGUAGES = {
    "C",
    "C++",
    "C#",
    "Go",
    "Java",
    "JavaScript",
    "Kotlin",
    "PHP",
    "Rust",
    "Scala",
    "Swift",
    "TypeScript",
}
HASH_COMMENT_LANGUAGES = {"Python", "Ruby"}
JVM_PACKAGE_LANGUAGES = {"Java", "Kotlin", "Scala"}
JS_TS_LANGUAGES = {"JavaScript", "TypeScript"}

REQUIRE_DECL_RE = re.compile(
    r"^(?:const|let|var)\s+[\w${}\[\],\s:]+\s*=\s*require\s*\("
)
BARE_REQUIRE_RE = re.compile(r"^require\s*\(")
EXPORT_FROM_RE = re.compile(r"^export\b.+\bfrom\b")


def _comment_char(language: str) -> str:
    if language in HASH_COMMENT_LANGUAGES:
        return "# "
    return "// "


def _comment_out(line: str, language: str) -> str:
    return f"{_comment_char(language)}{line}"


def _paren_delta(line: str) -> int:
    return line.count("(") - line.count(")")


def _is_js_require_declaration(stripped: str) -> bool:
    return bool(REQUIRE_DECL_RE.match(stripped) or BARE_REQUIRE_RE.match(stripped))


def _line_ends_statement(stripped: str) -> bool:
    return stripped.endswith(";")


def _filter_lines(lines: list[str], language: str) -> list[str]:
    new_lines: list[str] = []
    in_go_import_block = False
    in_python_from_import_block = False
    python_import_paren_balance = 0
    in_js_require_block = False

    for line in lines:
        stripped = line.strip()
        is_declaration = False

        if in_go_import_block:
            is_declaration = True
            if stripped.startswith(")"):
                in_go_import_block = False
        elif in_python_from_import_block:
            is_declaration = True
            python_import_paren_balance += _paren_delta(stripped)
            if python_import_paren_balance <= 0:
                in_python_from_import_block = False
                python_import_paren_balance = 0
        elif in_js_require_block:
            is_declaration = True
            if _line_ends_statement(stripped):
                in_js_require_block = False
        elif language == "Python":
            if stripped.startswith("import "):
                is_declaration = True
            elif stripped.startswith("from ") and " import " in stripped:
                is_declaration = True
                if "(" in stripped and _paren_delta(stripped) > 0:
                    in_python_from_import_block = True
                    python_import_paren_balance = _paren_delta(stripped)
        elif language == "Go":
            if stripped.startswith("package "):
                is_declaration = True
            elif stripped == "import (" or stripped.startswith("import ("):
                is_declaration = True
                if not stripped.endswith(")"):
                    in_go_import_block = True
            elif stripped.startswith("import "):
                is_declaration = True
        elif language in JVM_PACKAGE_LANGUAGES:
            if stripped.startswith("package ") or stripped.startswith("import "):
                is_declaration = True
        elif language in JS_TS_LANGUAGES:
            if stripped.startswith("import "):
                is_declaration = True
            elif EXPORT_FROM_RE.match(stripped):
                is_declaration = True
            elif _is_js_require_declaration(stripped):
                is_declaration = True
                if not _line_ends_statement(stripped):
                    in_js_require_block = True
        elif language in SLASH_COMMENT_LANGUAGES:
            if language in {"C", "C++"} and stripped.startswith("#include "):
                is_declaration = True
            elif language == "Rust" and stripped.startswith("use "):
                is_declaration = True
            elif language == "PHP" and (
                stripped.startswith("use ")
                or stripped.startswith("require ")
                or stripped.startswith("include ")
            ):
                is_declaration = True
            elif stripped.startswith("import "):
                is_declaration = True
        elif language == "Ruby":
            if stripped.startswith("require ") or stripped.startswith("load "):
                is_declaration = True

        new_lines.append(_comment_out(line, language) if is_declaration else line)

    return new_lines


def filter_imports(file_path: Path, language: str) -> None:
    """Comment out import/declaration lines while preserving line numbers."""
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return

    new_lines = _filter_lines(lines, language)

    with file_path.open("w", encoding="utf-8") as f:
        f.writelines(new_lines)


def apply_filter(project_dir: Path, languages: list, exts: dict) -> None:
    """Apply declaration-line filtering to all target-language files."""
    for language in languages:
        if language not in exts:
            continue
        extensions = exts[language]
        for ext in extensions:
            for file_path in project_dir.rglob(f"*{ext}"):
                if file_path.is_file():
                    filter_imports(file_path, language)
