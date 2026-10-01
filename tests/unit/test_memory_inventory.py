import pytest
from klaude_cli.memory_inventory import read_memory_inventory
from klaude_core.memory import Memory


def test_inventory_reads_bounded_public_facts_without_initializing_storage(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.memory_file.write_text(
        "\n".join([f"- Useful fact {i}" for i in range(12)]) + "\n- api_key=sk-secret-value\n"
    )
    memory.set_auto_memory(False)
    memory.db.close()
    before = memory.memory_file.read_bytes()
    result = read_memory_inventory(memory.sessions_db, memory.memory_file)
    assert result["enabled"] is False and result["count"] == 13
    assert result["hidden"] == 1 and len(result["facts"]) == 8
    assert "secret" not in repr(result)
    assert memory.memory_file.read_bytes() == before


@pytest.mark.parametrize("unsafe", ["symlink", "oversized", "fifo"])
def test_inventory_rejects_unsafe_memory_files(tmp_path, unsafe):
    import os

    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.db.close()
    path = tmp_path / "unsafe"
    if unsafe == "symlink":
        path.symlink_to(memory.memory_file)
    elif unsafe == "oversized":
        path.write_bytes(b"x" * 1_048_577)
    else:
        os.mkfifo(path)
    with pytest.raises((OSError, ValueError)):
        read_memory_inventory(memory.sessions_db, path)


def test_missing_database_is_not_created(tmp_path):
    import sqlite3

    database = tmp_path / "missing.db"
    with pytest.raises(sqlite3.Error):
        read_memory_inventory(database, tmp_path / "missing.md")
    assert not database.exists()
