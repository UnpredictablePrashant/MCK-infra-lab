import json
import os
import random
import sqlite3
import threading
import time
from urllib.parse import urlparse

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
    redirect,
    url_for,
    send_file,
)
from flask_sock import Sock

from compare_utils import DEFAULT_COMPARE_ENDPOINTS, compare_endpoints
from form_filler import generate_entry_text, run_fill_session
from migrate_db import run as run_migrations


DEFAULT_BASELINE_URL = (
    "http://a218f40cdece3464687b8c8c7d8addf2-557072703.us-east-1.elb.amazonaws.com/"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DOWNLOADS = {
    "lab3_ci_template": "lab3/templates/ci.yml",
    "lab3_cd_template": "lab3/templates/cd.yml",
    "lab3_runner_setup": "lab3/runner-setup.md",
    "lab3_blueprint": "lab3/blueprint.md",
    "lab3_orchestrator": "lab3/templates/orchestrator.yml",
    "lab3_reusable_build": "lab3/templates/reusable-build.yml",
    "lab3_reusable_deploy": "lab3/templates/reusable-deploy.yml",
}

LABS = {
    "lab1": {
        "id": "lab1",
        "code": "Lab 1",
        "title": "Zero-Downtime Migration",
        "status": "Active",
        "summary": "Migrate safely, keep data in sync, and verify parity against a baseline.",
        "tagline": (
            "Deploy the app, run an expand/backfill/cutover migration, and verify "
            "your data matches the baseline."
        ),
        "facts": [
            {"title": "Level", "body": "Intermediate"},
            {"title": "Estimated time", "body": "2-3 hours"},
            {"title": "Primary focus", "body": "Database migration safety"},
            {"title": "Stack", "body": "Kubernetes, Postgres, Flask verifier"},
        ],
        "steps": [
            {
                "title": "Deploy the app",
                "body": "Launch your app in Kubernetes and expose a public URL.",
                "output": "Live app URL for verification.",
                "details": (
                    "Deploy the GratitudeApp into your Kubernetes cluster. Ensure the "
                    "service is reachable from the public internet so the verifier can "
                    "compare endpoints."
                ),
                "code": "kubectl apply -f k8s/\n"
                "kubectl get ingress",
            },
            {
                "title": "Expand schema",
                "body": "Add backward-compatible tables/columns.",
                "output": "Migration applied without downtime.",
                "details": (
                    "Add new columns/tables without dropping or renaming existing "
                    "fields. The live app must keep working during the change."
                ),
                "code": "ALTER TABLE journal_entries ADD COLUMN mood_tag TEXT;",
            },
            {
                "title": "Backfill data",
                "body": "Copy existing data into the new schema.",
                "output": "Backfill logs + row counts.",
                "details": (
                    "Run a background job or migration script that copies data into "
                    "the new schema without blocking writes."
                ),
                "code": "python3 migrate_db.py",
            },
            {
                "title": "Dual-write",
                "body": "Write to old and new schema while traffic is live.",
                "output": "Both schemas updated on new writes.",
                "details": (
                    "Update the app so each write operation updates both the old and "
                    "new schema. Monitor error logs for mismatched writes."
                ),
                "code": "write_old(payload)\nwrite_new(payload)",
            },
            {
                "title": "Cutover + verify",
                "body": "Switch reads to the new schema and submit for comparison.",
                "output": "Leaderboard shows in-sync status.",
                "details": (
                    "Update the read path to use the new schema. Submit your app URL "
                    "to the verifier and confirm endpoints match the baseline."
                ),
                "code": "BASELINE_URL=... python3 app.py",
            },
        ],
        "deliverables": [
            {
                "title": "Migration plan",
                "body": "Documented expand/backfill/dual-write/cutover approach.",
            },
            {
                "title": "App endpoint",
                "body": "Public URL registered in the verifier.",
            },
            {
                "title": "Verification evidence",
                "body": "Sync status from leaderboard or comparison logs.",
            },
        ],
        "validation": [
            "API responses match baseline for all verifier endpoints.",
            "No downtime during migration.",
            "All data present after cutover.",
        ],
        "resources": [
            {
                "title": "Baseline app",
                "body": DEFAULT_BASELINE_URL.rstrip("/"),
            },
            {
                "title": "Verifier endpoints",
                "body": "/api/moods/all, /api/journal/entries/all, /api/stats/overview",
            },
            {
                "title": "Server values",
                "body": "/api/server/values/all",
            },
        ],
        "compare_enabled": True,
        "automation_enabled": True,
        "leaderboard_enabled": True,
        "submission_enabled": True,
        "form_cta": "Run comparison",
        "form_helper": "Submit your app URL to compare against the baseline.",
        "sections": [
            {
                "title": "Core steps",
                "items": [
                    {"title": "Deploy", "body": "Launch your app on Kubernetes."},
                    {
                        "title": "Migrate",
                        "body": "Use expand/backfill/dual-write for zero downtime.",
                    },
                    {"title": "Submit", "body": "Register your app URL for checking."},
                    {
                        "title": "Verify",
                        "body": "Track sync status on the lab leaderboard.",
                    },
                ],
            },
            {
                "title": "Zero-downtime phases",
                "items": [
                    {"title": "Expand", "body": "Add new schema fields safely."},
                    {"title": "Backfill", "body": "Copy data without blocking traffic."},
                    {"title": "Dual-write", "body": "Keep old and new data in sync."},
                    {"title": "Cutover", "body": "Switch reads to the new schema."},
                ],
            },
            {
                "title": "Verifier endpoints",
                "items": [
                    {"title": "/api/moods/all", "body": "Mood entry parity."},
                    {"title": "/api/journal/entries/all", "body": "Journal entry parity."},
                    {"title": "/api/stats/overview", "body": "Aggregate stats parity."},
                    {"title": "/api/server/values/all", "body": "Server state parity."},
                ],
            },
        ],
    },
    "lab2": {
        "id": "lab2",
        "code": "Lab 2",
        "title": "Terraform Modules: Files Service + S3",
        "status": "Active",
        "summary": "Add a files microservice with S3 storage using reusable Terraform modules.",
        "tagline": (
            "Build a Terraform module that provisions S3 + IAM + IRSA and deploys the "
            "files-service into the existing app stack."
        ),
        "facts": [
            {"title": "Level", "body": "Intermediate"},
            {"title": "Estimated time", "body": "3-4 hours"},
            {"title": "Primary focus", "body": "Terraform modularization"},
            {"title": "Stack", "body": "Terraform, EKS, S3, IAM/IRSA"},
        ],
        "steps": [
            {
                "title": "Scaffold module",
                "body": "Create module structure for the files-service stack.",
                "output": "Reusable module folder with inputs/outputs.",
                "details": (
                    "Create inputs for cluster, namespace, and S3 settings. Export "
                    "outputs like bucket name and service account."
                ),
                "code": "variable \"s3_bucket_name\" {\n  type = string\n}\n\n"
                "output \"bucket_name\" {\n  value = aws_s3_bucket.files.bucket\n}",
            },
            {
                "title": "Provision S3 + IAM",
                "body": "Add bucket, IAM policy, and IRSA role.",
                "output": "Role ARN for files-service-sa.",
                "details": (
                    "Scope the IAM policy to only the bucket and optional prefix. "
                    "Bind the role to the OIDC provider for IRSA."
                ),
                "code": "s3:PutObject\ns3:GetObject\ns3:ListBucket",
            },
            {
                "title": "Deploy Kubernetes resources",
                "body": "Use Terraform to deploy deployment/service/ingress.",
                "output": "files-service pods running with IRSA.",
                "details": (
                    "Use the Kubernetes provider to apply deployment, service, and "
                    "ingress manifests with the files-service service account."
                ),
                "code": "service_account_name = \"files-service-sa\"",
            },
            {
                "title": "Wire the root stack",
                "body": "Call the module and order dependencies.",
                "output": "Root plan applies without manual kubectl steps.",
                "details": (
                    "Call the module from root and pass in required variables. "
                    "Ensure S3/IAM resources are created before deployment."
                ),
                "code": "module \"files_service\" {\n  source = \"./modules/files\"\n}",
            },
            {
                "title": "Validate file flow",
                "body": "Upload, list, and download from the UI.",
                "output": "Files stored in S3 with correct prefix.",
                "details": (
                    "Use the GratitudeApp UI to upload a file, list it, and download "
                    "it again. Validate objects in S3."
                ),
                "code": "aws s3 ls s3://<bucket>/<prefix>/",
            },
        ],
        "deliverables": [
            {
                "title": "Terraform module",
                "body": "Module that provisions S3, IAM/IRSA, and k8s resources.",
            },
            {
                "title": "Root integration",
                "body": "Module call wired into the root stack.",
            },
            {
                "title": "Validation evidence",
                "body": "Screenshots or logs showing file upload + download.",
            },
        ],
        "validation": [
            "files-service uses IRSA (no static AWS keys).",
            "Ingress routes /api/files/* correctly.",
            "Terraform apply is repeatable without manual steps.",
        ],
        "resources": [
            {
                "title": "App repo",
                "body": "https://github.com/UnpredictablePrashant/GratitudeApp",
            },
            {
                "title": "Service account",
                "body": "files-service-sa with IRSA annotation.",
            },
            {
                "title": "Images",
                "body": "prashantdey/merndemoapp:fileservice1.0, clientv1.0",
            },
        ],
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "Register endpoint",
        "form_helper": "No submissions required for Lab 2.",
        "sections": [
            {
                "title": "What you will build",
                "items": [
                    {
                        "title": "Terraform module",
                        "body": (
                            "Create a reusable module that provisions the files-service "
                            "stack: S3 bucket, IAM policy/role, IRSA service account, and "
                            "Kubernetes deployment/service/ingress."
                        ),
                    },
                    {
                        "title": "Automation ready",
                        "body": (
                            "The module must be callable from the root stack so new labs can "
                            "enable files-service automatically without manual kubectl steps."
                        ),
                    },
                    {
                        "title": "Target app",
                        "body": (
                            "Use the GratitudeApp repo as the base application: "
                            "https://github.com/UnpredictablePrashant/GratitudeApp."
                        ),
                    },
                ],
            },
            {
                "title": "Inputs you must expose",
                "items": [
                    {
                        "title": "S3 settings",
                        "body": "S3_BUCKET, S3_PREFIX, and AWS_REGION as module inputs.",
                    },
                    {
                        "title": "Cluster + namespace",
                        "body": "Cluster name/region, namespace, and OIDC provider details.",
                    },
                    {
                        "title": "Images",
                        "body": (
                            "Files service image tag (prashantdey/merndemoapp:fileservice1.0) "
                            "and UI image tag if managed in Terraform."
                        ),
                    },
                ],
            },
            {
                "title": "IAM + IRSA requirements",
                "items": [
                    {
                        "title": "IAM policy",
                        "body": (
                            "Allow s3:PutObject, s3:GetObject, and s3:ListBucket scoped to "
                            "your bucket and optional prefix."
                        ),
                    },
                    {
                        "title": "IRSA role",
                        "body": "Create an IAM role for service account files-service-sa.",
                    },
                    {
                        "title": "Service account",
                        "body": (
                            "Annotate files-service-sa with the role ARN and bind it in the "
                            "deployment."
                        ),
                    },
                ],
            },
            {
                "title": "Kubernetes resources",
                "items": [
                    {
                        "title": "Deployment",
                        "body": (
                            "Deploy files-service with env vars for S3_BUCKET, S3_PREFIX, "
                            "AWS_REGION and the IRSA service account."
                        ),
                    },
                    {
                        "title": "Service",
                        "body": "Create a ClusterIP service for internal routing.",
                    },
                    {
                        "title": "Ingress",
                        "body": "Route /api/files/* to the files-service.",
                    },
                ],
            },
            {
                "title": "Dev team additions (already built)",
                "items": [
                    {
                        "title": "Service",
                        "body": "Node/Express + AWS SDK + multer under /api/files/*.",
                    },
                    {
                        "title": "Images",
                        "body": (
                            "prashantdey/merndemoapp:fileservice1.0 and "
                            "prashantdey/merndemoapp:clientv1.0."
                        ),
                    },
                    {
                        "title": "Kubernetes",
                        "body": (
                            "files-service-deployment.yml, files-service-cluster-ip-service.yml, "
                            "ingress-service.yml with /api/files/*."
                        ),
                    },
                ],
            },
            {
                "title": "Apply order + validation",
                "items": [
                    {
                        "title": "DB fixes",
                        "body": "Apply postgres-init-config.yml and postgres-migrate-job.yml.",
                    },
                    {
                        "title": "Infra rollout",
                        "body": "Apply S3 + IAM + IRSA before the deployment.",
                    },
                    {
                        "title": "Success criteria",
                        "body": (
                            "Upload a file, list objects, and download from the UI. "
                            "Confirm the pod uses IRSA (no static AWS keys)."
                        ),
                    },
                ],
            },
        ],
    },
    "lab3": {
        "id": "lab3",
        "code": "Lab 3",
        "title": "CI/CD on GitHub Actions + EKS",
        "status": "Active",
        "summary": (
            "Create a senior-grade pipeline with SonarQube quality gates, "
            "Trivy scans, and automated EKS deploys."
        ),
        "tagline": (
            "Stand up a self-hosted runner, enforce quality gates, scan for "
            "vulnerabilities, and deploy to EKS on merge."
        ),
        "facts": [
            {"title": "Level", "body": "Senior"},
            {"title": "Estimated time", "body": "4-6 hours"},
            {"title": "Primary focus", "body": "Advanced GitHub Actions + security gates"},
            {"title": "Stack", "body": "GitHub Actions, SonarQube, Trivy, ECR, EKS"},
            {"title": "Runner", "body": "Self-hosted EC2 with Docker Buildx"},
        ],
        "steps": [
            {
                "title": "Baseline infra (EKS + ECR)",
                "body": "Ensure EKS, ingress, CSI, and ECR repos exist per README.",
                "output": "ECR repos for all services are ready.",
                "details": (
                    "Create ECR repos for client, api-gateway, entries, moods-api, "
                    "moods-service, server, stats-api, stats-service, files-service."
                ),
                "code": "aws ecr create-repository --repository-name gratitudeapp-client\n"
                "aws ecr create-repository --repository-name gratitudeapp-api-gateway\n"
                "aws ecr create-repository --repository-name gratitudeapp-entries\n"
                "aws ecr create-repository --repository-name gratitudeapp-moods-api\n"
                "aws ecr create-repository --repository-name gratitudeapp-moods-service\n"
                "aws ecr create-repository --repository-name gratitudeapp-server\n"
                "aws ecr create-repository --repository-name gratitudeapp-stats-api\n"
                "aws ecr create-repository --repository-name gratitudeapp-stats-service\n"
                "aws ecr create-repository --repository-name gratitudeapp-files-service",
            },
            {
                "title": "OIDC role for GitHub Actions",
                "body": "Create IAM role trusting GitHub OIDC with least privilege.",
                "output": "Role ARN stored in GitHub secrets.",
                "details": (
                    "Grant minimal ECR push permissions and eks:DescribeCluster. "
                    "Use AWS_ROLE_TO_ASSUME in GitHub Actions secrets."
                ),
                "code": "{\n"
                "  \"Version\": \"2012-10-17\",\n"
                "  \"Statement\": [\n"
                "    {\n"
                "      \"Effect\": \"Allow\",\n"
                "      \"Principal\": {\n"
                "        \"Federated\": \"arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com\"\n"
                "      },\n"
                "      \"Action\": \"sts:AssumeRoleWithWebIdentity\",\n"
                "      \"Condition\": {\n"
                "        \"StringLike\": {\n"
                "          \"token.actions.githubusercontent.com:sub\": \"repo:<ORG>/<REPO>:*\"\n"
                "        }\n"
                "      }\n"
                "    }\n"
                "  ]\n"
                "}\n"
                "\n"
                "permissions:\n"
                "  id-token: write\n"
                "  contents: read",
            },
            {
                "title": "Provision self-hosted runner",
                "body": "Register an EC2 runner with Docker, kubectl, helm, awscli.",
                "output": "Runner online with labels gratitude-runner.",
                "details": (
                    "Recommended t3.large+ for parallel builds. Manage disk usage, "
                    "workspace cleanup, and concurrency on the runner."
                ),
                "code": "sudo apt-get update\n"
                "sudo apt-get install -y docker.io jq\n"
                "curl -sL https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o awscliv2.zip\n"
                "unzip awscliv2.zip && sudo ./aws/install\n"
                "curl -LO https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl\n"
                "sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl\n"
                "curl -LO https://get.helm.sh/helm-v3.14.0-linux-amd64.tar.gz\n"
                "tar -xzf helm-v3.14.0-linux-amd64.tar.gz && sudo mv linux-amd64/helm /usr/local/bin/helm",
                "downloads": [
                    {
                        "key": "lab3_runner_setup",
                        "label": "Runner setup guide",
                    },
                    {
                        "key": "lab3_blueprint",
                        "label": "Full lab blueprint",
                    },
                ],
            },
            {
                "title": "Create orchestration workflow",
                "body": "Detect changed services, fan-out builds, then fan-in deploy.",
                "output": "orchestrator.yml runs matrix builds in parallel.",
                "details": (
                    "Use dorny/paths-filter for change detection and fromJSON() to "
                    "build a dynamic matrix. Add workflow_dispatch inputs to "
                    "toggle build_all and deploy."
                ),
                "code": "jobs:\n"
                "  detect-changes:\n"
                "    runs-on: ubuntu-latest\n"
                "    outputs:\n"
                "      matrix: ${{ steps.set-matrix.outputs.matrix }}\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "      - id: filter\n"
                "        uses: dorny/paths-filter@v3\n"
                "        with:\n"
                "          filters: |\n"
                "            client: [\"client/**\"]\n"
                "            api-gateway: [\"services/api-gateway/**\"]\n"
                "      - id: set-matrix\n"
                "        run: |\n"
                "          echo 'matrix={\"include\":[{\"name\":\"client\",\"path\":\"client\",\"ecr_repo\":\"gratitudeapp-client\"}]}' >> $GITHUB_OUTPUT\n"
                "\n"
                "  build:\n"
                "    needs: detect-changes\n"
                "    strategy:\n"
                "      fail-fast: false\n"
                "      matrix: ${{ fromJSON(needs.detect-changes.outputs.matrix) }}\n"
                "    uses: ./.github/workflows/reusable-build.yml\n"
                "    with:\n"
                "      service_name: ${{ matrix.name }}\n"
                "      service_path: ${{ matrix.path }}\n"
                "      ecr_repo: ${{ matrix.ecr_repo }}\n"
                "      image_tag: ${{ github.sha }}\n"
                "    secrets: inherit",
                "downloads": [
                    {
                        "key": "lab3_orchestrator",
                        "label": "Download orchestrator.yml",
                    }
                ],
            },
            {
                "title": "Reusable build workflow",
                "body": "Build, test, SonarQube scan, Trivy scan, then push to ECR.",
                "output": "Images pushed only after quality gates pass.",
                "details": (
                    "Use workflow_call inputs for service_name/path/repo. Add "
                    "SonarQube scanning, Trivy fs + image scans, and fail on "
                    "HIGH/CRITICAL vulnerabilities."
                ),
                "code": "jobs:\n"
                "  build_scan_push:\n"
                "    runs-on: [self-hosted, linux, x64, gratitude-runner]\n"
                "    permissions:\n"
                "      id-token: write\n"
                "      contents: read\n"
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "      - uses: aws-actions/configure-aws-credentials@v4\n"
                "        with:\n"
                "          role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}\n"
                "          aws-region: ${{ secrets.AWS_REGION }}\n"
                "      - uses: aws-actions/amazon-ecr-login@v2\n"
                "      - uses: docker/build-push-action@v6\n"
                "        with:\n"
                "          context: ${{ inputs.service_path }}\n"
                "          push: false\n"
                "          tags: ${{ env.ECR_BASE }}/${{ inputs.ecr_repo }}:${{ inputs.image_tag }}\n"
                "      - name: SonarQube scan\n"
                "        run: |\n"
                "          docker run --rm \\\n"
                "            -e SONAR_HOST_URL=\"${{ secrets.SONAR_HOST_URL }}\" \\\n"
                "            -e SONAR_TOKEN=\"${{ secrets.SONAR_TOKEN }}\" \\\n"
                "            -v \"${{ github.workspace }}:/usr/src\" \\\n"
                "            sonarsource/sonar-scanner-cli:latest \\\n"
                "            -Dsonar.projectKey=gratitudeapp-${{ inputs.service_name }} \\\n"
                "            -Dsonar.sources=${{ inputs.service_path }}\n"
                "      - uses: aquasecurity/trivy-action@0.24.0\n"
                "        with:\n"
                "          scan-type: fs\n"
                "          scan-ref: ${{ inputs.service_path }}\n"
                "          exit-code: \"1\"\n"
                "          severity: \"CRITICAL,HIGH\"\n"
                "      - uses: aquasecurity/trivy-action@0.24.0\n"
                "        with:\n"
                "          scan-type: image\n"
                "          image-ref: ${{ env.ECR_BASE }}/${{ inputs.ecr_repo }}:${{ inputs.image_tag }}\n"
                "          exit-code: \"1\"\n"
                "          severity: \"CRITICAL,HIGH\"\n"
                "      - uses: docker/build-push-action@v6\n"
                "        with:\n"
                "          context: ${{ inputs.service_path }}\n"
                "          push: true\n"
                "          tags: ${{ env.ECR_BASE }}/${{ inputs.ecr_repo }}:${{ inputs.image_tag }}",
                "downloads": [
                    {
                        "key": "lab3_reusable_build",
                        "label": "Download reusable-build.yml",
                    }
                ],
            },
            {
                "title": "Reusable deploy workflow",
                "body": "Deploy to EKS after all builds complete.",
                "output": "Rollout status verified for each deployment.",
                "details": (
                    "Use kubectl apply for manifests and kubectl set image to update "
                    "tags. Gate production with GitHub Environments approval."
                ),
                "code": "jobs:\n"
                "  deploy:\n"
                "    runs-on: [self-hosted, linux, x64, gratitude-runner]\n"
                "    permissions:\n"
                "      id-token: write\n"
                "      contents: read\n"
                "    environment:\n"
                "      name: prod\n"
                "    steps:\n"
                "      - uses: aws-actions/configure-aws-credentials@v4\n"
                "        with:\n"
                "          role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}\n"
                "          aws-region: ${{ secrets.AWS_REGION }}\n"
                "      - run: aws eks update-kubeconfig --name ${{ secrets.EKS_CLUSTER_NAME }}\n"
                "      - run: kubectl apply -f k8s/\n"
                "      - run: kubectl rollout status deployment/api-gateway-deployment",
                "downloads": [
                    {
                        "key": "lab3_reusable_deploy",
                        "label": "Download reusable-deploy.yml",
                    }
                ],
            },
            {
                "title": "Concurrency + protection",
                "body": "Prevent deploy stampedes and enforce approvals.",
                "output": "Only one main deploy runs at a time.",
                "details": (
                    "Add concurrency group on main and environment protection for prod. "
                    "Keep fail-fast false for microservice builds."
                ),
                "code": "concurrency:\n"
                "  group: gratitudeapp-${{ github.ref }}\n"
                "  cancel-in-progress: true\n"
                "\n"
                "environment:\n"
                "  name: prod\n"
                "  url: https://your-app.example.com",
            },
            {
                "title": "Validate advanced behaviors",
                "body": "Prove selective builds, security gates, and rollout checks.",
                "output": "CI/CD behavior verified with evidence.",
                "details": (
                    "Modify a single service path to ensure only that service builds. "
                    "Force a Trivy HIGH issue to confirm gating."
                ),
                "code": "strategy:\n"
                "  fail-fast: false\n"
                "  max-parallel: 3\n"
                "\n"
                "uses: aquasecurity/trivy-action@0.24.0\n"
                "with:\n"
                "  exit-code: \"1\"\n"
                "  severity: \"CRITICAL,HIGH\"",
            },
        ],
        "deliverables": [
            {
                "title": "Workflow files",
                "body": (
                    ".github/workflows/orchestrator.yml, reusable-build.yml, "
                    "reusable-deploy.yml"
                ),
            },
            {
                "title": "OIDC IAM role",
                "body": "Role for GitHub Actions with least-privilege ECR/EKS access.",
            },
            {
                "title": "Runner evidence",
                "body": "Self-hosted runner registered with required labels.",
            },
            {
                "title": "Deployment proof",
                "body": "Rollout status output or screenshots from EKS.",
            },
        ],
        "validation": [
            "Dynamic matrix builds only changed services unless build_all is true.",
            "SonarQube + Trivy gates block failures before image push.",
            "Deploy runs only after all builds complete (fan-in).",
            "OIDC auth used; no static AWS keys in secrets.",
            "Concurrency + environment approval prevent deploy stampedes.",
        ],
        "resources": [
            {
                "title": "App repo",
                "body": "https://github.com/UnpredictablePrashant/GratitudeApp",
            },
            {
                "title": "Blueprint (download)",
                "body": "Download via the step modal (lab3/blueprint.md).",
            },
            {
                "title": "ECR repos",
                "body": (
                    "gratitudeapp-client, gratitudeapp-api-gateway, gratitudeapp-entries, "
                    "gratitudeapp-moods-api, gratitudeapp-moods-service, gratitudeapp-server, "
                    "gratitudeapp-stats-api, gratitudeapp-stats-service, gratitudeapp-files-service"
                ),
            },
            {
                "title": "Required tools",
                "body": "Docker Buildx, awscli v2, kubectl, helm, trivy (optional), sonar-scanner (optional)",
            },
        ],
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "Register endpoint",
        "form_helper": "No submissions required for Lab 3.",
        "sections": [
            {
                "title": "Pipeline goals",
                "items": [
                    {
                        "title": "CI quality gate",
                        "body": "Run tests, SonarQube analysis, and Trivy FS scans on PRs.",
                    },
                    {
                        "title": "CD automation",
                        "body": "Build/push images and deploy to EKS on main merges.",
                    },
                    {
                        "title": "Security baseline",
                        "body": "Fail builds on critical vulnerabilities or gate failures.",
                    },
                ],
            },
            {
                "title": "Advanced workflows",
                "items": [
                    {
                        "title": "Orchestration + fan-out",
                        "body": "Detect changes and run parallel builds using a dynamic matrix.",
                    },
                    {
                        "title": "Reusable workflows",
                        "body": "Use workflow_call for build and deploy logic reuse.",
                    },
                    {
                        "title": "Concurrency + approvals",
                        "body": "Protect production with environment approvals and concurrency groups.",
                    },
                ],
            },
            {
                "title": "Runner requirements",
                "items": [
                    {
                        "title": "Self-hosted runner",
                        "body": "EC2/VM with Docker, git, AWS CLI, kubectl, and network access.",
                    },
                    {
                        "title": "Access",
                        "body": "Runner can reach SonarQube, ECR, and the EKS cluster.",
                    },
                ],
            },
            {
                "title": "Workflow artifacts",
                "items": [
                    {
                        "title": "Orchestrator",
                        "body": "Use templates in lab3/templates/orchestrator.yml.",
                    },
                    {
                        "title": "Reusable build",
                        "body": "Use templates in lab3/templates/reusable-build.yml.",
                    },
                    {
                        "title": "Reusable deploy",
                        "body": "Use templates in lab3/templates/reusable-deploy.yml.",
                    },
                    {
                        "title": "Runner guide",
                        "body": "Follow lab3/runner-setup.md for provisioning steps.",
                    },
                ],
            },
            {
                "title": "Acceptance criteria",
                "items": [
                    {
                        "title": "PR checks",
                        "body": "CI runs with SonarQube + Trivy results visible in Actions.",
                    },
                    {
                        "title": "Automated deploy",
                        "body": "CD deploys to EKS with rollout status on main merge.",
                    },
                ],
            },
        ],
    },
    "lab4": {
        "id": "lab4",
        "code": "Lab 4",
        "title": "Observability on EKS: Prometheus + Grafana + SLI/SLO for GratitudeApp",
        "status": "Active",
        "summary": (
            "Install kube-prometheus-stack, define SLIs/SLOs, build Grafana dashboards, "
            "and alert on burn rate for GratitudeApp."
        ),
        "tagline": (
            "Stand up Prometheus + Grafana, validate scrape targets, and prove "
            "availability, latency, and saturation SLOs under load."
        ),
        "facts": [
            {"title": "Level", "body": "Intermediate"},
            {"title": "Estimated time", "body": "2-3 hours"},
            {"title": "Primary focus", "body": "Observability + SLI/SLO design"},
            {"title": "Stack", "body": "EKS, Prometheus, Grafana, Helm"},
        ],
        "steps": [
            {
                "title": "Confirm GratitudeApp endpoints",
                "body": "Identify the ingress, service LoadBalancer, or port-forward entrypoint.",
                "output": "Known base URL for load generation and probes.",
                "details": (
                    "Confirm the GratitudeApp namespace, services, and ingress. If you "
                    "have a known entrypoint, record the base URL for later steps."
                ),
                "code": "kubectl get ns\n"
                "kubectl get pods -A | head\n"
                "kubectl get svc -A | grep -i gratitude || true\n"
                "kubectl get ingress -A || true",
            },
            {
                "title": "Install kube-prometheus-stack",
                "body": "Install Prometheus, Alertmanager, Grafana, and exporters via Helm.",
                "output": "Monitoring stack running in the monitoring namespace.",
                "details": (
                    "This chart includes Prometheus, Alertmanager, Grafana, node-exporter, "
                    "kube-state-metrics, and default dashboards."
                ),
                "code": "kubectl create namespace monitoring\n\n"
                "helm repo add prometheus-community https://prometheus-community.github.io/helm-charts\n"
                "helm repo update\n\n"
                "helm install kps prometheus-community/kube-prometheus-stack \\\n"
                "  --namespace monitoring\n\n"
                "kubectl -n monitoring get pods",
            },
            {
                "title": "Access Grafana and Prometheus",
                "body": "Log into Grafana and open Prometheus for debugging queries.",
                "output": "Grafana UI reachable, Prometheus UI reachable.",
                "details": (
                    "Use port-forward for quick access or expose via ingress if required "
                    "by your cluster setup."
                ),
                "code": "kubectl -n monitoring get secret kps-grafana \\\n"
                "  -o jsonpath=\"{.data.admin-password}\" | base64 -d; echo\n\n"
                "kubectl -n monitoring port-forward svc/kps-grafana 3000:80\n\n"
                "kubectl -n monitoring port-forward \\\n"
                "  svc/kps-kube-prometheus-stack-prometheus 9090:9090",
            },
            {
                "title": "Verify scrape targets",
                "body": "Confirm kubelet, node-exporter, and kube-state-metrics are up.",
                "output": "Prometheus targets show healthy and queries return data.",
                "details": (
                    "In Prometheus UI, open Status > Targets. Ensure kubelet/cadvisor, "
                    "kube-state-metrics, and node-exporter are healthy."
                ),
                "code": "sum(rate(container_cpu_usage_seconds_total{namespace!=\"\",container!=\"\"}[5m]))\n\n"
                "sum(container_memory_working_set_bytes{namespace!=\"\",container!=\"\"})",
            },
            {
                "title": "Add GratitudeApp metrics",
                "body": "Scrape /metrics endpoints or add blackbox probes if unavailable.",
                "output": "GratitudeApp targets appear in Prometheus.",
                "details": (
                    "If GratitudeApp exposes /metrics, add a ServiceMonitor with a label "
                    "selector. If not, install the blackbox exporter and probe the "
                    "health endpoint for availability SLIs."
                ),
                "code": "apiVersion: monitoring.coreos.com/v1\n"
                "kind: ServiceMonitor\n"
                "metadata:\n"
                "  name: gratitudeapp-servicemonitor\n"
                "  namespace: monitoring\n"
                "  labels:\n"
                "    release: kps\n"
                "spec:\n"
                "  namespaceSelector:\n"
                "    matchNames:\n"
                "      - default\n"
                "  selector:\n"
                "    matchLabels:\n"
                "      app.kubernetes.io/part-of: gratitudeapp\n"
                "  endpoints:\n"
                "    - port: http\n"
                "      path: /metrics\n"
                "      interval: 15s\n"
                "---\n"
                "apiVersion: monitoring.coreos.com/v1\n"
                "kind: Probe\n"
                "metadata:\n"
                "  name: gratitudeapp-probe\n"
                "  namespace: monitoring\n"
                "  labels:\n"
                "    release: kps\n"
                "spec:\n"
                "  interval: 15s\n"
                "  module: http_2xx\n"
                "  prober:\n"
                "    url: blackbox-prometheus-blackbox-exporter.monitoring.svc:9115\n"
                "  targets:\n"
                "    staticConfig:\n"
                "      static:\n"
                "        - https://<YOUR-GRATITUDEAPP-URL>/health",
            },
            {
                "title": "Generate load",
                "body": "Drive consistent traffic from laptop or a load generator pod.",
                "output": "RPS, latency, and resource metrics move under load.",
                "details": (
                    "Use hey or k6 from your laptop when the app is public. For internal "
                    "apps, use a lightweight pod and curl/wget in a loop."
                ),
                "code": "hey -z 5m -c 50 https://<URL>/api/some-endpoint\n\n"
                "kubectl run -it --rm loadgen --image=busybox --restart=Never -- sh\n"
                "while true; do wget -qO- http://<service>.<ns>.svc.cluster.local:PORT/health >/dev/null; done",
            },
            {
                "title": "Define SLIs and SLOs",
                "body": "Document availability, latency, error rate, and saturation targets.",
                "output": "PromQL queries for SLI/SLO panels.",
                "details": (
                    "Use request metrics if available, or blackbox + k8s resource metrics "
                    "to define SLOs with clear error budgets."
                ),
                "code": "avg_over_time(probe_success{job=\"probe/gratitudeapp-probe\"}[5m])\n\n"
                "sum(rate(http_requests_total{service=\"gratitude\",status=~\"5..\"}[5m]))\n"
                "/\n"
                "sum(rate(http_requests_total{service=\"gratitude\"}[5m]))\n\n"
                "histogram_quantile(0.95,\n"
                "  sum(rate(http_request_duration_seconds_bucket{service=\"gratitude\"}[5m])) by (le)\n"
                ")\n\n"
                "sum(rate(container_cpu_usage_seconds_total{namespace=\"<ns>\",pod=~\"gratitude.*\",container!=\"\"}[5m]))\n"
                "/\n"
                "sum(kube_pod_container_resource_requests{namespace=\"<ns>\",pod=~\"gratitude.*\",resource=\"cpu\"})",
            },
            {
                "title": "Build the SLO dashboard",
                "body": "Create panels for availability, error rate, latency, and saturation.",
                "output": "Grafana dashboard screenshot during load.",
                "details": (
                    "Include availability (last 1h and 24h), error rate, latency p95/p99, "
                    "RPS, restarts, and CPU/memory saturation panels."
                ),
                "code": "sum(increase(kube_pod_container_status_restarts_total{namespace=\"<ns>\",pod=~\"gratitude.*\"}[15m]))",
            },
            {
                "title": "Create alert rules",
                "body": "Add burn-rate, latency, and saturation alerts via PrometheusRule.",
                "output": "Alerts visible in Prometheus UI.",
                "details": (
                    "Use the kube-prometheus-stack PrometheusRule CRD. Keep alerts simple "
                    "for the lab, then route via Alertmanager if desired."
                ),
                "code": "apiVersion: monitoring.coreos.com/v1\n"
                "kind: PrometheusRule\n"
                "metadata:\n"
                "  name: gratitudeapp-slo-alerts\n"
                "  namespace: monitoring\n"
                "  labels:\n"
                "    release: kps\n"
                "spec:\n"
                "  groups:\n"
                "  - name: gratitudeapp.slo.rules\n"
                "    rules:\n"
                "    - alert: GratitudeAppHighErrorRate\n"
                "      expr: (sum(rate(http_requests_total{service=\"gratitude\",status=~\"5..\"}[5m])) / sum(rate(http_requests_total{service=\"gratitude\"}[5m]))) > 0.01\n"
                "      for: 2m\n"
                "      labels:\n"
                "        severity: critical\n"
                "      annotations:\n"
                "        summary: \"High error rate detected on GratitudeApp\"",
            },
        ],
        "deliverables": [
            {
                "title": "Running monitoring stack",
                "body": "Prometheus + Grafana pods healthy in the monitoring namespace.",
            },
            {
                "title": "SLO dashboard evidence",
                "body": "Screenshot of Grafana dashboard during load.",
            },
            {
                "title": "Alert rules",
                "body": "At least one SLO burn-rate or saturation alert in Prometheus.",
            },
        ],
        "validation": [
            "Prometheus and Grafana pods are running in the monitoring namespace.",
            "Grafana login works and shows Kubernetes metrics.",
            "Load test increases RPS, CPU usage, or latency panels.",
            "At least one SLO panel is present and explained.",
            "At least one alert rule is visible in Prometheus.",
        ],
        "resources": [
            {
                "title": "kube-prometheus-stack chart",
                "body": "https://prometheus-community.github.io/helm-charts",
            },
            {
                "title": "PromQL basics",
                "body": "https://prometheus.io/docs/prometheus/latest/querying/basics/",
            },
            {
                "title": "Grafana dashboards",
                "body": "https://grafana.com/grafana/dashboards/",
            },
            {
                "title": "Blackbox exporter",
                "body": "https://github.com/prometheus/blackbox_exporter",
            },
        ],
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "Register endpoint",
        "form_helper": "No submissions required for Lab 4.",
        "sections": [
            {
                "title": "Audience and assumptions",
                "items": [
                    {
                        "title": "Prerequisites",
                        "body": "Learners know Kubernetes fundamentals and basic monitoring.",
                    },
                    {
                        "title": "GratitudeApp",
                        "body": "Already deployed in the cluster with ingress or LB.",
                    },
                    {
                        "title": "Tools",
                        "body": "kubectl, helm, and EKS kubeconfig access.",
                    },
                ],
            },
            {
                "title": "Learning outcomes",
                "items": [
                    {
                        "title": "Install monitoring stack",
                        "body": "Deploy Prometheus, Alertmanager, and Grafana via Helm.",
                    },
                    {
                        "title": "Discover targets",
                        "body": "Scrape nodes, pods, and application metrics if exposed.",
                    },
                    {
                        "title": "Define SLIs/SLOs",
                        "body": "Latency, error rate, availability, and saturation targets.",
                    },
                    {
                        "title": "Build dashboards",
                        "body": "Create Grafana panels aligned to the defined SLIs/SLOs.",
                    },
                    {
                        "title": "Alert on burn rate",
                        "body": "Add PrometheusRule alerts for SLOs and saturation.",
                    },
                    {
                        "title": "Validate telemetry",
                        "body": "Generate load and verify metrics end-to-end.",
                    },
                ],
            },
            {
                "title": "Instructor notes",
                "items": [
                    {
                        "title": "Pre-lab prep",
                        "body": "Ensure /metrics or ingress metrics exist; keep a known good endpoint.",
                    },
                    {
                        "title": "Common failure points",
                        "body": "ServiceMonitor label mismatch, missing release label, or ingress metrics off.",
                    },
                    {
                        "title": "Fallback plan",
                        "body": "Use blackbox probes plus k8s resource metrics when app metrics are absent.",
                    },
                ],
            },
        ],
    },
}


def list_labs():
    return [LABS[key] for key in sorted(LABS.keys())]


def get_lab(lab_id):
    return LABS.get(lab_id)


DEFAULT_LAB_ID = "lab1"
AUTOMATION_LAB_ID = "lab1"
COMPARE_LAB_ID = "lab1"


def parse_endpoints(raw_value):
    if not raw_value:
        return list(DEFAULT_COMPARE_ENDPOINTS)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def is_valid_url(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "lab1-default-secret")
sock = Sock(app)
clients = set()
active_fill_lock = threading.Lock()
fill_active = False
db_lock = threading.Lock()
automation_enabled = False
automation_paused_at = None
automation_total_paused_seconds = 0
next_auto_fill_at = None
next_auto_fill_entry_text = None
next_auto_fill_seed = None
last_auto_fill_wait_seconds = None

FILL_INTERVAL_SECONDS = int(os.environ.get("FILL_INTERVAL_SECONDS", "120"))
AUTO_INTERVAL_MIN_SECONDS = int(os.environ.get("AUTO_INTERVAL_MIN_SECONDS", "10"))
AUTO_INTERVAL_MAX_SECONDS = int(os.environ.get("AUTO_INTERVAL_MAX_SECONDS", "75"))
COMPARE_INTERVAL_SECONDS = int(os.environ.get("COMPARE_INTERVAL_SECONDS", "150"))
FILL_ITERATIONS = int(os.environ.get("FILL_ITERATIONS", "1"))
FILL_MODE = os.environ.get("FILL_MODE", "all")
DB_PATH = os.environ.get("DB_PATH", "app.db")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "lab1admin")


