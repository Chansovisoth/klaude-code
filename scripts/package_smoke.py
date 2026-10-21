"""Build and install every workspace wheel in an isolated temporary environment."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGES = {
    "klaude_application",
    "klaude_cli",
    "klaude_core",
    "klaude_knowledge",
    "klaude_tools",
    "klaude_web",
    "klaude_webhost",
}


def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="klaude-package-smoke-") as temporary:
        base = Path(temporary)
        artifacts = base / "dist"
        environment = base / "venv"
        run(
            "uv",
            "build",
            "--all-packages",
            "--wheel",
            "--out-dir",
            str(artifacts),
            "--no-build-logs",
        )
        wheels = sorted(artifacts.glob("*.whl"))
        built = {
            wheel.name.partition("-")[0].replace("-", "_").casefold() for wheel in wheels
        }
        missing = EXPECTED_PACKAGES - built
        if missing:
            raise RuntimeError(f"workspace wheels missing: {', '.join(sorted(missing))}")

        run("uv", "venv", "--python", sys.executable, str(environment))
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        klaude = environment / ("Scripts/klaude.exe" if os.name == "nt" else "bin/klaude")
        webui = environment / (
            "Scripts/klaude-webui.exe" if os.name == "nt" else "bin/klaude-webui"
        )
        run(
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            *(str(wheel) for wheel in wheels),
        )
        run(
            str(python),
            "-c",
            "import klaude_application, klaude_cli, klaude_core, "
            "klaude_knowledge, klaude_tools, klaude_web, klaude_webhost; "
            "from importlib.resources import files; "
            "assets = files('klaude_webhost').joinpath('static'); "
            "required = ('index.html', 'app.js', 'library.js', 'management.js', 'media.js', "
            "'attachments.js', "
            "'markdown.js', 'style.css', 'loading-indicator.js', "
            "'vendor/material-loading-shapes.js', 'vendor/material-loading-LICENSE.txt', "
            "'vendor/material-loading-NOTICE.txt', 'vendor/material-loading-manifest.json', "
            "'vendor/markdown-it.min.js', 'vendor/prism.min.js', 'vendor/manifest.json', "
            "'vendor/markdown-it-LICENSE.txt', 'vendor/markdown-it-THIRD-PARTY.txt', "
            "'vendor/prism-LICENSE.txt', 'fonts/Roboto.ttf', "
            "'fonts/JetBrainsMono.ttf', 'fonts/Roboto-OFL.txt', 'fonts/JetBrainsMono-OFL.txt'); "
            "assert all(assets.joinpath(name).read_bytes() for name in required), "
            "'WebUI assets missing from installed wheel'",
        )
        smoke_env = {**os.environ, "NO_COLOR": "1"}
        run(str(klaude), "--help", env=smoke_env)
        run(str(webui), "--help", env=smoke_env)
        print(f"package smoke passed: {len(wheels)} wheels, imports, and both CLI help commands")


if __name__ == "__main__":
    main()
