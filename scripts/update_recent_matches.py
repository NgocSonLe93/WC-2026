#!/usr/bin/env python3
"""Build data/recent_matches.json from the CC0 international-results dataset.

The website uses the latest 10 completed senior men's internationals before each
fixture. This script keeps a deeper buffer (25 per World Cup team), so current
World Cup matches can be merged and de-duplicated in the browser.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "recent_matches.json"
SOURCE = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
UA = "Mozilla/5.0 (compatible; WC2026-FormModel/1.0; +https://github.com/)"
KEEP_PER_TEAM = 25

TEAM_TO_CODE = {
    "Argentina":"ARG", "Spain":"ESP", "France":"FRA", "England":"ENG", "Portugal":"POR",
    "Brazil":"BRA", "Morocco":"MAR", "Netherlands":"NED", "Belgium":"BEL", "Germany":"GER",
    "Croatia":"CRO", "Colombia":"COL", "Mexico":"MEX", "Senegal":"SEN", "Uruguay":"URU",
    "United States":"USA", "Japan":"JPN", "Switzerland":"SUI", "Iran":"IRN", "Turkey":"TUR",
    "Ecuador":"ECU", "Austria":"AUT", "South Korea":"KOR", "Australia":"AUS", "Algeria":"ALG",
    "Egypt":"EGY", "Canada":"CAN", "Norway":"NOR", "Ivory Coast":"CIV", "Panama":"PAN",
    "Sweden":"SWE", "Czech Republic":"CZE", "Czechia":"CZE", "Paraguay":"PAR", "Scotland":"SCO",
    "Tunisia":"TUN", "DR Congo":"COD", "Uzbekistan":"UZB", "Qatar":"QAT", "Iraq":"IRQ",
    "South Africa":"RSA", "Saudi Arabia":"KSA", "Jordan":"JOR", "Bosnia and Herzegovina":"BIH",
    "Cape Verde":"CPV", "Ghana":"GHA", "Curaçao":"CUW", "Curacao":"CUW", "Haiti":"HAI",
    "New Zealand":"NZL",
}
CODE_TO_NAME = {code:name for name,code in TEAM_TO_CODE.items()}
CODE_TO_NAME.update({"CZE":"Czechia", "CUW":"Curaçao", "COD":"DR Congo", "BIH":"Bosnia and Herzegovina"})
TARGET_CODES = set(CODE_TO_NAME)


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,text/plain,*/*"})
    with urlopen(req, timeout=45) as response:
        return response.read().decode("utf-8-sig")


def score(value: str):
    try:
        number = float(value)
        if number != number:  # NaN
            return None
        return int(number)
    except Exception:
        return None


def main() -> None:
    rows = list(csv.DictReader(io.StringIO(fetch_text(SOURCE))))
    completed = []
    for index, row in enumerate(rows, 1):
        home_code = TEAM_TO_CODE.get((row.get("home_team") or "").strip())
        away_code = TEAM_TO_CODE.get((row.get("away_team") or "").strip())
        if not home_code or not away_code:
            continue
        hs, as_ = score(row.get("home_score", "")), score(row.get("away_score", ""))
        if hs is None or as_ is None:
            continue
        date = (row.get("date") or "").strip()
        if not date:
            continue
        completed.append({
            "id": f"intl-{index}",
            "date": date,
            "kickoff_utc": f"{date}T12:00:00Z",
            "tournament": (row.get("tournament") or "International").strip(),
            "neutral": str(row.get("neutral") or "").strip().lower() == "true",
            "home": {"name": CODE_TO_NAME.get(home_code, row.get("home_team")), "code": home_code},
            "away": {"name": CODE_TO_NAME.get(away_code, row.get("away_team")), "code": away_code},
            "score": {"home": hs, "away": as_},
        })

    completed.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
    selected_ids = set()
    counts = {code: 0 for code in TARGET_CODES}
    for item in completed:
        codes = (item["home"]["code"], item["away"]["code"])
        if not any(counts[code] < KEEP_PER_TEAM for code in codes):
            continue
        selected_ids.add(item["id"])
        for code in codes:
            if counts[code] < KEEP_PER_TEAM:
                counts[code] += 1
        if all(value >= KEEP_PER_TEAM for value in counts.values()):
            break

    selected = [item for item in completed if item["id"] in selected_ids]
    selected.sort(key=lambda item: (item["date"], item["id"]))
    payload = {
        "meta": {
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": "martj42/international_results (CC0)",
            "model_buffer_per_team": KEEP_PER_TEAM,
            "teams": len(TARGET_CODES),
            "matches": len(selected),
        },
        "matches": selected,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)
    missing = [code for code,value in counts.items() if value < 10]
    print(f"Wrote {OUT}: {len(selected)} matches for {len(TARGET_CODES)} teams")
    if missing:
        print("Warning - fewer than 10 matches:", ", ".join(sorted(missing)))


if __name__ == "__main__":
    main()
