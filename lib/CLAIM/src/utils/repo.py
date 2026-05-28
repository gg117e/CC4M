import os
import shutil
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))
from src.utils.print_utils import print_warning


def clear_repo(path: Path) -> None:
    """
    Clear a repository

    :param path: the path of the repository
    :return: None
    """
    try:
        # It is necessary to elevate permissions otherwise deleting fails
        for file in path.glob('.git/objects/pack/*.idx'):
            os.chmod(file, 0o777)
        for file in path.glob('.git/objects/pack/*.pack'):
            os.chmod(file, 0o777)

        shutil.rmtree(path)

    except Exception as e:
        print_warning(f'-failed to delete {path}. Reason: {e}')
