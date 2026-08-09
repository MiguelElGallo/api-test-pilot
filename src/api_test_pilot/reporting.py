"""Portable JSON, JUnit XML, and self-contained HTML report writers."""

from __future__ import annotations

import html
import json
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement

from api_test_pilot.models import RunSummary


def write_json(summary: RunSummary, destination: Path) -> None:
    """Write the canonical machine-readable report."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_junit(summary: RunSummary, destination: Path) -> None:
    """Write a JUnit report understood by common CI report viewers."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    suite = Element(
        "testsuite",
        name="api-test-pilot",
        tests=str(summary.total),
        failures=str(summary.failed),
        timestamp=summary.started_at.isoformat(),
    )
    for result in summary.results:
        case = SubElement(
            suite,
            "testcase",
            classname=f"api.{result.scenario.category.value}",
            name=result.scenario.identifier,
            time=f"{result.duration_ms / 1_000:.6f}",
        )
        if not result.passed:
            failure = SubElement(case, "failure", message=result.error or "API scenario failed")
            failure.text = result.response_excerpt or result.error or "No response body"
    ElementTree(suite).write(destination, encoding="utf-8", xml_declaration=True)


def write_html(summary: RunSummary, destination: Path) -> None:
    """Write a self-contained, human-readable regression report."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = "".join(
        (
            f"<tr class={'pass' if result.passed else 'fail'}>"
            f"<td>{html.escape(result.scenario.identifier)}</td>"
            f"<td>{html.escape(result.scenario.category.value)}</td>"
            f"<td>{html.escape(result.scenario.method)} {html.escape(result.scenario.path)}</td>"
            f"<td>{result.status_code if result.status_code is not None else 'N/A'}</td>"
            f"<td>{'PASS' if result.passed else 'FAIL'}</td>"
            f"<td>{html.escape(result.error or '')}</td></tr>"
        )
        for result in summary.results
    )
    analysis = html.escape(summary.ai_analysis or "AI analysis was not requested or not available.")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>API Test Pilot Report</title><style>
body{{font-family:system-ui,sans-serif;max-width:1200px;margin:2rem auto;
padding:0 1rem;color:#18212f}}
.cards{{display:flex;gap:1rem}}
.card{{padding:1rem;border:1px solid #d8dee9;border-radius:.5rem}}
table{{width:100%;border-collapse:collapse;margin-top:1rem}}
th,td{{padding:.6rem;border:1px solid #ddd;text-align:left}}
.pass td:nth-child(5){{color:#067647;font-weight:700}}
.fail td:nth-child(5){{color:#b42318;font-weight:700}}
pre{{white-space:pre-wrap;background:#f6f8fa;padding:1rem;border-radius:.5rem}}
</style></head><body><h1>API Test Pilot Report</h1>
<p>Target: <code>{html.escape(summary.base_url)}</code></p>
<div class="cards"><div class="card">Total: {summary.total}</div>
<div class="card">Passed: {summary.passed}</div>
<div class="card">Failed: {summary.failed}</div></div>
<table><thead><tr><th>Scenario</th><th>Category</th><th>Request</th>
<th>Status</th><th>Result</th><th>Error</th></tr></thead><tbody>{rows}</tbody></table>
<h2>AI-assisted failure analysis</h2><pre>{analysis}</pre></body></html>"""
    destination.write_text(document, encoding="utf-8")


def write_all(summary: RunSummary, directory: Path) -> dict[str, Path]:
    """Write all supported formats and return their resolved paths."""
    outputs = {
        "json": directory / "report.json",
        "junit": directory / "junit.xml",
        "html": directory / "report.html",
    }
    write_json(summary, outputs["json"])
    write_junit(summary, outputs["junit"])
    write_html(summary, outputs["html"])
    return outputs
