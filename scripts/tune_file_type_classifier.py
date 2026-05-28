"""Generate staged-classification misclassification analysis report."""

from __future__ import annotations

import argparse
import json
import logging
from math import fsum
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _find_repo_root(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return start


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
sys.path.append(str(REPO_ROOT / "src"))

from modules import util


LOGGER = logging.getLogger(__name__)
LABELS = ("logic", "data", "config", "test")
DEFAULT_GOLD = Path("tests/fixtures/file_type_gold_small.jsonl")
DEFAULT_REPORT = Path(
    "dest/analysis_reports/file_type_classifier_misclassification_report.md"
)


@dataclass(frozen=True)
class GoldSample:
    """Single labeled sample used for evaluation."""

    id: str
    file_path: str
    language: str | None
    file_text: str | None
    label: str


@dataclass(frozen=True)
class SamplePrediction:
    """Predicted label and explanation for one sample."""

    sample: GoldSample
    predicted_label: str
    stage: str
    matched_rules: tuple[str, ...]


@dataclass(frozen=True)
class LabelMetrics:
    """Per-label metrics."""

    label: str
    support: int
    precision: float
    recall: float
    f1: float


@dataclass(frozen=True)
class EvaluationResult:
    """Aggregate evaluation data."""

    accuracy: float
    macro_f1: float
    per_label: tuple[LabelMetrics, ...]
    confusion: dict[str, dict[str, int]]
    errors: tuple[SamplePrediction, ...]


def configure_logging(verbose: bool) -> None:
    """Configure logging level for this script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def load_gold_samples(gold_path: Path) -> list[GoldSample]:
    """Load JSONL gold samples for classifier evaluation."""
    samples: list[GoldSample] = []
    with gold_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            row = json.loads(stripped)
            samples.append(
                GoldSample(
                    id=str(row["id"]),
                    file_path=str(row["file_path"]),
                    language=row.get("language"),
                    file_text=row.get("file_text"),
                    label=str(row["label"]),
                )
            )
    if not samples:
        raise ValueError(f"gold dataset is empty: {gold_path}")
    return samples


def _collect_matches(text: str, patterns: tuple[object, ...]) -> tuple[str, ...]:
    """Collect regex pattern texts that match input text."""
    matched: list[str] = []
    for pat in patterns:
        if pat.search(text):
            matched.append(pat.pattern)
    return tuple(matched)


def explain_prediction(sample: GoldSample) -> SamplePrediction:
    """Classify one sample and return stage and matched rules."""
    predicted = util.get_file_type(
        sample.file_path,
        language=sample.language,
    )

    path_type = util._get_file_type_from_path(sample.file_path)
    if path_type != "logic":
        return SamplePrediction(
            sample,
            predicted,
            "path",
            (f"path_type={path_type}",),
        )

    lower_name = sample.file_path.lower().replace("\\", "/").rsplit("/", 1)[-1]
    ext = util._extract_extension(lower_name)
    if ext in util._CONFIG_EXTENSIONS:
        return SamplePrediction(sample, predicted, "extension", (f"ext={ext}",))
    if ext in util._DATA_EXTENSIONS:
        return SamplePrediction(sample, predicted, "extension", (f"ext={ext}",))

    return SamplePrediction(sample, predicted, "default", ())


def evaluate(samples: Iterable[GoldSample]) -> EvaluationResult:
    """Compute confusion matrix, per-label metrics, and error records."""
    confusion = {actual: {pred: 0 for pred in LABELS} for actual in LABELS}
    errors: list[SamplePrediction] = []
    total = 0
    correct = 0

    for sample in samples:
        pred = explain_prediction(sample)
        total += 1
        if sample.label not in confusion:
            raise ValueError(f"unknown label in gold: {sample.label}")
        confusion[sample.label][pred.predicted_label] += 1
        if pred.predicted_label == sample.label:
            correct += 1
        else:
            errors.append(pred)

    per_label: list[LabelMetrics] = []
    for label in LABELS:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in LABELS if other != label)
        fn = sum(confusion[label][other] for other in LABELS if other != label)
        support = sum(confusion[label].values())

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        per_label.append(
            LabelMetrics(
                label=label,
                support=support,
                precision=precision,
                recall=recall,
                f1=f1,
            )
        )

    macro_f1 = fsum(m.f1 for m in per_label) / len(LABELS)
    accuracy = correct / total if total else 0.0

    return EvaluationResult(
        accuracy=accuracy,
        macro_f1=macro_f1,
        per_label=tuple(per_label),
        confusion=confusion,
        errors=tuple(errors),
    )


def _format_float(value: float) -> str:
    return f"{value:.4f}"


def build_markdown_report(
    result: EvaluationResult,
    *,
    gold_path: Path,
    max_errors: int,
) -> str:
    """Build markdown report for staged classification evaluation."""
    lines: list[str] = []
    lines.append("# File Type Classifier Misclassification Report")
    lines.append("")
    lines.append(f"- Gold dataset: {gold_path.as_posix()}")
    lines.append(
        f"- Samples: {sum(sum(row.values()) for row in result.confusion.values())}"
    )
    lines.append(f"- Accuracy: {_format_float(result.accuracy)}")
    lines.append(f"- Macro-F1: {_format_float(result.macro_f1)}")
    lines.append("")

    lines.append("## Per-label Metrics")
    lines.append("")
    lines.append("| label | support | precision | recall | f1 |")
    lines.append("|---|---:|---:|---:|---:|")
    for m in result.per_label:
        lines.append(
            f"| {m.label} | {m.support} | {_format_float(m.precision)} | {_format_float(m.recall)} | {_format_float(m.f1)} |"
        )
    lines.append("")

    lines.append("## Confusion Matrix")
    lines.append("")
    lines.append("| actual \\ predicted | logic | data | config | test |")
    lines.append("|---|---:|---:|---:|---:|")
    for actual in LABELS:
        row = result.confusion[actual]
        lines.append(
            f"| {actual} | {row['logic']} | {row['data']} | {row['config']} | {row['test']} |"
        )
    lines.append("")

    lines.append("## Misclassifications")
    lines.append("")
    if not result.errors:
        lines.append("- No misclassifications.")
        return "\n".join(lines)

    lines.append("| id | expected | predicted | stage | path | matched_rules |")
    lines.append("|---|---|---|---|---|---|")
    for err in result.errors[:max_errors]:
        rules = "; ".join(err.matched_rules) if err.matched_rules else "-"
        lines.append(
            f"| {err.sample.id} | {err.sample.label} | {err.predicted_label} | {err.stage} | {err.sample.file_path} | {rules} |"
        )
    return "\n".join(lines)


def save_report(report_path: Path, text: str) -> None:
    """Persist markdown report to file."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold",
        type=Path,
        default=DEFAULT_GOLD,
        help="Path to JSONL gold dataset.",
    )
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--max-errors", type=int, default=50)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def main() -> int:
    """Run staged-classifier evaluation and write misclassification report."""
    args = parse_args()
    configure_logging(args.verbose)

    samples = load_gold_samples(args.gold)
    LOGGER.info("Loaded %d gold samples from %s", len(samples), args.gold)

    result = evaluate(samples)
    report = build_markdown_report(
        result,
        gold_path=args.gold,
        max_errors=args.max_errors,
    )
    save_report(args.report_out, report)

    LOGGER.info("Accuracy = %.4f", result.accuracy)
    LOGGER.info("Macro-F1 = %.4f", result.macro_f1)
    LOGGER.info("Misclassifications = %d", len(result.errors))
    LOGGER.info("Report saved: %s", args.report_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
