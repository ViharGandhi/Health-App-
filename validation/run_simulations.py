"""Reproducible offline audit. Does not modify production algorithms."""
from __future__ import annotations

import ast
import csv
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import random
from statistics import NormalDist, mean, median
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from strain import calculate_strain, strain_score, day_window, strain_analytics
from strain_service import demo_inputs, calculate_days, strain_response
from recovery_score import calculate_recovery, recovery_from_history, baseline_bounds
from recovery import RecoveryCalculator, RecoveryInput
from sleep_need import calculate_sleep_need, SleepNeedNight, strain_sleep_add
from sleep_efficiency import SleepEfficiencyCalculator
from sleep_consistency import SleepNight, score_main_sleep, SleepConsistencyCalculator
from sleepscore import SleepCalculator, SleepData, AyurvedicSleepCalculator
from sleep_stage_ranges import SleepNight as StageNight, StageSegment, stage_stats, personal_ranges
from sleep_stress import SleepNight as StressNight, StageSegment as StressSegment, ValidWindow, NightWindows, score_night, build_baseline
from health_trends import build_health_response, build_heart_rate_response
from sleep_trends import build_sleep_trend, range_start
from zoneinfo import ZoneInfo

OUT = ROOT / "validation"
DAY = date(2026, 10, 7)
BASE = datetime(2026, 10, 7, 7, tzinfo=timezone.utc)
SEED = 20261007
rng = random.Random(SEED)
rows, findings, snapshots = [], [], {}


def equal(actual, expected, tolerance):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and equal(actual[k], v, tolerance) for k, v in expected.items())
    if isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(equal(a, e, tolerance) for a, e in zip(actual, expected))
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        return actual == expected
    return isinstance(actual, (int, float)) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance)


def check(family, name, inputs, expected, actual, tolerance=1e-9):
    rows.append(dict(family=family, case=name, inputs=inputs, expected=expected, actual=actual,
                     tolerance=tolerance, passed=equal(actual, expected, tolerance)))


def finding(title, data, inference):
    findings.append(dict(title=title, data=data, inference=inference))


def cardio(hr, minutes, age=30, rest=56, sex="m", gap=60):
    samples = [(BASE + timedelta(seconds=i * gap), hr) for i in range(round(minutes * 60 / gap) + 1)]
    window = dict(start=BASE, end=BASE + timedelta(minutes=minutes))
    return calculate_strain(samples, [], window, age, [rest] * 7, sex)


def reference_recovery(baseline, recent, today, rhrs, rhr, sleep, need, illness=False):
    transformed = [math.log(v) for v in baseline]
    center = median(transformed)
    spread = max(1.4826 * median([abs(x - center) for x in transformed]), .05)
    signal = mean(math.log(v) for v in recent)
    if today is not None:
        signal = .7 * signal + .3 * math.log(today)
    zh = (signal - center) / spread
    zr = None
    if rhr is not None and len(rhrs) >= 21:
        rm = median(rhrs)
        rs = max(1.4826 * median([abs(v - rm) for v in rhrs]), 1.)
        zr = (rm - rhr) / rs
    performance = min(sleep / need, 1.) if sleep is not None and sleep >= 180 and need else None
    adj = -.5 * max(0., min(1., (.85 - performance) / .25)) if performance is not None else 0.
    z = max(-3., min(3., (.6 * zh + .4 * zr if zr is not None else zh) + adj))
    if illness:
        z = min(z, -.5)
    confidence = ("high" if len(baseline) >= 45 and len(recent) >= 6 and zr is not None and performance is not None
                  else "medium" if len(baseline) >= 28 and len(recent) >= 5 else "low")
    return dict(z=round(z, 2), percent=round(100 * NormalDist().cdf(z)) if confidence != "low" else None,
                zone="below_normal" if z < -.5 else "above_normal" if z > .5 else "normal", confidence=confidence,
                components=dict(z_hrv=zh, z_rhr=zr, sleep_adj=adj))


def sleep_data(hours=7.5, need=7.5, age=30, awake=20, interruptions=2):
    deep = max(.1, .2 - max(0, age - 30) * .002)
    return SleepData(hours * 3600, hours * deep * 3600, hours * .25 * 3600,
                     hours * (1 - deep - .25) * 3600, awake * 60, hours * 3600 + awake * 60,
                     datetime(2026, 10, 6, 23), datetime(2026, 10, 7, 7), interruptions)


def sleep_reference(data, need, age, shrv=45., shr=56., whr=72.):
    ratio = (data.total_duration + data.nap_duration_seconds) / 3600 / need
    # Product-approved sigmoid normalization (2026-10-08); coefficients stay unchanged.
    duration = (100 * (1 + math.exp(-2)) / (1 + math.exp(-8 * (ratio - .75))) if ratio <= 1 else 100 if ratio <= 1.1
                else max(30., 100 - (ratio - 1.1) * 75))
    target = max(.1, .2 - max(0, age - 30) * .002)
    stage = sum(w * min(100., 100 * v / (need * 3600 * t)) for w, v, t in
                ((.4, data.deep_sleep_duration, target), (.4, data.rem_sleep_duration, .20), (.2, data.core_sleep_duration, .5)))
    bounded = lambda v: max(0., min(100., v))
    components = dict(duration=duration, stage=stage,
        efficiency=bounded((data.total_duration / data.in_bed_duration - .7) / .25 * 100),
        hrv=bounded((shrv / 45 - .7) / .6 * 100), hr=bounded((1.3 - shr / 56) / .6 * 100),
        dip=bounded((whr - shr) / whr / .25 * 100),
        restfulness=bounded(100 * math.exp(-.035 * data.awake_duration / 60) - min(15., data.interruption_count * 2.5)))
    score = sum(components[k] * w for k, w in zip(components, (.27, .20, .10, .05, .05, .18, .15)))
    return score, components


