import json

from epanet_tools.io.reports import write_validation_report
from epanet_tools.models import ValidationIssue
from epanet_tools.topology.validation import PipeValidationReport


def test_write_validation_report_creates_json_and_csv(tmp_path) -> None:
    report = PipeValidationReport(
        feature_count=2,
        issues=[
            ValidationIssue(
                code="TEST_WARNING",
                severity="warning",
                message="Synthetic warning.",
                element_id="1",
            )
        ],
    )

    paths = write_validation_report(report, outdir=tmp_path, name="demo")

    assert paths["json"].exists()
    assert paths["csv"].exists()

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["feature_count"] == 2
    assert payload["issue_counts"] == {"info": 0, "warning": 1, "error": 0}
