---
name: parts-catalog
description: >-
  Build an interactive, clickable web parts catalog from a manufacturer's spare-
  parts book(s) and a price list — section drawings paired with their position
  lists, full-text search, a required-quantity order cart, prices, Excel/print
  export, an embedded service manual, and catalog⇄manual cross-references. Use
  whenever the user wants to turn one or more parts books / каталог запчастей /
  parts manuals into a browsable clickable catalog, extract the parts tables or
  catalog numbers, pull a price list into it, add another equipment book
  (engine, drive system, …) as a new chapter, or fix/extend a catalog built this
  way. Handles PDF (often split-zip, deflate64), binary Word .doc, .doc→PDF
  exports, Cummins-style Russian option PDFs, and .xlsx price lists; bilingual
  Chinese/English NHL/GE mining-equipment books and Russian Cummins books.
---

# Interactive parts catalog

Turn OEM spare-parts books (illustrations + parts tables) and a price list into
a static, dependency-free web catalog: each drawing shown with exactly its
position list, search across every part number, an order cart with required
quantities and prices, Excel export, and a browsable service manual linked to
the catalog. Opens by double-clicking `catalog/index.html` — no server, no build.

This skill is proven on the NHL **NTE240** mining truck: a 452-page bilingual
PDF part book, a `.doc`→PDF inverter/drive-system book, a **119-PDF Cummins
QSK60** engine catalog, a GE `.xlsx` price list, and a `.docx` operator manual —
combined into one catalog of **12 chapters / ~249 sections / ~6600 rows** with
**0 missing part numbers**. The bundled scripts are the actual working ones.

## The one rule that matters

**Every part number physically printed in the source must appear in the
catalog.** Table parsers drop rows silently and a visual spot-check never
catches it — the user *will* find the missing number on their drawing. After any
parser change, verify completeness (token cross-check → **0 missing**), every
time. This is not optional; most of the bundled code exists to hit that bar.

## Pipeline

1. **Get sources readable.**
   - Split-zip PDF (`*.zip.001..00N`): concatenate parts, then unzip. If the
     archive is **deflate64** (method 9), Python's `zipfile` cannot expand it —
     shell out to the system `unzip`.
   - Binary `.doc`: read the OLE2 streams directly (`olefile`); do **not** rely
     on LibreOffice — it fails to load these files here.
   - `.doc`→PDF export: parse the text layer (linear, one field per line).
   - `.xlsx` price list: `openpyxl`. `.docx` manual: `zipfile` + XML.
   - Deps: `pip install pymupdf olefile openpyxl playwright`.

2. **Understand the structure before parsing.** Dump the text of the first ~15
   pages and inspect **word coordinates** (`page.get_text("words")`) on one
   dense table page. Identify: the section-code pattern, the table header
   tokens, the column x-positions, and how drawing pages and table pages
   alternate. Do this per book — every book violates a different assumption.

3. **Extract** with the bundled scripts, adapting anchors/regex to the book.
   They emit/merge the `figures`-based `window.CATALOG` schema and render
   drawings. Pick the parser that matches the source shape:
   - `scripts/extract_pdf_catalog.py` — **coordinate** PDF part book (value-based
     table parser, per-page/per-side column detection, figure grouping).
   - `scripts/extract_inverter_catalog.py` — **linear-text** `.doc`→PDF book
     (row-signature detection, merges as a new chapter).
   - `scripts/extract_qsk60_catalog.py` — **Russian Cummins option PDFs** (one
     option per file; columns by x-position; new chapter).
   - `scripts/extract_prices.py` — `.xlsx` price list → `window.PRICES` + a
     unique-numbers CSV/xlsx carrying every attribute.
   - `scripts/extract_manual.py` — `.docx` operator manual → browsable HTML.
   - `scripts/extract_service.py` — a **repair/service book** (folder of per-
     section `.doc`/`.docx`, filenames carry the section code) → one repair page
     **per catalog section**, linked both ways. Reads binary `.doc` directly
     (olefile piece table + image scan).
   - **Read the matching file in `references/` first** — each lists the real
     failure modes (validated bugs) for that source shape.

4. **Verify — every time.** `scripts/verify_completeness.py parts.js source.pdf`
   must report **0 missing part numbers** (document-wide, not per-header-page).
   For non-PDF books, each extractor prints its own `printed vs captured`
   completeness line — it must be `missing: 0`.

5. **Build / update the web app.** Mirror `catalog/` — see
   `references/webapp.md` for the schema, the figure/carousel/quantity/cart/
   export UI, cross-references, and the rendering bugs to avoid. Theme via CSS
   variables so a client brand (colors + logo from a supplied template) swaps
   cleanly.

6. **Smoke-test in the real browser** (Chromium + Playwright preinstalled at
   `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`) before declaring done:
   first row is 001 (or the true first position) everywhere, positions ascending
   within each figure, drawings load (`naturalWidth>0`), cart totals update,
   exports download and re-open (round-trip through openpyxl), cross-references
   navigate both ways, **zero console errors**. Then commit and push.

## Adding another equipment book as a new chapter

The catalog is multi-book. Each extractor after the first **merges** into the
`parts.js` the previous one produced (load JSON, drop its own chapter for
idempotency, append `{chapters:[…], sections:[…]}`, rewrite). Assign a fresh
chapter code (`600`, `700`, …) and synthetic section codes (`600-0010` …) when
the book has no `NNN-NNNN` codes of its own. Re-run `extract_prices.py` last so
every book's numbers get matched to the price list. Order matters:
`pdf → inverter → qsk60 → manual → prices`.

**Name every section, don't show codes.** A book may store the descriptive name
in the field the sidebar doesn't display first, so sections surface as bare
option codes (`VC6715-02`) instead of names. Categorize with the `secName()`
rule — see `references/categorization.md` — and confirm in the sidebar that
every section reads as a name.

## Working style that fit this task
- The user iterates by pointing a phone photo at one screen. Treat each as a
  concrete bug: reproduce that exact section, find the mechanism, **fix the
  class of problem** (not the one instance), and re-verify across many sections.
- Prefer a committed, reproducible script over one-off commands, so the whole
  catalog regenerates from source. Keep sources under `sources/active/`
  (used) and `sources/archive/` (unused/older editions); the deliverable
  `catalog/` stays self-contained and downloadable on its own.
- Keep it openable by double-clicking `index.html` (data as JS globals, images
  by relative path, `.xlsx` written in-browser with no library) — no server.

## What each reference covers
- `references/pdf-column-tables.md` — coordinate PDF part books: the value-based
  parser and its failure modes (column drift, headerless continuation pages,
  section attribution from drawings not table stamps, header-noise filtering,
  REF/QTY swap).
- `references/doc-linear-tables.md` — `.doc`→PDF linear text: row-signature
  detection, NC letters, split `AR`, `#N/A`, source-duplicated pages,
  date-shaped part numbers.
- `references/russian-option-pdfs.md` — Cummins option PDFs: columns by
  x-position, vertically-centred multi-line names, cover vs table pages.
- `references/price-list.md` — matching the `.xlsx`; leading-zero article export.
- `references/manual.md` — `.docx` → browsable HTML + catalog cross-references.
- `references/categorization.md` — the chapter→section tree and, critically, how
  each section gets its **display name**: the `zh`/`en` slots differ per book, so
  a section can show a bare option code instead of a name (QSK60 bug). The
  `secName()` rule — a name has a space, a bare code does not — and how to
  categorize a newly added book.
- `references/webapp.md` — the web app: schema, UI, exports, cross-refs, gotchas.
