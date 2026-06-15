import pytest

from workflows.application.configuration import ConfigError, _st_presets
from workflows.infrastructure.ww3.server_sh import _st_executable_dir


def test_st_preset_accepts_model_base_directory_without_exe_suffix() -> None:
    assert _st_presets({"ST6": "/opt/ww3/ST6/"}) == {"ST6": "/opt/ww3/ST6"}


@pytest.mark.parametrize(
    ("configured_path", "expected"),
    [
        ("/opt/ww3/ST6", "/opt/ww3/ST6/exe"),
        ("/opt/ww3/ST6/exe", "/opt/ww3/ST6/exe"),
        ("/opt/ww3/ST6/exe/", "/opt/ww3/ST6/exe"),
    ],
)
def test_st_executable_dir_accepts_model_or_executable_directory(
    configured_path: str,
    expected: str,
) -> None:
    assert _st_executable_dir(configured_path) == expected


@pytest.mark.parametrize(
    "presets",
    [
        {"": "/opt/ww3/ST6"},
        {"ST6": ""},
    ],
)
def test_st_preset_still_rejects_empty_name_or_path(presets: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="名称和路径均不能为空"):
        _st_presets(presets)
