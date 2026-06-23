#!/usr/bin/env python3
"""Fetch World Cup 2026 data and write data/worldcup.json.
Primary source: worldcup26.ir public endpoints.
Fallback: openfootball/worldcup.json plus the public team list.
Uses only the Python standard library.
"""
from __future__ import annotations
import csv, io, json, os, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "worldcup.json"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
UA = "Mozilla/5.0 (compatible; WorldCup2026Dashboard/3.0; +https://github.com/)"

PRIMARY = "https://worldcup26.ir"
OPENFOOTBALL = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
STATIC_TEAMS = "https://raw.githubusercontent.com/rezarahiminia/worldcup2026/refs/heads/main/worldcup2026.teams.csv"


def fetch_text(url: str, timeout: int = 30) -> str:
    headers = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    token = os.getenv("WORLD_CUP_API_TOKEN", "").strip()
    if token and "worldcup26.ir" in url:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig")


def fetch_json(url: str):
    return json.loads(fetch_text(url))


def collection(payload, key):
    if isinstance(payload, list): return payload
    if not isinstance(payload, dict): return []
    if isinstance(payload.get(key), list): return payload[key]
    data = payload.get("data")
    if isinstance(data, list): return data
    if isinstance(data, dict) and isinstance(data.get(key), list): return data[key]
    return []


def truthy(v):
    if isinstance(v, bool): return v
    return str(v or "").strip().lower() in {"true","1","yes","finished","ft","fulltime"}


def n(v, default=0):
    try: return int(float(v))
    except Exception: return default


def parse_iso(value):
    if not value: return None
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def parse_local_with_offset(date_s, time_s):
    if not date_s: return None
    time_s = str(time_s or "00:00").strip()
    offset = 0
    m = re.search(r"UTC\s*([+-]\d{1,2})", time_s, re.I)
    if m:
        offset = int(m.group(1)); time_s = re.sub(r"\s*UTC\s*[+-]\d{1,2}", "", time_s, flags=re.I).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M"):
        try:
            dt = datetime.strptime(f"{date_s} {time_s}", fmt)
            return dt.replace(tzinfo=timezone(timedelta(hours=offset))).astimezone(timezone.utc)
        except Exception:
            pass
    return None


def canonical_team(raw):
    return {
        "id": str(raw.get("id") or raw.get("_id") or raw.get("team_id") or ""),
        "name": str(raw.get("name_en") or raw.get("name") or raw.get("team_name") or "Chưa xác định"),
        "code": str(raw.get("fifa_code") or raw.get("code") or ""),
        "iso2": str(raw.get("iso2") or raw.get("country_code") or "").upper(),
        "group": str(raw.get("groups") or raw.get("group") or "").upper(),
    }


def status_of(g):
    elapsed = str(g.get("time_elapsed") or g.get("status") or "").strip().lower()
    if truthy(g.get("finished")) or any(x in elapsed for x in ("finished","fulltime","ft","aet","pen")):
        return "finished"
    if elapsed and elapsed not in {"notstarted","scheduled","tbd","ns","0","false"}:
        return "live"
    return "upcoming"


def canonical_match(g, teams_by_id, stadiums_by_id=None):
    stadiums_by_id = stadiums_by_id or {}
    hid = str(g.get("home_team_id") or g.get("homeTeamId") or g.get("home_team") or "")
    aid = str(g.get("away_team_id") or g.get("awayTeamId") or g.get("away_team") or "")
    ht = teams_by_id.get(hid, {})
    at = teams_by_id.get(aid, {})
    def side(prefix, obj, tid):
        return {
            "id": tid,
            "name": str(g.get(f"{prefix}_team_name_en") or g.get(f"{prefix}_team_name") or obj.get("name") or "Chưa xác định"),
            "code": str(obj.get("code") or ""),
            "iso2": str(obj.get("iso2") or ""),
        }
    dt = parse_iso(g.get("date") or g.get("datetime") or g.get("utc_date") or g.get("start_time"))
    if not dt:
        raw = str(g.get("local_date") or "")
        if raw:
            parts = raw.split()
            dt = parse_local_with_offset(parts[0], parts[1] if len(parts)>1 else "00:00")
    vn_dt = dt.astimezone(VN) if dt else None
    st = status_of(g)
    hs = g.get("home_score", g.get("score_home", g.get("homeScore")))
    as_ = g.get("away_score", g.get("score_away", g.get("awayScore")))
    if st == "upcoming": hs = as_ = None
    stadium = stadiums_by_id.get(str(g.get("stadium_id") or ""), {})
    return {
        "id": str(g.get("id") or g.get("_id") or ""),
        "stage": str(g.get("type") or "group").lower(),
        "group": str(g.get("group") or "").upper(),
        "matchday": n(g.get("matchday")),
        "kickoff_utc": dt.isoformat().replace("+00:00","Z") if dt else "",
        "date_vn": vn_dt.strftime("%Y-%m-%d") if vn_dt else "",
        "time_vn": vn_dt.strftime("%H:%M") if vn_dt else "",
        "status": st,
        "elapsed": str(g.get("time_elapsed") or ""),
        "home": side("home", ht, hid),
        "away": side("away", at, aid),
        "score": {"home": n(hs) if hs is not None else None, "away": n(as_) if as_ is not None else None},
        "venue": str(stadium.get("name_en") or stadium.get("name") or g.get("venue") or g.get("ground") or ""),
    }