def make_stage(day, amounts):
    start = datetime.combine(day - timedelta(days=1), datetime.min.time(), timezone.utc).replace(hour=22)
    cursor, segments = start, []
    for name, minutes in zip(("awake", "light", "deep", "rem"), amounts):
        end = cursor + timedelta(minutes=minutes)
        if minutes:
            segments.append(StageSegment(cursor, end, name))
        cursor = end
    return StageNight(str(day), day, start, cursor, "STAGES", "SUCCEEDED", True, tuple(segments), main_sleep=True)


def stress_night(day, readings):
    start = datetime.combine(day - timedelta(days=1), datetime.min.time(), timezone.utc).replace(hour=23)
    night = StressNight(str(day), day, start, start + timedelta(hours=6), "STAGES",
                        (StressSegment(start, start + timedelta(hours=6), "LIGHT"),))
    cursor, windows = start, []
    for rmssd, hr, minutes in readings:
        end = cursor + timedelta(minutes=minutes)
        windows.append(ValidWindow(cursor, end, "LIGHT", math.log(rmssd), hr, minutes))
        cursor = end
    # Each synthetic night has 360 observed asleep minutes; windows cover all of it.
    return NightWindows(night, tuple(windows), 360., sum(w.minutes for w in windows) / 360.)


def run():
    # Closed-form continuous-HR cases and seeded parameter sweeps.
    for index in range(306):
        sex = "m" if index % 2 == 0 else "f"
        age, rest = (30, 56.) if index < 6 else (rng.randint(18, 100), rng.uniform(40, 85))
        hr, minutes = [(135, 45), (135, 45), (160, 45), (160, 45), (172, 60), (172, 60)][index] if index < 6 else (rng.uniform(30, 230), rng.randint(1, 240))
        hrr = max(0., min(1.1, (hr - rest) / max(208 - .7 * age - rest, 1)))
        a, b = (.64, 1.92) if sex == "m" else (.86, 1.67)
        load = minutes * hrr * a * math.exp(b * hrr) if hrr >= .2 else 0.
        score = min(math.nextafter(21., 0), 21 * (1 - math.exp(-load / 90)))
        value = cardio(hr, minutes, age, rest, sex)
        check("cardio strain", f"constant HR {index}", dict(age=age, rhr=rest, hr=hr, minutes=minutes, sex=sex, sample_interval_s=60),
              dict(load=load, strain=score, coverage=1.), {k: value[k] for k in ("load", "strain", "coverage")})
    for gap in (30, 60, 240, 300, 301, 600):
        result = cardio(160, gap / 60, gap=gap)
        check("cardio strain", f"gap {gap}s", dict(hr=160, gap_seconds=gap), gap / 60 if gap <= 300 else 0, result["counted_minutes"])
    tz = ZoneInfo("Europe/Berlin")
    first, last = datetime(2026, 10, 25, 2, 58, tzinfo=tz, fold=0), datetime(2026, 10, 25, 2, 2, tzinfo=tz, fold=1)
    value = calculate_strain([(first, 160), (last, 160)], [], dict(start=first, end=last), 30, [56], "m")
    check("cardio strain", "DST repeated hour", dict(start=first.isoformat(), end=last.isoformat()), dict(counted_minutes=4., coverage=1.), {k: value[k] for k in ("counted_minutes", "coverage")})
    for index in range(100):
        points = [(BASE, 125.)]
        for step in range(100):
            stamp = points[-1][0] + timedelta(seconds=rng.choice((30, 60, 90, 240, 300, 360)))
            points.append((stamp, 125 + 15 * math.sin(step / 9)))
        # Smooth values intentionally avoid the spike filter; test integration independently.
        session = dict(start=points[30][0], end=points[70][0], activity_name='Synthetic interval session')
        rest = 56.; hrmax = 187.; load = workout = counted = 0.
        for (t1,h1),(t2,h2) in zip(points,points[1:]):
            gap = (t2-t1).total_seconds()
            if gap > 300: continue
            minutes = gap/60; hrr = max(0,min(1.1,((h1+h2)/2-rest)/(hrmax-rest)))
            inc = minutes*hrr*.64*math.exp(1.92*hrr) if hrr>=.2 else 0
            load += inc; counted += minutes
            if session['start'] <= t1+(t2-t1)/2 <= session['end']: workout += inc
        result = calculate_strain(list(reversed(points)),[session],dict(start=BASE,end=points[-1][0]),30,[rest],'m')
        expected = dict(load=load,workout_load=workout,incidental_load=load-workout,counted_minutes=counted,
                        coverage=counted/((points[-1][0]-BASE).total_seconds()/60))
        check('cardio integration',f'irregular sinusoidal trace {index}',dict(age=30,rhr=rest,sex='m',samples=[[t.isoformat(),h] for t,h in points],workout_start=session['start'].isoformat(),workout_end=session['end'].isoformat()),expected,{k:result[k] for k in expected})
    history = [dict(date=DAY - timedelta(days=i), load=100 if i < 7 else 50, strain=10, coverage=1) for i in range(28)]
    check("strain analytics", "acute chronic ratio", dict(last_7_load=100, preceding_21_load=50), 1.6, strain_analytics(history, DAY, 12, 72)["acute_chronic_ratio"])
    inputs, steps = demo_inputs(DAY - timedelta(days=27), DAY, timezone.utc)
    values = calculate_days(DAY - timedelta(days=27), DAY, BASE.replace(hour=22), timezone.utc, 30, "m", False, inputs)
    snapshots["strain_demo_28_days"] = [dict(date=str(d), load=v["load"], strain=v["strain"], coverage=v["coverage"], steps=steps[d]) for d, v in values.items()]
    check("demo integrity", "raw strain inputs replay", dict(days=28, seed="date anchored"), snapshots["strain_demo_28_days"],
          [dict(date=str(d), load=v["load"], strain=v["strain"], coverage=v["coverage"], steps=steps[d]) for d, v in calculate_days(DAY - timedelta(days=27), DAY, BASE.replace(hour=22), timezone.utc, 30, "m", False, inputs).items()])

    for index in range(205):
        baseline = [40.] * 60 if index < 5 else [math.exp(rng.gauss(math.log(40), .12)) for _ in range(rng.randint(28, 60))]
        recent = [40.] * 7 if index < 5 else [rng.uniform(25, 70) for _ in range(7)]
        today, rhr, sleep, illness = [(40., 56., 450., False), (40., 56., 326.25, False), (80., 56., 450., False), (40., 56., 450., True), (40., None, None, False)][index] if index < 5 else (rng.uniform(15, 90), rng.uniform(45, 75), rng.uniform(180, 650), index % 11 == 0)
        rhrs = [56.] * 60
        data = dict(baseline_hrv=baseline, recent_hrv=recent, today_hrv=today, baseline_rhr=rhrs, today_rhr=rhr, sleep_min=sleep, need_min=450., illness_flag=illness)
        result = asdict(calculate_recovery(**data))
        expected = reference_recovery(baseline, recent, today, rhrs, rhr, sleep, 450., illness)
        check("connected recovery", f"robust reference {index}", data, expected, {k: result[k] for k in expected})
    for b, r in ((20, 7), (21, 3), (21, 4), (28, 5), (45, 6)):
        result = calculate_recovery([40] * b, [40] * r, 40, [56] * 60, 56, 450, 450)
        expected = dict(status="building_reference", confidence=None, percent=None) if b < 21 or r < 4 else dict(status="ok", confidence="low" if b < 28 or r < 5 else "high" if b >= 45 and r >= 6 else "medium", percent=None if b < 28 or r < 5 else 50)
        check("connected recovery", f"availability {b}/{r}", dict(baseline_nights=b, recent_nights=r), expected, {k: getattr(result, k) for k in expected})
    start, end = baseline_bounds(DAY)
    history = {"hrv": [dict(date=(start + timedelta(days=i)).isoformat(), value=40) for i in range(60)], "rhr": []}
    history["hrv"] += [dict(date=(DAY - timedelta(days=i)).isoformat(), value=40) for i in range(7)]
    history["hrv"] += [history["hrv"][0].copy(), dict(date=(DAY + timedelta(days=1)).isoformat(), value=999), dict(date=(DAY - timedelta(days=7)).isoformat(), value=999)]
    joined = recovery_from_history(history, DAY)
    # D-7 now belongs to the approved prior-seven-date signal; today is separate.
    join_z = min(3., .7 * math.log(999 / 40) / (7 * .05))
    check("date joins", "recovery dedup and excluded dates", dict(raw_rows=70, baseline_start=str(start), baseline_end=str(end)), dict(baseline_days=60, recent_nights=7, z=round(join_z, 2)), {k: getattr(joined, k) for k in ("baseline_days", "recent_nights", "z")})

    for index in range(202):
        percent = [0, 100][index] if index < 2 else rng.uniform(-20, 120)
        nap = 0 if index < 2 else rng.uniform(0, 180)
        actual = 450 if index < 2 else rng.uniform(180, 600)
        weights = [1, .85, .7, .55, .4, .25, .1]
        history = [SleepNeedNight(actual, percent)] * 7
        s = max(0, min(21, percent * .21))
        sigmoid = lambda x: 1 / (1 + math.exp(-.476 * (x - 14.38)))
        add = 26 * (sigmoid(s) - sigmoid(0)) / (sigmoid(21) - sigmoid(0))
        add = 0 if add < 1 else add
        debt = max(0, min(240, sum(w * (450 + add - actual) for w in weights) / sum(weights)))
        expected = dict(strain_add_min=add, sleep_debt_min=debt, debt_add_min=.34 * debt,
                        total_need_min=max(360, min(660, 450 + add + .34 * debt - nap)))
        result = asdict(calculate_sleep_need(percent, history, nap))
        check("sleep need", f"logistic and debt {index}", dict(strain_pct=percent, historical_sleep_min=actual, nap_min=nap, history_nights=7), expected, {k: result[k] for k in expected})

    for index in range(203):
        hours = [7.5, 7.500001, 3.75][index] if index < 3 else rng.uniform(2, 12)
        age = 30 if index < 3 else rng.randint(18, 100)
        awake = 20 if index < 3 else rng.uniform(0, 120)
        data = sleep_data(hours, age=age, awake=awake)
        score, components = sleep_reference(data, 7.5, age)
        actual = SleepCalculator.calculate_score(data, 7.5, 45, 56, 72, 45, 56, age)
        check("sleep score", f"weighted score {index}", dict(hours=hours, need_h=7.5, age=age, awake_min=awake, interruptions=2, hrv=45, sleeping_hr=56, waking_hr=72, components=components), score, actual)
    before = SleepCalculator.calculate_score(sleep_data(7.5), 7.5, 45, 56, 72, 45, 56, 30)
    after = SleepCalculator.calculate_score(sleep_data(7.500001), 7.5, 45, 56, 72, 45, 56, 30)
    finding("Sleep duration continuity regression", dict(at_7_5_h=before, at_7_500001_h=after, jump_points=after-before),
            "Approved sigmoid normalization reaches 100 at ratio 1; the prior 3.22-point discontinuity is removed. Oversleep penalty remains a product heuristic.")

    for asleep, bed, expected in ((27000, 28800, 93.8), (0, 28800, None), (30000, 28800, None), (27000, 0, None), (float('nan'), 28800, None), (86401, 86401, None)):
        check("sleep efficiency", f"{asleep}/{bed}", dict(asleep_s=str(asleep), period_s=bed), expected, SleepEfficiencyCalculator.calculate_single_night(asleep, bed))
    for index in range(100):
        bed = rng.uniform(60, 86400); asleep = rng.uniform(.01, bed)
        check("sleep efficiency", f"random {index}", dict(asleep_s=asleep, period_s=bed), round(100 * asleep / bed, 1), SleepEfficiencyCalculator.calculate_single_night(asleep, bed))
    for drift in (0, 30, 75, 120, 240, 720):
        current = SleepNight(DAY, BASE.replace(hour=23) - timedelta(days=1), BASE)
        previous = {DAY-timedelta(days=i): SleepNight(DAY-timedelta(days=i), current.bed_time-timedelta(days=i, minutes=drift), current.wake_time-timedelta(days=i, minutes=drift)) for i in range(1, 5)}
        raw = lambda x: 1 / (1 + math.exp(.05 * (x - 75)))
        expected = 0 if drift >= 240 else 100 * (raw(drift) - raw(240)) / (raw(0) - raw(240))
        result = score_main_sleep(current, previous)
        check("sleep consistency", f"clock drift {drift}", dict(drift_min=drift, prior_nights=4), dict(score=expected, drift_minutes=drift), dict(score=result.score, drift_minutes=result.drift_minutes))
    nights = [SleepNight(DAY-timedelta(days=i), BASE.replace(hour=23)-timedelta(days=i+1), BASE-timedelta(days=i)) for i in range(7)]
    check("sleep consistency", "seven fixed nights", dict(bed="23:00", wake="07:00", consecutive_nights=7), 0., SleepConsistencyCalculator.calculate(nights).timing_variability_minutes)
    check("sleep consistency", "missing calendar night", dict(nights=6), None, SleepConsistencyCalculator.calculate(nights[:6]).timing_variability_minutes)

    for index in range(100):
        amounts = [rng.randint(0, 60), rng.randint(180, 300), rng.randint(30, 100), rng.randint(30, 150)]
        stats, status = stage_stats(make_stage(DAY, amounts))
        expected = {s: 100 * m / sum(amounts) for s, m in zip(("awake", "light", "deep", "rem"), amounts)}
        check("stage ranges", f"partition {index}", dict(minutes=amounts), dict(status="ok", pct=expected), dict(status=status, pct={k: stats.pct[k] for k in expected}))
    prior = [stage_stats(make_stage(DAY-timedelta(days=4-i), (total-light-180, light, 90, 90)))[0] for i, (light, total) in enumerate(zip((270,258,300,282), (540,600,660,600)))]
    current = stage_stats(make_stage(DAY, (30,240,90,120)))[0]
    bands, used = personal_ranges(current, prior)
    check("stage ranges", "unequal-length pooled center", dict(light_minutes=[270,258,300,282], total_minutes=[540,600,660,600]), dict(center=46.25, spread=2.9652, low=43.2848, high=49.2152), {k: bands['light'][k] for k in ('center','spread','low','high')})

    stress_history = [stress_night(DAY-timedelta(days=i), [(40,60,5)] * 72) for i in range(1,8)]
    for name, readings, minutes in (("all normal", [(40,60,5)]*72, 0), ("all joint", [(20,80,5)]*72, 360), ("HRV only", [(20,60,5)]*72, 0), ("isolated joint", [(20,80,5)]+[(40,60,5)]*71, 0), ("two joint", [(20,80,5)]*2+[(40,60,5)]*70, 10)):
        result = score_night(stress_night(DAY, readings), stress_history, computed_at=BASE)
        check("sleep stress", name, dict(window_count=72, window_min=5, readings=readings, baseline_nights=7, baseline_hrv=40, baseline_hr=60), dict(stressed_minutes=minutes, stress_pct=round(100*minutes/360,2)), {k: result[k] for k in ('stressed_minutes','stress_pct')})
    repeated = [stress_history[0]] * 7
    duplicate_result = score_night(stress_night(DAY, [(20,80,5)]*72), repeated, computed_at=BASE)
    finding("Sleep stress unique-night regression", dict(unique_sleep_ids=1, supplied_rows=7, nights_used=duplicate_result['baseline']['nights_used'], status=duplicate_result['status']),
            "Repeated sessions now count once; seven copies of one night cannot establish a baseline. The connected path prepares unreconciled raw sessions before storage, making this gate necessary.")

    # Legacy prototype and remaining top-level helper calculations.
    for ratio in (.5, 1., 1.5):
        result = RecoveryCalculator.calculate(RecoveryInput(today_hrv=40*ratio, hrv_baseline=40, today_rhr=56, rhr_baseline=56, sleep_score=80, yesterday_strain=10.5))
        expected = .4 * max(0,min(100,(ratio-.5)*100)) + .25*50 + .25*80 + .1*50
        check("legacy recovery", f"HRV fallback {ratio}", dict(hrv_ratio=ratio, rhr=56, rhr_baseline=56, sleep_score=80, strain_21=10.5), expected, result['score'], 1e-6)
    for acr in (1.3, 1.65, 2., 3.):
        result = RecoveryCalculator.calculate(RecoveryInput(sleep_score=50, yesterday_strain=10.5, acr=acr))
        check("legacy recovery", f"ACR {acr}", dict(acr=acr), max(0,min(10,(acr-1.3)/.7*10)), result['acr_penalty'], 1e-6)
    hist=[38,41,36.5,40.2,43.1,39.8,42.5,44,37.9,41.3]
    logs=[math.log(v) for v in hist]; ewma=logs[0]
    for v in logs[1:]:ewma=.25*v+.75*ewma
    spread=math.sqrt(sum((v-mean(logs))**2 for v in logs)/(len(logs)-1))
    comp=max(0,min(100,50+25*(math.log(44)-ewma)/spread))
    actual=RecoveryCalculator.calculate(RecoveryInput(today_hrv=44,hrv_history=hist,sleep_score=50,yesterday_strain=10.5))
    check('legacy recovery','log EWMA and sample SD',dict(history=hist,today_hrv=44),round(comp,2),actual['hrv_component'],1e-6)
    for minutes,expected in ((0,50),(5,75),(10,100),(20,100),(30,60),(45,0)):
        check('legacy sleep helpers',f'latency {minutes}',dict(latency_min=minutes),expected,SleepCalculator.compute_sleep_latency_score(minutes*60))
    for count in (0,2,7):
        check('legacy sleep helpers',f'interruptions {count}',dict(count=count),max(0,100-15*count),SleepCalculator.compute_interruption_score(count))
    check('legacy sleep helpers','legacy sleep need',dict(baseline_h=7,actual_h=[6,8],strain_21=21),8.,SleepCalculator.calculate_sleep_need(7,[(7,6),(7,8)],21))
    intervals = [(datetime(2026,10,6,22), datetime(2026,10,7,6))]
    check("legacy sleep helpers", "Ayurvedic clock overlap", dict(start="22:00", end="06:00", pre_midnight_h=2, midnight_3_h=3, three_6_h=3), 10., AyurvedicSleepCalculator.calculate(intervals,DAY-timedelta(days=1)))
    check("legacy sleep helpers", "bedtime target", dict(wake="07:00", need_h=7.5, latency_min=12), "2026-10-06T23:18:00", SleepCalculator.bedtime_target(datetime(2026,10,7,7), 7.5).isoformat())
    check("legacy sleep helpers", "sleep debt hours", dict(need_actual_h=[[8,6],[8,9],[7,5]]), 4., SleepCalculator.compute_sleep_debt([(8,6),(8,9),(7,5)]))

    hrv_points = [dict(date=(DAY-timedelta(days=i)).isoformat(),value=40+i) for i in range(1,8)] + [dict(date=DAY.isoformat(),value=999)]
    health = build_health_response({'hrv':hrv_points}, [], DAY-timedelta(days=6), DAY,'W',False)
    check("health trends", "prior-only median", dict(prior_hrv=[41,42,43,44,45,46,47],today=999), 44., health.metrics['hrv'][-1].baseline)
    samples = [(BASE,60),(BASE+timedelta(minutes=5),80),(BASE+timedelta(minutes=16),100)]
    heart = build_heart_rate_response(samples,DAY,False)
    check("health trends", "15-minute medians", dict(readings=[['07:00',60],['07:05',80],['07:16',100]]), [70,100],[p.value for p in heart.heart_rate])
    check("health trends", "latest distinct from bin median", dict(readings=3),100,heart.latest_heart_rate.value)
    records=[]
    for i,(asleep,period) in enumerate(((240,300),(570,600))):
        day=DAY-timedelta(days=i)
        records.append(dict(date=day,bed_time=datetime.combine(day-timedelta(days=1),datetime.min.time()).replace(hour=22),wake_time=datetime.combine(day,datetime.min.time()).replace(hour=8),time_asleep_minutes=asleep,time_in_bed_minutes=period))
    trend=build_sleep_trend(records,DAY-timedelta(days=6),DAY,'W','efficiency',False)
    check("sleep trends", "duration-weighted efficiency with gaps",dict(asleep=[240,570],period=[300,600]),dict(average=90.,days=7,recorded=2,scored=2),dict(average=trend.average_value,days=len(trend.days),recorded=trend.recorded_nights,scored=trend.scored_days))
    for timeframe, length in (('W',7),('M',30)):
        check('calendar windows',timeframe,dict(end=str(DAY)),length,(DAY-range_start(DAY,timeframe)).days+1)

    # Data-quality probes deliberately kept separate from formula equivalence checks.
    bad_history={'hrv':[dict(date=(DAY-timedelta(days=i)).isoformat(),value=-1) for i in range(1,8)]}
    bad=build_health_response(bad_history,[],DAY,DAY,'W',False)
    finding('Health trend validity regression',dict(seven_prior_hrv_values=-1,returned_baseline=bad.metrics['hrv'][0].baseline),
            'Invalid summaries are excluded before current values, reference medians and period averages. Unspecified HRV/respiration/temperature/VO2 ceilings still need a product decision.')
    malformed=calculate_strain([(BASE,160),(BASE+timedelta(minutes=1),160)],[],dict(start=BASE,end=BASE+timedelta(minutes=1)),30,[1000],'m')
    finding('Strain resting-HR validity regression',dict(resting_hr=1000,hr_max=187,hr=160,load=malformed['load'],params=malformed['params']),
            'RHR outside existing HR limits or at/above estimated HRmax is rejected. Default 60 bpm is used when nothing remains, with rejection count and calibration flag.')
    history2={'hrv':[]}
    for i in range(60): history2['hrv'].append(dict(date=(start+timedelta(days=i)).isoformat(),value=40))
    history2['hrv'] += [dict(date=(DAY-timedelta(days=i)).isoformat(),value=40 if i else 80) for i in range(7)]
    double=recovery_from_history(history2,DAY)
    finding('Recovery current-night weighting regression',dict(today_hrv=80,other_recent_hrv=40,z_hrv=double.components['z_hrv'],effective_today_log_weight=.3),
            'Approved prior-seven-date recent window excludes today; today has exactly 30% log-signal weight. Minimum-count and confidence thresholds are unchanged.')

    # Replay whole demo endpoints with authentication disabled explicitly.
    # All calls stay in-process; a fixture miss cannot send a live request.
    from unittest.mock import AsyncMock, patch
    from fastapi.testclient import TestClient
    import httpx
    from main import app
    routes = ['/api/dashboard', '/api/strain?demo=true', '/api/strain/analytics?demo=true',
              '/api/recovery?demo=legacy', '/api/recovery?demo=estimate',
              '/api/recovery/analytics?demo=estimate', '/api/sleep', '/api/sleep/need',
              '/api/sleep/analytics', '/api/sleep/efficiency', '/api/sleep/consistency',
              '/api/sleep/consistency/score', '/api/sleep/stages/typical-ranges', '/api/sleep/stress',
              '/api/sleep/heart-rate', '/api/health', '/api/health/heart-rate']
    headers = {'X-User-Date': str(DAY), 'X-User-Age': '30', 'X-User-Sex': 'm', 'X-User-Timezone': 'Europe/Berlin'}
    def forbid_network(*args, **kwargs):
        raise RuntimeError('Live network forbidden during offline validation')
    snapshots['api_demo'] = {}
    with patch('main._get_token', new=AsyncMock(return_value=None)), patch.object(httpx.AsyncClient, 'send', forbid_network):
        with TestClient(app) as client:
            for route in routes:
                response = client.get(route, headers=headers)
                body = response.json()
                snapshots['api_demo'][route] = dict(status=response.status_code, body=body)
                check('demo API replay', route, dict(headers=headers, network='forbidden'), 200, response.status_code)


