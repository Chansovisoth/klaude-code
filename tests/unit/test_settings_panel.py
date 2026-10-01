"""Behavioral checks for the typed, scrollable settings panel."""

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
