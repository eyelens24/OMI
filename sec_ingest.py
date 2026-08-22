"""Create date-safe fundamental snapshots from the SEC Company Facts API.

This is a research-data importer, not a trading-data feed. SEC Company Facts
contains filing dates, not a guaranteed decision-time availability timestamp;
the exported timestamp is conservatively set to the end of the filing date.
Use a vendor or filing acceptance timestamps before relying on it for intraday
or production replay.
"""
import argparse
import csv
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen


SEC_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
FORMS = {"10-K", "10-Q", "20-F", "40-F"}
TAG_OPTIONS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
    "net_income": ("NetIncomeLoss",), "eps_diluted": ("EarningsPerShareDiluted",),
    "operating_income": ("OperatingIncomeLoss",), "assets": ("Assets",), "liabilities": ("Liabilities",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "long_term_debt": ("LongTermDebtCurrent", "LongTermDebtNoncurrent", "LongTermDebt"),
    "interest_expense": ("InterestExpenseNonoperating", "InterestExpense"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",), "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
}
OUTPUT_FIELDS = [
    "timestamp", "symbol", "cik", "form", "fiscal_period_end", "filing_date", "accession_number",
    "revenue", "revenue_growth_yoy", "net_income", "eps_diluted", "eps_growth_yoy", "operating_income",
    "assets", "liabilities", "cash", "long_term_debt", "interest_expense", "interest_coverage",
    "operating_cash_flow", "capex", "free_cash_flow", "fundamental_age_days", "availability_note",
]


def fetch_company_facts(cik, user_agent):
    # Do not request compressed content: this dependency-free importer keeps
    # the response handling deliberately simple and portable.
    request = Request(SEC_URL.format(cik=str(cik).zfill(10)), headers={"User-Agent": user_agent})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def units_for_tag(facts, tag):
    units = facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {})
    if "USD" in units:
        return units["USD"]
    if "USD/shares" in units:
        return units["USD/shares"]
    return next(iter(units.values()), [])


def value_for_filing(facts, options, accession):
    for tag in options:
        matches = [fact for fact in units_for_tag(facts, tag) if fact.get("accn") == accession]
        if matches:
            matches.sort(key=lambda fact: (bool(fact.get("fp")), fact.get("filed", ""), fact.get("end", "")))
            return matches[-1].get("val")
    return None


def as_number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def pct_change(current, prior):
    if current is None or prior in (None, 0):
        return None
    return round((current / prior - 1) * 100, 4)


def company_rows(facts, symbol=None):
    revenue_facts = []
    for tag in TAG_OPTIONS["revenue"]:
        revenue_facts = [fact for fact in units_for_tag(facts, tag) if fact.get("form") in FORMS and fact.get("accn")]
        if revenue_facts:
            break
    filings = {(fact["accn"], fact["filed"]): fact for fact in revenue_facts if fact.get("filed")}
    rows = []
    for (accession, filed), anchor in sorted(filings.items(), key=lambda item: item[0][1]):
        fiscal_end = anchor.get("end", "")
        values = {name: as_number(value_for_filing(facts, tags, accession)) for name, tags in TAG_OPTIONS.items()}
        filing_day = date.fromisoformat(filed)
        end_day = date.fromisoformat(fiscal_end) if fiscal_end else filing_day
        row = {
            "timestamp": f"{filed}T23:59:59+00:00", "symbol": symbol or facts.get("ticker", ""),
            "cik": str(facts.get("cik", "")).zfill(10), "form": anchor.get("form", ""),
            "fiscal_period_end": fiscal_end, "filing_date": filed, "accession_number": accession, **values,
            "fundamental_age_days": (filing_day - end_day).days,
            "availability_note": "Date-level SEC filing availability; use acceptance time/vendor as-of data for production replay.",
        }
        row["interest_coverage"] = round(values["operating_income"] / abs(values["interest_expense"]), 4) if values["operating_income"] is not None and values["interest_expense"] not in (None, 0) else None
        row["free_cash_flow"] = round(values["operating_cash_flow"] - abs(values["capex"] or 0), 4) if values["operating_cash_flow"] is not None else None
        rows.append(row)
    # SEC filings do not provide consensus estimates; reported growth is usable,
    # but revisions and earnings surprise cannot be invented from this source.
    for index, row in enumerate(rows):
        prior = rows[index - 4] if index >= 4 else None
        row["revenue_growth_yoy"] = pct_change(row["revenue"], prior["revenue"]) if prior else None
        row["eps_growth_yoy"] = pct_change(row["eps_diluted"], prior["eps_diluted"]) if prior else None
    return rows


def write_rows(rows, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in OUTPUT_FIELDS} for row in rows)


def main():
    parser = argparse.ArgumentParser(description="Download SEC Company Facts into point-in-time research CSV snapshots.")
    parser.add_argument("--cik", required=True, help="SEC CIK, with or without leading zeros")
    parser.add_argument("--symbol", default="", help="Ticker label to write to the output")
    parser.add_argument("--output", required=True, type=Path, help="Output CSV path")
    parser.add_argument("--user-agent", required=True, help="Identifying contact, e.g. 'Name email@example.com'")
    args = parser.parse_args()
    rows = company_rows(fetch_company_facts(args.cik, args.user_agent), args.symbol)
    if not rows:
        raise SystemExit("No supported 10-K/10-Q revenue filings were found for this CIK.")
    write_rows(rows, args.output)
    print(f"Wrote {len(rows)} SEC fundamental snapshots to {args.output}")


if __name__ == "__main__":
    main()
