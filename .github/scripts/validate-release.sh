#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

fail() {
  printf 'validation error: %s\n' "$*" >&2
  exit 1
}

for required_file in \
  LICENSE README.md README.zh-CN.md CHANGELOG.md CONTRIBUTING.md SECURITY.md \
  shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/references/state-helper.md \
  shared/.agents/skills/agent-relay-auto/scripts/workflow_state.py \
  shared/.agents/skills/agent-relay-auto/scripts/relay_state.py \
  shared/.agents/skills/agent-relay-auto/scripts/setup_runner.py \
  shared/.agents/skills/agent-relay-auto/scripts/runnerctl.py \
  shared/.agents/skills/agent-relay-auto/scripts/configure_runtime.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runner.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/adapters/factory.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/state_store.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_channel.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/wake_store.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/reporting.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/factory.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/runner.py \
  shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/recovery.py \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/scripts/workflow_state.py \
  shared/docs/agent/knowledge-index.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/docs/agent/knowledge-index.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/knowledge-index.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/locales/en-US/docs/agent/knowledge-index.md \
  compat/project-role-workflow/SKILL.md \
  docs/migration-v1.5.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/protocol.md \
  shared/docs/agent/tasks/_template/STATE.md \
  codex/prompts/replace-agent.md \
  cursor/.cursor/commands/replace-agent.md \
  docs/verification/automated-runner-v1.8.0.md \
  tests/test_workflow_state.py \
  tests/test_runner_service.py; do
  test -f "$required_file" || fail "missing required file: $required_file"
done

test "$(tr -d '[:space:]' < distribution/VERSION)" = '1.8.0' \
  || fail "distribution/VERSION must be 1.8.0"
grep -Fq '## [1.8.0]' CHANGELOG.md || fail "CHANGELOG is missing v1.8.0"

cmp -s \
  shared/.agents/skills/agent-relay-auto/scripts/workflow_state.py \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/scripts/workflow_state.py \
  || fail "workflow_state.py bootstrap copy differs from source"
test -x shared/.agents/skills/agent-relay-auto/scripts/workflow_state.py \
  || fail "workflow_state.py must be executable"

while IFS= read -r source_script; do
  relative="${source_script#shared/.agents/skills/agent-relay-auto/}"
  mirror="shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/${relative}"
  test -f "$mirror" || fail "missing bootstrap script mirror: $relative"
  cmp -s "$source_script" "$mirror" || fail "bootstrap script differs: $relative"
done < <(find shared/.agents/skills/agent-relay-auto/scripts -type f -name '*.py' ! -name '._*' ! -path '*/__pycache__/*' -print | sort)

python3 -m unittest discover -v tests

for skill_file in \
  shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/SKILL.md; do
  test "$(sed -n '1p' "$skill_file")" = '---' || fail "missing frontmatter start: $skill_file"
  sed -n '2,40p' "$skill_file" | grep -Eq '^name: [a-z0-9-]+$' || fail "invalid name field: $skill_file"
  sed -n '2,40p' "$skill_file" | grep -Eq '^description: .+' || fail "missing description field: $skill_file"
done

for reporting_file in \
  shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/references/runner.md \
  shared/docs/agent/workflow.md \
  docs/AGENT_RELAY_AUTO_USAGE.md \
  docs/AGENT_RELAY_AUTO_USAGE.en-US.md; do
  for contract in '.agent-relay-auto/planner-channel.json' '45' 'REPORTING'; do
    grep -Fq "$contract" "$reporting_file" || fail "missing v1.8 reporting contract '$contract' in $reporting_file"
  done
done

for wake_tool in codex opencode claude-code deepseek-harness; do
  grep -Fq "\"$wake_tool\"" shared/.agents/skills/agent-relay-auto/scripts/agent_relay_runtime/planner_wake/factory.py \
    || fail "missing Planner wake adapter mapping: $wake_tool"
done

