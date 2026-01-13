# Lab 1: Database Migration + Sync (Zero Downtime)

This lab teaches safe database migration and data synchronization. You will:
- Deploy the app in your own Kubernetes environment.
- Migrate the database with zero downtime.
- Verify data parity against the baseline app using the provided verifier UI.

## What You Are Building
You will run the verifier service in this folder. It:
- Accepts student app submissions (name + URL).
- Runs comparisons by the lab staff (not by students).
- Shows a shared leaderboard so everyone can see sync status.
- Automatically fills the baseline app and student apps on a timer (server-side).

## Prerequisites
- Python 3.9+
- Chrome/Chromium installed for Selenium (headless)
- Access to a Kubernetes cluster
- Your own app deployment endpoint (public URL)

## Baseline App
Baseline is the reference deployment used for comparison:
```
http://a218f40cdece3464687b8c8c7d8addf2-557072703.us-east-1.elb.amazonaws.com
```

## Run the Verifier Service
```bash
pip install -r requirements.txt
python3 app.py
```
Open:
- `http://localhost:8000` for students to submit their app link
- `http://localhost:8000/leaderboard` for the shared sync status and logs

Optional environment variables:
```
BASELINE_URL=http://a218f40cdece3464687b8c8c7d8addf2-557072703.us-east-1.elb.amazonaws.com
FILL_INTERVAL_SECONDS=120
FILL_ITERATIONS=1
FILL_MODE=all
DB_PATH=app.db
```

## How the Comparison Works
The verifier compares your app to the baseline using these endpoints:
- `/api/moods/all`
- `/api/journal/entries/all`
- `/api/stats/overview`
- `/api/server/values/all`

Only the DNS/host changes between baseline and your app. Paths are identical.

## Migration Steps (Zero Downtime)
Use a safe, phased migration strategy. The exact tooling depends on your stack,
but the workflow below is the standard approach.

### 1) Prepare (Expand)
- Add new tables/columns in a backward-compatible way.
- Avoid dropping or renaming fields in this phase.
- Deploy app code that can read/write both the old and new schema if needed.

### 2) Backfill
- Copy existing data into the new schema.
- Use a background job or migration script; do not block live traffic.
- Validate row counts and sample records.

### 3) Dual-Write / Sync
- Temporarily write to both old and new tables (or old and new DBs).
- Keep both in sync while traffic is live.
- Monitor lag or write errors.

### 4) Cutover (No Downtime)
- Switch reads to the new schema/database.
- Keep dual-write for a short stabilization window.
- Validate parity with the verifier.

### 5) Contract (Cleanup)
- Remove old tables/columns and turn off dual-writes.
- Update code to read/write only the new schema.

## Suggested Verification Workflow
1. Deploy your app on Kubernetes with the new DB.
2. Run your migration/backfill/dual-write steps.
3. Submit your app URL via the verifier UI.
4. Lab staff runs comparisons and updates the leaderboard.
5. Everyone can view sync status on the leaderboard.

## Troubleshooting
- If your app shows “Out of sync”, inspect the mismatched endpoint.
- Ensure your app’s API paths and payloads match the baseline.
- Confirm the migration completed and that data is up-to-date.

## Notes
- The leaderboard is persisted in SQLite (`app.db`).
- Logs are capped in the UI to avoid excessive memory usage.
