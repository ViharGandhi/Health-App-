"""Persist connected API results in normalized result and lineage tables."""
from datetime import date, timedelta
import hashlib
import json
import time

from health_database import epoch, json_text, number
from heart_rate_retention import without_day_traces


class Results:
    def __init__(self, db, user, day, profile=None):
        self.db, self.user, self.day = db, user, str(day)
        self.profile = profile or db.profile(user, self.day)

    @staticmethod
    def put(conn, table, **values):
        columns = ','.join(values)
        conn.execute(f'INSERT OR REPLACE INTO {table} ({columns}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))

    def run(self, conn, algorithm, payload, *, day=None, source=None, subject='', coverage=None, reason=None):
        day = str(day or self.day)
        profile = self.db.profile(self.user, day)
        pid = profile['profile_version_id'] if profile else None
        version = payload.get('algo_version') or payload.get('method') or payload.get('estimator') or 'app-2026-10-15'
        conn.execute('INSERT OR IGNORE INTO algorithm_versions(algorithm_code,version_label,params_json) VALUES (?,?,?)',
                     (algorithm, version, json_text(payload.get('config_snapshot', {}))))
        vid = conn.execute('SELECT algorithm_version_id FROM algorithm_versions WHERE algorithm_code=? AND version_label=?', (algorithm, version)).fetchone()[0]
        fingerprint = hashlib.sha256(json_text([payload, pid, vid]).encode()).hexdigest()
        existing = conn.execute('SELECT calc_run_id,input_fingerprint FROM calc_runs WHERE user_id=? AND algorithm_code=? AND target_date=? AND subject_key=? AND is_current=1', (self.user, algorithm, day, str(subject))).fetchone()
        if existing and existing['input_fingerprint'] == fingerprint:
            return existing['calc_run_id']
        partial = bool(payload.get('partial') or payload.get('low_coverage'))
        rid = conn.execute('INSERT INTO calc_runs(user_id,algorithm_code,algorithm_version_id,profile_version_id,target_date,source_date,subject_key,config_json,status,withheld_reason,coverage_pct,is_partial,has_defaults,input_fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (self.user, algorithm, vid, pid, day, str(source) if source else None, str(subject), json_text(payload.get('config_snapshot', {})), 'withheld' if reason else 'partial' if partial else 'ok', reason, coverage, int(partial), int(bool(payload.get('defaulted_components'))), fingerprint)).lastrowid
        for flag, detail in payload.get('defaulted_components', {}).items():
            self.put(conn, 'calc_flags', calc_run_id=rid, flag_code=f'default_{flag}', severity='warning', detail=json_text(detail))
        if reason:
            self.put(conn, 'calc_flags', calc_run_id=rid, flag_code='withheld', severity='blocking', detail=reason)
        return rid

    def sleep_id(self, conn, day=None, provider_id=None):
        if provider_id:
            row = conn.execute('SELECT sleep_session_id FROM sleep_sessions WHERE user_id=? AND provider_sleep_id=?', (self.user, provider_id)).fetchone()
        else:
            row = conn.execute('SELECT sleep_session_id FROM sleep_sessions WHERE user_id=? AND sleep_date=? AND is_nap=0 AND is_processed=1 ORDER BY is_main_sleep DESC,end_ts-start_ts DESC,provider_sleep_id DESC LIMIT 1', (self.user, str(day or self.day))).fetchone()
        return row[0] if row else None

    def dependency(self, conn, rid, *algorithms, day=None):
        for code in algorithms:
            row = conn.execute('SELECT calc_run_id FROM calc_runs WHERE user_id=? AND algorithm_code=? AND target_date=? AND is_current=1 ORDER BY computed_at DESC,calc_run_id DESC LIMIT 1', (self.user, code, str(day or self.day))).fetchone()
            if row and row[0] != rid:
                conn.execute('INSERT OR IGNORE INTO calc_run_dependencies VALUES (?,?)', (rid, row[0]))

    def reference(self, conn, rid, metric, value, count, start, end, days, method):
        if not start or not end:
            return None
        conn.execute('INSERT INTO reference_statistics(user_id,metric_code,as_of_date,window_start_date,window_end_date,window_days,ref_count,mean_value,method,calc_run_id) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,metric_code,as_of_date,window_days,method) DO UPDATE SET mean_value=excluded.mean_value,ref_count=excluded.ref_count,calc_run_id=excluded.calc_run_id',
                     (self.user, metric, self.day, start, end, days, count or 0, value, method, rid))
        return conn.execute('SELECT ref_stat_id FROM reference_statistics WHERE user_id=? AND metric_code=? AND as_of_date=? AND window_days=? AND method=?', (self.user, metric, self.day, days, method)).fetchone()[0]

    def sleep(self, data):
        with self.db.connect() as conn:
            sid = self.sleep_id(conn)
            source = data.get('waking_hr_date') or str(date.fromisoformat(self.day)-timedelta(days=1))
            need = data.get('sleep_need')
            if need:
                nr = self.run(conn, 'sleep_need', need, source=source)
                self.put(conn, 'sleep_need_results', calc_run_id=nr, user_id=self.user, sleep_date=self.day, source_date=source,
                         baseline_min=need.get('baseline_min'), strain_addition_min=need.get('strain_add_min'), debt_addition_min=need.get('debt_add_min'), nap_credit_min=need.get('nap_credit_min'), total_need_min=need.get('total_need_min'), sleep_debt_min=need.get('sleep_debt_min'))
                self.dependency(conn, nr, 'daily_strain', day=source)
            reason = data.get('status_reason') if data.get('score') is None else None
            sr = self.run(conn, 'sleep_score', data, source=source, subject=sid or '', coverage=100*data.get('component_coverage', 0), reason=reason)
            if sid is None:
                self.put(conn, 'calc_flags', calc_run_id=sr, flag_code='missing_sleep_session', severity='blocking', detail='No normalized main sleep for this date')
                return
            self.put(conn, 'calc_run_inputs', calc_run_id=sr, role='sleep_session', ref_table='sleep_sessions', ref_id=sid, ref_date=self.day)
            mr = self.run(conn, 'sleep_metrics', data, subject=sid)
            raw = conn.execute('SELECT * FROM sleep_sessions s LEFT JOIN sleep_summaries m USING(sleep_session_id) WHERE sleep_session_id=?', (sid,)).fetchone()
            asleep = data.get('total_sleep_hours', 0)*60
            stages = data.get('stages', {})
            self.put(conn, 'sleep_metrics', calc_run_id=mr, user_id=self.user, sleep_session_id=sid, sleep_date=self.day, bedtime_ts=raw['start_ts'], sleep_end_ts=raw['end_ts'],
                     sleep_onset_ts=raw['start_ts']+raw['minutes_to_fall_asleep']*60 if raw['minutes_to_fall_asleep'] is not None else None,
                     final_wake_ts=raw['end_ts']-raw['minutes_after_waking']*60 if raw['minutes_after_waking'] is not None else None,
                     total_asleep_min=asleep, in_bed_min=raw['minutes_in_bed'], awake_min=raw['minutes_awake'], latency_min=raw['minutes_to_fall_asleep'],
                     deep_min=stages.get('deep_minutes'), rem_min=stages.get('rem_minutes'), light_min=stages.get('core_minutes'), awake_stage_min=stages.get('awake_minutes'),
                     deep_pct=100*stages.get('deep_minutes', 0)/asleep if asleep else None, rem_pct=100*stages.get('rem_minutes', 0)/asleep if asleep else None,
                     light_pct=100*stages.get('core_minutes', 0)/asleep if asleep else None, efficiency_pct=data.get('efficiency_pct'), wake_events=raw['wake_count'], restfulness_score=data.get('restfulness_score'))
            vr = self.run(conn, 'sleep_nightly_vitals', data, source=source, subject=sid)
            refs = [self.reference(conn, vr, metric, data.get(key+'_baseline'), data.get(key+'_baseline_nights'), data.get('baseline_start'), data.get('baseline_end'), data.get('baseline_window_days', 60), 'prior_mean') for metric, key in [('hrv_rmssd_avg', 'hrv'), ('resting_hr_calc', 'rhr')]]
            self.put(conn, 'sleep_nightly_vitals', calc_run_id=vr, user_id=self.user, sleep_session_id=sid, sleep_date=self.day, source_date=source, hrv_rmssd=data.get('sleeping_hrv'), deep_hrv_rmssd=data.get('deep_sleep_hrv'), sleeping_hr_bpm=data.get('sleeping_hr'), prev_awake_hr_bpm=data.get('waking_hr'), hr_dip_pct=data.get('hr_dip_pct'), dip_component_score=data.get('hr_dip_score'), hrv_ref_stat_id=refs[0], rhr_ref_stat_id=refs[1])
            self.dependency(conn, vr, 'awake_hr', day=source)
            self.dependency(conn, vr, 'sleeping_hr')
            for algorithm, column, day in [('sleeping_hr', 'sleeping_hr_run_id', self.day), ('awake_hr', 'awake_hr_run_id', source)]:
                ref = conn.execute('SELECT calc_run_id FROM calc_runs WHERE user_id=? AND algorithm_code=? AND target_date=? AND is_current=1 ORDER BY calc_run_id DESC LIMIT 1', (self.user, algorithm, day)).fetchone()
                if ref:
                    conn.execute(f'UPDATE sleep_nightly_vitals SET {column}=? WHERE calc_run_id=?', (ref[0], vr))
            self.put(conn, 'sleep_scores', calc_run_id=sr, user_id=self.user, sleep_session_id=sid, sleep_date=self.day, source_date=source, overall_score=data.get('score'), score_status='withheld' if data.get('score') is None else 'partial' if data.get('partial') else 'complete')
            weights = {'duration': .27, 'stage_mix': .20, 'efficiency': .10, 'sleeping_hrv': .05, 'sleeping_hr': .05, 'hr_dip': .18, 'restfulness': .15}
            from sleepscore import SleepCalculator
            normalized = {'duration': data.get('duration_score'), 'stage_mix': data.get('stage_score'), 'hr_dip': data.get('hr_dip_score'), 'restfulness': data.get('restfulness_score'), 'efficiency': data.get('efficiency_pct')}
            # Use the same component formulas as the scorer for vital scores.
            normalized['sleeping_hrv'] = SleepCalculator.compute_sleeping_hrv_score(data.get('sleeping_hrv'), data.get('hrv_baseline'))
            normalized['sleeping_hr'] = SleepCalculator.compute_sleeping_hr_score(data.get('sleeping_hr'), data.get('rhr_baseline'))
            if data.get('efficiency_pct') is not None:
                from sleepscore import normalize_ratio
                normalized['efficiency'] = normalize_ratio(data['efficiency_pct']/100, .70, .95)
            raw_values = {'duration': data.get('total_sleep_hours'), 'stage_mix': None, 'efficiency': data.get('efficiency_pct'), 'sleeping_hrv': data.get('sleeping_hrv'), 'sleeping_hr': data.get('sleeping_hr'), 'hr_dip': data.get('hr_dip_pct'), 'restfulness': data.get('restfulness_score')}
            for key, weight in weights.items():
                old_key = 'stages' if key == 'stage_mix' else key
                available = data.get('components_available', {}).get(old_key, False)
                defaults = data.get('defaulted_components', {})
                if old_key in defaults:
                    normalized[key] = defaults[old_key]
                self.put(conn, 'sleep_score_components', calc_run_id=sr, component=key, weight=weight, raw_value=raw_values[key], component_score=normalized[key], is_available=int(available), is_default=int(old_key in defaults), default_reason='missing_input' if old_key in defaults else None)
            self.dependency(conn, sr, 'sleep_metrics', 'sleep_nightly_vitals', 'sleep_need')

    def sleeping_hr(self, day, sleep_id, data):
        with self.db.connect() as conn:
            sid = self.sleep_id(conn, provider_id=sleep_id)
            if sid is None:
                return
            total, covered = data.get('asleep_seconds', 0), data.get('covered_seconds', 0)
            coverage = min(100, 100*covered/total) if total else None
            rid = self.run(conn, 'sleeping_hr', data, day=day, subject=sid, coverage=coverage, reason=data.get('status') if data.get('value') is None else None)
            self.put(conn, 'sleeping_hr_results', calc_run_id=rid, user_id=self.user, sleep_session_id=sid, sleep_date=str(day), bpm=data.get('value'), method=data.get('method', 'ASLEEP_TIME_WEIGHTED_V1'), sample_count=data.get('sample_count'), counted_seconds=round(covered), max_gap_seconds=60, coverage_pct=coverage)

    def awake(self, day, data):
        with self.db.connect() as conn:
            rid = self.run(conn, 'awake_hr', data, day=day, source=day, reason=data.get('status') if data.get('value') is None else None)
            self.put(conn, 'awake_hr_results', calc_run_id=rid, user_id=self.user, source_date=str(day), window_start_ts=epoch(data.get('wake_time')), window_end_ts=epoch(data.get('cutoff')), wake_sleep_session_id=self.sleep_id(conn, day), mean_bpm=data.get('value'), retained_count=data.get('sample_count'), excluded_sleep_count=data.get('excluded_sleep_samples', 0), excluded_activity_count=data.get('excluded_activity_samples', 0))
            self.put(conn, 'calc_run_inputs', calc_run_id=rid, role='hr_range', ref_table='hr_samples', ref_date=str(day), range_start_ts=epoch(data.get('wake_time')), range_end_ts=epoch(data.get('cutoff')), row_count=data.get('sample_count'))
            for interval in data.get('activity_intervals', []):
                self.put(conn, 'calc_exclusion_intervals', calc_run_id=rid, start_ts=epoch(interval['start']), end_ts=epoch(interval['end']), reason='activity')

    def strain(self, data, day=None):
        day = str(day or data.get('date') or self.day)
        with self.db.connect() as conn:
            params = data.get('params', {})
            rid = self.run(conn, 'daily_strain', data, day=day, coverage=100*data.get('coverage', 0), reason='missing_age' if data.get('age_missing') else None)
            self.put(conn, 'daily_strain_results', calc_run_id=rid, user_id=self.user, strain_date=day, score=data.get('strain'), score_pct=data.get('strain')/21*100 if data.get('strain') is not None else None, label=data.get('label'), trimp_load=data.get('load'), workout_load=data.get('workout_load', data.get('workout_strain')), incidental_load=data.get('incidental_load', data.get('incidental_strain')), max_hr_est_bpm=params.get('hr_max'), max_hr_source='age_estimate' if params.get('hr_max') else None, resting_hr_param_bpm=params.get('hr_rest'), resting_hr_source=params.get('hr_rest_source'), age_used=data.get('age_used'), sex_used=params.get('sex'), sample_count=data.get('sample_count'), counted_seconds=round(data.get('counted_minutes', 0)*60), missing_age_flag=int(bool(data.get('age_missing'))), missing_calibration_flag=int(bool(data.get('calibrating'))))
            window = data.get('day_window') or {}
            if window.get('start') and window.get('end'):
                if not conn.execute("SELECT 1 FROM calc_run_inputs WHERE calc_run_id=? AND role='hr_range'", (rid,)).fetchone():
                    self.put(conn, 'calc_run_inputs', calc_run_id=rid, role='hr_range', ref_table='hr_samples', ref_date=day, range_start_ts=epoch(window['start']), range_end_ts=epoch(window['end']), row_count=data.get('sample_count'))
            for scope, key in [('all_hr', 'zone_minutes'), ('logged_activities', 'activity_zone_minutes')]:
                for zone, minutes in (data.get(key) or {}).items():
                    self.put(conn, 'strain_zone_durations', calc_run_id=rid, scope=scope, zone=int(zone.removeprefix('zone')), seconds=round(minutes*60))
            for workout in data.get('workouts', []):
                activity = conn.execute('SELECT activity_id FROM activities WHERE user_id=? AND start_ts=? AND end_ts=? ORDER BY activity_id LIMIT 1', (self.user, epoch(workout['start']), epoch(workout['end']))).fetchone()
                if activity is None:
                    continue
                wr = self.run(conn, 'workout', workout, day=day, subject=activity[0])
                self.put(conn, 'workout_results', calc_run_id=wr, user_id=self.user, activity_id=activity[0], strain=workout.get('strain'), load=workout.get('load'), avg_hr_bpm=workout.get('avg_hr'), max_hr_bpm=workout.get('max_hr'), duration_s=round(workout.get('duration_min', 0)*60))
                if not conn.execute("SELECT 1 FROM calc_run_inputs WHERE calc_run_id=? AND role='activity'", (wr,)).fetchone():
                    self.put(conn, 'calc_run_inputs', calc_run_id=wr, role='activity', ref_table='activities', ref_id=activity[0], range_start_ts=epoch(workout['start']), range_end_ts=epoch(workout['end']))
                for zone, minutes in workout.get('zone_minutes', {}).items():
                    self.put(conn, 'workout_zone_durations', calc_run_id=wr, zone=int(zone.removeprefix('zone')), seconds=round(minutes*60))
                self.dependency(conn, wr, 'daily_strain', day=day)
            analytics = data.get('analytics') or {}
            if analytics:
                tr = self.run(conn, 'training_trend', analytics, day=day)
                # Schema's single target cannot encode the app's low/high band;
                # preserve the band in config_json instead of inventing a midpoint.
                conn.execute('UPDATE calc_runs SET config_json=? WHERE calc_run_id=?', (json_text({'strain_target': analytics.get('strain_target')}), tr))
                self.put(conn, 'training_trend_results', calc_run_id=tr, user_id=self.user, as_of_date=day, avg_7d_strain=analytics.get('avg_strain_7d'), avg_28d_strain=analytics.get('avg_strain_28d'), acute_chronic_ratio=analytics.get('acute_chronic_ratio'), target_basis='recovery_band')

    def recovery(self, data):
        if data.get('estimator') == 'descriptive_vitals':
            return
        with self.db.connect() as conn:
            rid = self.run(conn, 'recovery', data, reason=data.get('status_reason') if data.get('score') is None else None)
            components = data.get('components') or {}; context = data.get('sleep_context') or {}
            self.put(conn, 'recovery_results', calc_run_id=rid, user_id=self.user, recovery_date=self.day, sleep_session_id=self.sleep_id(conn), score_pct=data.get('score'), status='withheld' if data.get('score') is None else 'computed', withheld_reason=data.get('status_reason') if data.get('score') is None else None, zone=data.get('zone'), confidence_label=data.get('confidence'), current_hrv_ms=data.get('today_hrv'), current_rhr_bpm=data.get('today_rhr'), hrv_z=components.get('z_hrv'), rhr_z=components.get('z_rhr'), combined_z=data.get('z'), sleep_adjustment=components.get('sleep_adj'), sleep_duration_min=context.get('sleep_min'), required_sleep_min=context.get('need_min'), sleep_performance_pct=context.get('performance')*100 if context.get('performance') is not None else None, rejected_reading_count=sum(data.get('rejected_readings', {}).values()), training_recommendation=data.get('training_recommendation'))
            self.dependency(conn, rid, 'sleep_need', 'sleep_metrics', 'sleeping_hr')

    def stress(self, data):
        with self.db.connect() as conn:
            for item in data.get('days', []):
                day = item['date']; rid = self.run(conn, 'stress_monitor', item, day=day, coverage=100*item.get('coverage', 0))
                mins = item.get('minutes', {})
                self.put(conn, 'stress_daily_summaries', calc_run_id=rid, user_id=self.user, stress_date=day, avg_score=item.get('average'), low_min=round(mins.get('low', 0)), medium_min=round(mins.get('medium', 0)), high_min=round(mins.get('high', 0)), scored_min=round(item.get('scored_minutes', 0)), unscored_min=round(item.get('unscored_minutes', 0)), coverage_pct=100*item.get('coverage', 0), baseline_count=item.get('baseline_days'), hrv_timing_status='verified' if item.get('hrv_quality_verified') else 'unverified', hrv_quality_status='good' if item.get('hrv_quality_verified') else 'unknown', hrv_gated=int(not item.get('sleep_hrv_enabled')))
                conn.execute('DELETE FROM stress_intervals WHERE calc_run_id=?', (rid,))
                for point in item.get('points', []):
                    self.put(conn, 'stress_intervals', calc_run_id=rid, user_id=self.user, start_ts=epoch(point['start']), end_ts=epoch(point['end']), score=point.get('score'), state=point.get('state'), hr_bpm=point.get('hr'), source=point.get('source'))
                    if point.get('reason'):
                        reason = {'exercise_recovery': 'exercise_mask', 'missing_hr': 'missing_hr', 'baseline_building': 'baseline_building'}.get(point['reason'])
                        if reason:
                            self.put(conn, 'calc_exclusion_intervals', calc_run_id=rid, start_ts=epoch(point['start']), end_ts=epoch(point['end']), reason=reason)

    def stage_ranges(self, data):
        with self.db.connect() as conn:
            for night in data.get('nights', []):
                rid = self.run(conn, 'sleep_stage_compare', night, day=night['night_date'], subject=night['sleep_id'])
                for stage, item in night.get('stages', {}).items():
                    if stage not in ('deep', 'rem', 'light', 'awake'):
                        continue
                    bounds = item.get('range_minutes') or {}
                    status = item.get('status')
                    self.put(conn, 'sleep_stage_comparisons', calc_run_id=rid, stage=stage, value_min=item.get('minutes'), ref_low_min=bounds.get('low'), ref_high_min=bounds.get('high'), reference_nights=night.get('nights_used'), status=status if status in ('within', 'above', 'below') else 'insufficient_data')

    def consistency(self, data):
        with self.db.connect() as conn:
            day = data.get('latest_sleep_date') or self.day
            rid = self.run(conn, 'sleep_consistency', data, day=day, subject=data.get('estimator', 'four_night_clock_consistency'), reason='no_qualifying_nights' if data.get('latest_score') is None else None)
            self.put(conn, 'sleep_consistency_results', calc_run_id=rid, user_id=self.user, sleep_date=day, score=data.get('latest_score'), drift_min=data.get('latest_drift_minutes'), window_days=4, nights_used=data.get('scored_days'))

    def activity(self, data):
        with self.db.connect() as conn:
            activity = conn.execute('SELECT activity_id FROM activities WHERE user_id=? AND start_ts=? AND end_ts=? LIMIT 1', (self.user, epoch(data['start']), epoch(data['end']))).fetchone()
            if activity is None:
                return
            rid = self.run(conn, 'workout', data, subject=activity[0], coverage=100*data.get('coverage', 0))
            self.put(conn, 'workout_results', calc_run_id=rid, user_id=self.user, activity_id=activity[0], strain=data.get('strain'), avg_hr_bpm=data.get('avg_hr'), max_hr_bpm=data.get('max_hr'), duration_s=round(data.get('duration_min', 0)*60))
            for key, value in data.get('averages', {}).items():
                if key in ('calories', 'steps'):
                    continue
                self.put(conn, 'workout_comparisons', calc_run_id=rid, comparison_key=key, value=data.get(key), prior_avg=value, comparison_count=data.get('comparison_count'))
            for zone in data.get('zones', []):
                if zone.get('minutes') is not None:
                    self.put(conn, 'workout_zone_durations', calc_run_id=rid, zone=zone['zone'], seconds=round(zone['minutes']*60), lower_bpm=zone.get('low'), upper_bpm=zone.get('high'))

    def sleep_stress(self, data):
        with self.db.connect() as conn:
            for night in data.get('nights', []):
                day = night['night_date']; sid = self.sleep_id(conn, provider_id=night['sleep_id'])
                if sid is None:
                    continue
                rid = self.run(conn, 'sleep_stress', night, day=day, subject=sid, coverage=100*night.get('coverage', 0), reason=night.get('withheld_reason'))
                self.put(conn, 'sleep_stress_results', calc_run_id=rid, user_id=self.user, sleep_session_id=sid, sleep_date=day, stressed_min=night.get('stressed_minutes'), stressed_pct=night.get('stress_pct'), episode_count=len(night.get('episodes', [])), coverage_pct=100*night.get('coverage', 0), hrv_timing_status='verified' if night.get('alignment_verified') else 'unverified', hrv_quality_status='unknown', stage_references_json=json_text(night.get('baseline', {})))
                conn.execute('DELETE FROM sleep_stress_episodes WHERE calc_run_id=?', (rid,))
                for episode in night.get('episodes', []):
                    self.put(conn, 'sleep_stress_episodes', calc_run_id=rid, start_ts=epoch(episode.get('start') or episode.get('start_utc')), end_ts=epoch(episode.get('end') or episode.get('end_utc')))


def persist_response(client, path, payload, day, params_hash=''):
    db = getattr(client, 'database', None)
    account = getattr(client, 'db_account', None)
    if db is None or account is None or payload.get('is_mock') is True:
        return
    writer = Results(db, account['user_id'], day)
    if path == '/api/sleep': writer.sleep(payload)
    elif path in ('/api/strain', '/api/home/metrics'): writer.strain(payload.get('strain') if isinstance(payload.get('strain'), dict) else payload)
    elif path == '/api/strain/analytics': writer.strain(payload['current'])
    elif path == '/api/recovery': writer.recovery(payload)
    elif path == '/api/recovery/analytics': writer.recovery(payload['current'])
    elif path == '/api/stress': writer.stress(payload)
    elif path == '/api/sleep/stages/typical-ranges': writer.stage_ranges(payload)
    elif path == '/api/sleep/stress':
        # The pipeline persists evidence before response-model defaults are
        # added. Do not supersede that run and detach its evidence windows.
        with db.connect() as conn:
            missing = [night for night in payload.get('nights', []) if not conn.execute('SELECT 1 FROM sleep_stress_results r JOIN calc_runs c USING(calc_run_id) JOIN sleep_sessions s USING(sleep_session_id) WHERE r.user_id=? AND s.provider_sleep_id=? AND c.is_current=1', (account['user_id'], night['sleep_id'])).fetchone()]
        if missing:
            writer.sleep_stress({'nights': missing})
    elif path == '/api/sleep/consistency/score': writer.consistency(payload)
    elif path == '/api/activity': writer.activity(payload)
    elif path == '/api/dashboard':
        writer.sleep(payload['sleep']); writer.strain(payload['strain']); writer.recovery(payload['recovery'])
    elif path == '/api/sleep/awake-heart-rate/recalculate':
        writer.awake(payload['awake_heart_rate']['date'], payload['awake_heart_rate']); writer.sleep(payload['sleep'])
    with db.connect() as conn:
        conn.execute('INSERT INTO presentation_snapshots(user_id,view_key,as_of_date,params_hash,payload) VALUES (?,?,?,?,?) ON CONFLICT(user_id,view_key,as_of_date,params_hash) DO UPDATE SET payload=excluded.payload,built_at=excluded.built_at,is_stale=0',
                     (account['user_id'], path, str(day), params_hash, json_text(without_day_traces(payload))))
