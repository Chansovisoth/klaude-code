"""Compatibility entry point for the shared fixed-operation worker."""

from klaude_application.background_worker import execute as execute
from klaude_application.background_worker import main as main

if __name__ == "__main__":
    main()