@app.get("/")
def index():
    return render_template("index.html", labs=list_labs())


@app.get("/lab1")
def lab1():
    return redirect(url_for("lab_detail", lab_id="lab1"))


@app.get("/lab2")
def lab2():
    return redirect(url_for("lab_detail", lab_id="lab2"))


@app.get("/lab3")
def lab3():
    return redirect(url_for("lab_detail", lab_id="lab3"))


@app.get("/lab4")
def lab4():
    return redirect(url_for("lab_detail", lab_id="lab4"))


@app.get("/downloads/<file_key>")
def download_file(file_key):
    relative_path = DOWNLOADS.get(file_key)
    if not relative_path:
        return "File not found.", 404
    full_path = os.path.join(BASE_DIR, relative_path)
    if not os.path.isfile(full_path):
        return "File not found.", 404
    return send_file(full_path, as_attachment=True)


@app.get("/labs/<lab_id>")
def lab_detail(lab_id):
    lab = get_lab(lab_id)
    if not lab:
        return "Lab not found.", 404
    return render_template(
        "lab_detail.html",
        lab=lab,
        labs=list_labs(),
        teams=list_teams(lab_id),
        compare_interval_seconds=COMPARE_INTERVAL_SECONDS,
    )


@app.get("/leaderboard")
def leaderboard_page():
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        return "Lab not found.", 404
    return render_template(
        "leaderboard.html",
        lab=lab,
        labs=list_labs(),
        compare_interval_seconds=COMPARE_INTERVAL_SECONDS,
    )


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        return render_template("admin.html", error="Invalid credentials.")
    return render_template("admin.html")


