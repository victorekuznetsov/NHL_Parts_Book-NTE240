# Russian Cummins option PDFs (`extract_qsk60_catalog.py`)

Source shape: an engine catalog delivered as **one PDF per option** (e.g.
"Genuine Cummins Parts N.pdf", 119 files). Each PDF is one option/section: a
**cover/drawing** page (an illustration plus an "Option Detail" title block) and
one or more **parts-table** pages. The table is already in **Russian**, columns
`№ · Номер по каталогу · Название · Кол-во · Dimensions`. Assign a new chapter
(`700`) and synthetic section codes (`700-00N0`) in file order.

## Read columns by x-position
The table text has no reliable reading order, so cluster by the **part-number
column** (x ≈ 128; a 5–7 digit number, optionally with a trailing letter; or a
sub-assembly option reference like `CM6726-07`) and read the other columns by
their x-band: № ≈ 67, Название ≈ 247, Кол-во ≈ 381, Dimensions ≈ 443.

## Multi-line names are vertically centred on the row
A row's name spans several y-lines and can **start above** the part-number line.
Bounding a row from its anchor down to the next drops the first name line and
picks up the next row's — so bound each row by the **midpoints** between
consecutive part-number anchors. This is the single fix that makes names correct
(`БОЛТ С ФЛАНЦЕВОЙ ШЕСТИГРАННОЙ ГОЛОВКОЙ`, not a scramble).

## Cover page is a drawing, not a table
The cover carries the option code (`BB67043-00`) in the part-no x-band. That is
an **option reference**, not a numeric part number — so classify a page as a
table only when it has the column header *or* several *numeric* part numbers,
and render the cover as the drawing. Otherwise the cover is parsed as a one-row
table and never rendered.

## Option code + name from the cover
The cover header appears in three wordings — `Option Detail - CODE`,
`Подробная информация об опции - CODE`, `Дополнительная информация — CODE` (note
the em-dash). The option name is the block after the code value, stopping at the
first `Не …`, a 3-digit group code, `Option Notes`, or a private-use glyph.
Drop options that yield neither parts nor a drawing (declaration/index pages).

## Sub-assembly references
A row may reference a sub-assembly by its option code instead of a part number —
keep the row (empty pn) and surface the reference in the name (`см. CM6726-07`).
