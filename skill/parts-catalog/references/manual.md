# Service manual `.docx` → browsable page (`extract_manual.py`)

Turn the operator / repair-and-maintenance manual (`.docx`) into a
self-contained, styled HTML page inside the catalog, linked both ways.

## Conversion
- Walk the document body **in order** (`xml.etree`, WordprocessingML namespace):
  `<w:p>` paragraphs and `<w:tbl>` tables.
- Headings come from paragraph **style ids**, not "Heading" names — here style
  `1` = heading 1, `2` = heading 2 (check `word/styles.xml` for the mapping);
  `toc N` styles are the contents list (skip). Build a contents sidebar from the
  headings.
- Images are **VML**, not DrawingML: `<w:pict>` → `<v:imagedata r:id="rIdN">`.
  Map `rId` via `word/_rels/document.xml.rels` to `word/media/*`, export them to
  `catalog/manual_media/`, place inline in document order.
- Tables → HTML tables. Text search over headings/paragraphs/cells with
  highlight is a few lines of client JS.

## Cross-references catalog ⇄ manual
Bidirectional deep links, keyed by a small **chapter ⇄ Russian-keyword** map:
- **Catalog → manual**: each section header links to `manual.html?from=<code>&q=<topic>`
  — the manual pre-searches the topic (highlights, scrolls to first hit) and
  shows a "← back to catalog section <code>" link for a clean round trip.
- **Manual → catalog**: a manual heading that names a system gets a
  `🔧 <System> в каталоге →` link to a catalog chapter via a `#/ch/<code>` route
  (opens the chapter's first section).
- The manual reads `?q=` (auto-search) and `?from=` (return link) URL params.

An operator manual is organised by controls/inspection, not strictly by parts
chapters, so manual→catalog links are sparse (only where a heading clearly names
a system) — that is expected and still useful.
