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

App repo: https://github.com/UnpredictablePrashant/GratitudeApp

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

### 2) Required Module Inputs (Explicit)
- `s3_bucket_name`
- `s3_prefix`
- `aws_region`
- `cluster_name`
- `namespace`
- `oidc_provider_arn`
- `oidc_provider_url`
- `files_service_image`
- `client_image` (optional, if managed in Terraform)

### 3) Module Resources (What to Create)
- S3 bucket (or data source if pre-existing).
- IAM policy scoped to the bucket/prefix:
  - `s3:PutObject`
  - `s3:GetObject`
  - `s3:ListBucket`
- IAM role for IRSA and trust policy for the cluster OIDC provider.
- Kubernetes service account `files-service-sa` annotated with the role ARN.
- Kubernetes deployment for files-service with:
  - env vars: `S3_BUCKET`, `S3_PREFIX`, `AWS_REGION`
  - `serviceAccountName: files-service-sa`
- ClusterIP service for files-service.
- Ingress route `/api/files/*`.

### 4) Wire It Into the Root Stack
- Call the module from your root Terraform configuration.
- Ensure dependencies are ordered: S3 + IAM + IRSA before the deployment.
- Keep the service account name consistent with `files-service-sa`.

### 5) Apply Order (for reference)
1. `postgres-init-config.yml`
2. `postgres-migrate-job.yml`
3. S3 + IAM + IRSA resources
4. files-service deployment, service, and ingress

### 6) Validation Checklist
- Files upload to S3, list correctly, and can be downloaded from the UI.
- `files-service` pods run using IRSA (no static AWS keys).
- Ingress routes `/api/files/*` to the files-service.
- Terraform plan/apply is repeatable without manual kubectl steps.

## Acceptance Criteria
- Files upload to S3, list correctly, and can be downloaded.
- The files-service pod runs with the IRSA service account (no static AWS keys).
- Ingress routes `/api/files/*` to the files-service.

## Tips
- Use module outputs to pass the bucket name into the Kubernetes deployment.
- Keep the policy scope limited to the bucket and prefix.

# Lab 3: CI/CD on GitHub Actions (Self-Hosted Runner + EKS)

This lab extends the GratitudeApp delivery pipeline for a senior profile.
You will build a production-grade CI/CD workflow on GitHub Actions using a
self-hosted runner, quality gates with SonarQube, container scanning with
Trivy, and automated deployment to EKS.

App repo: https://github.com/UnpredictablePrashant/GratitudeApp

## What You Are Building
You will implement:
- A self-hosted GitHub Actions runner machine (EC2 or on-prem VM).
- A CI pipeline with tests, linting, SonarQube analysis, and Trivy scans.
- A CD pipeline that builds and pushes images, then deploys to EKS.
- Secure secrets handling and least-privilege access to AWS and the cluster.

## Prerequisites
- GitHub repo admin access for Actions and secrets.
- An EKS cluster (existing or created in earlier labs).
- An ECR repo for container images.
- A running SonarQube instance with a project + token.
- A runner machine with Docker, git, and AWS CLI installed.

## Runner Machine Setup
1) Provision an EC2 instance (t3.medium+ recommended) in the same VPC as EKS.
2) Install Docker, git, AWS CLI, kubectl, and jq.
3) Register the self-hosted runner to your repo or org.
4) Ensure the runner can:
   - Reach SonarQube (network + token).
   - Push to ECR.
   - Access EKS (kubectl auth).

## Pipeline Overview
Use two workflows:
1) CI workflow (pull requests):
   - Install dependencies
   - Run unit tests
   - SonarQube analysis + quality gate
   - Trivy filesystem scan (dependencies)
2) CD workflow (main branch):
   - Build Docker image
   - Trivy image scan
   - Push image to ECR
   - Deploy to EKS (kubectl/Helm)

## Required Secrets (GitHub)
Set these in repo settings:
- `AWS_REGION`
- `AWS_ACCOUNT_ID`
- `ECR_REPOSITORY`
- `EKS_CLUSTER_NAME`
- `SONAR_HOST_URL`
- `SONAR_TOKEN`
- `KUBECONFIG_B64` (if not using IAM auth on runner)

Optional:
- `SLACK_WEBHOOK` (deployment notifications)

## Suggested Workflow Files
Create:
- `.github/workflows/ci.yml`
- `.github/workflows/cd.yml`

### ci.yml (example structure)
- Trigger: `pull_request`
- Runs on: `self-hosted`
- Steps:
  1) Checkout
  2) Setup Node/Java (if needed)
  3) Install deps and run tests
  4) SonarQube scan + quality gate
  5) Trivy filesystem scan

### cd.yml (example structure)
- Trigger: `push` to `main`
- Runs on: `self-hosted`
- Steps:
  1) Checkout
  2) Login to ECR
  3) Build and tag Docker image
  4) Trivy image scan
  5) Push to ECR
  6) Deploy to EKS (kubectl apply or Helm upgrade)
  7) Verify rollout status

## SonarQube Notes
- Enforce a quality gate that blocks CD when it fails.
- Use project key: `gratitudeapp` (or your naming standard).
- If using SonarQube Scanner, ensure Java is installed on the runner.

## Trivy Notes
Use:
- Filesystem scan in CI: `trivy fs --severity HIGH,CRITICAL .`
- Image scan in CD: `trivy image --severity HIGH,CRITICAL <image>`
- Fail the pipeline on critical vulnerabilities.

## Deployment Notes (EKS)
- Prefer `kubectl set image` or Helm for rollout.
- Use namespaces for dev/stage/prod.
- Track deployment status with `kubectl rollout status`.
- Store Kubernetes manifests in a `/k8s` folder in the app repo.

## Acceptance Criteria
- CI runs on pull requests and reports SonarQube + Trivy results.
- CD runs on merge to `main` and deploys to EKS automatically.
- Pipeline fails on quality gate or critical vulnerabilities.
- Deployment is repeatable and observable via rollout status.

## Tips
- Use OIDC or instance role on the runner instead of static AWS keys.
- Use caching (npm/pip/gradle) to speed up builds.
- Keep the runner isolated and updated; treat it as production infra.
