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

# Lab 2: Terraform Modules (Files Service + S3)

This lab teaches how to extend infrastructure with Terraform modules for a new
microservice. You will add a files-service that uses S3 for uploads, listings,
and downloads.

## What the Dev Team Already Built
- Files service (Node/Express + AWS SDK + multer) with routes under `/api/files/*`.
- UI wiring for uploads, list, and downloads in `MainComponent.js`.
- Kubernetes manifests:
  - `files-service-deployment.yml`
  - `files-service-cluster-ip-service.yml`
  - `ingress-service.yml` routing `/api/files/*`
- Docker images:
  - `prashantdey/merndemoapp:fileservice1.0`
  - `prashantdey/merndemoapp:clientv1.0`
- Required env vars for the service: `S3_BUCKET`, `S3_PREFIX`, `AWS_REGION`.
- IRSA setup:
  - IAM policy with `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`.
  - Service account `files-service-sa` bound to that policy.
  - Deployment updated to use the service account.
- Moods table fixes (permanent):
  - `postgres-init-config.yml` and `postgres-migrate-job.yml`.

## Your Task
Create Terraform modules so the infra changes above are reproducible.

### 1) Build a Files Service Module
Your module should:
- Create the IRSA IAM policy and role.
- Create or reference the S3 bucket.
- Create the Kubernetes service account with the IRSA annotation.
- Deploy the Kubernetes manifests for:
  - files-service deployment
  - ClusterIP service
  - Ingress route `/api/files/*`

Suggested inputs:
- Cluster name/region, namespace, OIDC provider ARN/URL.
- Image tags for files-service and client (if managed in Terraform).
- `S3_BUCKET`, `S3_PREFIX`, `AWS_REGION`.

Suggested outputs:
- Bucket name, service account name, and any service/ingress endpoints.

### 2) Wire It Into the Root Stack
- Call the module from your root Terraform configuration.
- Ensure dependencies are ordered: S3 + IAM + IRSA before the deployment.
- Keep the service account name consistent with `files-service-sa`.

### 3) Apply Order (for reference)
1. `postgres-init-config.yml`
2. `postgres-migrate-job.yml`
3. S3 + IAM + IRSA resources
4. files-service deployment, service, and ingress

## Acceptance Criteria
- Files upload to S3, list correctly, and can be downloaded.
- The files-service pod runs with the IRSA service account (no static AWS keys).
- Ingress routes `/api/files/*` to the files-service.

## Tips
- Use module outputs to pass the bucket name into the Kubernetes deployment.
- Keep the policy scope limited to the bucket and prefix.
