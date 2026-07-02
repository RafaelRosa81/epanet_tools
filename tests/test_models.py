from epanet_tools.models import HydraulicModel, Node, Pipe, PipeStatus, ValidationIssue


def test_hydraulic_model_can_store_nodes_pipes_and_issues() -> None:
    model = HydraulicModel(name="demo")
    model.nodes["J000001"] = Node(id="J000001", x=100.0, y=200.0, elevation_m=25.0)
    model.pipes["P000001"] = Pipe(
        id="P000001",
        from_node="J000001",
        to_node="J000002",
        length_m=12.5,
        diameter_mm=63.0,
        roughness=140.0,
        status=PipeStatus.OPEN,
    )
    model.issues.append(
        ValidationIssue(
            code="DEMO_WARNING",
            severity="warning",
            message="Synthetic warning for test coverage.",
        )
    )

    assert model.name == "demo"
    assert model.nodes["J000001"].elevation_m == 25.0
    assert model.pipes["P000001"].status is PipeStatus.OPEN
    assert model.issues[0].severity == "warning"
