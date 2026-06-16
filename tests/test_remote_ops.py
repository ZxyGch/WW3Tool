from workflows.application.remote_ops import _parse_sinfo_idle_resources


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
