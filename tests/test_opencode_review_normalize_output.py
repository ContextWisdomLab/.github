"""Tests for scripts/ci/opencode_review_normalize_output.py."""
from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from opencode_review_normalize_output import (
    admits_missing_structural_review,
    check_structural_approval,
    iter_json_objects,
    main,
    mentions_changed_file_evidence,
    valid_control,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_KWARGS = {
    "expected_head_sha": "sha1",
    "expected_run_id": "run1",
    "expected_run_attempt": "1",
}


def _valid_approve_value(**overrides: object) -> dict:
    """Return a minimal valid APPROVE control block."""
    base: dict = {
        "head_sha": "sha1",
        "run_id": "run1",
        "run_attempt": "1",
        "result": "APPROVE",
        "reason": "Reviewed scripts/ci/pr_review_merge_scheduler.py thoroughly.",
        "summary": "All changes in scripts/ci/pr_review_merge_scheduler.py look correct.",
        "findings": [],
    }
    base.update(overrides)
    return base


def _valid_request_changes_value(**overrides: object) -> dict:
    """Return a minimal valid REQUEST_CHANGES control block with one finding."""
    finding: dict = {
        "path": "scripts/ci/pr_review_merge_scheduler.py",
        "line": 10,
        "severity": "HIGH",
        "title": "Bug in function",
        "problem": "The function does X incorrectly.",
        "root_cause": "Missing validation.",
        "fix_direction": "Add validation.",
        "regression_test_direction": "Add a test for the edge case.",
        "suggested_diff": "- old\n+ new",
    }
    base: dict = {
        "head_sha": "sha1",
        "run_id": "run1",
        "run_attempt": "1",
        "result": "REQUEST_CHANGES",
        "reason": "Found issues in scripts/ci/pr_review_merge_scheduler.py.",
        "summary": "See findings.",
        "findings": [finding],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# admits_missing_structural_review()
# ---------------------------------------------------------------------------


def test_admits_missing_phrase():
    """Test admits_missing_structural_review() matches a known structural-failure phrase."""
    assert admits_missing_structural_review(
        "structural exploration was not possible", ""
    )


def test_admits_missing_pattern():
    """Test admits_missing_structural_review() matches a structural-failure regex pattern."""
    assert admits_missing_structural_review(
        "Could not inspect the changed files", ""
    )


def test_admits_missing_no_match():
    """Test admits_missing_structural_review() returns False for clean text."""
    assert not admits_missing_structural_review(
        "Reviewed all changes in scripts/ci/foo.py and they look good.", ""
    )


def test_admits_missing_phrase_in_summary():
    """Test admits_missing_structural_review() also checks the summary argument."""
    assert admits_missing_structural_review("", "no changed files")


# ---------------------------------------------------------------------------
# mentions_changed_file_evidence()
# ---------------------------------------------------------------------------


def test_mentions_file_path():
    """Test mentions_changed_file_evidence() detects a directory/file path."""
    assert mentions_changed_file_evidence("Changed scripts/ci/main.py", "")


def test_mentions_extension_file():
    """Test mentions_changed_file_evidence() detects a bare filename with extension."""
    assert mentions_changed_file_evidence("", "Updated requirements.txt")


def test_mentions_no_file():
    """Test mentions_changed_file_evidence() returns False when no file path is present."""
    assert not mentions_changed_file_evidence("looks good overall", "no files here")


# ---------------------------------------------------------------------------
# check_structural_approval()
# ---------------------------------------------------------------------------


def test_check_structural_approval_file_not_found(tmp_path: Path) -> None:
    """Test check_structural_approval() returns 65 when the file does not exist."""
    result = check_structural_approval(tmp_path / "nonexistent.json")
    assert result == 65


def test_check_structural_approval_invalid_json(tmp_path: Path) -> None:
    """Test check_structural_approval() returns 65 on a JSON parse error."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json{{{")
    result = check_structural_approval(bad)
    assert result == 65


def test_check_structural_approval_not_dict(tmp_path: Path) -> None:
    """Test check_structural_approval() returns 4 when the JSON value is not a dict."""
    f = tmp_path / "control.json"
    f.write_text('"just a string"')
    assert check_structural_approval(f) == 4


def test_check_structural_approval_approve_admits_missing(tmp_path: Path) -> None:
    """Test check_structural_approval() returns 4 when APPROVE admits missing structure."""
    f = tmp_path / "control.json"
    f.write_text(
        json.dumps(
            {
                "result": "APPROVE",
                "reason": "structural exploration was not possible",
                "summary": "ok",
            }
        )
    )
    assert check_structural_approval(f) == 4


def test_check_structural_approval_approve_no_file_evidence(tmp_path: Path) -> None:
    """Test check_structural_approval() returns 4 when APPROVE lacks file evidence."""
    f = tmp_path / "control.json"
    f.write_text(json.dumps({"result": "APPROVE", "reason": "looks good", "summary": "ok"}))
    assert check_structural_approval(f) == 4


def test_check_structural_approval_approve_valid(tmp_path: Path) -> None:
    """Test check_structural_approval() returns 0 for a properly evidenced APPROVE."""
    f = tmp_path / "control.json"
    f.write_text(
        json.dumps(
            {
                "result": "APPROVE",
                "reason": "Reviewed scripts/ci/pr_review_merge_scheduler.py.",
                "summary": "All changes look correct.",
            }
        )
    )
    assert check_structural_approval(f) == 0


def test_check_structural_approval_request_changes(tmp_path: Path) -> None:
    """Test check_structural_approval() returns 0 for a REQUEST_CHANGES block."""
    f = tmp_path / "control.json"
    f.write_text(
        json.dumps({"result": "REQUEST_CHANGES", "reason": "issues found", "summary": "fix it"})
    )
    assert check_structural_approval(f) == 0


# ---------------------------------------------------------------------------
# valid_control()
# ---------------------------------------------------------------------------


def test_valid_control_not_dict() -> None:
    """Test valid_control() returns None for non-dict input."""
    assert valid_control("string", **_VALID_KWARGS) is None


def test_valid_control_wrong_head_sha() -> None:
    """Test valid_control() returns None when head_sha does not match."""
    v = _valid_approve_value(head_sha="wrong")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_wrong_run_id() -> None:
    """Test valid_control() returns None when run_id does not match."""
    v = _valid_approve_value(run_id="wrong")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_wrong_run_attempt() -> None:
    """Test valid_control() returns None when run_attempt does not match."""
    v = _valid_approve_value(run_attempt="99")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_invalid_result() -> None:
    """Test valid_control() returns None for an unrecognized result value."""
    v = _valid_approve_value(result="MAYBE")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_reason_not_str() -> None:
    """Test valid_control() returns None when reason is not a string."""
    v = _valid_approve_value(reason=123)
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_reason_empty() -> None:
    """Test valid_control() returns None when reason is an empty/whitespace string."""
    v = _valid_approve_value(reason="   ")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_summary_not_str() -> None:
    """Test valid_control() returns None when summary is not a string."""
    v = _valid_approve_value(summary=None)
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_summary_empty() -> None:
    """Test valid_control() returns None when summary is an empty string."""
    v = _valid_approve_value(summary="")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_findings_none_approve() -> None:
    """Test valid_control() sets findings to [] for APPROVE when findings is None."""
    v = _valid_approve_value()
    del v["findings"]
    result = valid_control(v, **_VALID_KWARGS)
    assert result is not None
    assert result["findings"] == []


def test_valid_control_findings_not_list_request_changes() -> None:
    """Test valid_control() returns None when findings is not a list for REQUEST_CHANGES."""
    v = _valid_request_changes_value(findings="not a list")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_approve_with_non_empty_findings() -> None:
    """Test valid_control() returns None when APPROVE has non-empty findings."""
    finding = _valid_request_changes_value()["findings"][0]
    v = _valid_approve_value(findings=[finding])
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_request_changes_empty_findings() -> None:
    """Test valid_control() returns None when REQUEST_CHANGES has no findings."""
    v = _valid_request_changes_value(findings=[])
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_approve_admits_missing() -> None:
    """Test valid_control() returns None for APPROVE that admits missing structure."""
    v = _valid_approve_value(
        reason="structural exploration was not possible",
        summary="ok",
    )
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_approve_no_file_evidence() -> None:
    """Test valid_control() returns None for APPROVE with no changed file evidence."""
    v = _valid_approve_value(reason="everything looks fine", summary="all good")
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_approve_valid() -> None:
    """Test valid_control() returns a normalized dict for a valid APPROVE."""
    v = _valid_approve_value()
    result = valid_control(v, **_VALID_KWARGS)
    assert result is not None
    assert result["result"] == "APPROVE"
    assert result["findings"] == []


def test_valid_control_request_changes_valid() -> None:
    """Test valid_control() returns a normalized dict for a valid REQUEST_CHANGES."""
    v = _valid_request_changes_value()
    result = valid_control(v, **_VALID_KWARGS)
    assert result is not None
    assert result["result"] == "REQUEST_CHANGES"
    assert len(result["findings"]) == 1


def test_valid_control_finding_not_dict() -> None:
    """Test valid_control() returns None when a finding entry is not a dict."""
    v = _valid_request_changes_value(findings=["not-a-dict"])
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_finding_line_is_bool() -> None:
    """Test valid_control() returns None when finding line is a boolean (not an int)."""
    finding = dict(_valid_request_changes_value()["findings"][0])
    finding["line"] = True
    v = _valid_request_changes_value(findings=[finding])
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_finding_line_not_int() -> None:
    """Test valid_control() returns None when finding line is not an integer."""
    finding = dict(_valid_request_changes_value()["findings"][0])
    finding["line"] = "ten"
    v = _valid_request_changes_value(findings=[finding])
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_finding_line_zero() -> None:
    """Test valid_control() returns None when finding line is <= 0."""
    finding = dict(_valid_request_changes_value()["findings"][0])
    finding["line"] = 0
    v = _valid_request_changes_value(findings=[finding])
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_finding_missing_required_field() -> None:
    """Test valid_control() returns None when a required finding field is absent."""
    finding = dict(_valid_request_changes_value()["findings"][0])
    del finding["title"]
    v = _valid_request_changes_value(findings=[finding])
    assert valid_control(v, **_VALID_KWARGS) is None


def test_valid_control_finding_empty_required_field() -> None:
    """Test valid_control() returns None when a required finding field is empty."""
    finding = dict(_valid_request_changes_value()["findings"][0])
    finding["title"] = "   "
    v = _valid_request_changes_value(findings=[finding])
    assert valid_control(v, **_VALID_KWARGS) is None


# ---------------------------------------------------------------------------
# iter_json_objects()
# ---------------------------------------------------------------------------


def test_iter_json_objects_plain_json() -> None:
    """Test iter_json_objects() parses a plain JSON string."""
    result = iter_json_objects('{"key": "value"}')
    # Should contain at least the parsed object
    assert {"key": "value"} in result


def test_iter_json_objects_prose_with_json() -> None:
    """Test iter_json_objects() finds embedded JSON in surrounding prose."""
    text = 'Some text here {"result": "APPROVE"} more text'
    result = iter_json_objects(text)
    assert any(isinstance(v, dict) and v.get("result") == "APPROVE" for v in result)


def test_iter_json_objects_invalid_json() -> None:
    """Test iter_json_objects() handles text that is not valid JSON gracefully."""
    result = iter_json_objects("not json at all")
    # No valid JSON objects found
    assert result == []


def test_iter_json_objects_invalid_brace() -> None:
    """Test iter_json_objects() skips braces that start invalid JSON."""
    result = iter_json_objects("{invalid}")
    assert result == []


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def test_main_wrong_arg_count(capsys: pytest.CaptureFixture) -> None:
    """Test main() returns 64 and prints usage when called with wrong number of args."""
    result = main(["prog"])
    assert result == 64
    assert "usage" in capsys.readouterr().err.lower()


def test_main_check_structural_approval_delegates(tmp_path: Path) -> None:
    """Test main() delegates to check_structural_approval for --check-structural-approval."""
    f = tmp_path / "ctrl.json"
    f.write_text(
        json.dumps(
            {
                "result": "APPROVE",
                "reason": "Reviewed scripts/ci/foo.py.",
                "summary": "ok",
            }
        )
    )
    result = main(["prog", "--check-structural-approval", str(f)])
    assert result == 0


def test_main_file_not_found(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Test main() returns 65 when the output file cannot be read."""
    result = main(["prog", "sha1", "run1", "1", str(tmp_path / "missing.txt")])
    assert result == 65
    assert "cannot read" in capsys.readouterr().err


def test_main_no_valid_control(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Test main() returns 4 when no valid control block is found in the file."""
    f = tmp_path / "output.txt"
    f.write_text("just some prose, no valid control block here")
    result = main(["prog", "sha1", "run1", "1", str(f)])
    assert result == 4
    assert "NO_CONCLUSION" in capsys.readouterr().err


def test_main_valid_control_written(tmp_path: Path) -> None:
    """Test main() writes the normalized control block and returns 0."""
    control = _valid_approve_value()
    f = tmp_path / "output.txt"
    f.write_text(json.dumps(control))
    result = main(["prog", "sha1", "run1", "1", str(f)])
    assert result == 0
    written = f.read_text(encoding="utf-8")
    assert "opencode-review-control-v1" in written
    assert "APPROVE" in written


def test_main_first_invalid_second_valid(tmp_path: Path) -> None:
    """Test main() skips invalid control blocks and uses the first valid one."""
    invalid = {"head_sha": "sha1", "run_id": "run1", "run_attempt": "1", "result": "MAYBE"}
    valid = _valid_approve_value()
    f = tmp_path / "output.txt"
    # Put invalid first so the `continue` branch is exercised, then valid second
    f.write_text(json.dumps(invalid) + "\n" + json.dumps(valid))
    result = main(["prog", "sha1", "run1", "1", str(f)])
    assert result == 0
    written = f.read_text(encoding="utf-8")
    assert "APPROVE" in written
