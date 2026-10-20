"""Write-only private provider credential changes shared by terminal clients."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ProviderSecretUpdate:
    config_dir: Path
    name: str
    value: str = field(repr=False)

    def apply(self) -> None:
        if (
            not self.config_dir.is_absolute()
            or not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.name)
            or not isinstance(self.value, str)
        ):
            raise ValueError("Invalid provider credential change")
        from klaude_core.config import save_provider_secret

        save_provider_secret(self.config_dir, self.name, self.value)
