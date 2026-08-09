#!/usr/bin/env python3
"""
Set the catalog access password and issue date (the 1-month validity gate).

Writes the SHA-256 of the password and the issue date into catalog/gate.js. The
catalog opens freely for VALID_DAYS days from the issue date; after that it asks
for this password.

Usage:
  python3 tools/set_catalog_password.py "<пароль>" [ГГГГ-ММ-ДД] [дней]

  - пароль       — обязательный
  - ГГГГ-ММ-ДД   — дата издания (по умолчанию сегодня)
  - дней         — срок действия в днях (по умолчанию оставить как есть, 31)

Note: client-side gate on a static site — a licensing/expiry reminder, not
cryptographic protection.
"""
import os
import re
import sys
import hashlib
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# both gate files must stay in sync: the main catalog and the QSK60 engine
# sub-catalog share the same password/issue-date/validity.
GATES = [
    os.path.join(ROOT, "catalog", "gate.js"),
    os.path.join(ROOT, "catalog", "engine", "gate.js"),
]


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    password = sys.argv[1]
    issue = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    days = sys.argv[3] if len(sys.argv) > 3 else None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", issue):
        raise SystemExit("issue date must be YYYY-MM-DD")

    h = hashlib.sha256(password.encode("utf-8")).hexdigest()
    days_out = days
    for gate in GATES:
        if not os.path.exists(gate):
            continue
        s = open(gate, encoding="utf-8").read()
        s = re.sub(r'var ISSUE_DATE = "[^"]*";', 'var ISSUE_DATE = "%s";' % issue, s)
        s = re.sub(r'var PASS_SHA256 = "[^"]*";', 'var PASS_SHA256 = "%s";' % h, s)
        if days:
            s = re.sub(r'var VALID_DAYS = \d+;', "var VALID_DAYS = %d;" % int(days), s)
        open(gate, "w", encoding="utf-8").write(s)
        days_out = days or re.search(r"var VALID_DAYS = (\d+);", s).group(1)
        print("  ✓ %s" % os.path.relpath(gate, ROOT))
    print("Дата издания: %s   Срок действия: %s дней" % (issue, days_out))
    print("SHA-256 пароля записан в gate.js основного каталога и каталога двигателя (%s…)" % h[:16])


if __name__ == "__main__":
    main()
