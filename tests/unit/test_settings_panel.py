"""Behavioral checks for the typed, scrollable settings panel."""

import pytest
from klaude_cli.settings_panel import (
    PanelAction,
    PanelPage,
    PanelRow,
    PanelState,
    RowKind,
    render_body,
    render_footer,
    render_header,
)
from prompt_toolkit.utils import get_cwidth


def _page(checked: bool = True) -> PanelPage:
    return PanelPage(
        "tools",
        ("Settings", "Tools"),
        (
            PanelRow("heading", RowKind.SECTION, "Availability"),
            PanelRow(
                "web",
                RowKind.TOGGLE,
                "Auto web search",
                description="Search when current information is required",
                checked=checked,
                action=PanelAction("toggle", "web"),
                section_id="heading",
            ),
            PanelRow("note", RowKind.INFO, "Available tools depend on configuration"),
            PanelRow(
                "local",
                RowKind.TOGGLE,
                "Local knowledge",
                description="Search indexed local libraries",
                checked=False,
                action=PanelAction("toggle", "local"),
                section_id="heading",
            ),
            PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("back")),
        ),
    )


def _text(lines) -> str:
    return "\n".join("".join(text for _style, text in line) for line in lines)


def test_panel_has_fixed_header_footer_and_semantic_styles():
    state = PanelState(_page())
    body = render_body(state, 110)
    heading = next(line for line in body.lines if "AVAILABILITY" in str(line))
    selected = next(line for line in body.lines if "Auto web search" in str(line))
    assert heading == (
        ("class:panel.heading-marker", "▪ "),
        ("class:panel.section", "AVAILABILITY"),
    )
    assert body.row_for_line[body.lines.index(heading)] == "heading"
    assert selected[0] == ("class:panel.selected class:panel.focus", "› ")
    assert ("class:panel.selected class:toggle.on", "■") in selected
    square = selected.index(("class:panel.selected class:toggle.on", "■"))
    assert selected[square - 1] == ("class:panel.selected class:panel.value", "  [  ")
    assert selected[square + 1][0] == "class:panel.selected class:panel.value"
    assert "] ON" in selected[square + 1][1]
    assert any(
        style == "class:panel.selected class:panel.muted" and "Search when" in text
        for style, text in selected
    )
    assert "Settings › Tools" in str(render_header(state.page, 110))
    assert "↑↓ move · ENTER open/apply · SPACE toggle · / search · ESC back" in str(
        render_footer(110, search=False, status="Saved")
    )
    assert "Saved" not in _text(body.lines)


def test_panel_responsive_layout_keeps_values_and_wraps_descriptions():
    for width in (110, 70, 36, 18):
        body = render_body(PanelState(_page()), width)
        text = _text(body.lines)
        assert "Auto web search" in text
        assert "[  ■] ON" in text
        assert "[■  ] OFF" in text
        assert "Search when current information is required" in " ".join(text.split())
        if width < 55:
            compact = "\n".join(line.rstrip() for line in text.splitlines())
            assert "Auto web search\n    [  ■] ON" in compact


def test_panel_filter_keeps_section_and_stable_selection_through_refresh():
    state = PanelState(_page())
    state.move(1)
    assert state.picker.selected_id == "local"
    state.filter("local")
    assert [row.id for row in state.visible_rows()] == ["heading", "local", "back"]
    assert "▪ AVAILABILITY" in _text(render_body(state, 70).lines)
    assert "────────────" not in _text(render_body(state, 70).lines)
    state.scroll_top = 3
    state.replace(_page(False))
    assert state.picker.selected_id == "local"
    assert state.picker.query == "local"
    assert state.scroll_top == 3
    state.filter("")
    assert state.picker.selected_id == "local"


def test_panel_skips_nonselectable_rows_and_keeps_heading_visible():
    state = PanelState(_page())
    state.move(1)
    assert state.picker.selected_id == "local"
    state.move(-1)
    assert state.picker.selected_id == "web"
    body = render_body(state, 36)
    state.scroll_top = body.selected_line
    assert state.viewport(4, body) == 0


def test_panel_no_match_is_inert_and_visible():
    state = PanelState(_page())
    state.filter("nothing matching here")
    assert state.picker.selected_id is None
    assert "No matching options" in _text(render_body(state, 70).lines)


