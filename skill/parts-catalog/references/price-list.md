# Price list `.xlsx` (`extract_prices.py`)

The price list lists, per catalog number (Артикул): an interchangeable article
(Взаимозаменяемый артикул), a Russian name (Наименование), a price (Цена, CNY
без НДС) and a part group (Группа) — the "аналитики".

- The header is **below a contract preamble** — find the row containing
  `Артикул`, don't assume row 1.
- Build `pn -> {p:price, g:group, x:xref, n:ru_name}` keyed by article, and
  **also index by the interchangeable article** so a number listed only as a
  cross-reference still resolves.
- Match to catalog part numbers (run this **last**, after every book is merged,
  so all chapters get prices). Expect partial coverage — that is normal; unmatched
  parts show `—` in the UI.
- Emit a small `window.PRICES` (only catalog-referenced rows) plus a
  unique-numbers export with every attribute column.

## Leading zeros (the Excel trap)
Catalog numbers keep leading zeros (`00106267`, `09014080`). Excel auto-types a
CSV column as numeric on open and strips them (`106267`). Quoting CSV fields does
not stop this. Two fixes, both used here:
- **In-browser export** (the catalog's buttons): write a real **.xlsx** with the
  article columns as inline strings — genuine text, leading zeros preserved,
  prices still numeric. A tiny dependency-free xlsx writer (inline-string cells +
  a stored-method zip with CRC32) does this over `file://` with no library.
- **The generated CSV** (`all_part_numbers.csv`, for tooling): write the article
  columns as an `="…"` Excel-text formula.

Always validate an exported file by re-opening it (`openpyxl`): the article
loads as the string `"00106267"`, the price as a float.

## Updating prices later, in the browser (no rebuild)
The catalog can reload a price file **locally** so the client updates prices
without Python or the sandbox — a "💲 Обновить цены" button opens a modal that
reads an `.xlsx` **or** `.csv` in the browser and layers it over the factory
`data/prices.js`. Reuse the extractor's column logic verbatim (find the
`Артикул` header row, map Артикул / Взаимозам. / Наименование / Цена / Группа,
index by article **and** xref, `norm_art` strips a trailing `.0`, price accepts
comma decimals and NBSP). Design notes that mattered:
- **Read `.xlsx` in vanilla JS**: it's a ZIP of XML — parse the central
  directory from the local `File`, inflate each entry with
  `DecompressionStream("deflate-raw")` (Chromium; if absent, tell the user to
  save as `.csv`), then read `sharedStrings.xml` + the first sheet (resolve it
  via `workbook.xml` → `workbook.xml.rels`, don't hardcode `sheet1.xml`). Map
  cells by the `r=` column letter — **empty cells are omitted**, so positional
  indexing is wrong.
- **`.csv`**: detect `;` vs `,` (Russian Excel uses `;`), strip the BOM, honor
  quoted fields. Never `parseFloat` the article — leading zeros must survive.
- **Two persistence modes, offer both**: an overlay in `localStorage` (instant,
  this browser, layered over the factory map on load; a "reset to factory"
  clears it) **and** a downloadable regenerated `prices.js` the user drops into
  `data/` to make the change permanent and portable with the `catalog/` folder.
- Keep the overlay small — store only prices for numbers that exist in the
  catalog. Invalidate the search index and re-render after applying.
- The Python `extract_prices.py` stays the canonical/bulk path; the in-browser
  loader is for quick field updates.
