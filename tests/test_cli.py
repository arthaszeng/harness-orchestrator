"""Tests for harness CLI entry point."""

from __future__ import annotations

import builtins
import json
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harness.cli import app
from harness.core.state import TaskState
from harness.core.workflow_state import WorkflowState

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

runner = CliRunner()


class TestVersionOutput:
    def test_version_flag_contains_harness_flow(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "harness-flow" in result.output
        assert "harness-orchestrator" not in result.output

    def test_version_flag_short(self):
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "harness-flow" in result.output
        assert "harness-orchestrator" not in result.output


class TestHelpOutput:
    def test_help_lists_core_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "gate" in result.output
        assert "status" in result.output
        assert "update" in result.output
        assert "save-intervention-audit" in result.output
        assert "save-ship-metrics" in result.output

    def test_help_does_not_list_install(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        lines = result.output.lower().splitlines()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("install") and "completion" not in stripped:
                pytest.fail(f"'install' command found in help: {line}")

    def test_init_help_has_force_option(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        clean = _ANSI_RE.sub("", result.output)
        assert "--force" in clean

    def test_help_lists_git_lifecycle_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        clean = _ANSI_RE.sub("", result.output)
        assert "git-preflight" in clean
        assert "git-prepare-branch" in clean
        assert "git-sync-trunk" in clean
        assert "git-post-ship" in clean
        assert "git-post-ship-watch" in clean
        assert "git-post-ship-reconcile" in clean


class TestGateCommand:
    def test_gate_pass(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Plan\n\n## Deliverables\n", encoding="utf-8")
        (task_dir / "evaluation-r1.md").write_text(
            "# Eval\n\n## Verdict: PASS\n", encoding="utf-8",
        )

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate", "--task", "task-001"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "ready to ship" in clean.lower()
        assert "plan document" in clean.lower()
        assert "plan_exists" not in clean

    def test_gate_blocked_missing_eval(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate", "--task", "task-001"])
        assert result.exit_code == 1
        clean = _ANSI_RE.sub("", result.output)
        assert "not ready" in clean.lower()
        assert "code review record" in clean.lower()
        assert "eval_exists" not in clean

    def test_gate_no_task_dir(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        result = runner.invoke(app, ["gate"])
        assert result.exit_code == 1

    def test_gate_invalid_task_id_exits_with_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow" / "tasks").mkdir(parents=True)
        result = runner.invoke(app, ["gate", "--task", "task-999"])
        assert result.exit_code == 1
        clean = _ANSI_RE.sub("", result.output)
        assert "task-999" in clean

    def test_gate_auto_detects_latest_task(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        for i in [1, 2]:
            td = tmp_path / ".harness-flow" / "tasks" / f"task-00{i}"
            td.mkdir(parents=True)
            (td / "plan.md").write_text("# Plan\n\n## Deliverables\n", encoding="utf-8")
        (tmp_path / ".harness-flow" / "tasks" / "task-002" / "evaluation-r1.md").write_text(
            "# Eval\n\n## Verdict: PASS\n", encoding="utf-8",
        )

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "task-002" in clean

    def test_gate_invalid_workflow_state_exits_cleanly(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "plan.md").write_text("# Plan\n\n## Deliverables\n", encoding="utf-8")
        (task_dir / "evaluation-r1.md").write_text(
            "# Eval\n\n## Verdict: PASS\n", encoding="utf-8",
        )
        (task_dir / "workflow-state.json").write_text("{broken", encoding="utf-8")

        from unittest.mock import patch as mock_patch
        with mock_patch("harness.core.gates.get_head_commit_epoch", return_value=0.0):
            result = runner.invoke(app, ["gate", "--task", "task-001"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 1
        assert "existing workflow-state.json is invalid" in clean


class TestStatusCommand:
    def test_status_reads_canonical_workflow_state(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        workflow_state = WorkflowState(
            task_id="task-001",
            phase=TaskState.EVALUATING,
            iteration=2,
            branch="agent/task-001-workflow-intelligence",
        )
        workflow_state.active_plan.title = "Canonical Workflow State Artifact"
        workflow_state.blocker.reason = "awaiting ship readiness"
        workflow_state.save(task_dir)

        result = runner.invoke(app, ["status"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "evaluating" not in clean.lower()
        assert "workflow-state.json" not in clean
        assert "Canonical Workflow State Artifact" in clean
        assert "awaiting ship readiness" in clean
        assert "blocked" in clean.lower()

        rv = runner.invoke(app, ["status", "--verbose"])
        cv = _ANSI_RE.sub("", rv.output)
        assert rv.exit_code == 0
        assert "task-001" in cv
        assert "workflow-state.json" in cv
        assert "evaluating" in cv.lower()

    def test_status_renders_auto_reconcile_skip_by_default(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001").save(task_dir)
        result = runner.invoke(app, ["status"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "Background sync" in clean
        assert "off" in clean.lower()

    def test_status_renders_auto_reconcile_hit_when_pending_exists(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "harness.cli.is_auto_reconcile_eligible_subcommand",
            lambda *_a, **_k: False,
        )
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001").save(task_dir)
        queue = tmp_path / ".harness-flow" / "post-ship-pending.jsonl"
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text('{"task_key":"task-013"}\n', encoding="utf-8")
        result = runner.invoke(app, ["status"])
        clean = _ANSI_RE.sub("", result.output)
        assert result.exit_code == 0
        assert "Background sync" in clean
        assert "on" in clean.lower()
        assert "pending" in clean.lower()

    def test_status_without_pending_does_not_import_git_lifecycle(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-001"
        WorkflowState(task_id="task-001").save(task_dir)
        sys.modules.pop("harness.commands.git_lifecycle", None)

        imported: list[str] = []
        original_import = builtins.__import__

        def _tracking_import(name, *args, **kwargs):
            if name == "harness.commands.git_lifecycle":
                imported.append(name)
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _tracking_import)
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert imported == []


class TestSaveFeedbackLedgerCommand:
    def test_save_feedback_ledger_writes_file_and_updates_state(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-021"
        task_dir.mkdir(parents=True)
        WorkflowState(task_id="task-021").save(task_dir)

        body = (
            '{"id":"fb-1","task_id":"task-021","source_phase":"eval","source_role":"qa",'
            '"severity":"warn","category":"test","summary":"learning","status":"open",'
            '"decision":"none"}'
        )
        result = runner.invoke(
            app,
            ["save-feedback-ledger", "--task", "task-021", "--body", body],
        )
        assert result.exit_code == 0
        assert (task_dir / "feedback-ledger.jsonl").exists()
        state = WorkflowState.model_validate_json((task_dir / "workflow-state.json").read_text(encoding="utf-8"))
        assert state.artifacts.feedback_ledger == ".harness-flow/tasks/task-021/feedback-ledger.jsonl"

    def test_save_feedback_ledger_rejects_invalid_jsonl(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(
            app,
            ["save-feedback-ledger", "--task", "task-022", "--body", '{"id":"broken"'],
        )
        assert result.exit_code != 0

    def test_save_intervention_audit_writes_event(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-023"
        task_dir.mkdir(parents=True)
        WorkflowState(task_id="task-023").save(task_dir)
        result = runner.invoke(
            app,
            [
                "save-intervention-audit",
                "--task",
                "task-023",
                "--event-type",
                "manual_retry",
                "--command",
                "harness eval",
                "--summary",
                "rerun after failure",
            ],
        )
        assert result.exit_code == 0
        assert (task_dir / "intervention-audit.jsonl").exists()

    def test_save_intervention_audit_rejects_invalid_event_type(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        task_dir = tmp_path / ".harness-flow" / "tasks" / "task-024"
        task_dir.mkdir(parents=True)
        WorkflowState(task_id="task-024").save(task_dir)
        result = runner.invoke(
            app,
            [
                "save-intervention-audit",
                "--task",
                "task-024",
                "--event-type",
                "bad_type",
                "--command",
                "unknown",
            ],
        )
        assert result.exit_code != 0


class TestGitLifecycleCommands:
    def test_auto_reconcile_eligible_subcommand_true_for_status(self):
        from harness.core.post_ship_pending import is_auto_reconcile_eligible_subcommand
        assert is_auto_reconcile_eligible_subcommand("status") is True

    def test_auto_reconcile_eligible_subcommand_false_for_save_eval(self):
        from harness.core.post_ship_pending import is_auto_reconcile_eligible_subcommand
        assert is_auto_reconcile_eligible_subcommand("save-eval") is False

    def test_auto_reconcile_eligible_subcommand_false_for_none(self):
        from harness.core.post_ship_pending import is_auto_reconcile_eligible_subcommand
        assert is_auto_reconcile_eligible_subcommand(None) is False

    def test_git_post_ship_background_reconcile_skips_manager_when_no_pending(self, monkeypatch):
        from harness.commands.git_lifecycle import run_git_post_ship_reconcile_background

        called = {"create": False}

        def _create(*_args, **_kwargs):
            called["create"] = True
            return object()

        monkeypatch.setattr("harness.commands.git_lifecycle.has_pending_post_ship", lambda *_a, **_k: False)
        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipManager.create", _create)
        run_git_post_ship_reconcile_background(max_items=20)
        assert called["create"] is False

    def test_git_preflight_json_output(self, monkeypatch):
        from harness.integrations.git_ops import GitOperationResult

        class _Manager:
            def preflight_repo_state(self):
                return GitOperationResult(ok=True, code="OK", message="ready", context={"branch": "agent/task-001-x"})

        monkeypatch.setattr(
            "harness.commands.git_lifecycle.BranchLifecycleManager.create",
            lambda *_args, **_kwargs: _Manager(),
        )
        result = runner.invoke(app, ["git-preflight", "--json"])
        assert result.exit_code == 0
        assert '"ok": true' in result.output
        assert '"code": "OK"' in result.output

    def test_git_preflight_dirty_prints_recovery_on_stderr(self, monkeypatch, tmp_path: Path):
        from harness.integrations.git_ops import GitOperationResult

        class _Manager:
            def preflight_repo_state(self):
                return GitOperationResult(
                    ok=False,
                    code="DIRTY_WORKTREE",
                    message="working tree has uncommitted changes",
                )

        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir()
        (agents / "config.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
        monkeypatch.setattr(
            "harness.commands.git_lifecycle.BranchLifecycleManager.create",
            lambda *_args, **_kwargs: _Manager(),
        )
        result = runner.invoke(app, ["git-preflight"])
        assert result.exit_code == 1
        assert "What happened" in result.output

    def test_gate_no_task_prints_recovery(self, monkeypatch, tmp_path: Path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".harness-flow").mkdir()
        (tmp_path / ".harness-flow" / "config.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
        result = runner.invoke(app, ["gate"])
        assert result.exit_code == 1
        assert "What happened" in result.output

    def test_gate_blocked_prints_recovery(self, monkeypatch, tmp_path: Path):
        from harness.core.gates import CheckItem, CheckStatus, GateVerdict

        monkeypatch.chdir(tmp_path)
        agents = tmp_path / ".harness-flow"
        agents.mkdir()
        (agents / "config.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
        task = agents / "tasks" / "task-001"
        task.mkdir(parents=True)
        verdict = GateVerdict(
            passed=False,
            checks=[
                CheckItem(name="plan_exists", status=CheckStatus.BLOCKED, reason="missing plan"),
            ],
            summary="blocked",
        )
        monkeypatch.setattr("harness.commands.gate.check_ship_readiness", lambda *_a, **_k: verdict)
        monkeypatch.setattr("harness.commands.gate.write_gate_snapshot", lambda *_a, **_k: None)
        result = runner.invoke(app, ["gate"])
        assert result.exit_code == 1
        assert "What happened" in result.output

    def test_git_prepare_branch_failure_returns_exit_1(self, monkeypatch):
        from harness.integrations.git_ops import GitOperationResult

        class _Manager:
            def prepare_task_branch(self, *_args, **_kwargs):
                return GitOperationResult(ok=False, code="INVALID_TASK_KEY", message="invalid")

        monkeypatch.setattr(
            "harness.commands.git_lifecycle.BranchLifecycleManager.create",
            lambda *_args, **_kwargs: _Manager(),
        )
        result = runner.invoke(
            app,
            ["git-prepare-branch", "--task-key", "bad", "--short-desc", "x"],
        )
        assert result.exit_code == 1
        clean = _ANSI_RE.sub("", result.output)
        assert "INVALID_TASK_KEY" in clean

    def test_git_sync_trunk_json_output(self, monkeypatch):
        from harness.integrations.git_ops import GitOperationResult

        class _Manager:
            def sync_feature_with_trunk(self):
                return GitOperationResult(ok=True, code="OK", message="synced")

        monkeypatch.setattr(
            "harness.commands.git_lifecycle.BranchLifecycleManager.create",
            lambda *_args, **_kwargs: _Manager(),
        )
        result = runner.invoke(app, ["git-sync-trunk", "--json"])
        assert result.exit_code == 0
        assert '"code": "OK"' in result.output

    def test_git_post_ship_wait_merge_json_output(self, monkeypatch):
        from harness.integrations.git_ops import GitOperationResult

        class _Watcher:
            def wait_and_finalize(self, **_kwargs):
                return GitOperationResult(ok=True, code="POST_SHIP_DONE", message="done")

        class _Manager:
            def infer_task_key_from_branch(self, _branch=None):
                return "task-006"

        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipManager.create", lambda *_a, **_k: _Manager())
        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipWatcher.create", lambda *_a, **_k: _Watcher())

        result = runner.invoke(app, ["git-post-ship", "--task-key", "task-006", "--pr", "64", "--wait-merge", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["code"] == "POST_SHIP_DONE"
        assert "message" in payload
        assert "context" in payload

    def test_git_post_ship_wait_merge_timeout_is_deferred(self, monkeypatch):
        from harness.integrations.git_ops import GitOperationResult

        class _Watcher:
            def wait_and_finalize(self, **_kwargs):
                return GitOperationResult(ok=False, code="PR_WAIT_TIMEOUT", message="timeout")

        class _Manager:
            def infer_task_key_from_branch(self, _branch=None):
                return "task-009"

        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipManager.create", lambda *_a, **_k: _Manager())
        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipWatcher.create", lambda *_a, **_k: _Watcher())
        monkeypatch.setattr("harness.commands.git_lifecycle.enqueue_pending_post_ship", lambda *_a, **_k: True)

        result = runner.invoke(
            app,
            ["git-post-ship", "--task-key", "task-009", "--pr", "99", "--wait-merge", "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["code"] == "PR_WATCH_DEFERRED"
        assert payload["context"]["fallback_reason"] == "timeout"

    def test_git_post_ship_reconcile_json_output(self, monkeypatch):
        monkeypatch.setattr(
            "harness.commands.git_lifecycle.reconcile_pending_post_ship",
            lambda *_a, **_k: {"processed": 2, "merged": 1, "closed": 0, "retained": 1, "failed": 0},
        )
        monkeypatch.setattr(
            "harness.commands.git_lifecycle.record_intervention_event",
            lambda *_a, **_k: True,
        )

        class _Manager:
            pass

        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipManager.create", lambda *_a, **_k: _Manager())
        result = runner.invoke(app, ["git-post-ship-reconcile", "--json", "--max-items", "20"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["code"] == "POST_SHIP_RECONCILED"
        assert payload["context"]["audit_write"] == "ok"

    def test_git_post_ship_watch_json_output(self, monkeypatch, tmp_path: Path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "harness.commands.git_lifecycle.subprocess.Popen",
            lambda *_a, **_k: type("P", (), {"pid": 43210})(),
        )

        class _Manager:
            def infer_task_key_from_branch(self, _branch=None):
                return "task-010"

        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipManager.create", lambda *_a, **_k: _Manager())
        result = runner.invoke(
            app,
            ["git-post-ship-watch", "--task-key", "task-010", "--pr", "70", "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["code"] == "PR_WATCH_STARTED"
        assert payload["context"]["poll_interval_sec"] == "10"

    def test_git_post_ship_wait_merge_branch_changed_is_deferred(self, monkeypatch):
        from harness.integrations.git_ops import GitOperationResult

        class _Watcher:
            def wait_and_finalize(self, **_kwargs):
                return GitOperationResult(
                    ok=False,
                    code="POST_SHIP_DEFERRED_BRANCH_CHANGED",
                    message="deferred",
                )

        class _Manager:
            def infer_task_key_from_branch(self, _branch=None):
                return "task-011"

        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipManager.create", lambda *_a, **_k: _Manager())
        monkeypatch.setattr("harness.commands.git_lifecycle.PostShipWatcher.create", lambda *_a, **_k: _Watcher())
        monkeypatch.setattr("harness.commands.git_lifecycle.enqueue_pending_post_ship", lambda *_a, **_k: True)

        result = runner.invoke(
            app,
            ["git-post-ship", "--task-key", "task-011", "--pr", "70", "--wait-merge", "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["code"] == "PR_WATCH_DEFERRED"
        assert payload["context"]["fallback_reason"] == "branch_changed"

    def test_git_post_ship_requires_selector(self):
        result = runner.invoke(app, ["git-post-ship", "--task-key", "task-006"])
        assert result.exit_code != 0

    def test_git_post_ship_rejects_invalid_timeout(self):
        result = runner.invoke(
            app,
            ["git-post-ship", "--task-key", "task-006", "--pr", "64", "--timeout-sec", "0"],
        )
        assert result.exit_code != 0

    def test_git_post_ship_rejects_invalid_poll_interval(self):
        result = runner.invoke(
            app,
            ["git-post-ship", "--task-key", "task-006", "--pr", "64", "--poll-interval-sec", "0"],
        )
        assert result.exit_code != 0

    def test_git_post_ship_rejects_non_positive_pr(self):
        result = runner.invoke(
            app,
            ["git-post-ship", "--task-key", "task-006", "--pr", "0"],
        )
        assert result.exit_code != 0

    def test_git_post_ship_rejects_task_key_branch_mismatch(self):
        result = runner.invoke(
            app,
            ["git-post-ship", "--task-key", "task-007", "--branch", "agent/task-006-demo"],
        )
        assert result.exit_code != 0


class TestDebugLogOnReconcileFailure:
    """D3: _log_debug_error writes structured entries without blocking."""

    def test_log_debug_error_writes_to_debug_log(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        harness_dir = tmp_path / ".harness-flow"
        harness_dir.mkdir()

        from harness.cli import _log_debug_error

        try:
            raise RuntimeError("test boom")
        except Exception:
            _log_debug_error("gate")

        log_path = harness_dir / "debug.log"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "subcommand=gate" in content
        assert "RuntimeError" in content
        assert "test boom" in content

    def test_log_debug_error_no_harness_dir_is_noop(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from harness.cli import _log_debug_error

        try:
            raise RuntimeError("should not write")
        except Exception:
            _log_debug_error("status")

        assert not (tmp_path / ".harness-flow" / "debug.log").exists()
