# Task State

```yaml
task: "<TASK-ID>"
title: "<task-title>"
language: "<zh-CN|en-US>"
status: DRAFT
revision: 1
stage_round: 1
run_id: null
run_status: idle
run_attempt: 0
rework_round: 0
auto_replan_count: 0
agent_failure_count: 0
runtime_snapshot_ref: null
assignments:
  planner: "<planner-participant-id>"
  implementer: "<implementer-participant-id>"
  reviewer: "<reviewer-participant-id>"
assignment_change_refs:
  planner: null
  implementer: null
  reviewer: null
current_role: planner
current_participant: "<planner-participant-id>"
writer_session: null
execution: idle
subagent_policy: UNSELECTED
subagent_decision_ref: null
previous_role: null
previous_participant: null
previous_progress: null
latest_checkpoint: null
plan_version: null
approval_ref: null
code_delivery_ref: null
next_expected_output: requirement.md
question_id: null
question_ref: null
suspended_status: null
resume_role: null
blocked_reason: null
unblock_condition: null
resume_status: null
updated_at: "<ISO-8601>"
```

The task must equal `PROJECT_STATUS.md.active_task` before business writes. Increment `revision` for every STATE change and `stage_round` when stage or responsible participant changes. Each `assignment_change_refs` entry points to the latest Agent replacement management record for that role.
