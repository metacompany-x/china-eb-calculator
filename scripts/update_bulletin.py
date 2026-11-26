#!/usr/bin/env python3
"""Refresh China-mainland EB-1/2/3 Final Action Dates in data.json from the
U.S. State Department Visa Bulletin.

Run daily by .github/workflows/update-bulletin.yml. Looks for next month's
bulletin first (it is usually published mid-month), then this month's.
Writes data.json and sitemap.xml only when something changed. Exits non-zero
if no bulletin could be parsed, so a broken page format shows up as a failed
workflow run instead of silently bad data.
"""
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data.json"
SITEMAP = ROOT / "sitemap.xml"

BASE = "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin"
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
MON3 = {m[:3].upper(): i + 1 for i, m in enumerate(MONTHS)}
ROWS = {"1st": "EB1", "2nd": "EB2", "3rd": "EB3"}


def bulletin_url(year, month):
    fiscal_year = year + 1 if month >= 10 else year
    return f"{BASE}/{fiscal_year}/visa-bulletin-for-{MONTHS[month - 1]}-{year}.html"


class Tables(HTMLParser):
    """Collect every <table> as a list of rows of cell text."""

    def __init__(self):
        super().__init__()
        self.tables, self._stack = [], []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif self._stack and tag == "tr":
            self._stack[-1].append([])
        elif self._stack and tag in ("td", "th") and self._stack[-1]:
            self._stack[-1][-1].append("")

    def handle_endtag(self, tag):
        if tag == "table" and self._stack:
            self.tables.append(self._stack.pop())

    def handle_data(self, data):
        if self._stack and self._stack[-1] and self._stack[-1][-1]:
            self._stack[-1][-1][-1] += data


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def parse_date(cell, bulletin_first_day):
    cell = norm(cell).upper()
    if cell == "C":  # current: everyone with an earlier priority date is eligible
        return bulletin_first_day.isoformat()
    m = re.fullmatch(r"(\d{2})([A-Z]{3})(\d{2})", cell)
    if not m or m.group(2) not in MON3:
        return None  # "U" (unavailable) or an unexpected format
    return dt.date(2000 + int(m.group(3)), MON3[m.group(2)], int(m.group(1))).isoformat()


def parse_bulletin(html, year, month):
    """Return {"EB1": iso, "EB2": iso, "EB3": iso} for China, or raise ValueError."""
    p = Tables()
    p.feed(html)
    for rows in p.tables:
        rows = [[norm(c) for c in r] for r in rows if r]
        if not rows:
            continue
        head = [re.sub(r"[\s-]", "", c).lower() for c in rows[0]]
        if not head or not head[0].startswith("employment"):
            continue
        # The first employment table is Final Action Dates; the second is Dates for Filing.
        col = next((i for i, c in enumerate(head) if c.startswith("china")), None)
        if col is None:
            raise ValueError("China column not found in employment table")
        out = {}
        for r in rows[1:]:
            key = ROWS.get(r[0].lower()) if r else None
            if key and col < len(r):
                out[key] = parse_date(r[col], dt.date(year, month, 1))
        if set(out) != set(ROWS.values()):
            raise ValueError(f"missing rows: {out}")
        return out
    raise ValueError("employment Final Action Dates table not found")


# travel.state.gov blocks some automated requests; the same pages are also
# served under these State Department hostnames.
HOSTS = ["travel.state.gov", "adoption.state.gov", "childabduction.state.gov", "adoptions.state.gov"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_curl(url):
    """curl gets through some bot filters that refuse Python's HTTP client.
    Returns (status, body) or None if curl is unavailable."""
    import shutil
    import subprocess
    if not shutil.which("curl"):
        return None
    cmd = ["curl", "-sS", "-L", "--compressed", "-m", "30", "-w", "\n%{http_code}"]
    for k, v in HEADERS.items():
        cmd += ["-H", f"{k}: {v}"]
    p = subprocess.run(cmd + [url], capture_output=True, text=True)
    if p.returncode != 0:
        return (0, p.stderr.strip())
    body, _, code = p.stdout.rpartition("\n")
    return (int(code or 0), body)


def fetch(url):
    """Return the page HTML, or None if the bulletin is not published (404)."""
    errors = []
    for host in HOSTS:
        u = url.replace("travel.state.gov", host, 1)
        got = fetch_curl(u)
        if got:
            code, body = got
            if code == 404:
                return None
            if code == 200 and "Employment" in body:
                return body
            errors.append(f"{host} (curl): HTTP {code}")
        req = urllib.request.Request(u, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            if "Employment" in html:
                return html
            errors.append(f"{host}: page without bulletin tables")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            errors.append(f"{host}: HTTP {e.code}")
        except urllib.error.URLError as e:
            errors.append(f"{host}: {e.reason}")
    raise RuntimeError("; ".join(errors))


def main():
    today = dt.datetime.now(dt.timezone.utc).date()
    nxt = (today.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    data = json.loads(DATA.read_text(encoding="utf-8"))

    for d in (nxt, today.replace(day=1)):
        key = f"{d.year:04d}-{d.month:02d}"
        if key < data.get("bulletin", ""):
            continue  # never go back to an older bulletin
        url = bulletin_url(d.year, d.month)
        html = fetch(url)
        if html is None:
            print(f"{key}: not published yet")
            continue
        fad = parse_bulletin(html, d.year, d.month)
        # Keep the previous date for any category marked unavailable ("U").
        fad = {k: v or data["fad"][k] for k, v in fad.items()}
        print(f"{key}: {fad}")
        if key == data.get("bulletin") and fad == data.get("fad"):
            print("No change.")
            return 0
        data.update(bulletin=key, bulletinUrl=url, fad=fad, updated=today.isoformat())
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sm = SITEMAP.read_text(encoding="utf-8")
        SITEMAP.write_text(re.sub(r"<lastmod>[^<]*</lastmod>", f"<lastmod>{today.isoformat()}</lastmod>", sm), encoding="utf-8")
        print("data.json updated.")
        return 0

    print("No bulletin could be read for this month or next.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
