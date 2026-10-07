"""Read current owner-occupier stamp duty rates from each state revenue office and save them
for the mortgage calculator.

Run by .github/workflows/update-data.yml. Uses only the standard library.

Safety: every table is checked before anything is saved (expected number of rows, sensible
rates, and each bracket's base amount must follow on from the bracket before it). If any check
fails the script exits with an error, nothing is written, and GitHub emails the repo owner.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "public" / "mortgage-calculator" / "stamp-duty.json"
UA = "Mozilla/5.0 (my-tools stamp duty updater; +https://github.com/hillbrendon/my-tools)"

NSW_URL = "https://www.revenue.nsw.gov.au/taxes-duties-levies-royalties/transfer-duty/understanding-transfer-duty/calculate-transfer-duty"
VIC_GENERAL_URL = "https://www.sro.vic.gov.au/about-us/rates-and-statistics/current-rates/land-transfer-duty-non-principal-place-residence-current-rates"
VIC_PPR_URL = "https://www.sro.vic.gov.au/about-us/rates-and-statistics/current-rates/land-transfer-duty-principal-place-residence-current-rates"
QLD_URL = "https://qro.qld.gov.au/duties/transfer-duty/calculate/concession-rates/"


class CheckFailed(Exception):
    pass


def fetch_tables(url):
    """Return every <table> on the page as a list of rows, each row a list of cell texts."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    tables = []
    for table in re.findall(r"<table.*?</table>", page, re.S | re.I):
        rows = []
        for row in re.findall(r"<tr.*?</tr>", table, re.S | re.I):
            cells = re.findall(r"<t[hd].*?</t[hd]>", row, re.S | re.I)
            text = [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split()) for c in cells]
            if len(text) >= 2:
                rows.append(text)
        tables.append(rows)
    if not tables:
        raise CheckFailed(f"No tables found at {url}")
    return tables


def money(s):
    return float(s.replace(",", ""))


def upper_bound(range_text):
    """'$18,001 to $38,000' -> 38000; 'Not more than $350,000' -> 350000; 'Over $1m' -> None."""
    t = range_text.lower()
    nums = re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", range_text)
    if not nums:
        raise CheckFailed(f"No amount in range '{range_text}'")
    if " to " in t or " - " in t:
        return money(nums[-1])
    if "not more than" in t:
        return money(nums[0])
    if "more than" in t or "over" in t:
        return None
    raise CheckFailed(f"Can't read range '{range_text}'")


def parse_rate(rate_text):
    """'$225 plus $1.50 for every $100 over $18,000' -> base 225, rate 0.015, over 18000."""
    m = re.search(r"\$([\d.]+)\s+for (?:every|each) \$100", rate_text)
    if m:
        rate = float(m.group(1)) / 100
    else:
        m = re.search(r"([\d.]+)\s*%", rate_text)
        if not m:
            raise CheckFailed(f"No rate in '{rate_text}'")
        rate = float(m.group(1)) / 100
    base = re.match(r"\s*\$([\d,]+)\s*(?:plus|\+)", rate_text)
    over = re.search(r"(?:over|in excess of)\s+\$([\d,]+)", rate_text)
    minimum = re.search(r"minimum \$([\d,]+)", rate_text)
    bracket = {
        "base": money(base.group(1)) if base else 0,
        "rate": round(rate, 6),
        "over": money(over.group(1)) if over else 0,
    }
    if minimum:
        bracket["min"] = money(minimum.group(1))
    return bracket


def parse_table(rows, expected_rows):
    body = rows[1:]  # skip header
    if len(body) != expected_rows:
        raise CheckFailed(f"Expected {expected_rows} rows, found {len(body)}: the page layout may have changed")
    return [{"upTo": upper_bound(r[0]), **parse_rate(r[1])} for r in body]


def duty(b, price):
    return max(b["base"] + b["rate"] * max(price - b["over"], 0), b.get("min", 0))


def check(state, brackets):
    if brackets[-1]["upTo"] is not None:
        raise CheckFailed(f"{state}: last bracket should have no upper limit")
    prev_up = 0
    for i, b in enumerate(brackets):
        if not 0 < b["rate"] <= 0.1:
            raise CheckFailed(f"{state}: rate {b['rate']} looks wrong")
        if b["upTo"] is not None and b["upTo"] <= prev_up:
            raise CheckFailed(f"{state}: brackets are not in increasing order")
        # Where a bracket charges a marginal rate from the previous threshold, its base amount
        # must equal the duty at the top of the previous bracket (allowing for rounding).
        if i > 0 and b["over"] == prev_up:
            expected = duty(brackets[i - 1], prev_up)
            if abs(b["base"] - expected) > 5:
                raise CheckFailed(f"{state}: base ${b['base']:,.0f} at ${prev_up:,.0f} should be about ${expected:,.0f}")
        prev_up = b["upTo"] or prev_up


def nsw():
    general, premium = fetch_tables(NSW_URL)[:2]
    brackets = parse_table(general, 6)
    if len(premium) != 2:
        raise CheckFailed("NSW: premium duty table layout changed")
    threshold = money(re.findall(r"[\d,]+", premium[1][0])[0])
    brackets[-1]["upTo"] = threshold
    brackets.append({"upTo": None, **parse_rate(premium[1][1])})
    return brackets


def vic():
    general = parse_table(fetch_tables(VIC_GENERAL_URL)[0], 5)
    ppr = parse_table(fetch_tables(VIC_PPR_URL)[0][:-1], 4)  # last row says "concession does not apply"
    cap = ppr[-1]["upTo"]
    # PPR concession rates up to the cap, then the general rates above it.
    return ppr + [b for b in general if b["upTo"] is None or b["upTo"] > cap]


def qld():
    return parse_table(fetch_tables(QLD_URL)[0], 4)  # first table is the home concession rate


def main():
    states = {
        "NSW": {"name": "Revenue NSW", "url": NSW_URL, "basis": "general transfer duty and premium duty", "brackets": nsw()},
        "VIC": {"name": "State Revenue Office Victoria", "url": VIC_PPR_URL, "basis": "general rates with the principal place of residence concession", "brackets": vic()},
        "QLD": {"name": "Queensland Revenue Office", "url": QLD_URL, "basis": "home concession rates", "brackets": qld()},
    }
    for code, s in states.items():
        check(code, s["brackets"])

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    changed = [c for c in states if old.get("states", {}).get(c, {}).get("brackets") != states[c]["brackets"]]
    OUT.write_text(json.dumps({"checked": date.today().isoformat(), "states": states}, indent=2) + "\n", encoding="utf-8")
    print("Rates changed for: " + ", ".join(changed) if changed else "Rates unchanged.")


if __name__ == "__main__":
    try:
        main()
    except CheckFailed as e:
        sys.exit(f"Stamp duty check failed, nothing saved: {e}")
