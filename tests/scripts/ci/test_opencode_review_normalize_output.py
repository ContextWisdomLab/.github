"""Tests for opencode_review_normalize_output.py."""
import json
import pytest
from pathlib import Path

# Adjust sys.path to import the script correctly since it's not a standard package structure
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../scripts/ci')))
import opencode_review_normalize_output
from opencode_review_normalize_output import (
    valid_control,
    admits_missing_structural_review,
    mentions_changed_file_evidence,
    check_structural_approval,
    iter_json_objects,
    main,
)

def get_base_valid_value():
    """Test get base valid value."""
    return {
        "head_sha": "abc123sha",
        "run_id": "123456",
        "run_attempt": "1",
        "result": "APPROVE",
        "reason": "Good to go",
        "summary": "Looks fine. changes to src/main.py",
        "findings": []
    }

def test_valid_control_not_dict():
    """Test valid control not dict."""
    assert valid_control(
        "not a dict",
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

def test_valid_control_head_sha_mismatch():
    """Test valid control head sha mismatch."""
    value = get_base_valid_value()
    value["head_sha"] = "wrong_sha"
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

def test_valid_control_run_id_mismatch():
    """Test valid control run id mismatch."""
    value = get_base_valid_value()
    value["run_id"] = "wrong_id"
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

def test_valid_control_run_attempt_mismatch():
    """Test valid control run attempt mismatch."""
    value = get_base_valid_value()
    value["run_attempt"] = "wrong_attempt"
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

def test_valid_control_invalid_result():
    """Test valid control invalid result."""
    value = get_base_valid_value()
    value["result"] = "PENDING"
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

def test_valid_control_reason_invalid():
    """Test valid control reason invalid."""
    # missing reason
    value = get_base_valid_value()
    del value["reason"]
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # non-string reason
    value["reason"] = 123
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # empty whitespace reason
    value["reason"] = "   "
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

def test_valid_control_summary_invalid():
    """Test valid control summary invalid."""
    # missing summary
    value = get_base_valid_value()
    del value["summary"]
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # non-string summary
    value["summary"] = 123
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # empty whitespace summary
    value["summary"] = "   "
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

def test_valid_control_findings_logic():
    """Test valid control findings logic."""
    # findings not a list
    value = get_base_valid_value()
    value["findings"] = "not a list"
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # findings None on APPROVE converts to [] internally
    value = get_base_valid_value()
    del value["findings"]
    res = valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    )
    assert res is not None
    assert res["findings"] == []

    # APPROVE with non-empty findings should fail
    value = get_base_valid_value()
    value["findings"] = [{"dummy": "data"}]
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # REQUEST_CHANGES with empty findings should fail
    value = get_base_valid_value()
    value["result"] = "REQUEST_CHANGES"
    value["findings"] = []
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # REQUEST_CHANGES with findings None should fail
    value = get_base_valid_value()
    value["result"] = "REQUEST_CHANGES"
    del value["findings"]
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None


def get_base_valid_finding():
    """Test get base valid finding."""
    return {
        "path": "src/main.py",
        "line": 10,
        "severity": "high",
        "title": "Bug",
        "problem": "Crash",
        "root_cause": "Null ptr",
        "fix_direction": "Add check",
        "regression_test_direction": "Test null case",
        "suggested_diff": "if x is None: return"
    }