grep -Fq 'static_only' shared/docs/agent/integrations.md \
  || fail "DeepSeek Harness capability must be labelled truthfully"
git check-ignore -q .agent-relay-auto/planner-channel.json \
  || fail "Planner channel binding must remain ignored"

cmp -s \
  shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/SKILL.md \
  || fail "bootstrap Skill differs from source"

cmp -s \
  shared/.agents/skills/agent-relay-auto/references/runner.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/references/runner.md \
  || fail "runner reference bootstrap copy differs from source"

for contract_file in \
  shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/SKILL.md \
  shared/.agents/skills/agent-relay-auto/references/runner.md \
  shared/docs/agent/workflow.md; do
  for contract in 'implementation-done' 'protocol_failure: no_handoff' 'heartbeat_stale_seconds'; do
    grep -Fq "$contract" "$contract_file" || fail "missing v1.7 contract '$contract' in $contract_file"
  done
done

grep -Fq 'waiting_foreground_planner' shared/.agents/skills/agent-relay-auto/references/runner.md \
  || fail "PLANNING foreground wait contract is missing"

for policy_file in \
  shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/automation-policy.yaml \
  shared/.agents/skills/agent-relay-auto/assets/project-template/locales/en-US/docs/agent/automation-policy.yaml; do
  grep -Fq 'execution_mode: foreground' "$policy_file" || fail "missing foreground Planner in $policy_file"
  grep -Fq 'heartbeat_stale_seconds: 45' "$policy_file" || fail "missing runtime defaults in $policy_file"
  grep -Fq 'poll_interval_seconds: 45' "$policy_file" || fail "missing reporting interval in $policy_file"
  grep -Fq 'require_same_conversation: true' "$policy_file" || fail "missing exact-conversation policy in $policy_file"
done

if rg -n 'Runner automatically starts Planner|Runner 自动启动 Planner' README.md README.zh-CN.md docs/AGENT_RELAY_AUTO_USAGE* shared/docs shared/.agents/skills/agent-relay-auto/references; then
  fail "user-facing documentation still claims Runner starts Planner"
fi

cmp -s \
  shared/docs/agent/knowledge-index.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/docs/agent/knowledge-index.md \
  || fail "knowledge-index bootstrap copy differs from source"

test ! -d shared/.agents/skills/project-role-workflow \
  || fail "legacy full Skill directory must not remain in the template"
test ! -d shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/project-role-workflow \
  || fail "legacy full Skill directory must not remain in bootstrap assets"
test ! -e compat/project-role-workflow/assets \
  || fail "compatibility shim must not contain assets"
test ! -e compat/project-role-workflow/references \
  || fail "compatibility shim must not contain references"
test ! -e compat/project-role-workflow/scripts \
  || fail "compatibility shim must not contain scripts"

for tool_id in deepseek-harness opencode; do
  for tool_file in \
    shared/.agents/skills/agent-relay-auto/references/initialization.md \
    shared/.agents/skills/agent-relay-auto/assets/project-template/shared/.agents/skills/agent-relay-auto/references/initialization.md \
    shared/docs/agent/profiles/_templates/participant.md \
    shared/.agents/skills/agent-relay-auto/assets/project-template/shared/docs/agent/profiles/_templates/participant.md \
    shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/profiles/_templates/participant.md \
    shared/.agents/skills/agent-relay-auto/assets/project-template/locales/en-US/docs/agent/profiles/_templates/participant.md; do
    grep -Fq "$tool_id" "$tool_file" || fail "missing $tool_id in $tool_file"
  done
done

for integration_file in \
  shared/docs/agent/integrations.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/shared/docs/agent/integrations.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/locales/zh-CN/docs/agent/integrations.md \
  shared/.agents/skills/agent-relay-auto/assets/project-template/locales/en-US/docs/agent/integrations.md; do
  grep -Fq 'DeepSeek Harness' "$integration_file" || fail "missing DeepSeek Harness in $integration_file"
  grep -Fq 'OpenCode' "$integration_file" || fail "missing OpenCode in $integration_file"
