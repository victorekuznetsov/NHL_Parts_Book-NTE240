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