def load_static_team_map():
    try:
        rows = list(csv.DictReader(io.StringIO(fetch_text(STATIC_TEAMS))))
        items = [canonical_team(r) for r in rows]
        return items, {t["name"].casefold(): t for t in items}
    except Exception as e:
        print("Static team map failed:", e)
        return [], {}


def from_primary():
    games = collection(fetch_json(PRIMARY + "/get/games"), "games")
    teams_raw = collection(fetch_json(PRIMARY + "/get/teams"), "teams")
    try: stadium_raw = collection(fetch_json(PRIMARY + "/get/stadiums"), "stadiums")
    except Exception: stadium_raw = []
    if not games: raise RuntimeError("Primary API returned no matches")
    teams = [canonical_team(x) for x in teams_raw]
    by_id = {str(t["id"]): t for t in teams}
    stadiums = {str(x.get("id") or x.get("_id") or ""): x for x in stadium_raw}
    matches = [canonical_match(g, by_id, stadiums) for g in games]
    return teams, matches, "worldcup26.ir"


def from_openfootball():
    data = fetch_json(OPENFOOTBALL)
    raw_matches = data.get("matches", []) if isinstance(data, dict) else []
    if not raw_matches: raise RuntimeError("OpenFootball returned no matches")
    static_teams, by_name = load_static_team_map()
    dynamic = {}
    matches = []
    for idx, m in enumerate(raw_matches, 1):
        hname = str(m.get("team1") or "Chưa xác định")
        aname = str(m.get("team2") or "Chưa xác định")
        for name in (hname, aname):
            if name.casefold() not in by_name:
                by_name[name.casefold()] = {"id": name, "name": name, "code":"", "iso2":"", "group": str(m.get("group") or "").replace("Group ","").upper()}
                dynamic[name.casefold()] = by_name[name.casefold()]
        ht, at = by_name[hname.casefold()], by_name[aname.casefold()]
        dt = parse_local_with_offset(m.get("date"), m.get("time"))
        vn_dt = dt.astimezone(VN) if dt else None
        score = m.get("score") or {}
        ft = score.get("ft") if isinstance(score, dict) else None
        finished = isinstance(ft, list) and len(ft) >= 2 and all(x is not None for x in ft[:2])
        group = str(m.get("group") or "").replace("Group ","").upper()
        round_name = str(m.get("round") or "").lower()
        stage = "group" if group else ("final" if "final" == round_name else "r32" if "32" in round_name else "r16" if "16" in round_name else "qf" if "quarter" in round_name else "sf" if "semi" in round_name else "third" if "third" in round_name else round_name or "knockout")
        matches.append({
            "id": str(idx), "stage": stage, "group": group, "matchday": 0,
            "kickoff_utc": dt.isoformat().replace("+00:00","Z") if dt else "",
            "date_vn": vn_dt.strftime("%Y-%m-%d") if vn_dt else str(m.get("date") or ""),
            "time_vn": vn_dt.strftime("%H:%M") if vn_dt else "",
            "status": "finished" if finished else "upcoming", "elapsed":"",
            "home": {k:ht.get(k,"") for k in ("id","name","code","iso2")},
            "away": {k:at.get(k,"") for k in ("id","name","code","iso2")},
            "score": {"home": n(ft[0]) if finished else None, "away": n(ft[1]) if finished else None},
            "venue": str(m.get("ground") or ""),
        })
    teams_by_name = {t["name"].casefold(): t for t in static_teams}
    teams_by_name.update(dynamic)
    return list(teams_by_name.values()), matches, "openfootball/worldcup.json"


def validate(teams, matches):
    if len(matches) < 60: raise RuntimeError(f"Only {len(matches)} matches")
    if not any(m.get("date_vn") for m in matches): raise RuntimeError("No valid dates")
    return True


def main():
    errors = []
    for loader in (from_primary, from_openfootball):
        try:
            teams, matches, source = loader(); validate(teams, matches); break
        except Exception as e:
            errors.append(f"{loader.__name__}: {e}")
            print(errors[-1], file=sys.stderr)
    else:
        raise RuntimeError("All sources failed; existing data file is preserved. " + " | ".join(errors))
    payload = {"meta":{"updated_at":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),"source":source,"timezone":"Asia/Ho_Chi_Minh","version":3},"teams":teams,"matches":matches}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {OUT}: {len(teams)} teams, {len(matches)} matches, source={source}")

if __name__ == "__main__":
    main()
