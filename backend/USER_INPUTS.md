# Effort ratings and morning check-ins

Two things the user enters, saved per account in the normalized SQLite database
(`backend/user_inputs.py`, tables created on first use). Demo mode shows the
controls but saves nothing; saving needs a connected account (401 otherwise).

## Workout effort (effort load)

- Every workout gets a 1–10 "how hard was this workout overall?" rating on its
  activity page, grouped like Apple Watch: Easy 1–3, Moderate 4–6, Hard 7–8,
  All Out 9–10.
- Until the user rates it, the page shows an estimate from the workout's
  heart-rate Strain: each Strain band (Light <10, Moderate 10–14, High 14–18,
  All Out 18+) is spread over the matching effort numbers
  (`frontend/lib/effort.ts`). The estimate is saved only if the user keeps it.
- Effort load = effort × workout minutes, in arbitrary units (Foster 2001;
  validated for resistance training by Lea et al. 2022). Heart rate undercounts
  lifting, so for strength work the rating carries the load.
- It is shown on its own: on the activity page and as today / last 7 days /
  4-week weekly average on the Strain page. It is never converted into the
  heart-rate 0–21 Day Strain, because no validated conversion exists.
- `GET /api/effort?start&end` returns ratings and `daily_load`;
  `PUT /api/effort` saves `{activity_id, date, rpe, minutes}` (rpe 1–10,
  0 < minutes ≤ 600, no future dates); `DELETE /api/effort/{activity_id}` clears.

## Morning check-in

- One tap on the Recovery page: "How do you feel this morning?" from 1 (awful)
  to 5 (great). Self-reported wellness tracks training response at least as
  well as objective measures (Saw et al. 2015).
- It does not change the Recovery score. After about six weeks of check-ins,
  Recovery's weights can be compared with, and fitted to, how the user felt.
- `GET /api/checkins?start&end` and `PUT /api/checkins` with `{date, feeling}`.

Ranges default to the 28 days ending on the user's local date and may span at
most 400 days.