def write():
    OUT.mkdir(exist_ok=True)
    # JSON permits only valid numbers; string markers retain deliberately invalid inputs.
    def safe(obj):
        if isinstance(obj,float) and not math.isfinite(obj): return str(obj)
        if isinstance(obj,dict): return {k:safe(v) for k,v in obj.items()}
        if isinstance(obj,(list,tuple)): return [safe(v) for v in obj]
        return obj
    (OUT/'simulation-results.json').write_text(json.dumps(safe(dict(seed=SEED,anchor_date=str(DAY),cases=rows,findings=findings,demo=snapshots)),indent=2,allow_nan=False),encoding='utf-8')
    with (OUT/'simulation-results.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=['family','case','passed','tolerance','inputs','expected','actual']);writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(safe(v),ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
    source_files=sorted([*ROOT.glob('*.py'),*ROOT.glob('backend/*.py')])
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    manifest['validation/run_simulations.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT/'source-hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    inventory=[]
    for path in source_files:
        if path.name.startswith('test_'):continue
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                inventory.append(f'| `{path.relative_to(ROOT)}:{node.lineno}` | `{node.name}` |')
            elif isinstance(node,ast.ClassDef):
                for method in node.body:
                    if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)):
                        inventory.append(f'| `{path.relative_to(ROOT)}:{method.lineno}` | `{node.name}.{method.name}` |')
    (OUT/'algorithm-inventory.md').write_text('# Backend callable inventory\n\nIncludes adapters, persistence, auth and demo generators; inventory is not a claim of exhaustive coverage.\n\n| Source | Callable |\n|---|---|\n'+'\n'.join(inventory),encoding='utf-8')
    junit=ET.parse(OUT/'test-results.xml').getroot()
    suites=junit.findall('testsuite')
    totals={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    counts={}
    for row in rows:
        record=counts.setdefault(row['family'],[0,0]);record[0]+=1;record[1]+=row['passed']
    lines=['# Backend formula and simulation validation report', '', 'Follow-up audit: 2026-10-08. Synthetic anchor: 2026-10-07. Random seed: 20261007. The detailed follow-up report is validation/followup/REPORT.md.', '',
      '## Verdict', '',f"Backend suite: **{totals['tests']} JUnit cases total, {totals['failures']} failures, {totals['errors']} errors, {totals['skipped']} skipped**. Independent simulation checks: **{sum(r['passed'] for r in rows)}/{len(rows)} passed**. Passing formula checks do not establish physiological accuracy.", '',
      'Production corrections and approved specification changes are documented in validation/followup/REPORT.md. This is an offline implementation audit, not clinical validation or live Fitbit certification. Independent numerical calculations verify the selected equations, not their physiological coefficients.', '',
      '## Reproduce and inspect evidence', '', 'Run from the project root:', '', '```powershell', '.venv/Scripts/python.exe -m pytest backend -q --junitxml=validation/test-results.xml', '.venv/Scripts/python.exe validation/run_simulations.py', '```', '',
      'The XML records every existing test outcome. simulation-results.json and CSV preserve every generated input, expected value, actual value, tolerance and pass/fail result. JSON also includes 28 date-anchored demo daily results. source-hashes.json identifies the exact audited Python sources. algorithm-inventory.md lists backend callables; it is not an assertion that every branch is tested.', '',
      'All new numerical checks use fixed dates/seeds and are offline. No credentials or live APIs were used. Existing integration tests use mocked Google data/HTTP transports and temporary SQLite databases. Demo endpoints were replayed in-process with outbound async HTTP explicitly forbidden; complete responses are in simulation-results.json. Demo computation timestamps can change between runs; numerical simulation cases are deterministic. No frontend build or browser audit was performed.', '',
      'Oracle calibration: an initial sweep exposed a mistake in this audit script: its sleep-score reference used a 25% REM target, while source specifies 20%. That independent reference was corrected to the actual source constant; production code was not changed. The initial 110 mismatches are therefore audit-oracle errors, not backend defects. An initial endpoint replay also used an incorrect stage-range URL and received 404; the replay was corrected to /api/sleep/stages/typical-ranges. Final results below come from the corrected rerun.', '',
      '## Scope and check counts', '', '| Family | Checks | Passed |', '|---|---:|---:|']
    lines += [f'| {f} | {n} | {p} |' for f,(n,p) in counts.items()]
    lines += ['', '## Current formula specification', '',
      '### Cardio strain — strain.py', '',
      'The current algorithm supersedes the old weighted-zone/capacity implementation described earlier in chat. HRmax = 208 - 0.7*age. RHR = median of up to seven finite readings within the existing HR limits and strictly below estimated HRmax, fallback 60 bpm. Rejected readings are counted and mark calibrating. Clean samples by physical UTC time, deduplicate timestamps (first value wins), remove nonfinite/outside 30–230 bpm values, and remove values more than 35 bpm from a centered five-sample median with repeated edge padding. Arrays shorter than five skip the spike filter.', '',
      'For adjacent cleaned samples with 0 < physical gap <= 300 seconds: minutes = gap/60; HR = pair average; HRR = clamp((HR-RHR)/max(HRmax-RHR,1),0,1.1). Below HRR 0.20 gives zero load; otherwise load = minutes*HRR*a*exp(b*HRR). Coefficients: male a=0.64,b=1.92; female a=0.86,b=1.67. Total strain = 21*(1-exp(-total_load/90)), numerically capped just below 21. Zones are display-only, not load weights.', '',
      'Coverage = counted interval minutes / physical window minutes, capped at 1; below 60% is low coverage. Missing age withholds strain/load. Default RHR or defaulted sex marks calibrating. Current window starts after latest eligible main sleep of at least three hours; historical days run to next eligible sleep start, with midnight fallbacks. Midpoints assign each interval once to the first sorted matching workout. Workout details below 0.5 load are dropped, while total load retains them. Unlogged effort >=45% HRR lasting >=10 minutes is suggested without adding load twice.', '',
      'Seven/28-day strain averages use available days with positive coverage; acute/chronic uses mean recent seven-day raw load / mean 28-day raw load with at least 21 valid rows. Recovery-based target bands are 4–10 below 34, 10–14 from 34 to below 67, and 14–18 at 67+. These thresholds remain product heuristics.', '',
      '### Connected Recovery — backend/recovery_score.py', '',
      'Baseline spans day-67 through day-8 inclusive (60 dates). Approved recent window spans day-7 through day-1; today is excluded. Require 21 valid baseline HRV days and four prior recent HRV readings. In log HRV space: center=median; spread=max(1.4826*MAD,0.05). Signal=0.7*mean(recent ln HRV)+0.3*ln(today HRV), or recent mean alone if today is missing. zHRV=(signal-center)/spread.', '',
      'RHR uses at least 21 baseline readings with the same known device calculation method as today. zRHR=(median RHR-today RHR)/max(1.4826*MAD,1 bpm). Combined z=0.6*zHRV+0.4*zRHR when RHR is available, otherwise HRV alone. Sleep performance=min(sleep/need,1); sleep shorter than 180 minutes is discarded. Sleep adjustment=-0.5*clamp((0.85-performance)/0.25,0,1); no modifier for missing context. Final z clips to [-3,3]; illness flag caps z at -0.5. Respiratory/skin-temperature deviation beyond two robust spreads triggers that flag if the baseline has >=21 valid points and nonzero spread.', '',
      'Zones: below_normal for z<-0.5, above_normal for z>0.5, otherwise normal. High confidence requires >=45 baseline, >=6 recent, RHR and sleep context; medium >=28 baseline and >=5 recent; otherwise low. Percentage=rounded 100*normal CDF(z), withheld at low confidence. This is a baseline-relative mapping, not a probability of physiological recovery. Independent oracle uses statistics.NormalDist.cdf rather than the implementation erf expression.', '',
      '### Sleep need — backend/sleep_need.py', '',
      'All durations in minutes. Baseline 450. Convert strain percentage to 0–21 via *0.21 and clamp. Let L(s)=1/(1+exp(-0.476*(s-14.38))). Strain addition=26*(L(s)-L(0))/(L(21)-L(0)); additions below one minute become zero. Prior seven nights, most recent first, use weights [1,0.85,0.7,0.55,0.4,0.25,0.1]. Debt=clamp(weighted mean of baseline+historical strain addition-actual sleep,0,240), ignoring incomplete nights; surpluses offset deficits. Debt addition=34% of debt. Need=clamp(baseline+strain addition+debt addition-today nap minutes,360,660). This is weighted average debt, not cumulative debt.', '',
      '### Sleep score — sleepscore.py', '',
      'SleepData durations are seconds; sleep_need is hours. Duration ratio includes naps. At ratio<=1, approved duration=100*(1+exp(-2))/(1+exp(-8*(ratio-0.75))); at 1<ratio<=1.1, duration=100; above 1.1, duration=max(30,100-75*(ratio-1.1)). Stage denominator is required sleep seconds: deep target 20% through age30, then -0.2 percentage points/year floored at10%; REM20%, core50%. Each stage component caps at100; stage mix=40% deep+40%REM+20%core.', '',
      'Efficiency component maps asleep/period 70%–95% to0–100. HRV component maps baseline ratio0.7–1.3 to0–100; sleeping-HR uses the inverted mapping. Dip maps (wakingHR-sleepingHR)/wakingHR 0–25% to0–100. Restfulness=clamp(100*exp(-0.035*awake_minutes)-min(15,2.5*interruptions),0,100). Final weights: duration27%, stages20%, efficiency10%, HRV5%, HR5%, dip18%, restfulness15%. Missing HR-derived values default to50. Zero total sleep or nonpositive need returns0.', '',
      '### Efficiency, timing, ranges and sleep stress', '',
      'Standalone efficiency=round(100*asleep_seconds/period_seconds,1), only for finite 0<asleep<=period<=86400; otherwise None. Trend aggregate uses ratio of summed durations, not average of daily percentages. Four-night consistency uses circular onset/wake differences, average drift per pair, sigmoid centered75 minutes with slope0.05, normalized to100 at0 and0 at240 minutes. Weights0.4/0.3/0.2/0.1, renormalized for missing nights, at least two prior nights. Seven-night timing variability requires consecutive dates and uses circular clock mean plus population SD of wrapped deviations.', '',
      'Stage ranges require complete nonoverlapping contiguous processed stage partition and at least three asleep hours; naps excluded. Default denominator is full recorded sleep period. Restorative=deep+REM. Last up to seven unique prior wake dates, minimum four: center=100*sum(stage minutes)/sum(period minutes); spread=max(1.4826*MAD of daily stage percentages,1 percentage point). Band=center±spread clipped0–100. These are descriptive provisional bands.', '',
      'Sleep stress validates HRV windows, awake overlap, >=70% stage majority, HR35–130 bpm and >=60% inferred HR sample coverage. Baseline needs seven eligible main nights within14 dates, >=50% night coverage; use per-stage robust medians/spreads if >=30 windows, else pooled fallback. Log HRV spread floor0.02; HR spread floor0.5 bpm. Candidate requires both HRV drop z>=1 and HR rise z>=1. At least two exactly adjacent candidate windows form an episode. Stress%=100*episode minutes/valid window minutes; it is not a fraction of the entire night unless coverage is complete. Seeded stress cases here deliberately have full six-hour coverage.', '',
      '### Trend and legacy helpers', '',
      'Health: prior-only14-calendar-day median after seven readings, date-aligned gaps; intraday HR uses15-minute median bins, latest HR is a separate raw sample. Weekly windows have7 dates, monthly30; six/12-month windows use calendar arithmetic. Recovery analytics retain missing sleep-context flags on historical estimates and filter RHR method; strength minutes/steps are display aggregates, not additional cardio load.', '',
      'Legacy recovery.py remains a separate prototype:40%HRV+25%RHR+25%sleep+10%(1-strain/21)*100, ACR penalty0–10 above1.3, optional adjustment, clipped0–100. Legacy HRV uses EWMA ln baseline alpha0.25 and sample SD, mapped50+25*z; fallback scalar ratio0.5–1.5. Legacy sleep helpers include debt hours, clock consistency, latency score, bedtime subtraction and Ayurvedic clock-window points. They are inventoried and spot-checked, not asserted to have exhaustive branch coverage.', '',
      '## Selected data and numerical results', '', '| Family / case | Input | Expected | Actual | Pass |', '|---|---|---|---|---|']
    selected=[]
    for family in counts:
        group=[r for r in rows if r['family']==family]
        selected+=group[:3]
        if len(group)>3:selected+=group[-1:]
    for row in selected:
        inp=json.dumps(safe(row['inputs']),ensure_ascii=False)
        # Full inputs remain in evidence, especially long baseline arrays.
        if len(inp)>240:inp=inp[:237]+'... (full data in JSON)'
        def fmt(v):
            text=json.dumps(v,ensure_ascii=False) if not isinstance(v,float) else f'{v:.10g}'
            return text if len(text)<=350 else text[:347]+'... (full result in JSON)'
        lines.append(f"| {row['family']} / {row['case']} | {inp.replace('|','/')} | {fmt(row['expected'])} | {fmt(row['actual'])} | {row['passed']} |")
    lines+=['','## Numerical examples and inference by algorithm','',
      'At age 30 and resting HR 56 bpm, the male-coefficient constant-HR cases yield:', '',
      '| HR | Duration | Raw load | Strain |', '|---:|---:|---:|---:|']
    for index in (0,2,4):
        row=rows[index];lines.append(f"| {row['inputs']['hr']} bpm | {row['inputs']['minutes']} min | {row['actual']['load']:.6f} | {row['actual']['strain']:.6f} |")
    lines += ['',
      'Inference: higher HR and longer time increase load on these controlled cases, but strain compresses nonlinearly toward 21. Male/female coefficient sets yield different scores for the same input; this verifies the selected formula rather than demonstrating a measured sex difference. The 100 irregular traces check actual pair averaging, five-minute gap exclusion, coverage and workout/incidental conservation; raw samples are saved in JSON.', '',
      'Recovery: a flat 40 ms HRV / 56 bpm RHR reference with identical recent/current readings and adequate sleep gives z=0, 50%, normal, high confidence. Sleep at 326.25 of 450 minutes gives performance0.725 and adjustment-0.25 z. The illness cap produces z=-0.5 and 31%, while the exact boundary remains normal. Inference: this percentage describes position on a normal-CDF mapping; it cannot be interpreted as the probability of readiness. Low-confidence withholding, same-method RHR and prior-only dates are covered by the existing suite and the new threshold/join checks.', '',
      'Sleep need: 0 strain, seven450-minute nights and no naps gives450 minutes. 100% strain with the same historical sleep gives26 extra strain minutes,26 weighted debt minutes,8.84 repayment minutes and484.84 total minutes. Inference: the debt calculation includes each historical strain-adjusted need; it is not merely the shortfall against450. Naps reduce need, subject to the360-minute floor. Sweeps include negative/above100 strain percentages to verify the implemented clamp.', '',
      'Sleep efficiency:450 minutes asleep within480 minutes gives93.8%. Two unequal periods with240/300 and570/600 give90% pooled efficiency, rather than87.5% arithmetic mean of the daily ratios. Inference: longer sessions contribute more to this aggregate; invalid periods stay missing. Clock consistency checks distinguish four-night heuristic scores from seven-night SD and verify missing-date withholding.', '',
      'Stage ranges: prior light minutes[270,258,300,282] over total minutes[540,600,660,600] yield pooled center46.25%, robust spread2.9652 percentage points, and band43.2848–49.2152%. Inference: the center is duration-weighted while spread is based on daily percentages. The range is descriptive and does not constitute a population normal range.', '',
      'Sleep stress:72 five-minute joint HRV-drop/HR-rise windows against seven full six-hour reference nights give360 stressed minutes and100% of valid time. HRV drop alone gives0 stressed minutes; an isolated joint window gives0; two adjacent joint windows give10 minutes and2.78%. Inference: persistence and joint signals drive the detector, not HRV alone. These clear synthetic contrasts do not establish real-world sensitivity or specificity.', '',
      'Demo endpoints:17 routes returned200 with outbound async HTTP blocked. Full dashboard, legacy/estimated Recovery, strain, trend, sleep, stage-range and stress responses are retained. This establishes runnable demo assembly/API serialization; status checks alone are not independent physiological/numerical validation of every field.', '',
      'Suite runtime and warnings are recorded in validation/followup/final/tests.log and test-metadata.json; no runtime from the earlier audit is reused.', '',
      '## Reproduced issues and assumptions needing review','']
    for i,item in enumerate(findings,1):
        lines += [f"### {i}. {item['title']}",'',f"Evidence: `{json.dumps(item['data'])}`",'',item['inference'],'']
    lines+=['## Existing suite evidence by file','','| Test file | Cases | Failures/errors |','|---|---:|---:|']
    files={}
    for case in junit.iter('testcase'):
        label=case.attrib.get('classname','unknown').split('.')[0]
        rec=files.setdefault(label,[0,0]);rec[0]+=1;rec[1]+=int(case.find('failure') is not None or case.find('error') is not None)
    lines += [f'| {label} | {count} | {failed} |' for label,(count,failed) in sorted(files.items())]
    lines+=['','## Interpretation and limits','','Controlled checks establish agreement with the selected equations on the tested domains. The five original findings were independently reproduced and corrected under the documented product decisions. Follow-up evidence, all numerical deltas, commits, property limits and live-access requirements are in validation/followup/REPORT.md.','','No p-values, sensitivity, specificity, device accuracy or physiological accuracy are inferred from synthetic data. Real-device timestamp calibration, empirical coefficient validation, participant/day holdouts, and agreed HRV/respiration/temperature/VO2 ceilings remain outstanding. No live bearer token was accessible during this audit.']
    (OUT/'VALIDATION_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(checks=len(rows),passed=sum(r['passed'] for r in rows),failed=[r['case'] for r in rows if not r['passed']], findings=len(findings),existing_suite=totals)))


if __name__ == '__main__':
    run()
    write()
    sys.exit(0 if all(r['passed'] for r in rows) else 1)
