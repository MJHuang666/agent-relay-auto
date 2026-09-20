"""Deterministic Planner wake adapter for runtime tests."""

from __future__ import annotations

from .base import ObservationResult, PresentationResult, SubmissionReceipt, WakeCapabilities


class FakePlannerWakeAdapter:
    def __init__(self):
        self.submission_count = 0
        self.present_count = 0

    def probe(self, channel):
        return WakeCapabilities("verified", "verified", "verified", "verified")

    def resume(self, channel):
        return None

    def submit_report(self, channel, request):
        self.submission_count += 1
        return SubmissionReceipt(request.wake_key, channel.tool, channel.conversation_id, "fake-turn", "submitted")

    def observe(self, receipt):
        return ObservationResult("completed")

    def reconcile(self, channel, wake_key):
        return None

    def present(self, channel):
        self.present_count += 1
        return PresentationResult("presented")
