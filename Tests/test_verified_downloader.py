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


if __name__ == "__main__":
    unittest.main()
