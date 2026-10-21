"""Export official Material/AndroidX matched cubic geometry, with pinned hashes.

Maintenance only. Requires a JDK and downloads verified official artifacts into
a temporary directory; no dependency or build tool is needed by Klaude at runtime.
Use --cache /tmp/klaude-official-loading to reuse already verified downloads.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

from bundle_webui_loading import bundle

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "apps/webhost/src/klaude_webhost/static/vendor"
REVISION = "66b0eeb53afeb6025ffbbd37734b08e5bce197ed"
UPSTREAM = f"https://raw.githubusercontent.com/material-components/material-components-android/{REVISION}"
GOOGLE = "https://dl.google.com/dl/android/maven2"
SHAPE_PATH = "lib/java/com/google/android/material/shape/MaterialShapes.java"
DELEGATE_PATH = "lib/java/com/google/android/material/loadingindicator"
SOURCES = {
    "MaterialShapes.java": (f"{UPSTREAM}/{SHAPE_PATH}",
        "0e4510f198043e24183532029061af8048978feec7d7c84213a289ad55ef7aaf"),
    "LoadingIndicatorDrawingDelegate.java": (
        f"{UPSTREAM}/{DELEGATE_PATH}/LoadingIndicatorDrawingDelegate.java",
        "90248722df1026eddce98075212633b8027684db2ab5612fee07d7324ea2d234"),
    "LoadingIndicatorAnimatorDelegate.java": (
        f"{UPSTREAM}/{DELEGATE_PATH}/LoadingIndicatorAnimatorDelegate.java",
        "aa495c027eadfd744394ab97a6108f8468603861168fa35140edc2292f569b24"),
    "graphics-android.aar": (
        f"{GOOGLE}/androidx/graphics/graphics-shapes-android/1.0.1/graphics-shapes-android-1.0.1.aar",
        "7171269a4122feabb071768df46d10b362e47ac75fd0aa8dbcafa1f44f61b40c"),
    "collection.jar": (
        f"{GOOGLE}/androidx/collection/collection-jvm/1.4.2/collection-jvm-1.4.2.jar",
        "984ce9bd780055eafb8a105aca3f514686bf7b1b6272ec7c645a98ce40fc7db4"),
    "kotlin.jar": (
        "https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/"
        "kotlin-stdlib/1.9.24/kotlin-stdlib-1.9.24.jar",
        "858b902696da9cf585ab9d98ffc1c2712269828354dfe9107e3711b084a36468"),
    "LICENSE": (f"{UPSTREAM}/LICENSE",
        "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"),
}
NAMES = ["soft-burst", "cookie-9", "pentagon", "pill", "sunny", "cookie-4", "oval"]

# Only affine coordinates execute in these JVM shims. Path/drawable classes are
# signatures for unused upstream drawable helpers; rendering happens in SVG.
SHIMS = {
    "android/graphics/PointF.java": """package android.graphics;
public class PointF {
  public float x,y;
  public PointF(float x,float y) { this.x=x; this.y=y; }
  public void offset(float x,float y) { this.x+=x; this.y+=y; }
}""",
    "android/graphics/RectF.java": """package android.graphics;
public class RectF {
  public float left,top,right,bottom;
  public RectF(float l,float t,float r,float b) { left=l; top=t; right=r; bottom=b; }
  public float width() { return right-left; }
  public float height() { return bottom-top; }
  public float centerX() { return (left+right)/2; }
  public float centerY() { return (top+bottom)/2; }
}""",
    "android/graphics/Path.java": "package android.graphics; public class Path {}",
    "android/graphics/drawable/shapes/PathShape.java": """package android.graphics.drawable.shapes;
public class PathShape { public PathShape(android.graphics.Path p, float w, float h) {} }""",
    "android/graphics/drawable/ShapeDrawable.java": """package android.graphics.drawable;
public class ShapeDrawable {
  public ShapeDrawable(android.graphics.drawable.shapes.PathShape p) {}
}""",
    "androidx/annotation/NonNull.java": "package androidx.annotation; public @interface NonNull {}",
    "androidx/annotation/RestrictTo.java": """package androidx.annotation;
