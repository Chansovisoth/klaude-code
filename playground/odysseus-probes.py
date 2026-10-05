"""Isolated source probes, not live Odysseus/model or integration tests.

Run with python3 playground/odysseus-probes.py. Extract only inspected pure
helpers with the AST; do not import the app, start services, or access real data.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import re
import time
from collections import Counter
from pathlib import Path

SOURCE = Path(__file__).parent / "odysseus"


def node_name(node):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None


def extract(relative, names, class_members=None):
    tree = ast.parse((SOURCE / relative).read_text())
    selected = []
    for node in tree.body:
        if node_name(node) not in names:
            continue
        if isinstance(node, ast.ClassDef) and class_members is not None:
            node.body = [n for n in node.body if node_name(n) in class_members]
        selected.append(node)
    module = ast.Module(
        body=[
            ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
            *selected,
        ],
        type_ignores=[],
    )
    namespace = dict(
        re=re,
        math=math,
        time=time,
        Counter=Counter,
        logger=logging.getLogger("isolated-odysseus-probes"),
    )
    exec(compile(ast.fix_missing_locations(module), relative, "exec"), namespace)
    return namespace


budgets = extract(
    "src/context_budget.py",
    {
        "DEFAULT_HARD_MAX",
        "DEFAULT_BUDGET",
        "DEFAULT_HEADROOM",
        "_int_or_zero",
        "compute_input_token_budget",
    },
)["compute_input_token_budget"]
budget_results = {
    "unknown_auto": budgets(6000, 0, False),
    "8k_auto": budgets(6000, 8192, False),
    "16k_auto": budgets(6000, 16384, False),
    "explicit_4096": budgets(4096, 16384, True),
}
assert budget_results == dict(
    unknown_auto=6000,
    **{
        "8k_auto": 6963,
        "16k_auto": 13926,
        "explicit_4096": 4096,
    },
)

tools_ns = extract(
    "src/tool_index.py",
    {"ALWAYS_AVAILABLE", "ToolIndex"},
    {
        "_SCHEDULE_RE",
        "_WEB_RE",
        "_KEYWORD_HINTS",
        "get_tools_for_query",
    },
)
index = tools_ns["ToolIndex"]()
index.retrieve = lambda query, k=8: []  # Explicitly disable vector retrieval.
tool_results = {
    query: sorted(index.get_tools_for_query(query))
    for query in (
        "hello",
        "remember my preferred language is Python",
        "open https://example.com",
        "save this address for Alex",
        "summarize my inbox every morning",
    )
}
assert set(tool_results["hello"]) == {"manage_memory", "ask_user", "update_plan"}
assert {"web_fetch", "web_search"} <= set(tool_results["open https://example.com"])
assert "manage_contact" in tool_results["save this address for Alex"]
assert "manage_memory" not in tool_results["save this address for Alex"]
assert "manage_tasks" in tool_results["summarize my inbox every morning"]

memory_ns = extract(
    "src/chat_processor.py",
    {
        "_STOPWORDS",
        "_content_tokens",
        "ChatProcessor",
    },
    {
        "__init__",
        "RAG_SIMILARITY_THRESHOLD",
        "MEMORY_CONTEXT_LIMIT",
        "PINNED_MEMORY_LIMIT",
        "_is_core_memory",
        "_select_pinned_memories",
        "_hybrid_retrieve",
    },
)
processor = memory_ns["ChatProcessor"](None, None)
now = time.time()
entries = [
    dict(id="identity", text="My name is Alex", category="identity", timestamp=now),
    dict(
        id="postgres",
        text="PostgreSQL migration requires a backup before schema changes",
        category="preference",
        timestamp=now,
    ),
    dict(id="garden", text="Rose gardens require regular watering", category="fact", timestamp=now),
]
selected = processor._select_pinned_memories("PostgreSQL schema migration", entries)
memory_ids = [entry["id"] for entry in selected]
assert "identity" in memory_ids and "postgres" in memory_ids and "garden" not in memory_ids

plan_note = extract("src/agent_loop.py", {"build_active_plan_note"})["build_active_plan_note"]
plan = "- [x] inspect files\n- [ ] implement importer\n- [ ] run regression tests"
assert plan in plan_note(plan)
assert plan_note("") == ""

teacher = extract(
    "src/teacher_escalation.py",
    {
        "_TOOL_ERROR_PATTERNS",
        "_REPLY_GIVE_UP_PATTERNS",
        "evaluate_turn_regex",
    },
)["evaluate_turn_regex"]
classifier_results = {
    "explicit_tool_error": teacher([dict(error="missing file")], "Done"),
    "nonzero_test_exit_without_error_words": teacher(
        [dict(exit_code=1, output="3 failed, 8 passed")], "Done"
    ),
}
assert classifier_results["explicit_tool_error"][0] == "failure"
assert classifier_results["nonzero_test_exit_without_error_words"][0] == "ok"

print(
    json.dumps(
        dict(
            scope="Isolated helpers; no app, model calls, Chroma, MCP, or real memory store",
            budgets=budget_results,
            keyword_tools=tool_results,
            pinned_memory_selection=memory_ids,
            full_plan_retained=True,
            teacher_classifier=classifier_results,
        ),
        indent=2,
    )
)
