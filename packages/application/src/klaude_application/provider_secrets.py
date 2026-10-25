"""Write-only private provider credential changes shared by terminal clients."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderSecretUpdate:
    config_dir: Path
    name: str
    value: str = field(repr=False)

    def apply(
        self, *, before_publish: Callable[[dict[str, Any], dict[str, Any]], None] | None = None
    ) -> None:
        if (
            not self.config_dir.is_absolute()
            or not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.name)
            or not isinstance(self.value, str)
        ):
            raise ValueError("Invalid provider credential change")
        from klaude_core.config import save_provider_secret

        if before_publish is None:
            save_provider_secret(self.config_dir, self.name, self.value)
        else:
            save_provider_secret(
                self.config_dir, self.name, self.value, before_publish=before_publish
            )
