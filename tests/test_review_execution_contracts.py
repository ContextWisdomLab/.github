import json

from scripts.ci import review_execution_contracts as contracts


def test_discovers_runtime_lint_security_and_unpackaged_sources(tmp_path, capsys):
    """Contract discovery finds runtime matrices, linters, security tools, and package gaps."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(
        "strategy:\n  matrix:\n    python-version: ['3.11', '3.12']\n    node-version: [20, 22]\n",
        encoding="utf-8",
    )
    (repo / ".nvmrc").write_text("22\n", encoding="utf-8")
    (repo / "package.json").write_text(
        json.dumps(
            {
                "engines": {"node": ">=20"},
                "scripts": {
                    "coverage": "vitest run --coverage",
                    "e2e": "playwright test",
                    "lint": "eslint .",
                    "security": "semgrep scan",
                    "test": "vitest run",
                },
            }
        ),
        encoding="utf-8",
    )
    (repo / "package-lock.json").write_text("{}", encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        "[project]\nrequires-python = '>=3.11'\n[tool.ruff]\n[tool.interrogate]\nfail-under = 100\n",
        encoding="utf-8",
    )
    (repo / "tests").mkdir()
    (repo / "Cargo.toml").write_text("[package]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")
    (repo / "go.mod").write_text("module example.test/x\ngo 1.23\n", encoding="utf-8")
    (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (repo / "loose.rb").write_text("puts 'unpackaged'\n", encoding="utf-8")

    result = contracts.discover_contracts(repo)

    assert result["runtime_versions"]["node"] == [".nvmrc:22"]
    assert ".github/workflows/ci.yml:3.11" in result["workflow_versions"]["python"]
    assert result["python"][0]["requires_python"] == ">=3.11"
    assert "npm run test" in result["test_commands"]
    assert "npm run coverage" in result["coverage_commands"]
    assert "npm run e2e" in result["e2e_commands"]
    assert any("interrogate" in command for command in result["docstring_commands"])
    assert "npm run lint" in result["lint_commands"]
    assert any("ruff" in command for command in result["lint_commands"])
    assert "cargo audit" in result["security_commands"]
    assert "gosec ./..." in result["security_commands"]
    assert any(surface["language"] == "ruby" for surface in result["unpackaged_source_surfaces"])

    assert contracts.main(["--repo-root", str(repo), "--format", "markdown"]) == 0
    assert "Review Execution Contracts" in capsys.readouterr().out
