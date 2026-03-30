#!/usr/bin/env bash
set -euo pipefail

# Benchmark runner for the TODO API demo story.
# Usage: ./run_benchmark.sh [harness|codex|cursor]

MODE="${1:-harness}"
WORKDIR="/tmp/todo-benchmark-${MODE}-$(date +%s)"

echo "=== TODO API Benchmark ==="
echo "Mode: ${MODE}"
echo "Workdir: ${WORKDIR}"
echo ""

mkdir -p "${WORKDIR}"
cd "${WORKDIR}"
git init
git commit --allow-empty -m "init"

TASKS=(
    "初始化 FastAPI 项目，添加健康检查端点和基础项目结构"
    "实现 TODO CRUD API（创建、读取、更新、删除）+ SQLite 存储"
    "添加输入验证、错误处理和 Pydantic 模型"
    "实现分页、过滤（按状态）和排序功能"
    "添加完整的 pytest 测试套件，覆盖所有端点和边界情况"
)

PASSED=0
TOTAL=${#TASKS[@]}

case "${MODE}" in
    harness)
        harness install 2>/dev/null || true
        harness init --name todo-api --ci "pytest" -y
        for i in "${!TASKS[@]}"; do
            echo ""
            echo "--- Task $((i+1))/${TOTAL}: ${TASKS[$i]:0:60}... ---"
            if harness run "${TASKS[$i]}"; then
                PASSED=$((PASSED+1))
                echo "✓ Task $((i+1)) PASSED"
            else
                echo "✗ Task $((i+1)) BLOCKED"
            fi
        done
        ;;
    codex)
        for i in "${!TASKS[@]}"; do
            echo ""
            echo "--- Task $((i+1))/${TOTAL}: ${TASKS[$i]:0:60}... ---"
            if echo "${TASKS[$i]}" | codex exec --full-auto -C "${WORKDIR}" -; then
                PASSED=$((PASSED+1))
                echo "✓ Task $((i+1)) done"
            else
                echo "✗ Task $((i+1)) failed"
            fi
        done
        ;;
    cursor)
        for i in "${!TASKS[@]}"; do
            echo ""
            echo "--- Task $((i+1))/${TOTAL}: ${TASKS[$i]:0:60}... ---"
            if cursor agent --print --force --workspace "${WORKDIR}" "${TASKS[$i]}"; then
                PASSED=$((PASSED+1))
                echo "✓ Task $((i+1)) done"
            else
                echo "✗ Task $((i+1)) failed"
            fi
        done
        ;;
    *)
        echo "Unknown mode: ${MODE}. Use: harness, codex, or cursor."
        exit 1
        ;;
esac

echo ""
echo "=== Results ==="
echo "Mode: ${MODE}"
echo "Passed: ${PASSED}/${TOTAL}"
echo "Workdir: ${WORKDIR}"

if [ "${MODE}" = "harness" ]; then
    echo ""
    echo "Artifacts: ${WORKDIR}/.agents/tasks/"
    echo "Events: ${WORKDIR}/.agents/runs/"
fi