def test_valid_control_findings_validation():
    """Test valid control findings validation."""
    base_val = get_base_valid_value()
    base_val["result"] = "REQUEST_CHANGES"

    # Finding not a dict
    value = base_val.copy()
    value["findings"] = ["not a dict"]
    assert valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    ) is None

    # Line not int or <= 0
    for invalid_line in [True, False, "10", 0, -1]:
        value = base_val.copy()
        finding = get_base_valid_finding()
        finding["line"] = invalid_line
        value["findings"] = [finding]
        assert valid_control(
            value,
            expected_head_sha="abc123sha",
            expected_run_id="123456",
            expected_run_attempt="1"
        ) is None

    # Missing required fields
    required_fields = [
        "path", "severity", "title", "problem", "root_cause",
        "fix_direction", "regression_test_direction", "suggested_diff"
    ]
    for field in required_fields:
        # Field missing entirely
        value = base_val.copy()
        finding = get_base_valid_finding()
        del finding[field]
        value["findings"] = [finding]
        assert valid_control(
            value,
            expected_head_sha="abc123sha",
            expected_run_id="123456",
            expected_run_attempt="1"
        ) is None

        # Field empty string
        value = base_val.copy()
        finding = get_base_valid_finding()
        finding[field] = "   "
        value["findings"] = [finding]
        assert valid_control(
            value,
            expected_head_sha="abc123sha",
            expected_run_id="123456",
            expected_run_attempt="1"
        ) is None

        # Field non-string
        value = base_val.copy()
        finding = get_base_valid_finding()
        finding[field] = 123
        value["findings"] = [finding]
        assert valid_control(
            value,
            expected_head_sha="abc123sha",
            expected_run_id="123456",
            expected_run_attempt="1"
        ) is None

    # Valid REQUEST_CHANGES
    value = base_val.copy()
    value["findings"] = [get_base_valid_finding()]
    res = valid_control(
        value,
        expected_head_sha="abc123sha",
        expected_run_id="123456",
        expected_run_attempt="1"
    )
    assert res is not None
    assert res["result"] == "REQUEST_CHANGES"
    assert len(res["findings"]) == 1

def test_admits_missing_structural_review():
    """Test admits missing structural review."""
    # True cases from phrases
    assert admits_missing_structural_review("reason", "structural exploration was not possible")
    assert admits_missing_structural_review("could not access changed files", "summary")

    # True cases from patterns
    assert admits_missing_structural_review("reason", "could not inspect changed files")
    assert admits_missing_structural_review("reason", "no changes detected")
    assert admits_missing_structural_review("zero changed files", "summary")

    # False cases
    assert not admits_missing_structural_review("Good code", "LGTM")
    assert not admits_missing_structural_review("structural exploration was successful", "summary")

def test_mentions_changed_file_evidence():
    """Test mentions changed file evidence."""
    # True cases
    assert mentions_changed_file_evidence("Changes in src/main.py", "summary")
    assert mentions_changed_file_evidence("reason", "Edited the README")
    assert mentions_changed_file_evidence("reason", "Added component.tsx")
    assert mentions_changed_file_evidence("Modified AGENTS.md here", "summary")

    # False cases
    assert not mentions_changed_file_evidence("No concrete files", "just prose")
    assert not mentions_changed_file_evidence("Edited python", "but no py extension file path")

def test_valid_control_approve_admission_and_evidence():
    """Test valid control approve admission and evidence."""
    value = get_base_valid_value()
    value["result"] = "APPROVE"

    # Both fail (admitting missing structure + no evidence)
    value["reason"] = "could not inspect changed files"
    value["summary"] = "no evidence"
    assert valid_control(value, expected_head_sha="abc123sha", expected_run_id="123456", expected_run_attempt="1") is None

    # Fails admission only
    value["reason"] = "could not inspect changed files"
    value["summary"] = "Changes in src/main.py"
    assert valid_control(value, expected_head_sha="abc123sha", expected_run_id="123456", expected_run_attempt="1") is None

    # Fails evidence only
    value["reason"] = "Good to go"
    value["summary"] = "Looks fine, but no files mentioned"
    assert valid_control(value, expected_head_sha="abc123sha", expected_run_id="123456", expected_run_attempt="1") is None

    # Valid APPROVE
    value["reason"] = "Good to go"
    value["summary"] = "Looks fine. changes to src/main.py"
    res = valid_control(value, expected_head_sha="abc123sha", expected_run_id="123456", expected_run_attempt="1")
    assert res is not None
    assert res["result"] == "APPROVE"

