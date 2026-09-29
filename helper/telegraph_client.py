from __future__ import annotations

import asyncio
import json
import logging
import re
from html.entities import name2codepoint
from html.parser import HTMLParser
from secrets import token_hex

import aiohttp

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegra.ph"
PAGE_ROOT = "https://telegra.ph"

_RE_WHITESPACE = re.compile(r"(\s+)")
_ALLOWED_TAGS = {
    "a", "aside", "b", "blockquote", "br", "code", "em", "figcaption",
    "figure", "h3", "h4", "hr", "i", "iframe", "img", "li", "ol",
    "p", "pre", "s", "strong", "u", "ul", "video",
}
_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "keygen", "link", "menuitem", "meta", "param", "source", "track", "wbr",
}
_BLOCK_ELEMENTS = {
    "address", "article", "aside", "blockquote", "canvas", "dd", "div", "dl",
    "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "hgroup", "hr", "li", "main", "nav",
    "noscript", "ol", "p", "pre", "section", "table", "tfoot", "ul", "video",
}


class TelegraphError(RuntimeError):
    pass


class _HTMLToNodes(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.nodes = []
        self._current = self.nodes
        self._parents = []
        self._last_text = None
        self._tags = []

    def _add_text(self, value: str) -> None:
        if not value:
            return
        if "pre" not in self._tags:
            value = _RE_WHITESPACE.sub(" ", value)
            if self._last_text is None or self._last_text.endswith(" "):
                value = value.lstrip(" ")
            if not value:
                self._last_text = None
                return
            self._last_text = value
        if self._current and isinstance(self._current[-1], str):
            self._current[-1] += value
        else:
            self._current.append(value)

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED_TAGS:
            raise TelegraphError(f"Unsupported Telegraph HTML tag: <{tag}>")
        if tag in _BLOCK_ELEMENTS:
            self._last_text = None
        node = {"tag": tag}
        self._tags.append(tag)
        self._current.append(node)
        if attrs:
            # Telegraph only accepts href/src attrs on supported elements.
            clean_attrs = {
                key: value
                for key, value in attrs
                if key in {"href", "src"} and value is not None
            }
            if clean_attrs:
                node["attrs"] = clean_attrs
        if tag not in _VOID_ELEMENTS:
            self._parents.append(self._current)
            self._current = node["children"] = []

    def handle_endtag(self, tag):
        if tag in _VOID_ELEMENTS:
            return
        if not self._parents:
            raise TelegraphError(f"Unexpected closing tag: </{tag}>")
        self._current = self._parents.pop()
        node = self._current[-1]
        if not isinstance(node, dict) or node.get("tag") != tag:
            raise TelegraphError(f"Mismatched closing tag: </{tag}>")
        if self._tags:
            self._tags.pop()
        if not node.get("children"):
            node.pop("children", None)

    def handle_data(self, data):
        self._add_text(data)

    def handle_entityref(self, name):
        codepoint = name2codepoint.get(name)
        self._add_text(chr(codepoint) if codepoint else f"&{name};")

    def handle_charref(self, name):
        try:
            value = int(name[1:], 16) if name.lower().startswith("x") else int(name)
            self._add_text(chr(value))
        except ValueError:
            self._add_text(f"&#{name};")

    def get_nodes(self):
        if self._parents:
            raise TelegraphError("Unclosed Telegraph HTML tag")
        return self.nodes


def html_to_nodes(source: str):
    parser = _HTMLToNodes()
    parser.feed(source)
    parser.close()
    return parser.get_nodes()


class TelegraphClient:
    """Small async client using the canonical Telegraph API.

    Important: pages are created at api.telegra.ph and the URL returned by the
    API is used verbatim.  We never rewrite it to graph.org, because graph.org
    is not guaranteed to serve the same article path and can return 404.
    """

    def __init__(self, author_name: str = "MediaInfo X"):
        self.access_token: str | None = None
        self.author_name = author_name
        self._account_lock = asyncio.Lock()

    async def _post(self, method: str, data: dict) -> dict:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{API_ROOT}/{method}", data=data) as response:
                # Telegraph returns JSON even for API errors, but keep a useful
                # fallback message for network/proxy errors.
                raw = await response.text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise TelegraphError(
                        f"Telegraph returned HTTP {response.status} with invalid JSON"
                    ) from exc

        if payload.get("ok") is True:
            result = payload.get("result")
            if isinstance(result, dict):
                return result
            raise TelegraphError("Telegraph API returned an invalid result")

        error = str(payload.get("error") or "Telegraph API request failed")
        if error.startswith("FLOOD_WAIT_"):
            try:
                wait = int(error.rsplit("_", 1)[-1])
            except ValueError:
                wait = 1
            await asyncio.sleep(max(1, min(wait, 30)))
            return await self._post(method, data)
        raise TelegraphError(error)

    async def _ensure_account(self) -> None:
        if self.access_token:
            return
        async with self._account_lock:
            if self.access_token:
                return
            account = await self._post(
                "createAccount",
                {
                    "short_name": f"mi_{token_hex(4)}"[:32],
                    "author_name": self.author_name,
                },
            )
            token = str(account.get("access_token") or "").strip()
            if not token:
                raise TelegraphError("Telegraph account did not return an access token")
            self.access_token = token

    async def create_page(self, title: str, html_content: str) -> str:
        await self._ensure_account()
        nodes = html_to_nodes(html_content)
        if not nodes:
            raise TelegraphError("MediaInfo page content is empty")

        page = await self._post(
            "createPage",
            {
                "access_token": self.access_token,
                "title": (title or "MediaInfo")[:256],
                "author_name": self.author_name,
                "content": json.dumps(nodes, ensure_ascii=False, separators=(",", ":")),
                "return_content": "false",
            },
        )

        # This is the key fix: use the URL returned by Telegraph itself.
        url = str(page.get("url") or "").strip()
        if url:
            if url.startswith("http://"):
                url = "https://" + url[len("http://"):]
            return url

        path = str(page.get("path") or "").strip().lstrip("/")
        if path:
            return f"{PAGE_ROOT}/{path}"
        raise TelegraphError("Telegraph page was created without URL/path")


telegraph = TelegraphClient()
