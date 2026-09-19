"""A small, deliberately limited Markdown renderer for hypothesis card bodies.

The repo has no Markdown dependency and this module may not add one (Step 18
ground rule: no new runtime dependency -- see plan section 6 and T4's brief).
Pulling in a general-purpose Markdown library would also be the wrong shape
for this job: the 19 hypothesis/data cards under
``reports/research/hypotheses/`` are hand-written by one person (or an agent
following their template) and only ever use a handful of constructs --
headings, **bold**, `inline code`, fenced code blocks, links, unordered
lists, and GitHub-style tables. This renders exactly that set and nothing
more; anything else (nested emphasis, ordered lists, blockquotes, images,
setext headings, ...) falls through as an escaped paragraph rather than being
silently mis-rendered.

Security shape, in order, every time this runs:

1. ``secret_scrub`` first, on the raw Markdown text, so a card that quotes a
   leaked token in a status line (it has happened -- cron/log tails get
   pasted into lesson writeups) never reaches HTML at all.
2. Every literal run of text -- heading content between tokens, paragraph
   text, table cell text, code contents, link text -- goes through
   ``html.escape`` *before* it is wrapped in any tag this module generates.
   The only HTML tags in the output are ones this module writes itself
   (``<h1>``..``<h6>``, ``<p>``, ``<strong>``, ``<code>``, ``<pre>``, ``<ul>``,
   ``<li>``, ``<table>``/``<thead>``/``<tbody>``/``<tr>``/``<th>``/``<td>``,
   and ``<a>`` for links with a scheme allow-list). A card body can never
   inject a tag of its own -- ``<script>...`` in card prose becomes the text
   ``&lt;script&gt;...``, never a live element. ``tests/test_cockpit_hypotheses.py``
   asserts this directly.

Callers pass the parsed card's ``body_markdown`` (see
``open_composer.cockpit.data.hypotheses.Card``) to :func:`render_markdown` and
mark the result safe in the Jinja2 template (``{{ card_html | safe }}``) --
the escaping already happened here, so the template must not escape it again.
"""

from __future__ import annotations

import html
import re

from open_composer.cockpit.security import secret_scrub

# --------------------------------------------------------------------------
# Block-level patterns
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^```\s*([A-Za-z0-9_+-]*)\s*$")
_HEADING_LINE_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
# A GFM table separator row: one or more `---`/`:--`/`--:`/`:-:` cells joined
# by `|`. Requires at least one `|` (via the `(...)+` group below) so a plain
# `---` horizontal-rule-shaped line is never mistaken for a table separator.
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")
_LANG_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# --------------------------------------------------------------------------
# Inline-level pattern: one combined lexer so literal text between tokens is
# escaped exactly once, in source order. Group numbers (not just names) are
# used below because a mixed named/unnamed pattern still numbers every group
# left to right: 1=code(whole) 2=code(inner) 3=link(whole) 4=link(text)
# 5=link(url) 6=bold(whole) 7=bold(inner).
# --------------------------------------------------------------------------

_INLINE_TOKEN_RE = re.compile(
    r"(?P<code>`([^`]+)`)"
    r"|(?P<link>\[([^\]]*)\]\(([^()\s]+)\))"
    r"|(?P<bold>\*\*([^*]+)\*\*)"
)

# Only these URL shapes render as a clickable link; anything else (most
# notably `javascript:`) renders as plain escaped text instead of a link.
_SAFE_URL_RE = re.compile(r"^(https?://|/|#)", re.IGNORECASE)


