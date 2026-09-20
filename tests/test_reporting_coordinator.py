import tempfile
import json
import unittest
from pathlib import Path

from tests.shared.agent_relay_runtime_loader import load_runtime_module


reporting = load_runtime_module("reporting")
channel_module = load_runtime_module("reporting_channel", "planner_channel.py")
base = load_runtime_module("reporting_wake_base", "planner_wake/base.py")
config = load_runtime_module("reporting_config", "config.py")
wake_module = load_runtime_module("reporting_wake_store", "wake_store.py")


class FakeAdapter:
    def __init__(self):
        self.submit_count = 0
        self.remote_has_wake_key = False

    def submit_report(self, channel, request):
        self.submit_count += 1
        return base.SubmissionReceipt(request.wake_key, channel.tool, channel.conversation_id, "turn-1", "submitted")

    def observe(self, receipt):
        return base.ObservationResult("active")

    def reconcile(self, channel, wake_key):
        if self.remote_has_wake_key:
            return base.SubmissionReceipt(wake_key, "codex", "thr-1", "turn-existing", "submitted")
        return None

    def present(self, channel):
        return base.PresentationResult("presented")


class CompletedWithoutReportAdapter(FakeAdapter):
    def observe(self, receipt):
        return base.ObservationResult("completed")


class PresentationRetryAdapter(FakeAdapter):
    def __init__(self):
        super().__init__()
        self.present_count = 0

    def observe(self, receipt):
        return base.ObservationResult("completed")

    def present(self, channel):
        self.present_count += 1
        if self.present_count == 1:
            raise RuntimeError("application closed")
        return base.PresentationResult("presented")


class ReportingCoordinatorTests(unittest.TestCase):
    def make_repo(self):
        temporary = tempfile.TemporaryDirectory()
        repo = Path(temporary.name).resolve()
        task = repo / "docs/agent/tasks/TASK-001"
        task.mkdir(parents=True)
        (task / "STATE.md").write_text(
            "# State\n\n```yaml\ntask: TASK-001\nstatus: REPORTING\nrevision: 18\n"
            "stage_round: 1\nrun_attempt: 0\nrework_round: 0\nauto_replan_count: 0\n"
            "agent_failure_count: 0\nrun_status: idle\nrun_id: null\nruntime_snapshot_ref: null\n"
            "current_role: planner\ncurrent_participant: planner-codex\nwriter_session: null\n"
            "review_ref: review.md\ndelivery_id: delivery-1\n```\n",
            encoding="utf-8",
        )
        store = channel_module.PlannerChannelStore(repo)
        store.save(channel_module.PlannerChannel(
            "planner-codex", "codex", "thr-1", str(repo), "2026-09-20T00:00:00Z"
        ))
        return temporary, repo

    def test_second_tick_does_not_resubmit_after_receipt(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        adapter = FakeAdapter()
        coordinator = reporting.ReportingCoordinator(repo, lambda tool: adapter, config.ReportingPolicy())
        first = coordinator.tick("TASK-001")
        self.assertEqual(first.action, "report_submitted")
        state = (repo / "docs/agent/tasks/TASK-001/STATE.md").read_text(encoding="utf-8")
        self.assertIn("revision: 19", state)
        self.assertIn(first.wake_key, state)
        self.assertIn('"phase":"submitted"', state)
        self.assertEqual(coordinator.tick("TASK-001").action, "report_active")
        self.assertEqual(adapter.submit_count, 1)

    def test_ambiguous_crash_reconciles_before_retry(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        adapter = FakeAdapter()
        adapter.remote_has_wake_key = True
        key = wake_module.WakeKey("TASK-001", 19, "planner-codex", "thr-1").value()
        wake_module.WakeEventStore(repo).append({"wake_key": key, "status": "submitting", "attempt": 1})
        coordinator = reporting.ReportingCoordinator(repo, lambda tool: adapter, config.ReportingPolicy())
        self.assertEqual(coordinator.tick("TASK-001").action, "report_active")
        self.assertEqual(adapter.submit_count, 0)

    def test_missing_channel_or_review_evidence_blocks_without_submission(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        (repo / ".agent-relay-auto/planner-channel.json").unlink()
        adapter = FakeAdapter()
        decision = reporting.ReportingCoordinator(repo, lambda tool: adapter, config.ReportingPolicy()).tick("TASK-001")
        self.assertEqual(decision.action, "blocked")
        self.assertEqual(adapter.submit_count, 0)

    def test_completed_remote_turn_without_report_done_is_not_business_completion(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        adapter = CompletedWithoutReportAdapter()
        coordinator = reporting.ReportingCoordinator(
            repo, lambda tool: adapter,
            config.ReportingPolicy(model_retry_limit=0),
        )
        self.assertEqual(coordinator.tick("TASK-001").action, "report_submitted")
        decision = coordinator.tick("TASK-001")
        self.assertEqual(decision.action, "blocked")
        self.assertIn("report-done", decision.detail)
        self.assertIn("status: REPORTING", (repo / "docs/agent/tasks/TASK-001/STATE.md").read_text())

    def test_completed_without_report_done_uses_bounded_model_retry(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        adapter = CompletedWithoutReportAdapter()
        coordinator = reporting.ReportingCoordinator(
            repo, lambda tool: adapter,
            config.ReportingPolicy(model_retry_limit=1),
        )
        self.assertEqual(coordinator.tick("TASK-001").action, "report_submitted")
        self.assertEqual(coordinator.tick("TASK-001").action, "report_wake_pending")
        self.assertEqual(coordinator.tick("TASK-001").action, "report_submitted")
        self.assertEqual(coordinator.tick("TASK-001").action, "blocked")
        self.assertEqual(adapter.submit_count, 2)

    def test_done_retries_presentation_without_resubmitting_model(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)
        adapter = PresentationRetryAdapter()
        coordinator = reporting.ReportingCoordinator(
            repo, lambda tool: adapter,
            config.ReportingPolicy(presentation_retry_limit=2, presentation_retry_interval_seconds=0.001),
        )
        first = coordinator.tick("TASK-001")
        state_path = repo / "docs/agent/tasks/TASK-001/STATE.md"
        state_path.write_text(state_path.read_text().replace("status: REPORTING", "status: DONE"), encoding="utf-8")
        failed = coordinator.tick("TASK-001")
        self.assertEqual(failed.action, "report_presentation_retry")
        import time
        time.sleep(0.01)
        completed = coordinator.tick("TASK-001")
        self.assertEqual(completed.action, "report_completed")
        self.assertEqual(adapter.submit_count, 1)
        self.assertEqual(adapter.present_count, 2)

    def test_journal_never_persists_full_conversation_or_session_fallback_receipt(self):
        temporary, repo = self.make_repo()
        self.addCleanup(temporary.cleanup)

        class SessionReceiptAdapter(FakeAdapter):
            def submit_report(self, channel, request):
                self.submit_count += 1
                return base.SubmissionReceipt(
                    request.wake_key, channel.tool, channel.conversation_id,
                    channel.conversation_id, "submitted",
                )

        adapter = SessionReceiptAdapter()
        reporting.ReportingCoordinator(repo, lambda tool: adapter, config.ReportingPolicy()).tick("TASK-001")
        events = [
            json.loads(line)
            for line in (repo / ".agent-relay-auto/wake-events.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        submitted = next(event for event in events if event["status"] == "submitted")
        self.assertNotEqual(submitted["receipt_id"], "thr-1")
        self.assertTrue(submitted["receipt_id"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
