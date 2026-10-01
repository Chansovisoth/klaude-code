import asyncio
import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/compare_mcp_clients.py"


@pytest.mark.parametrize("backend", ["sdk", "fastmcp"])
def test_comparison_disabled_adapter_never_constructs_client(backend):
    adapter = runpy.run_path(str(SCRIPT))["Adapter"](backend, enabled=False)
    with pytest.raises(PermissionError, match="disabled"):
        asyncio.run(adapter.__aenter__())
    assert adapter.client is None


@pytest.mark.parametrize("backend", ["sdk", "fastmcp"])
def test_comparison_denied_call_never_reaches_client(backend):
    adapter = runpy.run_path(str(SCRIPT))["Adapter"](backend)
    with pytest.raises(PermissionError, match="denied"):
        asyncio.run(adapter.call("write", {"value": "private"}, permitted=False))
