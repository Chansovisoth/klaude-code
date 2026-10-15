"""Tag proposals use real bounded Vision HTTP and independent manual/AI metadata."""

import json

import pytest
from klaude_core import image_tags as tags

from .test_vision import vision_lab as vision_lab


def proposal(lab):
    cfg, _, _, item, _, mode, *_ = lab
    mode["text"] = '["red", "green", "diagram"]'
    return tags.suggest(cfg, tags.prepare(cfg, item["id"], item["revision"], 4096, 512))


def test_proposal_has_no_writes_and_saves_selected_tags_only(vision_lab):
    cfg, _, store, item, calls, *_ = vision_lab
    candidate = proposal(vision_lab)
    assert store.get(item["id"]) == item
    count = len(calls)
    saved = tags.apply(cfg, candidate, ["red", "diagram"])["item"]
    assert saved["tags"] == [] and saved["ai_tags"] == ["red", "diagram"]
    assert len(calls) == count
    assert store.tagging_info(item["id"])["red"]["model"] == candidate["model"]
    assert store.listing("media", query="diagram")["items"][0]["id"] == item["id"]
    assert store.listing("document", query="diagram")["items"] == []
    assert not (cfg.data_dir / "sessions.db").exists()


def test_manual_tags_are_preserved_and_promotion_removes_ai_duplicate(vision_lab):
    cfg, _, store, item, *_ = vision_lab
    item = store.change(item["id"], item["revision"], "tags", "Red, important")
    candidate = proposal((cfg, vision_lab[1], store, item, *vision_lab[4:]))
    saved = tags.apply(cfg, candidate, candidate["tags"])["item"]
    assert saved["tags"] == ["Red", "important"] and saved["ai_tags"] == ["green", "diagram"]
    saved = store.change(item["id"], saved["revision"], "tags", "Red, important, green")
    assert saved["ai_tags"] == ["diagram"]
    assert list(store.tagging_info(item["id"])) == ["diagram"]
    cleared = store.change(item["id"], saved["revision"], "clear_ai_tags")
    assert cleared["tags"] == saved["tags"] and cleared["ai_tags"] == []


@pytest.mark.parametrize("change", ["manual", "archive", "delete", "checksum"])
def test_changed_image_cannot_accept_old_proposal(vision_lab, change):
    cfg, _, store, item, *_ = vision_lab
    candidate = proposal(vision_lab)
    if change == "checksum":
        with store.database(write=True) as db:
            db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"changed", item["id"]))
    elif change == "manual":
        store.change(item["id"], item["revision"], "tags", "manual")
    else:
        archived = store.change(item["id"], item["revision"], "archive")
        if change == "delete":
            store.change(item["id"], archived["revision"], "delete")
    with pytest.raises(ValueError):
        tags.apply(cfg, candidate, candidate["tags"])


@pytest.mark.parametrize("response", ['[]', '{}', '[1]', '["a,b"]', '["\\u001b"]',
                                     '["' + 'a' * 41 + '"]', 'Some tags: ["red"]'])
def test_invalid_or_noisy_model_output_is_not_saved(vision_lab, response):
    cfg, _, store, item, _, mode, *_ = vision_lab
    mode["text"] = response
    with pytest.raises(ValueError):
        tags.suggest(cfg, tags.prepare(cfg, item["id"], item["revision"], 4096, 512))
    assert store.get(item["id"])["ai_tags"] == []


def test_unoffered_tags_rejected_and_archive_preserves_source(vision_lab):
    cfg, _, store, item, *_ = vision_lab
    candidate = proposal(vision_lab)
    with pytest.raises(ValueError, match="reviewed proposal"):
        tags.apply(cfg, candidate, ["unoffered"])
    saved = tags.apply(cfg, candidate, ["red"])["item"]
    archived = store.change(item["id"], saved["revision"], "archive")
    assert archived["ai_tags"] == ["red"]
    store.change(item["id"], archived["revision"], "delete")
    with store.database() as db:
        assert db.execute("SELECT count(*) FROM image_tags").fetchone()[0] == 0


def test_old_store_reads_without_schema_mutation(vision_lab):
    _, _, store, item, *_ = vision_lab
    with store.database(write=True) as db:
        db.execute("DROP TABLE image_tags")
    assert store.get(item["id"])["ai_tags"] == []
    assert store.listing("media", query="input")["items"]
    with store.database() as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='image_tags'").fetchone()


def test_deduplication_and_bounded_fenced_json():
    assert tags.parse('```json\n["Red", "red", " green "]\n```') == ["Red", "green"]
    with pytest.raises(ValueError):
        tags.parse(json.dumps(["x"] * 21))


def test_tui_proposals_start_unselected_and_preserve_manual_choices(vision_lab):
    from types import SimpleNamespace

    from klaude_cli.settings_panel import PanelAction, PanelState, render_body
    from klaude_cli.vision_panel import VisionPanel

    _, _, _, item, *_ = vision_lab
    host = SimpleNamespace(_ai_defaults=SimpleNamespace(defaults=None))
    library = SimpleNamespace(host=host, view="vision-result", show=lambda *a: None)
    panel = VisionPanel(library)
    panel.item = {**item, "tags": ["red"]}
    panel.tagging = True
    panel.result = {"tags": ["red", "green"], "model": "reviewed-model"}
    for width in (40, 70, 120):
        state = PanelState(panel.page(), "back")
        render_body(state, width)
        assert state.picker.selected_id == "back"
    rows = {row.id: row for row in panel.page().rows}
    assert not rows["apply"].enabled and not rows["select:0"].enabled
    panel.handle(PanelAction("library-vision-select:0"))
    assert panel.selected == set()
    panel.handle(PanelAction("library-vision-select:1"))
    assert panel.selected == {"green"}
    assert next(row for row in panel.page().rows if row.id == "apply").enabled