def test_toggle_text_comes_from_boolean_and_has_ascii_fallback():
    state = PanelState(_page(False))
    assert "[■  ] OFF" in _text(render_body(state, 70).lines)
    assert "[X  ] OFF" in _text(render_body(state, 70, unicode_blocks=False).lines)


def test_only_enabled_toggle_square_uses_accent_at_each_layout_width():
    for width in (110, 70, 36, 18):
        body = render_body(PanelState(_page()), width)
        assert ("class:panel.selected class:toggle.on", "■") in [
            fragment for line in body.lines for fragment in line
        ]
        off_fragments = [
            fragment for line, owner in zip(body.lines, body.row_for_line, strict=True)
            if owner == "local" for fragment in line
        ]
        assert ("class:panel.selected class:toggle.on", "■") not in off_fragments
        assert "[■  ] OFF" in "".join(text for _style, text in off_fragments)
    ascii_body = render_body(PanelState(_page()), 36, unicode_blocks=False)
    assert ("class:panel.selected class:toggle.on", "X") in [
        fragment for line in ascii_body.lines for fragment in line
    ]


def test_status_has_its_own_style_without_coloring_the_row():
    page = PanelPage(
        "save",
        ("Settings",),
        (
            PanelRow(
                "row",
                RowKind.ACTION,
                "Save preference",
                "[ Save ]",
                "Persist this choice",
                status="Saved",
                status_tone="success",
                action=PanelAction("save"),
            ),
        ),
    )
    body = render_body(PanelState(page), 70)
    assert any(style == "class:panel.selected class:panel.label" for style, _ in body.lines[0])
    assert any(
        style == "class:panel.selected class:panel.status.success" and "Saved" in text
        for line in body.lines
        for style, text in line
    )


def test_policy_value_tones_color_only_values_at_all_widths():
    page = PanelPage("policies", ("Settings", "Permissions"), (
        PanelRow("allow", RowKind.CHOICE, "Read file", "ALLOW",
                 value_tone="success", action=PanelAction("policy", "allow")),
        PanelRow("ask", RowKind.CHOICE, "Write file", "ASK",
                 value_tone="warning", action=PanelAction("policy", "ask")),
        PanelRow("deny", RowKind.CHOICE, "Run shell", "DENY",
                 value_tone="error", action=PanelAction("policy", "deny")),
    ))
    for width in (110, 70, 36, 18):
        body = render_body(PanelState(page), width)
        for identity, policy, tone in (
            ("allow", "ALLOW", "success"),
            ("ask", "ASK", "warning"),
            ("deny", "DENY", "error"),
        ):
            fragments = [
                (style, text)
                for line, owner in zip(body.lines, body.row_for_line, strict=True)
                if owner == identity for style, text in line
            ]
            assert any(policy in text and f"class:panel.value.{tone}" in style
                       for style, text in fragments)
            assert all("class:panel.value." not in style
                       for style, text in fragments if policy not in text)


def test_focus_background_follows_wrapped_row_without_recoloring_description():
    page = _page()
    for width in (110, 70, 36, 18):
        body = render_body(PanelState(page), width)
        focused = [
            line for line, owner in zip(body.lines, body.row_for_line, strict=True)
            if owner == "web"
        ]
        assert focused
        assert all(
            style.startswith("class:panel.selected") for line in focused
            for style, _text in line
        )
        assert all(
            sum(len(text) for _style, text in line) <= width
            for line in focused
        )
        assert any(
            "class:panel.muted" in style and "Search when" in text
            for line in focused for style, text in line
        )
        assert not any(
            "class:panel.selected" in style for line, owner in zip(
                body.lines, body.row_for_line, strict=True
            ) if owner == "local" for style, _text in line
        )


def test_long_value_stacks_before_description_and_narrow_header_keeps_title():
    page = PanelPage(
        "detail",
        ("Settings", "Permissions", "MCP Servers", "firecrawl"),
        (
            PanelRow(
                "policy",
                RowKind.NAVIGATION,
                "Current policy",
                "A very long current policy value that must remain visible",
                "Some explanatory context",
                action=PanelAction("open"),
            ),
        ),
    )
    for width in (95, 65, 30):
        lines = _text(render_body(PanelState(page), width).lines)
        assert "A very long current policy value that must remain visible" in " ".join(
            lines.split()
        )
    assert "firecrawl" in str(render_header(page, 30, "policy"))
    assert "/policy" in str(render_footer(30, search=True, query="policy"))


