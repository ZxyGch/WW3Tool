from workflows.application.remote_ops import _forcing_excluded_relpaths, _parse_sinfo_idle_resources
from workflows.domain.config_models import ForcingConfig, PipelineConfig, WorkdirConfig


def test_parse_sinfo_idle_resources_counts_idle_and_mixed_cpus() -> None:
    output = "\n".join(
        [
            "node001|idle|64|0/64/0/64|cpu",
            "node002|mixed|64|40/24/0/64|cpu",
            "node003|allocated|64|64/0/0/64|cpu",
            "node004|down|64|0/0/64/64|cpu",
        ]
    )

    data = _parse_sinfo_idle_resources(output)

    assert data["idle_nodes"] == 1
    assert data["idle_cpus"] == 88
    assert data["idle_node_details"][0]["node"] == "node001"
    assert data["mixed_node_details"][0]["idle_cpus"] == 24
    assert data["idle_summary"][0]["cpu"] == "cpu"
    assert data["idle_summary"][0]["nodes"] == 2
    assert data["idle_summary"][0]["cores"] == 88
    assert data["partitions"] == ["cpu"]


def test_parse_sinfo_idle_resources_merges_same_cpu_partition() -> None:
    output = "\n".join(
        [
            "node001|idle|64|0/64/0/64|CPU6240R",
            "node002|mixed|64|48/16/0/64|CPU6240R",
            "node003|idle|32|0/32/0/32|CPU6336Y",
        ]
    )

    data = _parse_sinfo_idle_resources(output)

    assert data["idle_summary"][0]["cpu"] == "CPU6240R"
    assert data["idle_summary"][0]["nodes"] == 2
    assert data["idle_summary"][0]["cores"] == 80
    assert data["idle_summary"][0]["max_cores_per_node"] == 64


def test_parse_sinfo_idle_resources_keeps_all_partitions_for_dropdown() -> None:
    output = "\n".join(
        [
            "node001|allocated|64|64/0/0/64|CPU6240R",
            "node002|idle|32|0/32/0/32|CPU6336Y",
            "node003|down|64|0/0/64/64|CPU8358,CPU8360Y*",
        ]
    )

    data = _parse_sinfo_idle_resources(output)

    assert data["partitions"] == ["CPU6240R", "CPU6336Y", "CPU8358", "CPU8360Y"]


def test_forcing_excluded_relpaths_uses_relative_workdir_paths(tmp_path) -> None:
    forcing_dir = tmp_path / "forcing"
    forcing_dir.mkdir()
    forcing_file = forcing_dir / "wind.nc"
    forcing_file.write_bytes(b"forcing")
    (tmp_path / "server.sh").write_text("echo ok\n")

    config = PipelineConfig(
        source_path=None,
        base_dir=tmp_path,
        workdir=WorkdirConfig(path=tmp_path),
        forcing=ForcingConfig(wind=forcing_file),
    )

    assert _forcing_excluded_relpaths(config, str(tmp_path)) == {"forcing/wind.nc"}
