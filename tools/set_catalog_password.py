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
GATE = os.path.join(ROOT, "catalog", "gate.js")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    password = sys.argv[1]
    issue = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    days = sys.argv[3] if len(sys.argv) > 3 else None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", issue):
        raise SystemExit("issue date must be YYYY-MM-DD")

    h = hashlib.sha256(password.encode("utf-8")).hexdigest()
    s = open(GATE, encoding="utf-8").read()
    s = re.sub(r'var ISSUE_DATE = "[^"]*";', 'var ISSUE_DATE = "%s";' % issue, s)
    s = re.sub(r'var PASS_SHA256 = "[^"]*";', 'var PASS_SHA256 = "%s";' % h, s)
    if days:
        s = re.sub(r'var VALID_DAYS = \d+;', "var VALID_DAYS = %d;" % int(days), s)
    open(GATE, "w", encoding="utf-8").write(s)
    print("Дата издания: %s   Срок действия: %s дней" %
          (issue, days or re.search(r"var VALID_DAYS = (\d+);", s).group(1)))
    print("SHA-256 пароля записан в catalog/gate.js (%s…)" % h[:16])


if __name__ == "__main__":
    main()
