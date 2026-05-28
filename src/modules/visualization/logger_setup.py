import logging
import sys
import time
from pathlib import Path
from datetime import datetime


def setup_logger(script_path: str) -> logging.Logger:
    """
    スクリプトごとのロガーを設定する。
    ログファイルは logs/ ディレクトリに保存される。

    Args:
        script_path: 実行中のスクリプトのパス (__file__)

    Returns:
        設定済みの Logger オブジェクト
    """
    script_name = Path(script_path).stem
    project_root = Path(script_path).parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = log_dir / f"{timestamp}_{script_name}.log"

    logger = logging.getLogger(script_name)
    logger.setLevel(logging.INFO)

    # ファイルハンドラの設定
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    # 既存のハンドラがあれば削除（重複防止）
    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(file_handler)

    # コンソール出力は既存のprintと競合しないよう、ここでは追加しない
    # 必要であれば StreamHandler を追加する

    return logger


def log_execution_time(logger: logging.Logger, start_time: float):
    """
    実行時間を計算してログと標準出力に記録する。
    """
    end_time = time.time()
    elapsed_time = end_time - start_time
    message = f"Total execution time: {elapsed_time:.2f} seconds"
    logger.info(message)
    print(message)
