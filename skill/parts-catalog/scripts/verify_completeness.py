#!/usr/bin/env python3
"""
Verify that an extracted catalog (catalog/data/parts.js) captured every part
number that is actually printed in the source, and report position gaps.

Two independent checks — run this after every extraction change, because table
parsers silently drop rows and a visual spot-check will not catch it:

1. Token cross-check (needs the source PDF): for each table page, compare the
   part-number tokens physically present in the part-number column against the
   parsed part numbers. A non-zero "missing" count means the parser dropped
   real rows — investigate the column layout on that page.

2. Position-gap report (data only): within each section, list REF numbers that
   are missing from the 1..max sequence. Most gaps are legitimate (a number
   used only as a quantity, a kit sub-item, a drawing-only callout). Confirm a
   gap is legitimate by checking that the missing number is NOT printed in the
   REF column of the page — do not "fix" a number the book never listed.

Usage:
  python3 verify_completeness.py catalog/data/parts.js [source.pdf]
"""
import sys, re, json


def load_catalog(path):
    raw = open(path, encoding="utf-8").read()
    return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])


def gap_report(data):
    print("== position-gap report (verify each is legitimate before acting) ==")
    flagged = 0
    for s in data["sections"]:
        refs = []
        for f in s.get("figures", [{"parts": s.get("parts", [])}]):
            for p in f["parts"]:
                m = re.match(r"(\d+)", p.get("ref", ""))
                if m:
                    refs.append(int(m.group(1)))
        if not refs:
            continue
        mx = max(refs)
        miss = [n for n in range(1, mx + 1) if n not in set(refs)]
        if len(miss) > 3:
            flagged += 1
            print("  %-14s max %3d  missing %s" % (s["code"], mx, miss[:14]))
    print("  sections with >3 missing positions: %d" % flagged)


def token_crosscheck(data, pdf_path):
    """Document-wide cross-check: every catalog number physically printed in a
    part-number column of the source must appear at least as many times in the
    parsed data.

    This is deliberately *not* scoped per header page — many continuation table
    pages in this book omit the repeated column header, and a per-header-page
    check silently skips them (the same blind spot that drops their rows). We
    compare multisets across the whole document instead, so a dropped row on any
    page is caught."""
    import fitz
    from collections import Counter
    doc = fitz.open(pdf_path)
    pn_re = re.compile(r"\d{7,8}|9\d{5}|UR[0-9A-Z][0-9A-Z\-]{2,}")

    def col_token(w):
        tok = w[4].rstrip(".,;")
        if pn_re.fullmatch(tok) and w[1] > 60 and (118 < w[0] < 212 or 515 < w[0] < 602):
            return tok
        return None

    printed = Counter()
    for i in range(doc.page_count):
        for w in doc[i].get_text("words"):
            tok = col_token(w)
            if tok:
                printed[tok] += 1

    parsed = Counter()
    for s in data["sections"]:
        for f in s.get("figures", [{"parts": s.get("parts", [])}]):
            for p in f["parts"]:
                if p["pn"]:
                    parsed[p["pn"]] += 1

    print("\n== document-wide token cross-check against %s ==" % pdf_path)
    missing = {t: n - parsed[t] for t, n in printed.items() if parsed[t] < n}
    total_missing = sum(missing.values())
    for t in sorted(missing):
        print("  MISSING %s  printed=%d captured=%d" % (t, printed[t], parsed[t]))
    print("  distinct part numbers printed in columns: %d" % len(printed))
    print("  total genuinely-missing part-number tokens: %d" % total_missing)
    if total_missing == 0:
        print("  OK — every printed part number was captured.")


if __name__ == "__main__":
    data = load_catalog(sys.argv[1])
    gap_report(data)
    if len(sys.argv) > 2:
        token_crosscheck(data, sys.argv[2])
