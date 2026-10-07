"""Fetch the RBA's average mortgage rate and save it for the mortgage calculator.

Source: RBA statistical table F6 (Housing Lending Rates), series FLRHOFP:
average rate on new owner-occupier principal-and-interest loans funded in the month.

Run by .github/workflows/update-rates.yml once a month. Uses only the standard library.
"""
import csv
import io
import json
import urllib.request
from datetime import datetime
from pathlib import Path

CSV_URL = "https://www.rba.gov.au/statistics/tables/csv/f6-data.csv"
SOURCE_PAGE = "https://www.rba.gov.au/statistics/tables/#interest-rates"
SERIES_ID = "FLRHOFP"
OUT = Path(__file__).resolve().parent.parent / "public" / "mortgage-calculator" / "rates.json"


def main():
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "my-tools rate updater"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8-sig")

    rows = list(csv.reader(io.StringIO(text)))
    header = {r[0]: r for r in rows if r and r[0] in ("Series ID", "Publication date")}
    col = header["Series ID"].index(SERIES_ID)

    # Data rows start with a date like 31/07/2026; take the latest one that has a value.
    data = [r for r in rows if r and r[0][:2].isdigit() and len(r) > col and r[col].strip()]
    if not data:
        raise SystemExit(f"No data found for {SERIES_ID}")
    latest = data[-1]
    rate = float(latest[col])
    if not 0 < rate < 25:
        raise SystemExit(f"Rate {rate} looks wrong; not saving")

    month = datetime.strptime(latest[0], "%d/%m/%Y").strftime("%B %Y")
    result = {
        "rate": rate,
        "month": month,
        "published": header["Publication date"][col],
        "description": "Average rate on new owner-occupier principal-and-interest loans",
        "source": "Reserve Bank of Australia, table F6",
        "sourceUrl": SOURCE_PAGE,
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{rate}% for {month} -> {OUT}")


if __name__ == "__main__":
    main()