def test_footer_group_has_one_noninteractive_blank_line_and_keeps_focus():
    for width in (110, 70, 18):
        for existing_gap in (False, True):
            content = [PanelRow("option", RowKind.CHOICE, "Theme", "Autumn")]
            if existing_gap:
                content.append(PanelRow("gap", RowKind.SEPARATOR, ""))
            content.extend([
                PanelRow("reset", RowKind.ACTION, "Restore preferences", footer=True,
                         action=PanelAction("legacy-choice", "reset to default")),
                PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("back")),
            ])
            state = PanelState(PanelPage("test", ("Settings",), tuple(content)), "reset")
            body = render_body(state, width)
            reset_line = body.row_for_line.index("reset")
            assert not "".join(text for _style, text in body.lines[reset_line - 1]).strip()
            assert "".join(text for _style, text in body.lines[reset_line - 2]).strip()
            assert body.selected_line == reset_line
            assert state.picker.selected_id == "reset"
            state.move(-1)
            assert state.picker.selected_id == "option"


def _registry_page(
    description: str = "Search code examples and extract public documentation",
) -> PanelPage:
    return PanelPage(
        "registry", ("Settings", "MCP Servers", "Registry"),
        (
            PanelRow("heading", RowKind.SECTION, "Official MCP Registry"),
            PanelRow("registry:example", RowKind.NAVIGATION,
                     "io.github.example/documentation-server", "2026.10.2-preview.12",
                     description, section_id="heading", search_terms="Friendly Browser",
                     action=PanelAction("open", "example")),
            PanelRow("search", RowKind.ACTION, "Search again", footer=True),
            PanelRow("back", RowKind.NAVIGATION, "Back", footer=True),
        ),
        column_headers=("MCP Name", "Version", "Description"),
    )


@pytest.mark.parametrize("width", (140, 100, 70, 60, 59, 36, 18))
def test_registry_table_wraps_every_field_without_ellipsis(width):
    description = "Browse code examples and documentation. 文档检索示例 " * 6
    page = _registry_page(description)
    state = PanelState(page)
    body = render_body(state, width)
    fragments = [fragment for line, owner in zip(body.lines, body.row_for_line, strict=True)
                 if owner == "registry:example" for fragment in line]
    for field, style in ((page.rows[1].label, "panel.label"),
                         (page.rows[1].value, "panel.value"),
                         (description, "panel.muted")):
        rendered = "".join(text for tone, text in fragments if style in tone)
        assert "".join(rendered.split()) == "".join(field.split())
        assert "…" not in rendered
    assert all(get_cwidth("".join(text for _style, text in line)) <= width
               for line in body.lines)
    assert all("panel.selected" in style for style, _text in fragments)
    header = "".join(text for _style, text in render_header(page, width))
    if width >= 60:
        assert header.count("\n") == 2
        assert all(column.upper() in header for column in page.column_headers)
        heading_fragments = render_header(page, width)
        assert all(text == text.strip() and " " not in text
                   for style, text in heading_fragments if style == "class:panel.section")
    else:
        assert header.count("\n") == 1
    search_line = body.row_for_line.index("search")
    assert not _text((body.lines[search_line - 1],)).strip()


def test_registry_table_filter_refresh_keeps_identity_and_searches_hidden_friendly_title():
    state = PanelState(_registry_page())
    for query in ("examples", "2026.10.2", "Friendly Browser", "documentation-server"):
        state.filter(query)
        assert state.picker.selected_id == "registry:example"
        assert "heading" in [row.id for row in state.visible_rows()]
    state.scroll_top = 2
    state.replace(_registry_page("Updated documentation-server description"))
    assert state.picker.query == "documentation-server"
    assert state.picker.selected_id == "registry:example"
    assert state.scroll_top == 2
    state.filter("")
    assert state.picker.selected_id == "registry:example"


def test_registry_table_long_row_can_scroll_resize_and_restore_focus():
    state = PanelState(_registry_page("Detailed example and reference information " * 12))
    body = render_body(state, 18)
    assert state.scroll_row(10, body)
    target = state.focus_line(body)
    assert body.row_for_line[target] == "registry:example"
    top = state.viewport(8, body)
    assert top <= target < top + 8
    assert top > body.selected_line
    wider = render_body(state, 140)
    target = state.focus_line(wider)
    top = state.viewport(8, wider)
    assert top <= target < top + 8
    assert wider.row_for_line[target] == "registry:example"
    state.move(1)
    assert state.picker.selected_id == "search"
    state.focus_line(render_body(state, 18))
    state.move(-1)
    assert state.focus_line(render_body(state, 18)) == body.selected_line
    state.scroll_row(5, body)
    state.filter("example")
    assert state.focus_line(render_body(state, 18)) == body.selected_line


