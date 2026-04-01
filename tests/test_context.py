"""TaskContext 单元测试"""

from harness.core.context import TaskContext, _new_id


def test_new_id_returns_12_char_hex():
    id1 = _new_id()
    assert len(id1) == 12
    int(id1, 16)


def test_task_context_defaults():
    ctx = TaskContext(task_id="task-001")
    assert ctx.task_id == "task-001"
    assert len(ctx.trace_id) == 12
    assert len(ctx.span_id) == 12
    assert ctx.iteration == 1
    assert ctx.depth == 0
    assert ctx.readonly is False


def test_child_span_inherits_trace_id():
    parent = TaskContext(task_id="task-001")
    child = parent.child_span()
    assert child.trace_id == parent.trace_id
    assert child.span_id != parent.span_id
    assert child.depth == parent.depth + 1
    assert child.task_id == parent.task_id


def test_child_span_override_readonly():
    parent = TaskContext(task_id="task-001", readonly=False)
    child = parent.child_span(readonly=True)
    assert child.readonly is True
    assert parent.readonly is False


def test_next_iteration_increments():
    ctx = TaskContext(task_id="task-001", iteration=2)
    next_ctx = ctx.next_iteration()
    assert next_ctx.iteration == 3
    assert next_ctx.trace_id == ctx.trace_id
    assert next_ctx.span_id != ctx.span_id
    assert next_ctx.depth == ctx.depth


def test_frozen():
    ctx = TaskContext(task_id="task-001")
    try:
        ctx.task_id = "changed"
        assert False, "should be frozen"
    except AttributeError:
        pass
