"""build_role() 工厂和扩展字段的测试"""

from harness.core.roles import (
    ROLE_REGISTRY,
    RoleCapability,
    WorkflowPhase,
    build_role,
)


def test_build_role_defaults():
    role = build_role(
        name="test",
        agent_name="harness-test",
        capability=RoleCapability.READONLY,
        description="test role",
        phases=(WorkflowPhase.EVALUATING,),
    )
    assert role.concurrency_safe is False
    assert role.max_retries == 1
    assert role.name == "test"


def test_build_role_override():
    role = build_role(
        name="reviewer",
        agent_name="harness-reviewer",
        capability=RoleCapability.READONLY,
        description="code reviewer",
        phases=(WorkflowPhase.EVALUATING,),
        concurrency_safe=True,
        max_retries=3,
    )
    assert role.concurrency_safe is True
    assert role.max_retries == 3


def test_evaluator_is_concurrency_safe():
    assert ROLE_REGISTRY["evaluator"].concurrency_safe is True
    assert ROLE_REGISTRY["alignment_evaluator"].concurrency_safe is True


def test_builder_is_not_concurrency_safe():
    assert ROLE_REGISTRY["builder"].concurrency_safe is False


def test_existing_roles_have_new_fields():
    for name, desc in ROLE_REGISTRY.items():
        assert hasattr(desc, "concurrency_safe"), f"{name} missing concurrency_safe"
        assert hasattr(desc, "max_retries"), f"{name} missing max_retries"


def test_role_descriptor_frozen():
    role = build_role(
        name="frozen",
        agent_name="harness-frozen",
        capability=RoleCapability.READONLY,
        description="immutable",
        phases=(),
    )
    try:
        role.name = "changed"
        assert False, "should be frozen"
    except AttributeError:
        pass