public @interface RestrictTo { Scope[] value(); public enum Scope { LIBRARY_GROUP } }""",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate(cache: Path, check: bool) -> None:
    inputs = {}
    for name, (url, expected) in SOURCES.items():
        saved = cache / name
        if saved.exists():
            data = saved.read_bytes()
        else:
            with urlopen(url, timeout=30) as response:
                data = response.read(4_000_001)
            if len(data) > 4_000_000:
                raise ValueError("Source exceeds maintenance download bound")
            saved.write_bytes(data)
        if digest(data) != expected:
            raise ValueError(f"Upstream source hash changed: {name}")
        inputs[name] = data
    with tempfile.TemporaryDirectory(prefix="klaude-material-export-") as temporary:
        base = Path(temporary)
        for name, text in SHIMS.items():
            path = base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for path in (ROOT / "scripts/material_loading_export").glob("*.java"):
            (base / path.name).write_bytes(path.read_bytes())
        (base / "MaterialShapes.java").write_bytes(inputs["MaterialShapes.java"])
        graphics = zipfile.ZipFile(io.BytesIO(inputs["graphics-android.aar"]))
        (base / "graphics.jar").write_bytes(graphics.read("classes.jar"))
        classpath = ":".join(map(str, [base / "graphics.jar", cache / "collection.jar",
                                      cache / "kotlin.jar"]))
        subprocess.run(["javac", "-cp", classpath, "-d", str(base),
                        *map(str, sorted(base.rglob("*.java")))], check=True)
        result = subprocess.run(["java", "-cp", f"{base}:{classpath}", "Export"],
                                capture_output=True, text=True, check=True)
        morphs = json.loads(result.stdout)
    assert len(morphs) == 7
    for morph in morphs:
        assert len(morph["start"]) == len(morph["end"])
        assert len(morph["start"]) % 6 == 2
    data = {"names": NAMES, "morphs": morphs}
    script = (
        "/* Generated from Google Material / AndroidX; Apache-2.0.\n"
        " * Copyright 2024 The Android Open Source Project.\n"
        " * See material-loading-LICENSE.txt, material-loading-NOTICE.txt.\n"
        " * Regenerate: python3 scripts/vendor_webui_loading.py */\n"
        '"use strict";\nwindow.MaterialLoadingGeometry = Object.freeze('
        + json.dumps(data, separators=(",", ":")) + ");\n"
    ).encode()
    outputs = {
        "material-loading-shapes.js": script,
        "material-loading-LICENSE.txt": inputs["LICENSE"],
        "material-loading-NOTICE.txt": (
            "Google Material loading indicator geometry and motion\n"
            "Copyright 2024 The Android Open Source Project. Apache-2.0.\n"
            f"Material Components for Android revision: {REVISION}\n"
            "AndroidX graphics-shapes 1.0.1 performs the original curve matching.\n"
            "Generated cubic data and SVG adaptation: Klaude contributors, 2026.\n"
            "The Android source is unmodified during export. Android affine shims\n"
            "replace platform calls during maintenance only; no Android code runs\n"
            "in the browser. See scripts/vendor_webui_loading.py for provenance.\n"
        ).encode(),
    }
    manifest = {"material_revision": REVISION, "graphics_shapes_version": "1.0.1",
                "sources": {name: {"url": url, "sha256": sha}
                            for name, (url, sha) in SOURCES.items()},
                "assets": {name: digest(value) for name, value in outputs.items()}}
    outputs["material-loading-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    for name, content in outputs.items():
        path = DEST / name
        if check:
            assert path.read_bytes() == content, f"Regenerate {name}"
        else:
            path.write_bytes(content)
    print(f"{'Verified' if check else 'Exported'} seven official matched cubic morphs")
    bundle(check)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="klaude-material-sources-") as temporary:
        cache = args.cache or Path(temporary)
        cache.mkdir(parents=True, exist_ok=True)
        generate(cache, args.check)


if __name__ == "__main__":
    main()
