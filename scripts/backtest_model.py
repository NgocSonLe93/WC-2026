#!/usr/bin/env python3
"""Walk-forward backtest for the World Cup prediction model.

The script deliberately uses only information available before each match.
Historical team strength is represented by a sequential Elo rating, avoiding
future FIFA-ranking leakage. It compares:
  1) class-frequency baseline,
  2) rating-only multinomial baseline,
  3) raw recent-form + Poisson model,
  4) temperature-calibrated Poisson model.

Only Python's standard library is required.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "recent_matches.json"
WORLD_CUP_PATH = ROOT / "data" / "worldcup.json"
OUTPUT_PATH = ROOT / "data" / "model_evaluation.json"

TEST_START = "2024-01-01"
MIN_FULL_HISTORY = 10
MAX_RECENT = 10
MAX_SCORE = 10
EPS = 1e-15

ALIASES = {
    "IRI": "IRN", "DZA": "ALG", "HTI": "HAI", "DRC": "COD", "DRK": "COD",
    "SCT": "SCO", "KOR": "KOR", "TUR": "TUR",
}


def clamp(v: float, low: float, high: float) -> float:
    return max(low, min(high, v))


def canonical(code: str) -> str:
    raw = str(code or "").strip().upper()
    return ALIASES.get(raw, raw)


def parse_time(raw: str) -> float:
    text = str(raw or "").strip()
    if not text:
        return 0.0
    if len(text) == 10:
        text += "T12:00:00Z"
    text = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def tournament_weight(name: str) -> float:
    s = str(name or "").lower()
    if "fifa world cup" in s and "qualification" not in s and "qualifier" not in s:
        return 1.20
    if "world cup qualification" in s or "world cup qualifier" in s:
        return 1.05
    official = (
        "uefa euro", "copa américa", "copa america", "african cup", "africa cup",
        "asian cup", "gold cup", "oceania nations", "concacaf championship",
    )
    if any(x in s for x in official):
        return 1.05
    if "nations league" in s:
        return 0.95
    if "friendly" in s:
        return 0.70
    return 0.90


@dataclass(frozen=True)
class Match:
    id: str
    date: str
    kickoff_utc: str
    tournament: str
    neutral: bool
    home_code: str
    home_name: str
    away_code: str
    away_name: str
    home_goals: int
    away_goals: int

    @property
    def timestamp(self) -> float:
        return parse_time(self.kickoff_utc or self.date)

    @property
    def result(self) -> int:
        # 0 home win, 1 draw, 2 away win
        if self.home_goals > self.away_goals:
            return 0
        if self.home_goals == self.away_goals:
            return 1
        return 2


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_history_match(raw: dict, idx: int) -> Match | None:
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    score = raw.get("score") or {}
    hc, ac = canonical(home.get("code")), canonical(away.get("code"))
    try:
        hg, ag = int(score.get("home")), int(score.get("away"))
    except (TypeError, ValueError):
        return None
    if not hc or not ac:
        return None
    date = str(raw.get("date") or raw.get("kickoff_utc") or "")[:10]
    kickoff = str(raw.get("kickoff_utc") or (date + "T12:00:00Z" if date else ""))
    return Match(
        id=str(raw.get("id") or f"history-{idx}"), date=date, kickoff_utc=kickoff,
        tournament=str(raw.get("tournament") or "International"), neutral=bool(raw.get("neutral", True)),
        home_code=hc, home_name=str(home.get("name") or hc),
        away_code=ac, away_name=str(away.get("name") or ac),
        home_goals=hg, away_goals=ag,
    )


def normalize_world_cup_match(raw: dict, idx: int) -> Match | None:
    if str(raw.get("status")) != "finished":
        return None
    home = raw.get("home") or {}
    away = raw.get("away") or {}
    score = raw.get("score") or {}
    hc, ac = canonical(home.get("code")), canonical(away.get("code"))
    try:
        hg, ag = int(score.get("home")), int(score.get("away"))
    except (TypeError, ValueError):
        return None
    if not hc or not ac:
        return None
    kickoff = str(raw.get("kickoff_utc") or "")
    date = str(raw.get("date_vn") or kickoff)[:10]
    return Match(
        id=f"wc-{raw.get('id', idx)}", date=date, kickoff_utc=kickoff or date + "T12:00:00Z",
        tournament="FIFA World Cup 2026", neutral=True,
        home_code=hc, home_name=str(home.get("name") or hc),
        away_code=ac, away_name=str(away.get("name") or ac),
        home_goals=hg, away_goals=ag,
    )


def load_matches() -> List[Match]:
    merged: Dict[Tuple[str, str, str, int, int], Match] = {}
    history = load_json(HISTORY_PATH)
    for idx, raw in enumerate(history.get("matches") or []):
        m = normalize_history_match(raw, idx)
        if m:
            merged[(m.date, m.home_code, m.away_code, m.home_goals, m.away_goals)] = m
    wc = load_json(WORLD_CUP_PATH)
    for idx, raw in enumerate(wc.get("matches") or []):
        m = normalize_world_cup_match(raw, idx)
        if m:
            merged[(m.date, m.home_code, m.away_code, m.home_goals, m.away_goals)] = m
    return sorted(merged.values(), key=lambda x: (x.timestamp, x.id))


def poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def normalize_probs(values: Sequence[float]) -> List[float]:
    vals = [max(EPS, float(x)) for x in values]
    total = sum(vals)
    return [x / total for x in vals]


def temperature_scale(probs: Sequence[float], temperature: float) -> List[float]:
    t = max(0.05, temperature)
    powered = [max(EPS, p) ** (1.0 / t) for p in probs]
    return normalize_probs(powered)


def outcome_metrics(rows: Sequence[dict], prob_key: str) -> dict:
    if not rows:
        return {"matches": 0, "brier": None, "log_loss": None, "accuracy": None, "ece": None}
    brier = log_loss = correct = 0.0
    observations: List[Tuple[float, int]] = []
    for row in rows:
        probs = normalize_probs(row[prob_key])
        y = row["result"]
        brier += sum((probs[j] - (1.0 if j == y else 0.0)) ** 2 for j in range(3))
        log_loss += -math.log(max(EPS, probs[y]))
        correct += int(max(range(3), key=lambda j: probs[j]) == y)
        observations.extend((probs[j], 1 if j == y else 0) for j in range(3))
    bins = calibration_bins(observations)
    return {
        "matches": len(rows),
        "brier": brier / len(rows),
        "log_loss": log_loss / len(rows),
        "accuracy": correct / len(rows),
        "ece": bins["ece"],
    }


def calibration_bins(observations: Sequence[Tuple[float, int]], bins_count: int = 10) -> dict:
    buckets = [[] for _ in range(bins_count)]
    for p, y in observations:
        idx = min(bins_count - 1, int(clamp(p, 0.0, 0.999999) * bins_count))
        buckets[idx].append((p, y))
    total = max(1, len(observations))
    rows = []
    ece = 0.0
    for idx, bucket in enumerate(buckets):
        low, high = idx / bins_count, (idx + 1) / bins_count
        if bucket:
            avg_pred = sum(p for p, _ in bucket) / len(bucket)
            observed = sum(y for _, y in bucket) / len(bucket)
            ece += len(bucket) / total * abs(avg_pred - observed)
        else:
            avg_pred = observed = None
        rows.append({
            "label": f"{int(low*100)}–{int(high*100)}%", "low": low, "high": high,
            "count": len(bucket), "predicted": avg_pred, "observed": observed,
        })
    return {"ece": ece, "bins": rows}


def softmax(scores: Sequence[float]) -> List[float]:
    m = max(scores)
    vals = [math.exp(s - m) for s in scores]
    return normalize_probs(vals)


def baseline_features(row: dict) -> List[float]:
    d = clamp(row["elo_diff"] / 400.0, -3.0, 3.0)
    return [1.0, d, abs(d), 0.0 if row["neutral"] else 1.0]


def train_softmax(rows: Sequence[dict], epochs: int = 2200, lr: float = 0.045, l2: float = 0.002) -> List[List[float]]:
    feature_count = 4
    weights = [[0.0] * feature_count for _ in range(3)]
    if not rows:
        return weights
    n = len(rows)
    for epoch in range(epochs):
        grads = [[0.0] * feature_count for _ in range(3)]
        for row in rows:
            x = baseline_features(row)
            scores = [sum(weights[c][j] * x[j] for j in range(feature_count)) for c in range(3)]
            probs = softmax(scores)
            for c in range(3):
                err = probs[c] - (1.0 if row["result"] == c else 0.0)
                for j in range(feature_count):
                    grads[c][j] += err * x[j]
        step = lr / math.sqrt(1.0 + epoch / 350.0)
        for c in range(3):
            for j in range(feature_count):
                reg = l2 * weights[c][j] if j else 0.0
                weights[c][j] -= step * (grads[c][j] / n + reg)
    return weights


def softmax_predict(weights: Sequence[Sequence[float]], row: dict) -> List[float]:
    x = baseline_features(row)
    return softmax([sum(weights[c][j] * x[j] for j in range(len(x))) for c in range(3)])


def result_points(gf: int, ga: int) -> int:
    return 3 if gf > ga else 1 if gf == ga else 0


def weighted_team_summary(code: str, history: Sequence[dict], elo: Dict[str, float], base: float) -> dict:
    rows = list(history)[-MAX_RECENT:][::-1]
    if not rows:
        return {"count": 0, "gfpg": base, "gapg": base, "ppg": 1.25, "form": 0.5}
    weighted = []
    for idx, row in enumerate(rows):
        recency = math.exp(-0.15 * idx)
        type_w = tournament_weight(row["tournament"])
        opp_rating = float(row.get("opp_elo", 1500.0))
        attack_adj = clamp(opp_rating / 1500.0, 0.84, 1.16)
        defense_adj = clamp(1500.0 / max(800.0, opp_rating), 0.84, 1.16)
        w = recency * type_w
        weighted.append({
            "w": w, "gf": row["gf"] * attack_adj, "ga": row["ga"] * defense_adj,
            "points": result_points(row["gf"], row["ga"]),
            "form": 1.0 if row["gf"] > row["ga"] else 0.5 if row["gf"] == row["ga"] else 0.0,
        })

    def slice_summary(items: Sequence[dict]) -> dict:
        if not items:
            return {"count": 0, "gfpg": base, "gapg": base, "ppg": 1.25, "form": 0.5}
        total_w = sum(x["w"] for x in items) or 1.0
        return {
            "count": len(items),
            "gfpg": sum(x["gf"] * x["w"] for x in items) / total_w,
            "gapg": sum(x["ga"] * x["w"] for x in items) / total_w,
            "ppg": sum(x["points"] * x["w"] for x in items) / total_w,
            "form": sum(x["form"] * x["w"] for x in items) / total_w,
        }

    newest, older = slice_summary(weighted[:5]), slice_summary(weighted[5:10])

    def blend(key: str, default: float) -> float:
        if newest["count"] and older["count"]:
            return 0.75 * newest[key] + 0.25 * older[key]
        if newest["count"]:
            return newest[key]
        if older["count"]:
            return older[key]
        return default

    return {
        "count": len(rows), "gfpg": blend("gfpg", base), "gapg": blend("gapg", base),
        "ppg": blend("ppg", 1.25), "form": blend("form", 0.5),
    }


def poisson_prediction(home_stats: dict, away_stats: dict, home_elo: float, away_elo: float, base: float, neutral: bool) -> dict:
    h_attack = clamp(home_stats["gfpg"] / base, 0.55, 1.85)
    h_concede = clamp(home_stats["gapg"] / base, 0.55, 1.85)
    a_attack = clamp(away_stats["gfpg"] / base, 0.55, 1.85)
    a_concede = clamp(away_stats["gapg"] / base, 0.55, 1.85)
    rating_diff = clamp((home_elo - away_elo) / 1050.0, -0.62, 0.62)
    fifa_home, fifa_away = math.exp(rating_diff), math.exp(-rating_diff)
    form_home = clamp(0.90 + 0.20 * home_stats["form"], 0.90, 1.10)
    form_away = clamp(0.90 + 0.20 * away_stats["form"], 0.90, 1.10)
    ppg_diff = clamp((home_stats["ppg"] - away_stats["ppg"]) / 3.0, -1.0, 1.0)
    ppg_home, ppg_away = 1.0 + 0.10 * ppg_diff, 1.0 - 0.10 * ppg_diff
    home_field = 1.07 if not neutral else 1.0
    away_field = 0.95 if not neutral else 1.0
    home_lam = clamp(base * math.sqrt(h_attack * a_concede) * fifa_home * form_home * ppg_home * home_field, 0.18, 3.80)
    away_lam = clamp(base * math.sqrt(a_attack * h_concede) * fifa_away * form_away * ppg_away * away_field, 0.18, 3.80)
    scores = []
    outcomes = [0.0, 0.0, 0.0]
    mass = 0.0
    for hg in range(MAX_SCORE + 1):
        ph = poisson(hg, home_lam)
        for ag in range(MAX_SCORE + 1):
            p = ph * poisson(ag, away_lam)
            mass += p
            outcomes[0 if hg > ag else 1 if hg == ag else 2] += p
            scores.append((p, hg, ag))
    outcomes = [x / mass for x in outcomes]
    scores = sorted(((p / mass, hg, ag) for p, hg, ag in scores), reverse=True)
    return {"probs": outcomes, "home_lambda": home_lam, "away_lambda": away_lam, "scores": scores}


def update_elo(elo: Dict[str, float], m: Match, k: float = 24.0) -> None:
    rh, ra = elo[m.home_code], elo[m.away_code]
    home_adv = 0.0 if m.neutral else 65.0
    expected_h = 1.0 / (1.0 + 10.0 ** (-(rh + home_adv - ra) / 400.0))
    actual_h = 1.0 if m.home_goals > m.away_goals else 0.5 if m.home_goals == m.away_goals else 0.0
    margin = abs(m.home_goals - m.away_goals)
    margin_mult = 1.0 if margin <= 1 else math.log(margin + 1.0) * (2.2 / ((rh - ra) * 0.001 + 2.2))
    delta = k * margin_mult * (actual_h - expected_h)
    elo[m.home_code] = rh + delta
    elo[m.away_code] = ra - delta


def build_walk_forward_rows(matches: Sequence[Match]) -> Tuple[List[dict], dict]:
    elo: Dict[str, float] = defaultdict(lambda: 1500.0)
    histories: Dict[str, deque] = defaultdict(lambda: deque(maxlen=40))
    prior_matches: deque = deque(maxlen=250)
    rows: List[dict] = []
    excluded = Counter()

    for m in matches:
        if not m.timestamp:
            excluded["invalid_time"] += 1
            continue
        prior_goal_count = sum(x.home_goals + x.away_goals for x in prior_matches)
        base = clamp(prior_goal_count / (2.0 * len(prior_matches)), 0.90, 1.85) if len(prior_matches) >= 8 else 1.35
        h_hist, a_hist = histories[m.home_code], histories[m.away_code]
        h_stats = weighted_team_summary(m.home_code, h_hist, elo, base)
        a_stats = weighted_team_summary(m.away_code, a_hist, elo, base)
        h_elo, a_elo = elo[m.home_code], elo[m.away_code]
        pred = poisson_prediction(h_stats, a_stats, h_elo, a_elo, base, m.neutral)
        rows.append({
            "id": m.id, "date": m.date, "timestamp": m.timestamp, "tournament": m.tournament,
            "neutral": m.neutral, "home_code": m.home_code, "home_name": m.home_name,
            "away_code": m.away_code, "away_name": m.away_name,
            "home_goals": m.home_goals, "away_goals": m.away_goals, "result": m.result,
            "home_history": len(h_hist), "away_history": len(a_hist),
            "elo_diff": h_elo - a_elo, "raw_probs": pred["probs"],
            "home_lambda": pred["home_lambda"], "away_lambda": pred["away_lambda"],
            "score_probs": pred["scores"],
        })
        update_elo(elo, m)
        histories[m.home_code].append({"gf": m.home_goals, "ga": m.away_goals, "opp_elo": a_elo, "tournament": m.tournament})
        histories[m.away_code].append({"gf": m.away_goals, "ga": m.home_goals, "opp_elo": h_elo, "tournament": m.tournament})
        prior_matches.append(m)
    return rows, dict(excluded)


def class_prior(rows: Sequence[dict]) -> List[float]:
    counts = [1.0, 1.0, 1.0]
    for row in rows:
        counts[row["result"]] += 1.0
    return normalize_probs(counts)


def choose_temperature(rows: Sequence[dict]) -> float:
    if not rows:
        return 1.0
    best_t, best_loss = 1.0, float("inf")
    for step in range(55, 251):
        t = step / 100.0
        loss = 0.0
        for row in rows:
            probs = temperature_scale(row["raw_probs"], t)
            loss += -math.log(max(EPS, probs[row["result"]]))
        loss /= len(rows)
        if loss < best_loss:
            best_t, best_loss = t, loss
    return best_t


def goal_metrics(rows: Sequence[dict]) -> dict:
    if not rows:
        return {"team_goal_mae": None, "total_goal_mae": None, "poisson_deviance": None, "top1_score": None, "top3_score": None, "top5_score": None}
    team_mae = total_mae = deviance = 0.0
    top_hits = {1: 0, 3: 0, 5: 0}
    for row in rows:
        hg, ag = row["home_goals"], row["away_goals"]
        hl, al = row["home_lambda"], row["away_lambda"]
        team_mae += (abs(hl - hg) + abs(al - ag)) / 2.0
        total_mae += abs((hl + al) - (hg + ag))
        for y, lam in ((hg, hl), (ag, al)):
            deviance += 2.0 * ((y * math.log(y / lam) if y > 0 else 0.0) - (y - lam))
        ranked = [(x[1], x[2]) for x in row["score_probs"]]
        true_score = (hg, ag)
        for k in top_hits:
            top_hits[k] += int(true_score in ranked[:k])
    n = len(rows)
    return {
        "team_goal_mae": team_mae / n,
        "total_goal_mae": total_mae / n,
        "poisson_deviance": deviance / (2.0 * n),
        "top1_score": top_hits[1] / n,
        "top3_score": top_hits[3] / n,
        "top5_score": top_hits[5] / n,
    }


def year_metrics(rows: Sequence[dict], prob_key: str) -> List[dict]:
    groups: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        groups[row["date"][:4]].append(row)
    result = []
    for year in sorted(groups):
        metrics = outcome_metrics(groups[year], prob_key)
        result.append({"year": year, **metrics})
    return result


def worst_errors(rows: Sequence[dict], prob_key: str, limit: int = 12) -> List[dict]:
    labels = ["Thắng đội 1", "Hòa", "Thắng đội 2"]
    bad = []
    for row in rows:
        probs = row[prob_key]
        predicted = max(range(3), key=lambda j: probs[j])
        if predicted == row["result"]:
            continue
        bad.append({
            "date": row["date"], "match": f"{row['home_name']} – {row['away_name']}",
            "score": f"{row['home_goals']}–{row['away_goals']}",
            "predicted": labels[predicted], "actual": labels[row["result"]],
            "confidence": probs[predicted], "probabilities": probs,
        })
    bad.sort(key=lambda x: x["confidence"], reverse=True)
    return bad[:limit]


def main() -> None:
    matches = load_matches()
    rows, excluded = build_walk_forward_rows(matches)
    train = [r for r in rows if r["date"] < TEST_START and r["home_history"] >= 5 and r["away_history"] >= 5]
    test_all = [r for r in rows if r["date"] >= TEST_START and r["home_history"] >= 5 and r["away_history"] >= 5]
    test_full = [r for r in test_all if r["home_history"] >= MIN_FULL_HISTORY and r["away_history"] >= MIN_FULL_HISTORY]
    test = test_full or test_all

    prior = class_prior(train)
    weights = train_softmax(train)
    temperature = choose_temperature(train)
    for row in rows:
        row["prior_probs"] = prior
        row["elo_probs"] = softmax_predict(weights, row)
        row["calibrated_probs"] = temperature_scale(row["raw_probs"], temperature)

    model_specs = [
        ("prior", "Tỷ lệ cố định", "prior_probs"),
        ("rating", "Rating-only baseline", "elo_probs"),
        ("poisson_raw", "Poisson thô", "raw_probs"),
        ("poisson_calibrated", "Poisson đã hiệu chỉnh", "calibrated_probs"),
    ]
    models = {}
    for key, label, pkey in model_specs:
        models[key] = {"label": label, **outcome_metrics(test, pkey)}

    calibration = calibration_bins([
        (row["calibrated_probs"][j], 1 if row["result"] == j else 0)
        for row in test for j in range(3)
    ])

    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_matches": len(matches), "walk_forward_rows": len(rows),
            "train_matches": len(train), "test_matches": len(test),
            "test_matches_full_10": len(test_full), "test_matches_min_5": len(test_all),
            "test_start": TEST_START, "minimum_history_primary": MIN_FULL_HISTORY,
            "temperature": temperature,
            "method": "Walk-forward; only pre-match data; sequential Elo proxy; 10 recent matches; 2024+ holdout",
            "note": "Historical FIFA snapshots are not bundled. Validation uses a pre-match sequential Elo rating to avoid future-ranking leakage.",
        },
        "models": models,
        "calibration": calibration,
        "goals": goal_metrics(test),
        "by_year": year_metrics(test, "calibrated_probs"),
        "worst_errors": worst_errors(test, "calibrated_probs"),
        "coefficients": {
            "rating_baseline_weights": weights,
            "class_prior": prior,
            "temperature": temperature,
        },
        "data_quality": {
            "excluded": excluded,
            "test_excluded_for_under_5": len([r for r in rows if r["date"] >= TEST_START and (r["home_history"] < 5 or r["away_history"] < 5)]),
            "test_partial_5_to_9": len(test_all) - len(test_full),
        },
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} | test={len(test)} | T={temperature:.2f}")
    for key, item in models.items():
        print(key, {k: round(v, 4) if isinstance(v, float) else v for k, v in item.items() if k != 'label'})


if __name__ == "__main__":
    main()
