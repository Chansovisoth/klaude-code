"""Terminal compatibility adapter for the shared owned worker lifecycle."""

from __future__ import annotations

import os as os
import subprocess as subprocess
from collections.abc import Callable

from klaude_application.background_jobs import MAX_JOB_OUTPUT, BackgroundJob
from klaude_application.background_jobs import OwnedBackgroundJobs as ApplicationBackgroundJobs


class OwnedBackgroundJobs(ApplicationBackgroundJobs):
    def __init__(self, emit: Callable[[str, object], None]):
        super().__init__(emit)


__all__ = ["MAX_JOB_OUTPUT", "BackgroundJob", "OwnedBackgroundJobs"]
