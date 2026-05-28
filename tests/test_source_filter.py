from pathlib import Path

from modules.source_filter import filter_imports


def _filter_text(tmp_path: Path, language: str, text: str) -> list[str]:
    path = tmp_path / "sample.txt"
    path.write_text(text, encoding="utf-8")

    original_line_count = len(text.splitlines())
    filter_imports(path, language)
    filtered = path.read_text(encoding="utf-8").splitlines()

    assert len(filtered) == original_line_count
    return filtered


def test_filters_jvm_package_and_import_lines(tmp_path: Path) -> None:
    filtered = _filter_text(
        tmp_path,
        "Java",
        "\n".join(
            [
                "package food;",
                "import org.springframework.boot.SpringApplication;",
                "",
                "@SpringBootApplication",
                "public class FoodMapApplication {}",
            ]
        ),
    )

    assert filtered[0] == "// package food;"
    assert filtered[1] == "// import org.springframework.boot.SpringApplication;"
    assert filtered[3] == "@SpringBootApplication"


def test_filters_javascript_require_and_export_from_lines(tmp_path: Path) -> None:
    filtered = _filter_text(
        tmp_path,
        "JavaScript",
        "\n".join(
            [
                "var Parser = require('./parser')",
                "  , Lexer = require('./lexer')",
                "  , utils = require('./utils');",
                "const fs = require('fs');",
                "require('dotenv').config();",
                "export { Button } from './button';",
                "function run() { return require(name); }",
            ]
        ),
    )

    assert filtered[0] == "// var Parser = require('./parser')"
    assert filtered[1] == "//   , Lexer = require('./lexer')"
    assert filtered[2] == "//   , utils = require('./utils');"
    assert filtered[3] == "// const fs = require('fs');"
    assert filtered[4] == "// require('dotenv').config();"
    assert filtered[5] == "// export { Button } from './button';"
    assert filtered[6] == "function run() { return require(name); }"


def test_filters_go_package_and_import_block(tmp_path: Path) -> None:
    filtered = _filter_text(
        tmp_path,
        "Go",
        "\n".join(
            [
                "package main",
                "",
                "import (",
                '    "fmt"',
                '    "net/http"',
                ") // imports",
                "",
                "func main() {}",
            ]
        ),
    )

    assert filtered[0] == "// package main"
    assert filtered[2] == "// import ("
    assert filtered[3] == '//     "fmt"'
    assert filtered[4] == '//     "net/http"'
    assert filtered[5] == "// ) // imports"
    assert filtered[7] == "func main() {}"


def test_filters_python_multiline_from_import_block(tmp_path: Path) -> None:
    filtered = _filter_text(
        tmp_path,
        "Python",
        "\n".join(
            [
                "from package.module import (",
                "    Foo,",
                "    Bar,",
                ")",
                "import os",
                "",
                "def run():",
                "    return Foo()",
            ]
        ),
    )

    assert filtered[0] == "# from package.module import ("
    assert filtered[1] == "#     Foo,"
    assert filtered[2] == "#     Bar,"
    assert filtered[3] == "# )"
    assert filtered[4] == "# import os"
    assert filtered[6] == "def run():"