@pytest.mark.parametrize("width", [24, 70, 110])
def test_section_comment_is_muted_and_wraps_without_underlining(width):
    comment = "Configuration snapshot 0s old"
    state = PanelState(PanelPage("mcp", ("Settings", "MCPs"), (
        PanelRow("configured", RowKind.SECTION, "MCP Servers", description=comment),
    )))
    body = render_body(state, width)
    fragments = [fragment for line in body.lines for fragment in line]
    assert any(style == "class:panel.section" and text == "MCP SERVERS"
               for style, text in fragments)
    muted = " ".join(text.strip() for style, text in fragments if style == "class:panel.muted")
    assert muted == comment
    assert all(get_cwidth("".join(text for _, text in line)) <= width for line in body.lines)
    if width >= 70:
        assert len(body.lines) == 1


@pytest.mark.parametrize("count", [0, 1, 2])
def test_installed_skill_heading_has_muted_inventory_count(count):
    from klaude_cli.skills_panel import skills_page

    page = skills_page([{"name": f"skill-{index}"} for index in range(count)], "/tmp/inbox")
    heading = next(row for row in page.rows if row.id == "installed")
    assert heading.label == "SKILLS"
    assert heading.description == f"{count} installed"
    line = next(line for line in render_body(PanelState(page), 70).lines
                if ("class:panel.section", "SKILLS") in line)
    assert ("class:panel.section", "SKILLS") in line
    assert ("class:panel.heading-marker", ":") not in line
    assert ("class:panel.muted", f"  {count} installed") in line
    assert not any(row.id == "count" for row in page.rows)


@pytest.mark.parametrize("width", [24, 55, 100])
def test_skills_page_clear_import_flow_and_compact_inventory(width):
    from klaude_cli.skills_panel import skills_page

    inbox = "/tmp/klaude/skills-inbox"
    page = skills_page([
        {"name": "testing", "library": "testing", "indexed_file_count": 1, "identity": "a"},
        {"name": "frontend", "library": "shared", "indexed_file_count": 3, "identity": "b"},
    ], inbox)
    assert [row.id for row in page.rows[:6]] == [
        "discovery", "search", "add", "import", "inbox", "installed",
    ]
    rows = {row.id: row for row in page.rows}
    assert rows["inbox"].label == f"Drop ZIPs or skill files here: {inbox}, then import"
    assert rows["inbox"].description == ""
    assert rows["import"].description == ""
    assert rows["import"].action.kind == "skill-import"
    assert rows["skill:testing"].value == "1 file"
    assert rows["skill:testing"].description == ""
    assert rows["skill:frontend"].description == "Library: shared"
    state = PanelState(page, "import")
    assert state.picker.selected_id == "import"
    body = render_body(state, width)
    path_lines = [line for line, owner in zip(body.lines, body.row_for_line, strict=True)
                  if owner == "inbox"]
    assert "".join(text for line in path_lines for _, text in line).replace(" ", "").endswith(
        f"{inbox}, then import".replace(" ", "")
    )
    assert all(get_cwidth("".join(text for _, text in line)) <= width for line in body.lines)
    assert "klaude import-skill" not in "".join(text for line in body.lines for _, text in line)
    state.picker.filter("frontend")
    assert any(row.id == "installed" for row in state.picker.visible)
    assert state.picker.selected_id == "skill:frontend"


@pytest.mark.parametrize("width", [18, 70, 110])
@pytest.mark.parametrize("confirmation", [False, True])
def test_mcp_delete_back_and_cancel_have_gap_without_reset(width, confirmation):
    from klaude_cli.mcp_management import removal_confirmation, removal_page

    page = removal_confirmation("docs") if confirmation else removal_page([
        {"name": "docs", "enabled": False},
    ])
    identity = "cancel" if confirmation else "back"
    state = PanelState(page, identity)
    body = render_body(state, width)
    index = body.row_for_line.index(identity)
    assert not "".join(text for _, text in body.lines[index - 1]).strip()
    assert "".join(text for _, text in body.lines[index - 2]).strip()
    assert body.selected_line == index
    state.picker.filter("no matching server")
    assert identity in [row.id for row in state.visible_rows()]
