import http.server
import json
import pathlib
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from unittest import mock

from calculators import safe_parse_yaml
from calculators.ngram_waste import mine_ngram_waste
from calculators.runway_churn import simulate_cash_flow_runway
from connectors.approval_gate import ApprovalGate, check_strategy_lock
from connectors.identity_resolver import anonymize_customer_key
from connectors.llm_router import load_attachment_file
from connectors.sanitizer import sanitize_untrusted_text
from scripts.cmo_runner import _read_safe_cli_input
from scripts.geo_benchmark import safe_urlopen, validate_endpoint_url
from scripts.mcp_server import handle_jsonrpc_message
from scripts.validate_skills import run_cmo_check_block


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestSecurityHardening(unittest.TestCase):
    def test_ssrf_userinfo_trailing_dot_ipv4_mapped_numeric_and_dns(self) -> None:
        blocked = [
            "https://trusted.example@127.0.0.1/v1",
            "https://metadata.google.internal./computeMetadata/v1/",
            "http://metadata.google.internal./",
            "https://[::ffff:169.254.169.254]/latest/meta-data",
            "https://[::ffff:10.0.0.1]/admin",
            "https://2130706433/v1",
            "https://0x7f000001/v1",
            "https://10.20.30.40/v1",
            "https://172.16.0.5/v1",
            "https://192.168.1.10/v1",
            "https://myservice.internal/v1",
            "file:///etc/passwd",
        ]
        for bad_url in blocked:
            with self.assertRaises(ValueError, msg=f"Expected SSRF rejection for {bad_url}"):
                validate_endpoint_url(bad_url, resolve_dns=False)

        # DNS rebinding / internal DNS resolution rejection
        fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("169.254.169.254", 0))]
        with mock.patch("scripts.geo_benchmark.socket.getaddrinfo", return_value=fake_addrinfo):
            with self.assertRaises(ValueError):
                validate_endpoint_url("https://rebind.attacker.example/v1", resolve_dns=True)

        fake_loopback = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 0))]
        with mock.patch("scripts.geo_benchmark.socket.getaddrinfo", return_value=fake_loopback):
            with self.assertRaises(ValueError):
                validate_endpoint_url("https://localrebind.attacker.example/v1", resolve_dns=True)

    def test_safe_urlopen_blocks_redirects_and_oversized_responses(self) -> None:
        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://169.254.169.254/latest/meta-data")
                    self.end_headers()
                    return
                if self.path == "/big":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"A" * 2048)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # 302 redirect must be blocked (never followed)
            req_redir = urllib.request.Request(f"http://127.0.0.1:{port}/redirect")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                safe_urlopen(req_redir, timeout=5)
            self.assertEqual(ctx.exception.code, 302)

            # Response exceeding max_bytes must fail closed
            req_big = urllib.request.Request(f"http://127.0.0.1:{port}/big")
            with self.assertRaises(RuntimeError):
                safe_urlopen(req_big, timeout=5, max_bytes=1024)

            # Normal bounded request succeeds
            req_ok = urllib.request.Request(f"http://127.0.0.1:{port}/ok")
            status, body = safe_urlopen(req_ok, timeout=5, max_bytes=1024)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body.decode("utf-8")), {"ok": True})
        finally:
            server.shutdown()
            server.server_close()

    def test_attachment_and_cli_file_exfiltration_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            txt = root / "notes.txt"
            txt.write_text("secret notes", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_attachment_file(txt)

            dot_png = root / ".hidden.png"
            dot_png.write_bytes(b"\x89PNG\r\n\x1a\n")
            with self.assertRaises(ValueError):
                load_attachment_file(dot_png)

            good_png = root / "ok.png"
            good_png.write_bytes(b"\x89PNG\r\n\x1a\n")
            link_png = root / "link.png"
            link_png.symlink_to(good_png)
            with self.assertRaises(ValueError):
                load_attachment_file(link_png)

            # cmo_runner _read_safe_cli_input blocks out-of-workspace, dotfiles, and symlinks
            ws = root / "ws"
            ws.mkdir()
            env_f = ws / ".env"
            env_f.write_text("GEMINI_API_KEY=AIzaSySecret123456789012345", encoding="utf-8")
            with self.assertRaises(ValueError):
                _read_safe_cli_input(str(env_f), ws)
            with self.assertRaises(ValueError):
                _read_safe_cli_input("/etc/passwd", ws)

            safe_brief = ws / "brief.md"
            safe_brief.write_text("Launch oak desk campaign", encoding="utf-8")
            self.assertEqual(_read_safe_cli_input(str(safe_brief), ws), "Launch oak desk campaign")

    def test_mcp_blocks_hidden_workspace_files_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = pathlib.Path(tmp)
            (ws / ".env").write_text("OPENAI_API_KEY=sk-test1234567890123456", encoding="utf-8")
            (ws / ".git").mkdir()
            (ws / ".git" / "config").write_text("[core]\n", encoding="utf-8")
            (ws / "page.html").write_text("<h2>Hi</h2>", encoding="utf-8")

            r_env = handle_jsonrpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "freecmo_ai_search_fanout_audit", "arguments": {"file_path": ".env"}},
                },
                repo_root=ws,
            )
            assert r_env is not None
            self.assertTrue(r_env["result"]["isError"])

            r_git = handle_jsonrpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "freecmo_weekly_brief", "arguments": {"state_path": ".git/config"}},
                },
                repo_root=ws,
            )
            assert r_git is not None
            self.assertTrue(r_git["result"]["isError"])

            r_ok = handle_jsonrpc_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "freecmo_ai_search_fanout_audit", "arguments": {"file_path": "page.html"}},
                },
                repo_root=ws,
            )
            assert r_ok is not None
            self.assertFalse(r_ok["result"]["isError"])

    def test_strategy_lock_frontmatter_boundary_and_approval_gate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bt = root / "brand-truth.md"
            # Spoofed status: locked in markdown body without frontmatter lock must stay draft_pending_review
            bt.write_text("# Notes\nstatus: locked\n", encoding="utf-8")
            self.assertEqual(check_strategy_lock(bt), "draft_pending_review")

            bt.write_text("---\nstatus: draft_pending_review\n---\nstatus: locked\n", encoding="utf-8")
            self.assertEqual(check_strategy_lock(bt), "draft_pending_review")

            bt.write_text("---\nstatus: locked\n---\n# Brand\n", encoding="utf-8")
            self.assertEqual(check_strategy_lock(bt), "locked")

            gate = ApprovalGate(root / "shift.jsonl", root / "rollbacks", bt, workspace_root=root)
            payload = {"x": 1}
            now = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
            gate.record_validator_pass("sub-1", payload, timestamp=now)
            gate.record_reviewer_approval("sub-1", payload, approved=True, timestamp=now)
            gate.record_composer_signoff("app-1", "sub-1", payload, timestamp=now)

            # Protected governance files must never be mutated via execute_write
            with self.assertRaises(PermissionError):
                gate.execute_write(
                    "act-prot",
                    "sub-1",
                    "app-1",
                    payload,
                    {},
                    target_file=root / "guardrails.yaml",
                    now=now + timedelta(seconds=1),
                )
            # Escaping workspace_root must raise PermissionError
            with self.assertRaises(PermissionError):
                gate.execute_write(
                    "act-esc",
                    "sub-1",
                    "app-1",
                    payload,
                    {},
                    target_file=root.parent / "outside.json",
                    now=now + timedelta(seconds=1),
                )

    def test_calculator_dos_bounds_yaml_utf8_and_cmo_check_hardening(self) -> None:
        with self.assertRaises(ValueError):
            simulate_cash_flow_runway(10000, 1000, 100, 50, horizon_months=99999)
        with self.assertRaises(ValueError):
            mine_ngram_waste(
                [{"search_term": "oak desk", "spend_usd": 50, "clicks": 10, "conversions": 0}],
                allowable_cac_usd=40,
                max_ngram=12,
            )

        parsed = safe_parse_yaml('title: "Nordic — Studio café"\n')
        self.assertEqual(parsed["title"], "Nordic — Studio café")

        bad_check = """
calculator: os
function: system
inputs:
  cmd: id
steps:
  - exploit
expected:
  x: 1
"""
        errs_empty_decl = run_cmo_check_block(bad_check, [])
        self.assertTrue(len(errs_empty_decl) > 0)

        private_fn_check = """
calculator: cac_ltv
function: _internal_helper
inputs: {}
steps:
  - none
expected: {}
"""
        errs_priv = run_cmo_check_block(private_fn_check, ["cac_ltv"])
        self.assertTrue(any("private" in e.lower() or "invalid" in e.lower() for e in errs_priv))

    def test_secret_redaction_and_salted_pii_hashing(self) -> None:
        text = (
            "Keys: rk_live_1234567890abcdef, shpat_1234567890abcdef, "
            "ya29.a0AfH6SMBxTestToken12345, github_pat_11ABCDEF0123456789abcdef, "
            "Bearer abcdefghijklmnopqrstuvwxyz12345, -----BEGIN RSA PRIVATE KEY-----"
        )
        cleaned = sanitize_untrusted_text(text)
        for leak in ("rk_live_", "shpat_", "ya29.", "github_pat_", "abcdefghijklmnopqrstuvwxyz", "PRIVATE KEY"):
            self.assertNotIn(leak, cleaned)
        self.assertGreaterEqual(cleaned.count("[REDACTED_SECRET]"), 5)

        unsalted = anonymize_customer_key("alice@example.com")
        salted = anonymize_customer_key("alice@example.com", salt="prod-secret-salt-2026")
        self.assertNotEqual(unsalted, salted)
        self.assertEqual(len(salted), 24)


if __name__ == "__main__":
    unittest.main()