done

test ! -d shared/.agents/skills/agent-relay-auto/assets/project-template/adapters/dsh \
  || fail "DeepSeek Harness must reuse the shared entry, not a duplicate adapter"
test ! -d shared/.agents/skills/agent-relay-auto/assets/project-template/adapters/opencode \
  || fail "OpenCode must reuse the shared entry, not a duplicate adapter"

python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path.cwd()
errors = []
link_re = re.compile(r'(?<!!)\[[^]]*\]\(([^)]+)\)')

for path in list(root.rglob('*.md')) + list(root.rglob('*.mdc')):
    if path.name.startswith('._') or any(part in {'.git', 'dist', '.learnings'} for part in path.parts):
        continue
    text = path.read_text(encoding='utf-8')
    if 'locales/en-US/docs/agent' in str(path):
        if any('\u4e00' <= char <= '\u9fff' for char in text):
            errors.append(f'Chinese text found in English overlay: {path.relative_to(root)}')
    for target in link_re.findall(text):
        target = target.strip().strip('<>').split('#', 1)[0].split('?', 1)[0]
        if not target or target.startswith(('/', '#', 'http:', 'https:', 'mailto:')):
            continue
        if not (path.parent / target).exists():
            errors.append(f'broken local link in {path.relative_to(root)}: {target}')

if errors:
    print('\n'.join(errors), file=sys.stderr)
    sys.exit(1)
PY

metadata_files="$(git ls-files | awk -F/ '$NF == ".DS_Store" || $NF ~ /^\._/')"
test -z "$metadata_files" || fail "metadata files must not be tracked source: $metadata_files"

bootstrap_example='shared/.agents/skills/agent-relay-auto/assets/project-template/shared/docs/agent/tasks/TASK-EXAMPLE-001'
test ! -e "$bootstrap_example" || fail "bootstrap assets must not include TASK-EXAMPLE-001"

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/agent-relay-auto-validate.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT
package_root="$build_dir/agent-relay-auto-skill-pack"
version="$(tr -d '[:space:]' < distribution/VERSION)"
archive="$build_dir/agent-relay-auto-skill-pack-v${version}.zip"
checksum="$archive.sha256"

mkdir -p "$package_root"
for package_dir in shared codex cursor compat; do
  rsync -a --exclude '._*' --exclude '.DS_Store' --exclude '__pycache__' --exclude '*.pyc' \
    "$package_dir/" "$package_root/$package_dir/"
done
mkdir -p "$package_root/docs"
cp docs/migration-v1.5.md "$package_root/docs/"
cp distribution/INSTALL.md distribution/INSTALL_PROMPT.md distribution/VERSION "$package_root/"
find "$package_root" -exec touch -h -t 202609200000 {} +

(
  cd "$build_dir"
  find agent-relay-auto-skill-pack -print | LC_ALL=C sort | zip -X -q "$archive" -@
)
unzip -tqq "$archive"

if command -v sha256sum >/dev/null 2>&1; then
  archive_hash="$(sha256sum "$archive" | awk '{print $1}')"
else
  archive_hash="$(shasum -a 256 "$archive" | awk '{print $1}')"
fi
printf '%s  %s\n' "$archive_hash" "$(basename "$archive")" > "$checksum"
test -s "$checksum" || fail "checksum was not generated"

if unzip -Z1 "$archive" | grep -Eq '(^|/)(\._|\.DS_Store)'; then
  fail "archive contains macOS metadata"
fi
if unzip -Z1 "$archive" | grep -Fq 'assets/project-template/shared/docs/agent/tasks/TASK-EXAMPLE-001'; then
  fail "archive bootstrap assets include TASK-EXAMPLE-001"
fi

printf 'validated source and generated release archive: %s\n' "$archive_hash"
