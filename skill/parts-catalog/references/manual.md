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

## A repair/service book keyed by section (`extract_service.py`)
A service book often ships as a **folder of per-section Word files**, each
filename carrying the catalog section code (`…020-0040…`). That makes it trivial
to organise **by catalog section** — group files by the `NNN-NNNN` in the name.
- **`.docx`**: parse from XML (text + VML/DrawingML images) as above.
- **`.doc`** (binary Word, LibreOffice can't load them here): read the OLE2
  `WordDocument` stream and decode the **piece table** (CLX in `1Table`/`0Table`:
  skip `0x01` Prc runs, read the `0x02` Pcdt PlcPcd; each PCD's fc bit 30 marks a
  compressed CP12xx piece at fc/2, else UTF-16LE). Strip field codes
  (`\x13…\x14…\x15`) and control chars. Extract **PNG/JPEG** blobs by signature
  scan of the `Data` stream (these books use raster images, no EMF/WMF); append
  them as an illustrations block.
- Title each page by the **catalog section name** (join by code), write one
  `service/<code>.html` per section, a `service.html` index grouped by chapter,
  and a `window.SERVICE = {code:title}` manifest.
- **Link both ways**: the catalog section shows "🔧 Инструкция по ремонту раздела →"
  when `window.SERVICE[code]` exists; the repair page links back to
  `index.html#/s/<code>`.
- The outer split zip may be **deflate64** with mojibake filenames — `unzip`
  returns a warning exit code but still extracts; don't fail on it, verify by the
  extracted files. Match the section code from the ASCII `NNN-NNNN` in each name
  (it survives the encoding mangling).
