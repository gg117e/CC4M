import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent
logger = logging.getLogger(__name__)


def _public_web_url(host: str, port: int, *, visualize_only: bool) -> str:
    public_host = os.environ.get("MSCCVIS_PUBLIC_HOST")
    if not public_host:
        public_host = "localhost" if host in {"0.0.0.0", "::"} else host

    base_url = os.environ.get("MSCCVIS_PUBLIC_URL") or f"http://{public_host}:{port}"
    if visualize_only:
        return f"{base_url.rstrip('/')}/visualize/"
    return base_url


def run_script(script_name: str, script_args: list[str] | None = None) -> int:
    """Run a script under src/commands in a child Python process."""
    script_path = project_root / "src" / "commands" / script_name
    if not script_path.exists():
        logger.error(f"Script not found: {script_path}")
        return 1
    cmd = [sys.executable, str(script_path)]
    if script_args:
        cmd.extend(script_args)
    completed = subprocess.run(cmd)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="CC4M CLI launcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "generate-dataset",
        help="Run src/commands/pipeline/generate_dataset.py",
    )
    subparsers.add_parser(
        "run-all-steps",
        help="Run src/commands/csv_build/run_all_step.py",
        description=(
            "Run the CSV build pipeline. Extra arguments are passed through to "
            "run_all_step.py."
        ),
    )
    subparsers.add_parser(
        "determine-analyzed-commits",
        help="Run src/commands/pipeline/determine_analyzed_commits.py",
    )
    subparsers.add_parser(
        "refresh-service-map",
        help="Run src/commands/pipeline/refresh_service_map.py",
    )
    subparsers.add_parser(
        "check-run-all-steps",
        help="Check run-all-steps progress",
    )
    subparsers.add_parser(
        "summarize-csv",
        help="Run src/commands/csv_analysis/generate_report.py",
    )
    subparsers.add_parser(
        "csv-boxplot",
        help="Run src/commands/csv_analysis/generate_figure.py",
    )

    web_parser = subparsers.add_parser("web-ui", help="Start the Web UI")
    web_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host (default: 127.0.0.1)",
    )
    web_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Bind port (default: 8000)",
    )
    web_parser.add_argument(
        "--visualize-only",
        action="store_true",
        help="Redirect / to /visualize/ for local visualization-only use",
    )

    args, unknown = parser.parse_known_args()

    if args.command == "generate-dataset":
        return run_script("pipeline/generate_dataset.py", unknown)
    if args.command == "run-all-steps":
        return run_script("csv_build/run_all_step.py", unknown)
    if args.command == "determine-analyzed-commits":
        return run_script("pipeline/determine_analyzed_commits.py", unknown)
    if args.command == "refresh-service-map":
        return run_script("pipeline/refresh_service_map.py", unknown)
    if args.command == "check-run-all-steps":
        return run_script("misc/check_progress.py", unknown)
    if args.command == "summarize-csv":
        return run_script("csv_analysis/generate_report.py", unknown)
    if args.command == "csv-boxplot":
        return run_script("csv_analysis/generate_figure.py", unknown)
    if args.command == "web-ui":
        if args.visualize_only:
            os.environ["MSCCVIS_VISUALIZE_ONLY"] = "1"

        import uvicorn

        display_url = _public_web_url(
            args.host,
            args.port,
            visualize_only=args.visualize_only,
        )
        logger.info("CC4M is ready at: %s", display_url)
        uvicorn.run(
            "src.web.app:app",
            host=args.host,
            port=args.port,
            log_level=os.environ.get("MSCCVIS_UVICORN_LOG_LEVEL", "warning"),
            reload=False,
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