def _render_inline(text: str) -> str:
    """Render inline spans (code/link/bold) in one left-to-right pass.

    Every character of ``text`` ends up in the output either inside an
    ``html.escape``d literal run or inside an ``html.escape``d token payload
    -- there is no path from input text to output that skips escaping.
    """
    pieces: list[str] = []
    pos = 0
    for match in _INLINE_TOKEN_RE.finditer(text):
        if match.start() > pos:
            pieces.append(html.escape(text[pos : match.start()]))
        if match.group("code") is not None:
            pieces.append(f"<code>{html.escape(match.group(2))}</code>")
        elif match.group("link") is not None:
            link_text = html.escape(match.group(4))
            url = match.group(5)
            if _SAFE_URL_RE.match(url):
                safe_url = html.escape(url, quote=True)
                pieces.append(f'<a href="{safe_url}" rel="noopener noreferrer">{link_text}</a>')
            else:
                # Unrecognized/unsafe scheme: keep the source text visible but
                # inert, never a clickable (and possibly script-running) link.
                pieces.append(html.escape(match.group(0)))
        elif match.group("bold") is not None:
            pieces.append(f"<strong>{html.escape(match.group(7))}</strong>")
        pos = match.end()
    if pos < len(text):
        pieces.append(html.escape(text[pos:]))
    return "".join(pieces)


def _split_table_row(line: str) -> list[str]:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    return [cell.strip() for cell in trimmed.split("|")]


def _render_table(header_cells: list[str], body_rows: list[list[str]]) -> str:
    """Render a GitHub-style table using the cockpit's own table convention.

    ``class="responsive-table"`` plus a ``data-label`` on every ``<td>`` is
    the pattern documented at the top of
    ``open_composer/cockpit/static/css/cockpit.css`` -- it is what turns a
    wide table into stacked cards under the phone breakpoint. Every table
    this renderer produces uses it so a card's table reads the same way the
    health screen's tables already do.
    """
    thead = "<tr>" + "".join(f"<th>{_render_inline(cell)}</th>" for cell in header_cells) + "</tr>"
    body_parts: list[str] = []
    for row in body_rows:
        cells_html: list[str] = []
        for idx, cell in enumerate(row):
            label = header_cells[idx] if idx < len(header_cells) else ""
            cells_html.append(f'<td data-label="{html.escape(label)}">{_render_inline(cell)}</td>')
        body_parts.append("<tr>" + "".join(cells_html) + "</tr>")
    tbody = "".join(body_parts)
    return f'<table class="responsive-table"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'


def render_markdown(text: str) -> str:
    """Render ``text`` (a hypothesis card body) to a small, safe HTML subset.

    ``text`` is scrubbed for secret-shaped substrings first (see the module
    docstring), then walked line by line as a small block-level state
    machine. Anything not recognized as a fenced code block, heading, table,
    or unordered list is treated as paragraph text.
    """
    scrubbed = secret_scrub(text or "")
    lines = scrubbed.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n = len(lines)
    out: list[str] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_buffer:
            return
        joined = " ".join(line.strip() for line in paragraph_buffer if line.strip())
        paragraph_buffer.clear()
        if joined:
            out.append(f"<p>{_render_inline(joined)}</p>")

    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()

        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            flush_paragraph()
            lang = fence_match.group(1) or ""
            code_lines: list[str] = []
            i += 1
            while i < n and not _FENCE_RE.match(lines[i].strip()):
                code_lines.append(lines[i])
                i += 1
            i += 1  # consume the closing fence, if any (tolerate an unterminated block at EOF)
            code_text = html.escape("\n".join(code_lines))
            lang_class = (
                f' class="language-{html.escape(lang)}"' if _LANG_NAME_RE.match(lang) else ""
            )
            out.append(f"<pre><code{lang_class}>{code_text}</code></pre>")
            continue

        heading_match = _HEADING_LINE_RE.match(line)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            out.append(f"<h{level}>{_render_inline(heading_match.group(2).strip())}</h{level}>")
            i += 1
            continue

        if "|" in line and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1].strip()):
            flush_paragraph()
            header_cells = _split_table_row(line)
            i += 2
            body_rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                body_rows.append(_split_table_row(lines[i]))
                i += 1
            out.append(_render_table(header_cells, body_rows))
            continue

        if _UL_ITEM_RE.match(line):
            flush_paragraph()
            items: list[str] = []
            while i < n and _UL_ITEM_RE.match(lines[i]):
                items.append(_render_inline(_UL_ITEM_RE.match(lines[i]).group(1).strip()))
                i += 1
            out.append("<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>")
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        paragraph_buffer.append(line)
        i += 1

    flush_paragraph()
    return "\n".join(out)
