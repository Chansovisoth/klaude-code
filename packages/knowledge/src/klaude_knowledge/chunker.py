"""Heading-aware chunking for markdown/docs.

Strategy: split on headings, carry the heading path into every chunk
(so 'Configuring next.config.js' context travels with the text), pack
sections into ~CHUNK_CHARS chunks, and never split a fenced code block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CHUNK_CHARS = 2400  # ~600 tokens
MIN_CHARS = 200

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


@dataclass
class Chunk:
    text: str
    section: str


def _blocks(md: str) -> list[tuple[str, str]]:
    """Yield (heading_path, block_text) preserving code fences."""
    lines = md.splitlines()
    path: list[str] = []
    buf: list[str] = []
    in_fence = False
    out: list[tuple[str, str]] = []

    def flush():
        if buf and "".join(buf).strip():
            out.append((" > ".join(path), "\n".join(buf).strip()))
        buf.clear()

    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            continue
        m = None if in_fence else _HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = path[: level - 1]
            path.append(m.group(2).strip())
        else:
            buf.append(line)
    flush()
    return out


def chunk_markdown(md: str, title: str = "") -> list[Chunk]:
    chunks: list[Chunk] = []
    cur_text: list[str] = []
    cur_section = title

    def emit():
        text = "\n\n".join(cur_text).strip()
        if len(text) >= MIN_CHARS:
            header = f"[{cur_section}]\n" if cur_section else ""
            chunks.append(Chunk(text=header + text, section=cur_section))
        cur_text.clear()

    for section, block in _blocks(md):
        section = section or title
        # a very long single block (e.g. big code sample) becomes its own chunk
        if len(block) > CHUNK_CHARS:
            emit()
            cur_section = section
            cur_text.append(block)
            emit()
            continue
        if cur_text and (
            section != cur_section or sum(map(len, cur_text)) + len(block) > CHUNK_CHARS
        ):
            emit()
        cur_section = section
        cur_text.append(block)
    emit()

    # fallback: unstructured text with no headings and short blocks
    if not chunks and md.strip():
        text = md.strip()
        for i in range(0, len(text), CHUNK_CHARS):
            piece = text[i : i + CHUNK_CHARS]
            if len(piece) >= MIN_CHARS or i == 0:
                chunks.append(Chunk(text=piece, section=title))
    return chunks