@app.get("/admin/panel")
def admin_panel():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        lab = get_lab(DEFAULT_LAB_ID)
        lab_id = lab["id"]
    paused_seconds = automation_total_paused_seconds
    if automation_paused_at is not None:
        paused_seconds += int(time.time() - automation_paused_at)
    next_fill_in = None
    if next_auto_fill_at is not None:
        next_fill_in = max(0, int(next_auto_fill_at - time.time()))
    return render_template(
        "admin_panel.html",
        lab=lab,
        labs=list_labs(),
        automation_enabled=automation_enabled,
        auto_interval_min=AUTO_INTERVAL_MIN_SECONDS,
        auto_interval_max=AUTO_INTERVAL_MAX_SECONDS,
        teams=list_teams(lab_id),
        submissions=list_students(lab_id),
        automation_paused_seconds=paused_seconds,
        next_fill_in_seconds=next_fill_in,
        next_fill_entry_text=next_auto_fill_entry_text,
        baseline_url=get_setting("baseline_url", DEFAULT_BASELINE_URL),
    )


@app.post("/admin/toggle")
def admin_toggle():
    global automation_enabled, automation_paused_at, automation_total_paused_seconds
    global next_auto_fill_at, next_auto_fill_entry_text, next_auto_fill_seed
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    automation_enabled = not automation_enabled
    now = int(time.time())
    if not automation_enabled:
        automation_paused_at = now
        next_auto_fill_at = None
        next_auto_fill_entry_text = None
        next_auto_fill_seed = None
        broadcast_fill_meta()
        broadcast("fill_log", {"message": f"Automation paused at {time.ctime(now)}."})
    else:
        if automation_paused_at is not None:
            paused_for = now - automation_paused_at
            automation_total_paused_seconds += paused_for
            broadcast(
                "fill_log",
                {
                    "message": (
                        f"Automation resumed after {paused_for}s paused "
                        f"(total paused {automation_total_paused_seconds}s)."
                    )
                },
            )
        automation_paused_at = None
        broadcast_fill_meta()
    return redirect(url_for("admin_panel", lab=lab_id))


