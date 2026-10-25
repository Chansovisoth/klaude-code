"""Short lived owner-scoped, inert previews of assistant HTML and SVG."""

from __future__ import annotations

import html
import re
import secrets
import threading
import time
from html.parser import HTMLParser

MAX_SOURCE = 128_000
PREVIEW_CSP = (
    "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
    "img-src data:; font-src 'none'; connect-src 'none'; form-action 'none'; "
    "base-uri 'none'; object-src 'none'; frame-src 'none'; "
    "frame-ancestors 'self'; sandbox"
)
TAGS = frozenset(
    (
        "html body main section article aside header footer nav div span p br hr "
        "h1 h2 h3 h4 h5 h6 strong em b i u s small sub sup pre code blockquote "
        "ul ol li dl dt dd table caption colgroup col thead tbody tfoot tr th td "
        "figure figcaption img picture a button label input textarea select option "
        "details summary style svg g defs symbol use image path rect circle ellipse line "
        "polyline polygon text tspan textpath title desc clippath mask pattern "
        "lineargradient radialgradient stop filter feblend fecolormatrix "
        "fecomponenttransfer fecomposite feconvolvematrix fediffuselighting "
        "fedisplacementmap fedistantlight fedropshadow feflood fefunca fefuncb "
        "fefuncg fefuncr fegaussianblur feimage femerge femergenode femorphology "
        "feoffset fepointlight fespecularlighting fespotlight fetile feturbulence"
    ).split()
)
VOID = frozenset("br hr img input col".split())
RASTER_DATA = re.compile(r"data:image/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+\Z")


class _InertHTML(HTMLParser):
    """Serialize only passive HTML/SVG, escaping all text and attribute values.

    This also removes refresh/navigation and resource URLs. The response CSP and
    sandbox remain independent barriers, including for malformed browser markup.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.style = False
        self.tokens = 0
        self.suppressed: str | None = None
        self.suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tokens += 1
        if self.tokens > 10_000:
            raise ValueError("Preview is too complex")
        if self.suppressed is not None:
            if tag == self.suppressed:
                self.suppressed_depth += 1
            return
        if tag in {"script", "iframe", "object", "template", "noscript"}:
            self.suppressed = tag
            self.suppressed_depth = 1
            return
        if tag not in TAGS or tag in {"html", "body"}:
            return
        self.style = tag == "style"
        clean = []
        for key, raw in attrs:
            value = raw or ""
            if (
                not re.fullmatch(r"[a-z][a-z0-9:_-]*", key)
                or key.startswith("on")
                or key
                in {
                    "srcdoc",
                    "srcset",
                    "action",
                    "formaction",
                    "target",
                    "download",
                    "autofocus",
                    "nonce",
                    "is",
                    "popover",
                    "form",
                    "ping",
                }
            ):
                continue
            if key in {"href", "xlink:href", "src", "poster", "background"}:
                if not (
                    value.startswith("#")
                    or tag in {"img", "image", "feimage"}
                    and RASTER_DATA.fullmatch(value)
                ):
                    continue
            clean.append(f' {key}="{html.escape(value, quote=True)}"')
        self.parts.append(f"<{tag}{''.join(clean)}>")

    def handle_endtag(self, tag: str) -> None:
        if self.suppressed is not None:
            if tag == self.suppressed:
                self.suppressed_depth -= 1
                if not self.suppressed_depth:
                    self.suppressed = None
            return
        if tag in TAGS and tag not in VOID and tag not in {"html", "body"}:
            self.parts.append(f"</{tag}>")
        if tag == "style":
            self.style = False

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.suppressed is not None:
            return
        self.parts.append(data if self.style else html.escape(data))


def preview_document(source: str) -> bytes:
    if not isinstance(source, str) or len(source) > MAX_SOURCE:
        raise ValueError("Preview exceeds display bound")
    parser = _InertHTML()
    parser.feed(source)
    parser.close()
    return (
        "<!doctype html><html><head><meta charset=utf-8>"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<style>body{margin:16px;font-family:system-ui,sans-serif;overflow-wrap:anywhere}"
        "svg,img{max-width:100%;height:auto}svg{display:block;margin:auto}"
        "pre{overflow:auto}table{max-width:100%}</style></head><body>"
        + "".join(parser.parts)
        + "</body></html>"
    ).encode()


class ChatPreviews:
    """Keep at most eight bounded documents in memory for five minutes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, tuple[str, float, bytes]] = {}

    def create(self, owner: str, source: str) -> str:
        document = preview_document(source)
        with self._lock:
            now = time.monotonic()
            self._items = {key: item for key, item in self._items.items() if item[1] > now}
            while len(self._items) >= 8:
                self._items.pop(next(iter(self._items)))
            identity = secrets.token_hex(16)
            self._items[identity] = (owner, now + 300, document)
            return identity

    def read(self, owner: str, identity: str) -> bytes:
        with self._lock:
            item = self._items.get(identity)
            if item is None or item[0] != owner or item[1] <= time.monotonic():
                raise FileNotFoundError("Preview expired; open it again")
            return item[2]

    def revoke(self, owner: str | None = None) -> None:
        with self._lock:
            self._items = {
                key: item
                for key, item in self._items.items()
                if owner is not None and item[0] != owner
            }
