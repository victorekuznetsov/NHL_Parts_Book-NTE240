# Coordinate PDF part books (`extract_pdf_catalog.py`)

Source shape: A4-landscape pages, alternating **drawing** pages (illustrations
with numbered callouts) and **table** pages. Tables are usually **two columns**
(left/right), each headed `注/NC 序号/REF 数量/QTY 件号/PART NO. 中文名称/ZH 英文名称/EN`.

Every item below was a real bug that a visual spot-check missed and the
completeness cross-check caught. Read the relevant one before touching the parser.

## Parse by VALUE, not by fixed column x
Column x-positions drift page to page, and on many pages the data sits a few px
**left of its own header** — so nearest-header assignment drops the 8-digit
number into the QTY column and the whole row is lost. Instead:
1. Detect per-page column anchors from the page's own header row.
2. Cluster words into rows by y.
3. In each row, **find the part-number token by its pattern** (`_is_pn`), then
   REF/QTY are the numeric tokens to its left, ZH/EN the tokens to its right.

## Header position varies per page *and* per column
The amount of running-header matter above a table changes page to page, so the
header band (and the body-top below which data starts) is **not** at a fixed y.
Worse, the left and right columns can carry their headers at **different**
heights. Detect the header band from each side's own label tokens and derive a
**per-side** `body_top`; fall back to a low default (~65) for continuation pages
that repeat no header. A single page-wide body-top drops the top rows of one
column.

## REF/QTY swap from horizontal drift
When the data columns sit ~15–20 px left of their header labels, a raw
nearest-anchor test puts the position number (序号/REF) and the quantity
(数量/QTY) in the wrong columns — the catalog shows quantities as positions and
they stop matching the drawing callouts. **Correct the drift with the part
number's own offset from the PART-NO anchor**, then match REF/QTY to the shifted
anchors; fall back to left-to-right `NC REF QTY` order when two numbers can't be
separated.

## Section identity comes from DRAWINGS, not table stamps
The title block on a **table** page can print the code of the *following*
section, not the parts on it (e.g. dump-body liner rows 001–010 sit on a page
stamped as the next section; a weight-system row sits on a page stamped as the
one after). Trusting those stamps scatters positions into neighbouring sections.
Take section identity **only from drawing pages and section-title sheets** (they
name their section correctly) and attribute every table's rows to the most
recent such section — never to the code printed on the table page itself.

## Drawings vs tables, and headerless continuation pages
- A page with an embedded raster image is a **drawing** — render it. In this
  book such pages never hold table rows (every number sits on an image-free
  page), so do not parse them; that keeps drawing-title-block IDs out of the list.
- An image-free page with parseable rows is a **table**, even when it repeats
  no column header (a continuation page). Detect these or their rows are dropped
  silently — the completeness check has the same blind spot as the parser, so
  make the check **document-wide**.

## Rows that look empty but are real
- **Quantity `AR`** ("As Required") instead of a number — accept `\d{1,4}|AR|A/R`.
- **Blank quantity**, **alphanumeric positions** like `4A`.
- **Kit sub-components**: a REF + name but **no part number** — keep them (empty
  pn, not orderable) so the on-screen list matches the drawing callouts.

## Header/divider noise that must be filtered
Headerless pages sweep the running-header/title band into phantom rows. Drop:
- **Running-header ECN blocks** — `A 20190313 NHK007 PM00001468` land as a row
  with no REF, no Chinese name, an English "name" of only drawing/ECN codes.
  Require an unmistakable signature (`PMnnnn` or `NHxxx`) AND that every name
  token is code-like — so a real part (a genuine word, even a stray letter) is
  never dropped.
- **Chapter-contents / divider sheets** (`章 …`, `手册号 版本 修改号 涉及序列号`)
  become one long pn-less row — drop by those markers.
- **Name pollution** — strip trailing running-header captions/codes
  (`自系列号`, `FROM SERIAL`, `PM…`, `NH…`, dates) from the ZH/EN names.

## Part-number whitelist beats a permissive matcher
Validate the exact forms printed in the part-no columns and whitelist only those
(here: `\d{7,8}`, `9\d{5}`, `UR…`). A permissive "alnum with a digit" matcher
lets `PMnnnnnnnn`, ECN codes, the model name and section codes leak in as
phantom rows. Confirm the whitelist matches **every** printed column token
before trusting it.

## Figures — pair each drawing with its own positions
Walk a section's pages in order; a figure is a run of drawing pages plus the
table pages that surround them. Because the book orders drawing/table
inconsistently, attach table rows to the drawing they belong to (before or
after), and only start a new figure once the current one has both a drawing and
its table — so genuinely interleaved sections still split one drawing per list,
while several sheets sharing one list become one figure with a carousel.
