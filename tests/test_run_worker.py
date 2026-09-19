import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


run_worker = load_runtime_module("run_worker")


class RunWorkerTests(unittest.TestCase):
    def test_worker_writes_process_heartbeat_logs_and_exit_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run-1"
            fixture = Path(__file__).resolve().parent / "fixtures/sleeping_agent_cli.py"
            spec = run_worker.RunWorkerSpec(
                "run-1", run_dir, Path.cwd(),
                (sys.executable, str(fixture), "--sleep", "0.03", "--exit", "7"),
                0.01,
            )
            self.assertEqual(run_worker.execute(spec), 7)
            process = json.loads((run_dir / "process.json").read_text())
            heartbeat = json.loads((run_dir / "heartbeat.json").read_text())
            exit_record = json.loads((run_dir / "exit.json").read_text())
            self.assertEqual(exit_record["exit_code"], 7)
            self.assertEqual(exit_record["run_id"], "run-1")
            self.assertIn("fixture stdout", (run_dir / "stdout.log").read_text())
            self.assertIn("fixture stderr", (run_dir / "stderr.log").read_text())
            self.assertGreater(heartbeat["sequence"], 0)
            self.assertIn("command_sha256", process)
            self.assertNotIn("environment", process)

    def test_worker_does_not_wait_for_next_heartbeat_after_fast_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run-fast"
            started_at = time.monotonic()
            spec = run_worker.RunWorkerSpec(
                "run-fast",
                run_dir,
                Path.cwd(),
                (sys.executable, "-c", "print('done')"),
                2,
            )

            self.assertEqual(run_worker.execute(spec), 0)
            self.assertLess(time.monotonic() - started_at, 1)


if __name__ == "__main__":
    unittest.main()
