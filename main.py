#!/usr/bin/env python3
"""Deterministic Roblox Up-and-Coming forecaster (stdlib only)."""
import datetime as dt
import json
import math
import os
from collections import defaultdict
from pathlib import Path

INPUT = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))


def stamp(value):
    """Parse the recorder's UTC timestamps without depending on local time."""
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def num(value, default=0.0):
    return float(value) if isinstance(value, (int, float)) else default


def bounded(value, low, high):
    return max(low, min(high, value))


def softmax(values, temperature):
    peak = max(values)
    weights = [math.exp((value - peak) / temperature) for value in values]
    total = sum(weights)
    return [weight / total for weight in weights]


def named_probabilities(ids, values, mass):
    """Round a softmax while preserving the deliberate unnamed probability share."""
    rounded = [round(mass * value, 12) for value in values]
    overflow = sum(rounded) - mass
    if overflow > 0.0:
        rounded[-1] = round(rounded[-1] - overflow, 12)
    return list(zip(ids, rounded))


def load_task():
    task = json.loads((INPUT / "task.json").read_text(encoding="utf-8"))
    if not isinstance(task, dict) or not isinstance(task.get("output"), str):
        raise ValueError("task.json must provide an output filename")
    places = task.get("places")
    if not isinstance(places, int) or places < 1 or places > 100:
        raise ValueError("task.json places must be an integer from 1 to 100")
    return task, places


def main():
    task, places = load_task()
    lines = (INPUT / "history.ndjson").read_text(encoding="utf-8").splitlines()
    snapshots = [json.loads(line) for line in lines if line.strip()]
    if not snapshots:
        raise ValueError("history.ndjson has no snapshots")

    last = snapshots[-1]
    last_chart = sorted(
        last.get("up_and_coming") or [],
        key=lambda row: (num(row.get("rank"), 9999), num(row.get("universe_id"))),
    )
    if len(last_chart) < places:
        raise ValueError("last chart does not contain enough games")

    series = defaultdict(list)
    details = {}
    cross = defaultdict(list)
    observed = set()
    for index, snapshot in enumerate(snapshots):
        at = stamp(snapshot.get("at"))
        for row in snapshot.get("up_and_coming") or []:
            uid = row.get("universe_id")
            if not isinstance(uid, int):
                continue
            observed.add(uid)
            series[uid].append((index, at, num(row.get("rank"), 9999), num(row.get("playing"))))
        for uid_text, detail in (snapshot.get("details") or {}).items():
            if not isinstance(detail, dict):
                continue
            try:
                uid = int(uid_text)
            except (TypeError, ValueError):
                continue
            details[uid] = detail
        for chart_name in ("top_trending", "top_playing_now"):
            for row in snapshot.get(chart_name) or []:
                uid = row.get("universe_id")
                if isinstance(uid, int):
                    cross[uid].append((index, num(row.get("rank"), 9999)))

    last_time = stamp(last.get("at")) or 0.0
    current_rank = {
        row["universe_id"]: num(row.get("rank"), 9999)
        for row in last_chart
        if isinstance(row.get("universe_id"), int)
    }
    scores = {}
    for uid in sorted(current_rank):
        history = series[uid]
        _, now_time, rank_now, playing_now = history[-1]
        _, old_time, old_rank, old_playing = history[max(0, len(history) - 6)]
        elapsed_days = max(0.25, ((now_time or last_time) - (old_time or last_time)) / 86400.0)
        rank_velocity = bounded((old_rank - rank_now) / elapsed_days, -12.0, 12.0)
        growth = bounded(math.log((playing_now + 10.0) / (old_playing + 10.0)), -2.0, 2.0)

        cross_bonus = 0.0
        recent_cutoff = len(snapshots) - 4
        for seen_index, rank in cross.get(uid, []):
            if seen_index >= recent_cutoff:
                cross_bonus = max(cross_bonus, max(0.0, 1.0 - rank / 100.0))

        created_time = stamp(details.get(uid, {}).get("created"))
        age_days = ((last_time - created_time) / 86400.0) if created_time else 12.0
        age_factor = 0.0
        if age_days > 24.0:
            age_factor -= bounded((age_days - 24.0) * 0.55, 0.0, 4.0)
        elif age_days < 5.0:
            age_factor += 0.45 + 0.12 * max(0.0, rank_velocity)
        elif age_days < 10.0:
            age_factor += 0.20

        rank_score = max(0.0, 42.0 - rank_now) / 7.0
        scores[uid] = rank_score + 0.34 * rank_velocity + 1.05 * growth + 1.15 * cross_bonus + age_factor

    ordered = sorted(scores, key=lambda uid: (-scores[uid], current_rank[uid], uid))
    candidates = ordered[:min(len(ordered), max(15, places + 5))]
    probabilities = []
    for place in range(1, places + 1):
        place_scores = [scores[uid] - 0.24 * abs(current_rank[uid] - place) for uid in candidates]
        for uid, probability in named_probabilities(candidates, softmax(place_scores, 1.5), 0.80):
            probabilities.append({"universe_id": uid, "place": place, "p": probability})

    top10 = ordered[:places]
    if len(top10) != places or len(set(top10)) != places or not set(top10).issubset(observed):
        raise ValueError("could not form a valid top10")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    forecast = {"probabilities": probabilities, "top10": top10}
    (OUTPUT / task["output"]).write_text(
        json.dumps(forecast, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