def broadcast_fill_meta():
    if not automation_enabled:
        broadcast(
            "fill_meta",
            {"next_in_seconds": None, "entry_text": None, "status": "paused"},
        )
        return
    if next_auto_fill_at is None:
        broadcast(
            "fill_meta",
            {"next_in_seconds": None, "entry_text": None, "status": "pending"},
        )
        return
    next_in = max(0, int(next_auto_fill_at - time.time()))
    broadcast(
        "fill_meta",
        {
            "next_in_seconds": next_in,
            "entry_text": next_auto_fill_entry_text,
            "status": "scheduled",
        },
    )


@app.post("/admin/interval")
def admin_interval_update():
    global AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    min_value = (request.form.get("auto_interval_min") or "").strip()
    max_value = (request.form.get("auto_interval_max") or "").strip()
    try:
        min_seconds = int(min_value)
        max_seconds = int(max_value)
    except ValueError:
        return redirect(url_for("admin_panel", lab=lab_id))
    if min_seconds < 1 or max_seconds < 1 or min_seconds > max_seconds:
        return redirect(url_for("admin_panel", lab=lab_id))
    AUTO_INTERVAL_MIN_SECONDS = min_seconds
    AUTO_INTERVAL_MAX_SECONDS = max_seconds
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/teams")
def admin_team_create():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab = (request.form.get("lab") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    members = (request.form.get("members") or "").strip()
    if not get_lab(lab):
        lab = DEFAULT_LAB_ID
    if not lab or not name or not members:
        return redirect(url_for("admin_panel", lab=lab or DEFAULT_LAB_ID))
    create_team(lab, name, members)
    return redirect(url_for("admin_panel", lab=lab))


@app.post("/admin/teams/<int:team_id>/update")
def admin_team_update(team_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab = (request.form.get("lab") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    members = (request.form.get("members") or "").strip()
    if not get_lab(lab):
        lab = DEFAULT_LAB_ID
    if not lab or not name or not members:
        return redirect(url_for("admin_panel", lab=lab or DEFAULT_LAB_ID))
    update_team(team_id, lab, name, members)
    return redirect(url_for("admin_panel", lab=lab))


@app.post("/admin/teams/<int:team_id>/delete")
def admin_team_delete(team_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    delete_team(team_id)
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/baseline")
def admin_baseline_update():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    baseline_url = (request.form.get("baseline_url") or "").strip()
    if not is_valid_url(baseline_url):
        return redirect(url_for("admin_panel", lab=lab_id))
    set_setting("baseline_url", baseline_url)
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/submissions/delete")
def admin_submission_delete():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    target_url = (request.form.get("url") or "").strip()
    if not target_url:
        return redirect(url_for("admin_panel", lab=lab_id))
    delete_submission(lab_id, target_url)
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting(key, fallback=None):
    with db_lock:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()
    return row["value"] if row else fallback


def set_setting(key, value):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
            conn.commit()
        finally:
            conn.close()


def init_db():
    run_migrations()
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    lab TEXT NOT NULL,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    added_at INTEGER NOT NULL,
                    PRIMARY KEY (lab, url)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leaderboard (
                    lab TEXT NOT NULL,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    last_checked INTEGER,
                    sync INTEGER,
                    PRIMARY KEY (lab, url)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def list_teams(lab=None):
    with db_lock:
        conn = get_db()
        try:
            if lab:
                rows = conn.execute(
                    """
                    SELECT id, lab, name, members, updated_at
                    FROM teams
                    WHERE lab = ?
                    ORDER BY name ASC
                    """,
                    (lab,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, lab, name, members, updated_at
                    FROM teams
                    ORDER BY lab ASC, name ASC
                    """
                ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in rows]


def create_team(lab, name, members):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO teams (lab, name, members, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lab, name, members, now, now),
            )
            conn.commit()
        finally:
            conn.close()


def update_team(team_id, lab, name, members):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                UPDATE teams
                SET lab = ?, name = ?, members = ?, updated_at = ?
                WHERE id = ?
                """,
                (lab, name, members, now, team_id),
            )
            conn.commit()
        finally:
            conn.close()


def delete_team(team_id):
    with db_lock:
        conn = get_db()
        try:
            conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
            conn.commit()
        finally:
            conn.close()


def upsert_student(lab_id, name, url):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO students (lab, url, name, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lab, url) DO UPDATE SET
                    name=excluded.name,
                    added_at=excluded.added_at
                """,
                (lab_id, url, name, now),
            )
            conn.commit()
        finally:
            conn.close()


def list_students(lab_id=None):
    with db_lock:
        conn = get_db()
        try:
            if lab_id:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, added_at
                    FROM students
                    WHERE lab = ?
                    ORDER BY added_at DESC
                    """,
                    (lab_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, added_at
                    FROM students
                    ORDER BY added_at DESC
                    """
                ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in rows]


def ensure_leaderboard_entry(lab_id, target_url, name):
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO leaderboard (lab, url, name, last_checked, sync)
                VALUES (?, ?, ?, NULL, NULL)
                ON CONFLICT(lab, url) DO UPDATE SET
                    name=excluded.name
                """,
                (lab_id, target_url, name),
            )
            conn.commit()
        finally:
            conn.close()


def delete_submission(lab_id, target_url):
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                "DELETE FROM students WHERE lab = ? AND url = ?",
                (lab_id, target_url),
            )
            conn.execute(
                "DELETE FROM leaderboard WHERE lab = ? AND url = ?",
                (lab_id, target_url),
            )
            conn.commit()
        finally:
            conn.close()


def update_leaderboard(lab_id, target_url, name, sync_status):
    now = int(time.time())
    sync_value = 1 if sync_status is True else 0 if sync_status is False else None
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO leaderboard (lab, url, name, last_checked, sync)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(lab, url) DO UPDATE SET
                    name=excluded.name,
                    last_checked=excluded.last_checked,
                    sync=excluded.sync
                """,
                (lab_id, target_url, name, now, sync_value),
            )
            conn.commit()
        finally:
            conn.close()


def list_leaderboard(lab_id=None):
    with db_lock:
        conn = get_db()
        try:
            if lab_id:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, last_checked, sync
                    FROM leaderboard
                    WHERE lab = ?
                    ORDER BY COALESCE(last_checked, 0) DESC
                    """,
                    (lab_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, last_checked, sync
                    FROM leaderboard
                    ORDER BY COALESCE(last_checked, 0) DESC
                    """
                ).fetchall()
        finally:
            conn.close()
    items = []
    for row in rows:
        sync_value = None
        if row["sync"] is not None:
            sync_value = bool(row["sync"])
        items.append(
            {
                "lab": row["lab"],
                "name": row["name"],
                "url": row["url"],
                "last_checked": row["last_checked"],
                "sync": sync_value,
            }
        )
    return items


@app.post("/api/compare")
def compare():
    global fill_active
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    target_url = (payload.get("url") or "").strip()
    lab_id = (payload.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    baseline_url = (payload.get("baseline_url") or "").strip() or os.environ.get(
        "BASELINE_URL", get_setting("baseline_url", DEFAULT_BASELINE_URL)
    )

    if not lab:
        return jsonify({"error": "Unknown lab."}), 400
    if not name:
        return jsonify({"error": "Name is required."}), 400
    if not target_url:
        return jsonify({"error": "App URL is required."}), 400
    if not is_valid_url(target_url):
        return jsonify({"error": "App URL must include http or https."}), 400
    if lab["compare_enabled"] and not is_valid_url(baseline_url):
        return jsonify({"error": "Baseline URL is invalid."}), 500

    upsert_student(lab_id, name, target_url)
    ensure_leaderboard_entry(lab_id, target_url, name)

    if not lab["compare_enabled"]:
        return jsonify(
            {
                "name": name,
                "target_url": target_url,
                "status": "registered",
                "compare_enabled": False,
            }
        )

    endpoints = parse_endpoints(os.environ.get("COMPARE_ENDPOINTS"))
    started_at = time.time()
    ok, results = compare_endpoints(baseline_url, target_url, endpoints)
    elapsed_ms = int((time.time() - started_at) * 1000)
    update_leaderboard(lab_id, target_url, name, ok)

    with active_fill_lock:
        if not fill_active:
            fill_active = True
            shared_seed = int(time.time())
            job_payload = {
                "url": target_url,
                "baseline_url": baseline_url,
                "iterations": 1,
                "mode": FILL_MODE,
                "min_wait": 1,
                "max_wait": 2,
                "headless": True,
                "seed": shared_seed,
                "entry_mode": "local",
                "entry_text": generate_entry_text("local", seed=shared_seed),
                "target_name": name,
            }
            broadcast("fill_start", {"message": f"New app detected. Filling {target_url}."})
            thread = threading.Thread(target=run_fill_job, args=(job_payload,), daemon=True)
            thread.start()

    return jsonify(
        {
            "name": name,
            "baseline_url": baseline_url,
            "target_url": target_url,
            "status": "match" if ok else "mismatch",
            "elapsed_ms": elapsed_ms,
            "results": results,
            "compare_enabled": True,
        }
    )


@app.get("/api/students")
def students():
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        return jsonify({"error": "Unknown lab."}), 400
    return jsonify({"students": list_students(lab_id)})


def broadcast(event, payload):
    message = json.dumps({"event": event, "payload": payload})
    stale = []
    for ws in clients:
        try:
            ws.send(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        clients.discard(ws)


@sock.route("/ws")
def ws_handler(ws):
    clients.add(ws)
    try:
        while ws.receive() is not None:
            pass
    finally:
        clients.discard(ws)


def run_fill_job(payload):
    global fill_active
    try:
        baseline_url = payload.get("baseline_url")
        entry_text = payload.get("entry_text")
        if baseline_url:
            if entry_text:
                broadcast(
                    "fill_log",
                    {"message": f"[baseline] entry: {entry_text}"},
                )
            try:
                run_fill_session(
                    url=baseline_url,
                    mode=payload["mode"],
                    iterations=payload["iterations"],
                    min_wait=payload["min_wait"],
                    max_wait=payload["max_wait"],
                    headless=payload["headless"],
                    seed=payload["seed"],
                    entry_mode=payload["entry_mode"],
                    entry_text=entry_text,
                    log_cb=lambda message: broadcast(
                        "fill_log", {"message": f"[baseline] {message}"}
                    ),
                )
            except Exception as exc:
                broadcast(
                    "fill_error",
                    {"message": f"Auto-fill failed for baseline ({baseline_url}): {exc}"},
                )
                return
            broadcast(
                "fill_log",
                {"message": f"[baseline] fill completed for {baseline_url}"},
            )
        try:
            if entry_text:
                broadcast(
                    "fill_log",
                    {
                        "message": (
                            f"[{payload.get('target_name', 'target')}] "
                            f"{payload['url']} entry: {entry_text}"
                        )
                    },
                )
            run_fill_session(
                url=payload["url"],
                mode=payload["mode"],
                iterations=payload["iterations"],
                min_wait=payload["min_wait"],
                max_wait=payload["max_wait"],
                headless=payload["headless"],
                seed=payload["seed"],
                entry_mode=payload["entry_mode"],
                entry_text=entry_text,
                log_cb=lambda message: broadcast(
                    "fill_log", {"message": f"[target] {message}"}
                ),
            )
        except Exception as exc:
            broadcast(
                "fill_error",
                {"message": f"Auto-fill failed for target ({payload['url']}): {exc}"},
            )
            return
        target_label = payload.get("target_name") or "target"
        broadcast(
            "fill_log",
            {"message": f"[{target_label}] fill completed for {payload['url']}"},
        )
        broadcast("fill_done", {"message": "Form filling complete."})
    except Exception as exc:
        broadcast("fill_error", {"message": f"Form filling failed: {exc}"})
    finally:
        with active_fill_lock:
            fill_active = False


@app.get("/api/leaderboard")
def get_leaderboard():
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        return jsonify({"error": "Unknown lab."}), 400
    return jsonify({"leaderboard": list_leaderboard(lab_id)})

def compare_and_update(lab_id, target_url, name, baseline_url):
    endpoints = parse_endpoints(os.environ.get("COMPARE_ENDPOINTS"))
    ok, _results = compare_endpoints(baseline_url, target_url, endpoints)
    update_leaderboard(lab_id, target_url, name, ok)
    return ok


def run_fill_loop():
    global fill_active, next_auto_fill_at, next_auto_fill_entry_text, next_auto_fill_seed
    global last_auto_fill_wait_seconds
    while True:
        if not automation_enabled:
            next_auto_fill_at = None
            next_auto_fill_entry_text = None
            next_auto_fill_seed = None
            broadcast_fill_meta()
            time.sleep(random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS))
            continue
        baseline_url = os.environ.get(
            "BASELINE_URL", get_setting("baseline_url", DEFAULT_BASELINE_URL)
        )
        if not is_valid_url(baseline_url):
            wait_seconds = random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS)
            last_auto_fill_wait_seconds = wait_seconds
            next_auto_fill_at = time.time() + wait_seconds
            next_auto_fill_seed = int(next_auto_fill_at)
            next_auto_fill_entry_text = generate_entry_text("local", seed=next_auto_fill_seed)
            broadcast_fill_meta()
            time.sleep(wait_seconds)
            continue

        with active_fill_lock:
            if fill_active:
                wait_seconds = random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS)
                last_auto_fill_wait_seconds = wait_seconds
                next_auto_fill_at = time.time() + wait_seconds
                next_auto_fill_seed = int(next_auto_fill_at)
                next_auto_fill_entry_text = generate_entry_text("local", seed=next_auto_fill_seed)
                broadcast_fill_meta()
                time.sleep(wait_seconds)
                continue
            fill_active = True

        try:
            broadcast("fill_start", {"message": "Auto-fill: baseline + student apps."})
            if next_auto_fill_entry_text is not None and next_auto_fill_seed is not None:
                shared_seed = next_auto_fill_seed
                entry_text = next_auto_fill_entry_text
            else:
                shared_seed = int(time.time())
                entry_text = generate_entry_text("local", seed=shared_seed)
            next_auto_fill_at = None
            next_auto_fill_entry_text = None
            next_auto_fill_seed = None
            broadcast_fill_meta()
            if entry_text:
                broadcast("fill_log", {"message": f"[baseline] entry: {entry_text}"})
            try:
                run_fill_session(
                    url=baseline_url,
                    mode=FILL_MODE,
                    iterations=FILL_ITERATIONS,
                    min_wait=1,
                    max_wait=2,
                    headless=True,
                    seed=shared_seed,
                    entry_mode="local",
                    entry_text=entry_text,
                    log_cb=lambda message: broadcast(
                        "fill_log", {"message": f"[baseline] {message}"}
                    ),
                )
            except Exception as exc:
                broadcast(
                    "fill_error",
                    {"message": f"Auto-fill failed for baseline ({baseline_url}): {exc}"},
                )
                continue

            students = list_students(AUTOMATION_LAB_ID)

            for student in students:
                url = student["url"]
                name = student["name"]
                if not is_valid_url(url):
                    update_leaderboard(AUTOMATION_LAB_ID, url, name, False)
                    broadcast("fill_log", {"message": f"[{name}] invalid URL; skipped."})
                    continue
                broadcast("fill_log", {"message": f"[{name}] filling {url}"})
                try:
                    if entry_text:
                        broadcast(
                            "fill_log",
                            {"message": f"[{name}] entry: {entry_text}"},
                        )
                    run_fill_session(
                        url=url,
                        mode=FILL_MODE,
                        iterations=FILL_ITERATIONS,
                        min_wait=1,
                        max_wait=2,
                        headless=True,
                        seed=shared_seed,
                        entry_mode="local",
                        entry_text=entry_text,
                        log_cb=lambda message: broadcast(
                            "fill_log", {"message": f"[{name}] {message}"}
                        ),
                    )
                except Exception as exc:
                    broadcast(
                        "fill_error",
                        {"message": f"Auto-fill failed for {name} ({url}): {exc}"},
                    )
                    continue
                broadcast(
                    "fill_log",
                    {"message": f"[{name}] fill completed for {url}"},
                )
                compare_and_update(AUTOMATION_LAB_ID, url, name, baseline_url)
            broadcast("fill_done", {"message": "Auto-fill cycle complete."})
        except Exception as exc:
            broadcast("fill_error", {"message": f"Auto-fill failed: {exc}"})
        finally:
            with active_fill_lock:
                fill_active = False
        wait_seconds = random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS)
        last_auto_fill_wait_seconds = wait_seconds
        next_auto_fill_at = time.time() + wait_seconds
        next_auto_fill_seed = int(next_auto_fill_at)
        next_auto_fill_entry_text = generate_entry_text("local", seed=next_auto_fill_seed)
        broadcast_fill_meta()
        time.sleep(wait_seconds)


def run_compare_loop():
    while True:
        baseline_url = os.environ.get(
            "BASELINE_URL", get_setting("baseline_url", DEFAULT_BASELINE_URL)
        )
        if not is_valid_url(baseline_url):
            time.sleep(COMPARE_INTERVAL_SECONDS)
            continue
        students = list_students(COMPARE_LAB_ID)
        if students:
            broadcast(
                "fill_log",
                {"message": "Periodic check: validating submitted apps."},
            )
        for student in students:
            url = student["url"]
            name = student["name"]
            if not is_valid_url(url):
                update_leaderboard(COMPARE_LAB_ID, url, name, False)
                broadcast("fill_log", {"message": f"[{name}] invalid URL; skipped."})
                continue
            compare_and_update(COMPARE_LAB_ID, url, name, baseline_url)
        time.sleep(COMPARE_INTERVAL_SECONDS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    init_db()
    thread = threading.Thread(target=run_fill_loop, daemon=True)
    thread.start()
    compare_thread = threading.Thread(target=run_compare_loop, daemon=True)
    compare_thread.start()
    app.run(host="0.0.0.0", port=port, debug=False)