def test_check_structural_approval(tmp_path, capsys):
    """Test check structural approval."""
    # Invalid JSON
    f = tmp_path / "control.json"
    f.write_text("{invalid json", encoding="utf-8")
    assert check_structural_approval(f) == 65
    captured = capsys.readouterr()
    assert "cannot read OpenCode control JSON" in captured.err

    # Valid JSON, but not a dict
    f.write_text("[\"not a dict\"]", encoding="utf-8")
    assert check_structural_approval(f) == 4
    captured = capsys.readouterr()
    assert "NO_CONCLUSION" in captured.err

    # Valid dict, APPROVE, but missing evidence
    data = {
        "result": "APPROVE",
        "reason": "Good to go",
        "summary": "No file mentioned"
    }
    f.write_text(json.dumps(data), encoding="utf-8")
    assert check_structural_approval(f) == 4
    captured = capsys.readouterr()
    assert "NO_CONCLUSION" in captured.err

    # Valid dict, APPROVE, but admits missing structure
    data = {
        "result": "APPROVE",
        "reason": "could not inspect changed files",
        "summary": "changes to src/main.py"
    }
    f.write_text(json.dumps(data), encoding="utf-8")
    assert check_structural_approval(f) == 4
    captured = capsys.readouterr()
    assert "NO_CONCLUSION" in captured.err

    # Valid dict, APPROVE, valid evidence
    data = {
        "result": "APPROVE",
        "reason": "Good to go",
        "summary": "changes to src/main.py"
    }
    f.write_text(json.dumps(data), encoding="utf-8")
    assert check_structural_approval(f) == 0

    # Valid dict, not APPROVE
    data = {
        "result": "REQUEST_CHANGES",
        "reason": "Bad",
        "summary": "Fix it"
    }
    f.write_text(json.dumps(data), encoding="utf-8")
    assert check_structural_approval(f) == 0

def test_iter_json_objects():
    """Test iter json objects."""
    # Only prose
    assert iter_json_objects("Just some text here.") == []

    # Valid JSON alone
    assert iter_json_objects('{"key": "value"}') == [{"key": "value"}, {"key": "value"}]

    # Multiple JSONs with prose
    text = '''
    Here is a block:
    {"a": 1}
    And another:
    {"b": 2}
    And an invalid one: { "c":
    '''
    res = iter_json_objects(text)
    assert len(res) == 2
    assert res[0] == {"a": 1}
    assert res[1] == {"b": 2}

def test_main_cli(tmp_path, capsys):
    """Test main cli."""
    # Invalid arg length
    assert main(["opencode_review_normalize_output.py"]) == 64
    captured = capsys.readouterr()
    assert "usage:" in captured.err

    # File read error
    assert main(["script", "sha", "id", "attempt", "nonexistent.json"]) == 65
    captured = capsys.readouterr()
    assert "cannot read OpenCode output file" in captured.err

    # No valid objects
    f = tmp_path / "output.txt"
    f.write_text("just prose", encoding="utf-8")
    assert main(["script", "sha", "id", "attempt", str(f)]) == 4
    captured = capsys.readouterr()
    assert "NO_CONCLUSION" in captured.err

    # Valid output
    data = get_base_valid_value()
    data["head_sha"] = "sha"
    data["run_id"] = "id"
    data["run_attempt"] = "attempt"
    f.write_text(json.dumps(data), encoding="utf-8")
    assert main(["script", "sha", "id", "attempt", str(f)]) == 0

    # Ensure output was normalized and written
    out_text = f.read_text(encoding="utf-8")
    assert "opencode-review-gate" in out_text
    assert "opencode-review-control-v1" in out_text
    assert '"head_sha":"sha"' in out_text

def test_main_check_structural_approval(tmp_path):
    """Test main check structural approval."""
    data = get_base_valid_value()
    f = tmp_path / "output.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    assert main(["script", "--check-structural-approval", str(f)]) == 0

def test_main_cli_invalid_control(tmp_path):
    """Test main cli invalid control."""
    data = get_base_valid_value()
    # Modify data so valid_control returns None
    data["result"] = "INVALID_RESULT_TYPE"
    f = tmp_path / "output.json"
    f.write_text(json.dumps(data), encoding="utf-8")

    assert main(["script", "abc123sha", "123456", "1", str(f)]) == 4

import subprocess

def test_module_execution():
    """Test module execution."""
    import runpy
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../scripts/ci/opencode_review_normalize_output.py'))
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(script_path, run_name="__main__")
    assert excinfo.value.code == 64
