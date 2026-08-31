#!/usr/bin/env python3
"""Contract test for the installer's resumable, checksummed downloader."""

from __future__ import annotations

import hashlib
import http.server
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOWNLOADER = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/download_verified.py"


class DisconnectOnceHandler(http.server.BaseHTTPRequestHandler):
    payload = bytes((index * 31) % 251 for index in range(2_400_000))
    disconnected = False

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        range_header = self.headers.get("Range")
        start = int(range_header.split("=")[1].split("-")[0]) if range_header else 0
        status = 206 if start else 200
        self.send_response(status)
        self.send_header("Content-Length", str(len(self.payload) - start))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{len(self.payload)-1}/{len(self.payload)}")
        self.end_headers()
        if not self.__class__.disconnected:
            self.__class__.disconnected = True
            self.wfile.write(self.payload[start:start + 700_000])
            self.wfile.flush()
            self.connection.shutdown(1)
            return
        self.wfile.write(self.payload[start:])

    def log_message(self, _format, *_args):
        pass


class VerifiedDownloaderTests(unittest.TestCase):
    def test_disconnect_resumes_range_and_verifies_digest(self):
        DisconnectOnceHandler.disconnected = False
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), DisconnectOnceHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "artifact.bin"
                expected = hashlib.sha256(DisconnectOnceHandler.payload).hexdigest()
                completed = subprocess.run(
                    ["python3", str(DOWNLOADER),
                     "--url", f"http://127.0.0.1:{server.server_port}/artifact.bin",
                     "--sha256", expected, "--output", str(output),
                     "--label", "test artifact", "--progress-start", "40",
                     "--progress-end", "60", "--timeout", "1", "--retries", "3"],
                    text=True, capture_output=True, timeout=20,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), expected)
                self.assertIn("retrying test artifact from 700.0 KB", completed.stdout)
                self.assertIn("2.4 MB / 2.4 MB (100%)", completed.stdout)
                self.assertIn("NHSTEP|download|60|", completed.stdout)
                self.assertFalse(output.with_suffix(".bin.part").exists())
        finally:
            server.shutdown()
            server.server_close()

    def test_complete_partial_is_promoted_without_network(self):
        payload = b"already complete" * 1024
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "checkpoint.pt"
            partial = output.with_suffix(".pt.part")
            partial.write_bytes(payload)
            completed = subprocess.run(
                ["python3", str(DOWNLOADER),
                 "--url", "http://127.0.0.1:1/must-not-be-contacted",
                 "--sha256", hashlib.sha256(payload).hexdigest(),
                 "--output", str(output), "--label", "complete partial",
                 "--retries", "1"],
                text=True, capture_output=True, timeout=5,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(output.read_bytes(), payload)
            self.assertFalse(partial.exists())

    def test_rejects_malformed_digest_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                ["python3", str(DOWNLOADER), "--url", "http://127.0.0.1:1/no",
                 "--sha256", "not-a-digest", "--output", str(Path(directory) / "x"),
                 "--label", "bad digest", "--retries", "1"],
                text=True, capture_output=True, timeout=5,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("64 hexadecimal", completed.stderr)


if __name__ == "__main__":
    unittest.main()
