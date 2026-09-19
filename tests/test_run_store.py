import json
import tempfile
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


run_store = load_runtime_module("run_store")


class RunStoreTests(unittest.TestCase):
    def test_creates_structured_run_files_and_marks_unknown_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            store = run_store.RunStore(Path(directory), max_log_bytes=100)
            run_path = store.create(
                {
                    "task_id": "TASK-001",
                    "role": "implementer",
                    "participant_id": "impl-a",
                    "agent": "fake",
                    "model": "test-model",
                    "run_id": "run-001",
                    "start_revision": 4,
                }
            )
            context_path = store.write_launch_context("run-001", {"run_id": "run-001", "role": "implementer"})
            store.append("run-001", "stdout", "hello\n")
            store.append("run-001", "stdout", "x" * 200)
            store.finish("run-001", 0, None)
            self.assertTrue((run_path / "metadata.json").is_file())
            self.assertTrue((run_path / "events.jsonl").is_file())
            self.assertTrue((run_path / "usage.json").is_file())
            self.assertTrue((run_path / "stdout.log.1").is_file())
            self.assertEqual(json.loads(context_path.read_text(encoding="utf-8"))["run_id"], "run-001")
            usage = json.loads((run_path / "usage.json").read_text(encoding="utf-8"))
            self.assertEqual(usage["status"], "unavailable")
            metadata = json.loads((run_path / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "finished")

    def test_reads_durable_process_exit_and_protocol_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = run_store.RunStore(Path(directory))
            run_path = store.create({"task_id": "TASK-001", "run_id": "run-001"})
            (run_path / "process.json").write_text('{"run_id":"run-001","pid":12}\n')
            (run_path / "exit.json").write_text('{"run_id":"run-001","exit_code":0}\n')
            self.assertEqual(store.read_process("run-001")["pid"], 12)
            self.assertEqual(store.read_exit("run-001")["exit_code"], 0)
            store.mark_protocol_result("run-001", "completed")
            self.assertEqual(json.loads((run_path / "protocol.json").read_text())["result"], "completed")


if __name__ == "__main__":
    unittest.main()
