import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "shared/.agents/skills/agent-relay-auto"
LEGACY_IN_TEMPLATE = ROOT / "shared/.agents/skills/project-role-workflow"
COMPATIBILITY_SHIM = ROOT / "compat/project-role-workflow/SKILL.md"


class AgentRelayContractTests(unittest.TestCase):
    def test_automatic_handoff_does_not_instruct_manual_continue(self):
        skill = (ROOT / "shared/.agents/skills/agent-relay-auto/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("automatic mode", skill.lower())
        self.assertIn("must not ask the user to open the next role", skill.lower())
        workflow_documents = (
            ROOT / "shared/docs/agent/workflow.md",
            CANONICAL / "assets/project-template/shared/docs/agent/workflow.md",
            CANONICAL / "assets/project-template/locales/zh-CN/docs/agent/workflow.md",
            CANONICAL / "assets/project-template/locales/en-US/docs/agent/workflow.md",
        )
        for document in workflow_documents:
            text = document.read_text(encoding="utf-8").lower()
            self.assertIn("mode: automatic", text, document)
            self.assertIn("runner", text, document)

    def test_canonical_skill_identity(self):
        skill = CANONICAL / "SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertIn("name: agent-relay-auto", skill.read_text(encoding="utf-8"))
        self.assertFalse(LEGACY_IN_TEMPLATE.exists())

    def test_legacy_compatibility_is_thin(self):
        self.assertTrue(COMPATIBILITY_SHIM.is_file())
        self.assertFalse((COMPATIBILITY_SHIM.parent / "assets").exists())
        self.assertFalse((COMPATIBILITY_SHIM.parent / "references").exists())
        self.assertFalse((COMPATIBILITY_SHIM.parent / "scripts").exists())

    def test_public_documents_use_canonical_command(self):
        public_documents = (
            ROOT / "README.md",
            ROOT / "README.zh-CN.md",
            ROOT / "docs/AGENT_RELAY_AUTO_USAGE.md",
            ROOT / "docs/AGENT_RELAY_AUTO_USAGE.en-US.md",
        )
        for document in public_documents:
            text = document.read_text(encoding="utf-8")
            self.assertIn("$agent-relay-auto", text, document)
            self.assertNotIn("$project-role-workflow", text, document)

    def test_knowledge_index_is_present_in_all_template_variants(self):
        documents = (
            ROOT / "shared/docs/agent/knowledge-index.md",
            CANONICAL
            / "assets/project-template/shared/docs/agent/knowledge-index.md",
            CANONICAL
            / "assets/project-template/locales/zh-CN/docs/agent/knowledge-index.md",
            CANONICAL
            / "assets/project-template/locales/en-US/docs/agent/knowledge-index.md",
        )
        for document in documents:
            text = document.read_text(encoding="utf-8")
            self.assertIn("| ID |", text, document)
            self.assertIn("ACTIVE", text, document)
            self.assertIn("SUPERSEDED", text, document)
            self.assertIn("RETIRED", text, document)

    def test_public_brand_and_migration_material_are_present(self):
        self.assertIn("lightweight multi-Agent collaboration framework", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("轻量级多 Agent 接力协作框架", (ROOT / "README.zh-CN.md").read_text(encoding="utf-8"))
        migration = (ROOT / "docs/migration-v1.5.md").read_text(encoding="utf-8")
        self.assertIn("Uncommitted-state handoff package", migration)
        self.assertIn("未提交状态交接包", migration)

    def test_automated_runner_contract_is_mirrored(self):
        canonical = CANONICAL / "references/runner.md"
        mirror = CANONICAL / "assets/project-template/shared/.agents/skills/agent-relay-auto/references/runner.md"
        self.assertTrue(canonical.is_file())
        self.assertTrue(mirror.is_file())
        self.assertEqual(canonical.read_text(encoding="utf-8"), mirror.read_text(encoding="utf-8"))
        text = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        for command in ("Runner 状态", "启动 Runner", "暂停当前任务", "立即中断当前角色", "恢复当前任务"):
            self.assertIn(command, text)

    def test_original_planner_reporting_contract_is_bilingual_and_complete(self):
        documents = (
            ROOT / "README.md",
            ROOT / "README.zh-CN.md",
            ROOT / "docs/AGENT_RELAY_AUTO_USAGE.md",
            ROOT / "docs/AGENT_RELAY_AUTO_USAGE.en-US.md",
            ROOT / "shared/docs/agent/workflow.md",
            CANONICAL / "assets/project-template/locales/zh-CN/docs/agent/workflow.md",
            CANONICAL / "assets/project-template/locales/en-US/docs/agent/workflow.md",
            CANONICAL / "assets/project-template/locales/zh-CN/docs/agent/integrations.md",
            CANONICAL / "assets/project-template/locales/en-US/docs/agent/integrations.md",
        )
        for document in documents:
            text = document.read_text(encoding="utf-8")
            self.assertIn("45", text, document)
            self.assertIn("REPORTING", text, document)
            for tool in ("codex", "opencode", "claude-code", "deepseek-harness"):
                self.assertIn(tool, text, document)

        skill = (CANONICAL / "SKILL.md").read_text(encoding="utf-8")
        for token in (
            ".agent-relay-auto/planner-channel.json",
            "same Planner conversation",
            "does not type `continue`",
            "verified",
            "experimental",
            "static_only",
            "unavailable",
            "Runner never writes `DONE` directly",
        ):
            self.assertIn(token, skill)

    def test_canonical_skill_runtime_mirror_has_no_drift(self):
        mirror = CANONICAL / "assets/project-template/shared/.agents/skills/agent-relay-auto"
        canonical_files = {
            path.relative_to(CANONICAL)
            for path in CANONICAL.rglob("*")
            if path.is_file()
            and "assets" not in path.relative_to(CANONICAL).parts
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
            and not path.name.startswith("._")
        }
        mirror_files = {
            path.relative_to(mirror)
            for path in mirror.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix != ".pyc"
            and not path.name.startswith("._")
        }
        self.assertEqual(canonical_files, mirror_files)
        for relative in canonical_files:
            self.assertEqual((CANONICAL / relative).read_bytes(), (mirror / relative).read_bytes(), relative)


if __name__ == "__main__":
    unittest.main()
