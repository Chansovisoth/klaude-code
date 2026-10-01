import pytest
from klaude_cli.main import ChatCommandCompleter
from klaude_cli.mcp_suggestions import search_suggestions
from prompt_toolkit.document import Document


@pytest.mark.parametrize("query", ["con", "context7", "contxt7"])
def test_query_hints_match_prefix_exact_and_typo(query):
    assert search_suggestions(query, ["Context7"])[0] == ("Context7", "loaded registry result")
    assert ("Context7", "suggested search") in search_suggestions(query)


def test_first_open_has_ordered_search_terms_without_claiming_popularity():
    hints = search_suggestions("")
    assert [name for name, _ in hints[:3]] == ["Context7", "GitHub", "filesystem"]
    assert all(source == "suggested search" for _, source in hints)
    assert len(hints) <= 8


def test_loaded_names_are_ranked_bounded_and_sanitized():
    names = ["io.example/context7", "bad\x1b[31m", "x" * 121]
    values = search_suggestions("context7", names)
    assert (names[0], "loaded registry result") in values
    assert all("\x1b" not in name and len(name) <= 120 for name, _ in values)
    assert len(search_suggestions("")) <= 8
    assert search_suggestions("x" * 121) == []


def test_suggestions_are_modal_and_do_not_fall_through_to_chat_or_files():
    active = True
    completer = ChatCommandCompleter(
        mcp_suggestions_provider=lambda query: search_suggestions(query, ["Context7"])
        if active else None
    )
    values = list(completer.get_completions(Document("con"), None))
    assert values[0].text == "Context7" and values[0].start_position == -3
    assert not list(completer.get_completions(Document("/status"), None))
    active = False
    assert list(completer.get_completions(Document("/status"), None))[0].text == "/status"


def test_secrets_and_other_disabled_completion_modes_never_suggest():
    completer = ChatCommandCompleter(
        completion_enabled=lambda: False,
        mcp_suggestions_provider=lambda _: [("secret", "must not appear")],
    )
    assert list(completer.get_completions(Document(""), None)) == []
