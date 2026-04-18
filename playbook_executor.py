"""
Shared playbook execution module.

Used by the CAPA CLI (./capa), test runner (run-test-suite.py), and
UI backend (app.py). Provides a single implementation for building
Ansible playbook commands, handling credentials securely, and running
playbooks with optional real-time output streaming and sidecar log tailing.
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


SENSITIVE_KEYS = frozenset({
    "aws_access_key_id", "aws_secret_access_key",
    "ocm_client_id", "ocm_client_secret",
})

DEFAULT_TIMEOUT = 7200


def build_playbook_command(
    playbook_path: str,
    extra_vars: Optional[Dict[str, Any]] = None,
    verbosity: int = 0,
    env: Optional[Dict[str, str]] = None,
) -> tuple:
    """Build an ansible-playbook command and environment dict.

    Credentials (AWS/OCM keys) are placed in the environment rather than
    on the command line to avoid exposure in process listings.

    Returns:
        (cmd: List[str], env: Dict[str, str])
    """
    cmd = ["ansible-playbook", str(playbook_path)]

    if verbosity > 0:
        cmd.append("-" + "v" * min(verbosity, 4))

    if env is None:
        env = os.environ.copy()

    for key, value in (extra_vars or {}).items():
        str_key = str(key)
        if str_key.lower() in SENSITIVE_KEYS:
            env[str_key.upper()] = str(value).strip() if value is not None else ""
        elif isinstance(value, (dict, list)):
            cmd.extend(["-e", f"{str_key}={json.dumps(value)}"])
        elif isinstance(value, bool):
            cmd.extend(["-e", f"{str_key}={'true' if value else 'false'}"])
        else:
            str_value = str(value).strip() if value is not None else ""
            cmd.extend(["-e", f"{str_key}={str_value}"])

    return cmd, env


def run_playbook_blocking(
    playbook_path: str,
    extra_vars: Optional[Dict[str, Any]] = None,
    cwd: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    verbosity: int = 0,
    capture_output: bool = True,
) -> Dict[str, Any]:
    """Run a playbook synchronously (blocking). Returns result dict.

    Used by the CLI where streaming is not needed.
    """
    if not os.path.exists(playbook_path):
        return {"success": False, "error": f"Playbook not found: {playbook_path}",
                "elapsed": 0, "returncode": -1}

    cmd, env = build_playbook_command(playbook_path, extra_vars, verbosity)
    start = time.time()

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=capture_output,
            text=True, timeout=timeout, env=env,
        )
        elapsed = time.time() - start

        if result.returncode == 0:
            return {"success": True, "elapsed": elapsed, "returncode": 0,
                    "stdout": result.stdout or "", "stderr": result.stderr or ""}
        else:
            error = (result.stderr or result.stdout or "")[-500:]
            return {"success": False, "elapsed": elapsed, "returncode": result.returncode,
                    "error": error, "stdout": result.stdout or "", "stderr": result.stderr or ""}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {"success": False, "elapsed": elapsed, "returncode": -1,
                "error": f"Timeout after {timeout}s"}


class StreamingPlaybookRunner:
    """Run a playbook with real-time output streaming and optional sidecar tailing.

    Used by the test runner and backend where line-by-line output is needed
    for agent processing and live UI updates.
    """

    def __init__(
        self,
        playbook_path: str,
        extra_vars: Optional[Dict[str, Any]] = None,
        cwd: Optional[str] = None,
        timeout: Optional[int] = DEFAULT_TIMEOUT,
        verbosity: int = 0,
        on_line: Optional[Callable[[str], None]] = None,
        sidecar_logfile: Optional[str] = None,
        on_sidecar_line: Optional[Callable[[str], None]] = None,
        sidecar_poll_interval: float = 2.0,
        env: Optional[Dict[str, str]] = None,
    ):
        self.playbook_path = playbook_path
        self.timeout = timeout
        self.on_line = on_line
        self.sidecar_logfile = sidecar_logfile
        self.on_sidecar_line = on_sidecar_line
        self.sidecar_poll_interval = sidecar_poll_interval

        self.cmd, self.env = build_playbook_command(
            playbook_path, extra_vars, verbosity, env,
        )
        self.cwd = cwd

        self._sidecar_stop = threading.Event()
        self._sidecar_thread = None
        self.output_lines: List[str] = []
        self.returncode: Optional[int] = None
        self.elapsed: float = 0

    def run(self) -> Dict[str, Any]:
        """Execute the playbook, streaming output. Returns result dict."""
        if not os.path.exists(self.playbook_path):
            return {"success": False, "error": f"Playbook not found: {self.playbook_path}",
                    "elapsed": 0, "returncode": -1, "output_lines": []}

        start = time.time()

        try:
            if self.sidecar_logfile and self.on_sidecar_line:
                self._start_sidecar()

            process = subprocess.Popen(
                self.cmd, cwd=self.cwd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=self.env,
            )

            try:
                for line in process.stdout:
                    line_stripped = line.rstrip()
                    self.output_lines.append(line_stripped)
                    if self.on_line:
                        self.on_line(line_stripped)

                self.returncode = process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                self.elapsed = time.time() - start
                return {"success": False, "elapsed": self.elapsed, "returncode": -1,
                        "error": f"Timeout after {self.timeout}s",
                        "output_lines": self.output_lines}

        except Exception as e:
            self.elapsed = time.time() - start
            return {"success": False, "elapsed": self.elapsed, "returncode": -1,
                    "error": str(e), "output_lines": self.output_lines}
        finally:
            self._stop_sidecar()

        self.elapsed = time.time() - start
        return {
            "success": self.returncode == 0,
            "elapsed": self.elapsed,
            "returncode": self.returncode,
            "output_lines": self.output_lines,
        }

    def _start_sidecar(self):
        """Start background thread that tails the sidecar log file."""
        def _tail():
            last_pos = 0
            while not self._sidecar_stop.is_set():
                try:
                    if os.path.exists(self.sidecar_logfile):
                        with open(self.sidecar_logfile, 'r') as f:
                            f.seek(last_pos)
                            for line in f:
                                line = line.strip()
                                if line and self.on_sidecar_line:
                                    try:
                                        self.on_sidecar_line(line)
                                    except Exception:
                                        pass
                            last_pos = f.tell()
                except Exception:
                    pass
                self._sidecar_stop.wait(self.sidecar_poll_interval)

        self._sidecar_thread = threading.Thread(target=_tail, daemon=True)
        self._sidecar_thread.start()

    def _stop_sidecar(self):
        """Signal the sidecar thread to stop and wait for it."""
        self._sidecar_stop.set()
        if self._sidecar_thread is not None:
            self._sidecar_thread.join(timeout=5)
