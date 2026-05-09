#!/usr/bin/env python3
"""
Build multiple documentation artifacts from ../HELP_FA.md (stdlib only).

Usage (from repo root):
    python3 docs/build_docs.py

Outputs under docs/:
    help-fa.md       — copy of source for browsing inside docs/
    help-fa.html     — standalone RTL Persian HTML
    help-fa.txt      — plain text (tables flattened)
    help-fa-slides.html — Reveal.js CDN slideshow (one slide per ## section)
    help-fa.adoc     — AsciiDoctor-friendly outline + tables
"""
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = Path(__file__).resolve().parent
SOURCE = ROOT / "HELP_FA.md"


def inline_md(s: str) -> str:
    """Bold **x**, `code`, escape HTML."""
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def md_tables_and_rest_to_html(lines: list[str]) -> tuple[list[str], int]:
    """Parse one markdown table starting at lines[i]. Returns HTML rows and new index."""
    i = 0
    if i >= len(lines) or not lines[0].strip().startswith("|"):
        return [], 0
    rows_raw = []
    idx = 0
    while idx < len(lines) and lines[idx].strip().startswith("|"):
        rows_raw.append(lines[idx].strip())
        idx += 1
    if len(rows_raw) < 2:
        return [], idx
    def split_row(r: str) -> list[str]:
        inner = r.strip()[1:-1] if r.startswith("|") else r
        parts = [c.strip() for c in inner.split("|")]
        return parts

    header_cells = split_row(rows_raw[0])
    body_rows = []
    for r in rows_raw[2:]:  # skip separator row
        body_rows.append(split_row(r))

    out = ["<table>", "<thead><tr>"]
    for c in header_cells:
        out.append(f"<th>{inline_md(c)}</th>")
    out.append("</tr></thead><tbody>")
    for br in body_rows:
        out.append("<tr>")
        for j, c in enumerate(br):
            cell = c if j < len(br) else ""
            out.append(f"<td>{inline_md(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return out, idx


def markdown_help_fragment(md: str) -> str:
    """Body HTML only (no html/head wrapper)."""
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.strip() == "---":
            out.append("<hr>")
            i += 1
            continue

        if line.startswith("# "):
            out.append(f"<h1>{inline_md(line[2:].strip())}</h1>")
            i += 1
            continue
        if line.startswith("## "):
            out.append(f"<h2>{inline_md(line[3:].strip())}</h2>")
            i += 1
            continue
        if line.startswith("### "):
            out.append(f"<h3>{inline_md(line[4:].strip())}</h3>")
            i += 1
            continue

        if line.strip().startswith("|"):
            tbl_lines = []
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                tbl_lines.append(lines[j])
                j += 1
            html_tbl, consumed = md_tables_and_rest_to_html(tbl_lines)
            out.extend(html_tbl)
            i += consumed
            continue

        if line.strip().startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith("- "):
                item = lines[i].strip()[2:]
                out.append(f"<li>{inline_md(item)}</li>")
                i += 1
            out.append("</ul>")
            continue

        if line.strip().startswith("*"):
            out.append(f"<p><em>{inline_md(line.strip().lstrip('*').strip())}</em></p>")
            i += 1
            continue

        if re.match(r"^\d+\.\s", line.strip()):
            out.append("<ol>")
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                item = re.sub(r"^\d+\.\s*", "", lines[i].strip())
                out.append(f"<li>{inline_md(item)}</li>")
                i += 1
            out.append("</ol>")
            continue

        if line.strip() == "":
            i += 1
            continue

        # Paragraph (possibly multi-line until blank or structural)
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("#") and not lines[i].strip().startswith("|") and not lines[i].strip().startswith("- ") and not re.match(r"^\d+\.\s", lines[i].strip()) and lines[i].strip() != "---":
            para.append(lines[i])
            i += 1
        out.append("<p>" + inline_md(" ".join(para)) + "</p>")

    return "\n".join(out)


def markdown_help_to_html(md: str) -> str:
    inner = markdown_help_fragment(md)
    shell = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>راهنمای فارسی — Firmware Converter</title>
<style>
  :root {{ font-family: "Segoe UI", Tahoma, "DejaVu Sans", sans-serif; }}
  body {{ max-width: 52rem; margin: 2rem auto; padding: 0 1.25rem; line-height: 1.65;
          background: #0b1220; color: #e6eef8; }}
  h1 {{ font-size: 1.75rem; border-bottom: 1px solid #2a3f66; padding-bottom: 0.5rem; }}
  h2 {{ font-size: 1.25rem; margin-top: 2rem; color: #9bdcff; }}
  h3 {{ font-size: 1.05rem; margin-top: 1.25rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.92rem; }}
  th, td {{ border: 1px solid #2a3f66; padding: 0.45rem 0.6rem; text-align: right; }}
  th {{ background: #152544; }}
  code {{ background: #152544; padding: 0.1em 0.35em; border-radius: 4px; font-size: 0.88em; }}
  hr {{ border: none; border-top: 1px solid #2a3f66; margin: 2rem 0; }}
  ul, ol {{ padding-right: 1.5rem; }}
</style>
</head>
<body>
{body}
<p style="margin-top:3rem;opacity:.7;font-size:.9rem;">ساخته‌شده با <code>docs/build_docs.py</code></p>
</body>
</html>
"""
    return shell.format(body=inner)


def split_slides(md: str) -> list[tuple[str, str]]:
    """Return list of (title, body_md) for each ## section; preamble before first ## is slide 0."""
    lines = md.splitlines()
    slides: list[tuple[str, str]] = []
    preamble: list[str] = []
    current_title = ""
    current_body: list[str] = []

    def flush_preamble():
        nonlocal preamble
        if preamble:
            text = "\n".join(preamble).strip()
            if text:
                slides.append(("مقدمه", text))
            preamble = []

    for line in lines:
        if line.startswith("## "):
            flush_preamble()
            if current_title or current_body:
                slides.append((current_title, "\n".join(current_body).strip()))
            current_title = line[3:].strip()
            current_body = []
            continue
        if not slides and not current_title:
            preamble.append(line)
        else:
            current_body.append(line)

    flush_preamble()
    if current_title or current_body:
        slides.append((current_title, "\n".join(current_body).strip()))
    return slides


def reveal_html(md: str) -> str:
    slides = split_slides(md)
    sections = []
    for title, body in slides:
        inner = markdown_help_fragment(body) if body else ""
        sections.append(
            f'<section dir="rtl"><h2>{html.escape(title)}</h2>{inner}</section>'
        )

    return f"""<!DOCTYPE html>
<html lang="fa">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>راهنما — اسلاید</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.0.4/dist/reveal.css"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5.0.4/dist/theme/night.css"/>
<style>
.reveal .slides section {{ text-align: right; font-family: "Segoe UI", Tahoma, sans-serif; }}
.reveal h1, .reveal h2, .reveal h3 {{ text-transform: none; }}
.reveal table {{ font-size: 0.45em; }}
.reveal code {{ background: rgba(255,255,255,0.1); }}
</style>
</head>
<body>
<div class="reveal"><div class="slides">
{"".join(sections)}
</div></div>
<script src="https://cdn.jsdelivr.net/npm/reveal.js@5.0.4/dist/reveal.js"></script>
<script>Reveal.initialize({{ hash: true, slideNumber: true, rtl: true }});</script>
</body>
</html>
"""


def to_plain_text(md: str) -> str:
    t = md
    t = re.sub(r"^#+\s+", "", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"^---\s*$", "\n" + "=" * 50 + "\n", t, flags=re.M)
    lines = t.splitlines()
    out: list[str] = []
    for line in lines:
        if line.strip().startswith("|"):
            out.append(line.replace("|", " ").strip())
        else:
            out.append(line)
    return "\n".join(out).strip() + "\n"


def to_asciidoc(md: str) -> str:
    """Rough conversion for AsciiDoctor / PDF pipelines (review tables)."""
    lines = md.splitlines()
    out: list[str] = [
        "= راهنمای فارسی — Firmware Converter",
        "",
        ":lang: fa",
        ":toc: left",
        ":sectanchors:",
        "",
    ]
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# "):
            # Title already in document header block
            pass
        elif line.startswith("## "):
            out.append(f"== {line[3:].strip()}")
            out.append("")
        elif line.startswith("### "):
            out.append(f"=== {line[4:].strip()}")
            out.append("")
        elif line.strip() == "---":
            out.append("")
            out.append("'''")
            out.append("")
        elif line.strip().startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            i -= 1
            rows = []
            for r in tbl:
                cells = [c.strip() for c in r.strip().strip("|").split("|")]
                rows.append(cells)
            if len(rows) >= 2:
                out.append("|===")
                out.append("| " + " | ".join(rows[0]))
                out.append("")
                for br in rows[2:]:
                    out.append("| " + " | ".join(br))
                out.append("|===")
                out.append("")
        elif line.strip().startswith("- "):
            out.append(f"* {line.strip()[2:]}")
        elif re.match(r"^\d+\.\s", line.strip()):
            out.append(re.sub(r"^(\d+)\.\s", r". ", line.strip(), count=1))
        elif line.strip():
            out.append(line)
            out.append("")
        i += 1
    return "\n".join(out)


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Missing source: {SOURCE}")
    text = SOURCE.read_text(encoding="utf-8")

    shutil.copy2(SOURCE, DOCS / "help-fa.md")
    (DOCS / "help-fa.html").write_text(markdown_help_to_html(text), encoding="utf-8")
    (DOCS / "help-fa.txt").write_text(to_plain_text(text), encoding="utf-8")
    (DOCS / "help-fa-slides.html").write_text(reveal_html(text), encoding="utf-8")
    (DOCS / "help-fa.adoc").write_text(to_asciidoc(text), encoding="utf-8")
    print("Wrote:", DOCS / "help-fa.md")
    print("Wrote:", DOCS / "help-fa.html")
    print("Wrote:", DOCS / "help-fa.txt")
    print("Wrote:", DOCS / "help-fa-slides.html")
    print("Wrote:", DOCS / "help-fa.adoc")


if __name__ == "__main__":
    main()
