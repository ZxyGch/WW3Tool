"""ww3_grid.nml 解析：注释行不得参与取值。

工具生成的 ww3_grid.nml 在真实赋值前带有 ``!     SPECTRUM%NK = 0`` 之类的模板说明行。
2026-09-15 用工具真实模板做端到端预检时，边界 pregrid 从注释里读到 NK=NTH=0 而失败；
run_boundary_ww3_live.py 自己写的精简 namelist 没有注释，所以此前的真实积分验收没有暴露。
"""

from pathlib import Path

import pytest

from workflows.infrastructure.boundary.nml_text import effective_nml_assignments
from workflows.infrastructure.boundary.rect_boundary import _parse_nml_assignments, set_mask_nml
from workflows.infrastructure.boundary.spectrum_coords import parse_spectrum_from_nml

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("version", ["6.07", "7.14"])
def test_parse_spectrum_from_real_template(version):
    nml = REPO / "public" / f"{version}_nml" / "ww3_grid.nml"
    if not nml.is_file():
        pytest.skip(f"缺少模板 {nml}")
    text = nml.read_text(encoding="utf-8")
    assert "!     SPECTRUM%NK          = 0" in text  # 模板里确有注释掉的 0，本测试才有意义
    spec = parse_spectrum_from_nml(nml)
    assert len(spec.frequencies_hz) == 35
    assert len(spec.directions_deg) == 36
    assert spec.frequencies_hz[0] == pytest.approx(0.0375)
    assert spec.frequencies_hz[1] / spec.frequencies_hz[0] == pytest.approx(1.1)


def test_effective_assignments_skip_comments_and_last_wins():
    text = (
        "!     SPECTRUM%NK = 0             ! 注释说明\n"
        "SPECTRUM%NK = 99\n"  # 组外赋值不生效
        "&SPECTRUM_NML\n"
        "  SPECTRUM%NK   =  35   ! 行内注释\n"
        "! SPECTRUM%NK   =  12\n"  # 真实值之后的注释备选也不得覆盖
        "  SPECTRUM%NTH  =  24\n"
        "  SPECTRUM%NTH  =  36\n"  # 同键多次赋值，后者生效
        "/\n"
        "&MASK_NML\n"
        "  MASK%FILENAME = 'dir/a!b.mask'  ! 引号内的 ! 与 / 不是注释或组结束\n"
        "/\n"
    )
    values = effective_nml_assignments(text)
    assert values["SPECTRUM%NK"] == "35"
    assert values["SPECTRUM%NTH"] == "36"
    assert values["MASK%FILENAME"] == "dir/a!b.mask"


def test_effective_assignments_one_line_group():
    values = effective_nml_assignments("&RECT_NML RECT%NX = 61, RECT%NY = 7 /\n  RECT%NX = 1\n")
    assert values == {"RECT%NX": "61", "RECT%NY": "7"}


def test_rect_parser_ignores_commented_override(tmp_path: Path):
    nml = tmp_path / "ww3_grid.nml"
    nml.write_text("&RECT_NML\n  RECT%NX = 61\n!  RECT%NX = 0\n/\n", encoding="utf-8")
    assert _parse_nml_assignments(nml)["RECT%NX"] == "61"


def test_set_mask_nml_ignores_commented_group(tmp_path: Path):
    doc = "!&MASK_NML\n!  MASK%FILENAME = 'unset'\n!/\n"
    nml = tmp_path / "ww3_grid.nml"
    nml.write_text(doc + "&MASK_NML\n  MASK%FILENAME = 'grid.mask_nobound'\n/\n", encoding="utf-8")
    set_mask_nml(nml, "boundary/grid.mask_boundary")
    text = nml.read_text(encoding="utf-8")
    assert text.startswith(doc)  # 注释说明块原样保留，不被写入有效赋值
    values = effective_nml_assignments(text)
    assert values["MASK%FILENAME"] == "boundary/grid.mask_boundary"
    assert values["MASK%IDLA"] == "1" and values["MASK%IDFM"] == "1"
