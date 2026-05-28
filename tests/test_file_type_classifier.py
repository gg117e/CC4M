from pathlib import Path

from modules.util import get_file_type


def test_get_file_type_uses_path_for_test_file():
    result = get_file_type("services/auth/tests/test_login.py", language="Python")
    assert result == "test"


def test_get_file_type_defaults_to_logic_without_special_signal():
    result = get_file_type("src/service/user_service.py")
    assert result == "logic"


def test_get_file_type_models_path_without_data_content_returns_logic():
    result = get_file_type("src/models/user.py")
    assert result == "logic"
