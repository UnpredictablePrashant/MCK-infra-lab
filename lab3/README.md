# Lab 3: CI/CD on GitHub Actions (Self-Hosted Runner + EKS)

This lab extends the GratitudeApp delivery pipeline for a senior profile.
You will build a production-grade CI/CD workflow on GitHub Actions using a
self-hosted runner, quality gates with SonarQube, container scanning with
Trivy, and automated deployment to EKS.

App repo: https://github.com/UnpredictablePrashant/GratitudeApp

## What You Are Building
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

## Lab Steps

### 1) Provision the Runner
Follow `lab3/runner-setup.md` to set up the self-hosted runner machine.

### 2) Add the Workflow Files
Copy templates into the app repo:
- `lab3/templates/ci.yml` -> `.github/workflows/ci.yml`
- `lab3/templates/cd.yml` -> `.github/workflows/cd.yml`

Update placeholders in the templates (deployment name, manifest path, etc.).

### 3) Configure GitHub Secrets
Set these in repo settings:
- `AWS_REGION`
- `AWS_ACCOUNT_ID`
- `ECR_REPOSITORY`
- `EKS_CLUSTER_NAME`
- `SONAR_HOST_URL`
- `SONAR_TOKEN`

Optional:
- `AWS_ROLE_ARN` (OIDC assume role if not using instance profile)
- `K8S_MANIFEST_PATH` (default: `k8s`)
- `DEPLOYMENT_NAME` (default: `gratitudeapp`)
- `SLACK_WEBHOOK`

### 4) Run CI and CD
- Open a PR to trigger CI (SonarQube + Trivy filesystem scan).
- Merge to `main` to trigger CD (build, scan, push, deploy).

## Acceptance Criteria
- CI runs on pull requests and reports SonarQube + Trivy results.
- CD runs on merge to `main` and deploys to EKS automatically.
- Pipeline fails on quality gate or critical vulnerabilities.
- Deployment is repeatable and observable via rollout status.

## Tips
- Use OIDC or instance role on the runner instead of static AWS keys.
- Use caching (npm/pip/gradle) to speed up builds.
- Keep the runner isolated and updated; treat it as production infra.
