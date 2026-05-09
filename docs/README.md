# Documentation variants (`docs/`)

The Persian manual **`HELP_FA.md`** (repository root) is written for **end users who only use the GUI** — no code paths, no Git, no JSON field names.

Developers edit `HELP_FA.md`, then refresh derived files here.

## Regenerate

From the repo root:

```bash
python3 docs/build_docs.py
```

Requires **Python 3** stdlib only (no pip packages).

## Which file to ship or open?

| File | Best for |
|------|-----------|
| **help-fa.html** | **Best default for GUI users:** open in any browser; RTL + readable styling; no build step for them. |
| **help-fa.md** | Same text as root after rebuild; good if users have an editor that previews Markdown. |
| **help-fa.txt** | Plain text: email, `notepad`, or embed next to a portable `.exe`. |
| **help-fa-slides.html** | Short training walkthrough: arrow keys (**Reveal.js** from CDN — needs internet for first load). |
| **help-fa.adoc** | Pipeline to PDF via **AsciiDoctor** (`asciidoctor-pdf`) if you want a printable manual. |

## PDF / DOCX (optional)

Not generated automatically here:

- **HTML → PDF:** open `help-fa.html` in the browser and Print → PDF.
- **AsciiDoc → PDF:** `asciidoctor-pdf docs/help-fa.adoc`
- **Markdown → PDF:** **Pandoc** (`pandoc HELP_FA.md -o manual.pdf`) if installed.

After editing **`HELP_FA.md`**, run `build_docs.py` so everything under `docs/` stays aligned.
