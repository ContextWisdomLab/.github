import json
import socket
import sys

import pytest

from scripts.ci import sandboxed_web_e2e


def free_port():
    """Return an available localhost TCP port for a short-lived test service."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http_server_command(port: int, label: str) -> str:
    """Build a simple Python HTTP service command."""
    return (
        f"{sys.executable} -c \""
        "import http.server, socketserver; "
        "socketserver.TCPServer.allow_reuse_address=True; "
        f"handler=http.server.SimpleHTTPRequestHandler; "
        f"server=socketserver.TCPServer(('127.0.0.1', {port}), handler); "
        f"print('{label} ready', flush=True); "
        "server.serve_forever()"
        "\""
    )


def test_sandboxed_web_e2e_runs_services_and_does_not_mutate_source(tmp_path, capsys):
    """Web E2E helper runs backend/frontend plus E2E in a copied workspace."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "index.html").write_text("ok", encoding="utf-8")
    backend_port = free_port()
    frontend_port = free_port()
    e2e_cmd = (
        f"{sys.executable} -c \""
        "import pathlib, urllib.request; "
        f"print(urllib.request.urlopen('http://127.0.0.1:{backend_port}/index.html').status); "
        f"print(urllib.request.urlopen('http://127.0.0.1:{frontend_port}/index.html').status); "
        "pathlib.Path('e2e-created.txt').write_text('sandbox-only')"
        "\""
    )

    exit_code = sandboxed_web_e2e.main(
        [
            "--repo-root",
            str(repo),
            "--backend-cmd",
            http_server_command(backend_port, "backend"),
            "--frontend-cmd",
            http_server_command(frontend_port, "frontend"),
            "--backend-ready-url",
            f"http://127.0.0.1:{backend_port}/index.html",
            "--frontend-ready-url",
            f"http://127.0.0.1:{frontend_port}/index.html",
            "--startup-timeout",
            "20",
            "--e2e-timeout",
            "20",
            "--allow-env",
            "GITHUB_TOKEN",
            "--network",
            "not-required",
            "--evidence-note",
            "local web app e2e",
            "--e2e-cmd",
            e2e_cmd,
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "SANDBOXED_WEB_E2E_RESULT" in captured.out
    result_line = [line for line in captured.out.splitlines() if line.startswith(sandboxed_web_e2e.RESULT_MARKER)][-1]
    payload = json.loads(result_line.removeprefix(sandboxed_web_e2e.RESULT_MARKER).strip())
    assert payload["backend_ready"] is True
    assert payload["frontend_ready"] is True
    assert payload["exit_code"] == 0
    assert payload["sandboxed"] is True
    assert payload["allowed_env"] == ["GITHUB_TOKEN"]
    assert payload["network"] == "not-required"
    assert payload["evidence_note"] == "local web app e2e"
    assert not (repo / "e2e-created.txt").exists()


def test_sandboxed_web_e2e_reports_readiness_failure(tmp_path, capsys):
    """Readiness failures return a distinct nonzero exit code."""
    repo = tmp_path / "repo"
    repo.mkdir()
    backend_port = free_port()
    frontend_port = free_port()

    exit_code = sandboxed_web_e2e.main(
        [
            "--repo-root",
            str(repo),
            "--backend-cmd",
            http_server_command(backend_port, "backend"),
            "--frontend-cmd",
            http_server_command(frontend_port, "frontend"),
            "--backend-ready-url",
            "http://127.0.0.1:1/not-ready",
            "--frontend-ready-url",
            f"http://127.0.0.1:{frontend_port}/",
            "--startup-timeout",
            "1",
            "--e2e-timeout",
            "5",
            "--e2e-cmd",
            f"{sys.executable} -c \"raise SystemExit(99)\"",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 125
    assert "service readiness failed" in captured.err
    assert "SANDBOXED_WEB_E2E_RESULT" in captured.out


def test_parse_args_rejects_non_positive_timeouts():
    """The CLI rejects unusable timeout values."""
    with pytest.raises(SystemExit):
        sandboxed_web_e2e.parse_args(
            [
                "--backend-cmd",
                "backend",
                "--frontend-cmd",
                "frontend",
                "--e2e-cmd",
                "e2e",
                "--startup-timeout",
                "0",
            ]
        )
