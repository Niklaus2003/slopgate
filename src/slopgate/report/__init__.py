"""Receipt generators, run summary reporting, and calibration analytics."""

from slopgate.report.calibration import (
    CalibrationMetrics,
    compute_calibration_metrics,
    export_calibration_report,
    render_markdown_calibration_report,
)
from slopgate.report.receipts import (
    build_item_receipt,
    export_receipt_to_disk,
    render_markdown_receipt,
)
from slopgate.report.summary import RunSummary, calculate_percentiles

__all__ = [
    "CalibrationMetrics",
    "RunSummary",
    "build_item_receipt",
    "calculate_percentiles",
    "compute_calibration_metrics",
    "export_calibration_report",
    "export_receipt_to_disk",
    "render_markdown_calibration_report",
    "render_markdown_receipt",
]
