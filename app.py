import json
import os
import random
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from shlex import split as shlex_split
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
                    "to define SLOs with clear error budgets and thresholds."
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
                "title": "SLO/SLI tasks (with thresholds)",
                "body": "Calculate ratios for availability, error rate, latency, and saturation.",
                "output": "SLO targets documented and validated under load.",
                "details": (
                    "Use the formulas below to compute SLIs and compare against targets. "
                    "Keep all ratios within thresholds during a 15-minute load test."
                ),
                "code": "Availability SLI (success ratio):\n"
                "avg_over_time(probe_success{job=\"probe/gratitudeapp-probe\"}[5m])\n"
                "Target: >= 0.999 (99.9%)\n\n"
                "Error rate SLI (5xx ratio):\n"
                "sum(rate(http_requests_total{service=\"gratitude\",status=~\"5..\"}[5m]))\n"
                "/\n"
                "sum(rate(http_requests_total{service=\"gratitude\"}[5m]))\n"
                "Target: <= 0.01 (1%)\n\n"
                "Latency SLI (p95):\n"
                "histogram_quantile(0.95,\n"
                "  sum(rate(http_request_duration_seconds_bucket{service=\"gratitude\"}[5m])) by (le)\n"
                ")\n"
                "Target: <= 0.300 seconds\n\n"
                "CPU saturation SLI:\n"
                "sum(rate(container_cpu_usage_seconds_total{namespace=\"<ns>\",pod=~\"gratitude.*\",container!=\"\"}[5m]))\n"
                "/\n"
                "sum(kube_pod_container_resource_requests{namespace=\"<ns>\",pod=~\"gratitude.*\",resource=\"cpu\"})\n"
                "Target: <= 0.75 (75%)\n\n"
                "Memory saturation SLI:\n"
                "sum(container_memory_working_set_bytes{namespace=\"<ns>\",pod=~\"gratitude.*\",container!=\"\"})\n"
                "/\n"
                "sum(kube_pod_container_resource_limits{namespace=\"<ns>\",pod=~\"gratitude.*\",resource=\"memory\"})\n"
                "Target: <= 0.80 (80%)",
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
            {
                "title": "Submit your endpoint",
                "body": "Register your DNS endpoint for automated load tests.",
                "output": "Submission recorded for the lab.",
                "details": (
                    "Use the submission form on the Lab 4 page to register your name "
                    "and DNS endpoint. The form is located on this page."
                ),
                "code": "Submission link: /labs/lab4",
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
        "submission_enabled": True,
        "form_cta": "Register endpoint",
        "form_helper": "Submit your name and DNS endpoint in the form on this page.",
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
    "lab5": {
        "id": "lab5",
        "code": "Lab 5",
        "title": "RBAC over EKS: IAM User + aws-auth + RoleBinding",
        "status": "Active",
        "summary": (
            "Create an IAM user for CLI-based EKS access, map it through aws-auth, "
            "and enforce namespace-scoped permissions with Kubernetes RBAC."
        ),
        "tagline": (
            "Grant controlled default-namespace access for a developer user while "
            "blocking cluster-admin actions and cross-namespace privilege."
        ),
        "facts": [
            {"title": "Level", "body": "Intermediate"},
            {"title": "Estimated time", "body": "1.5-2 hours"},
            {"title": "Primary focus", "body": "EKS authentication + Kubernetes RBAC"},
            {"title": "Stack", "body": "IAM, EKS, aws-auth ConfigMap, Role, RoleBinding"},
        ],
        "steps": [
            {
                "title": "Create IAM user for programmatic access",
                "body": "Create an IAM user and attach EKS cluster access policy.",
                "output": "User demo-eks-user has CLI credentials and EKS policy attached.",
                "details": (
                    "Create IAM user demo-eks-user with programmatic access. "
                    "Attach AmazonEKSClusterPolicy so the user can talk to EKS APIs."
                ),
                "rationale": (
                    "Real-world problem: teams often over-share admin credentials for kubectl. "
                    "Why this step: create a distinct identity for least-privilege access. "
                    "How it helps: enables traceable, scoped access per user."
                ),
                "code": "aws iam create-user --user-name demo-eks-user\n"
                "aws iam attach-user-policy --user-name demo-eks-user "
                "--policy-arn arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
            },
            {
                "title": "Map IAM user in aws-auth ConfigMap",
                "body": "Add the IAM user mapping to EKS authentication config.",
                "output": "IAM user maps to username dev-user and group dev-group.",
                "details": (
                    "EKS authenticates IAM identities through the aws-auth ConfigMap. "
                    "Add mapUsers entry for your IAM user ARN and place it in dev-group."
                ),
                "rationale": (
                    "Real-world problem: IAM permissions alone do not grant kubectl access. "
                    "Why this step: aws-auth links IAM identity to Kubernetes principals. "
                    "How it helps: enables RBAC-driven authorization inside the cluster."
                ),
                "code": "kubectl edit configmap aws-auth -n kube-system\n"
                "mapUsers: |\n"
                "  - userarn: arn:aws:iam::<account-id>:user/demo-eks-user\n"
                "    username: dev-user\n"
                "    groups:\n"
                "      - dev-group",
            },
            {
                "title": "Create and apply namespace Role",
                "body": "Define permissions for app resources in default namespace.",
                "output": "developer-role allows CRUD for workloads and services in default.",
                "details": (
                    "Create Role developer-role in namespace default for pods, services, "
                    "deployments, and replicasets with get/list/watch/create/update/delete."
                ),
                "rationale": (
                    "Real-world problem: developers need app-level control, not cluster admin. "
                    "Why this step: Role scopes actions to a namespace and resource set. "
                    "How it helps: enforces least privilege while preserving productivity."
                ),
                "code": "apiVersion: rbac.authorization.k8s.io/v1\n"
                "kind: Role\n"
                "metadata:\n"
                "  namespace: default\n"
                "  name: developer-role\n"
                "rules:\n"
                "- apiGroups: [\"\", \"apps\"]\n"
                "  resources:\n"
                "    - pods\n"
                "    - services\n"
                "    - deployments\n"
                "    - replicasets\n"
                "  verbs:\n"
                "    - get\n"
                "    - list\n"
                "    - watch\n"
                "    - create\n"
                "    - update\n"
                "    - delete\n"
                "kubectl apply -f developer-role.yml",
            },
            {
                "title": "Bind Role to dev-group",
                "body": "Create RoleBinding so mapped IAM user inherits developer-role.",
                "output": "dev-group receives permissions in namespace default.",
                "details": (
                    "Create RoleBinding developer-binding in default namespace with "
                    "subject kind Group name dev-group and roleRef developer-role."
                ),
                "rationale": (
                    "Real-world problem: identity mappings exist, but no permissions bind to them. "
                    "Why this step: RoleBinding connects the group to actual allowed actions. "
                    "How it helps: converts authentication into effective authorization."
                ),
                "code": "apiVersion: rbac.authorization.k8s.io/v1\n"
                "kind: RoleBinding\n"
                "metadata:\n"
                "  name: developer-binding\n"
                "  namespace: default\n"
                "subjects:\n"
                "- kind: Group\n"
                "  name: dev-group\n"
                "  apiGroup: rbac.authorization.k8s.io\n"
                "roleRef:\n"
                "  kind: Role\n"
                "  name: developer-role\n"
                "  apiGroup: rbac.authorization.k8s.io\n"
                "kubectl apply -f developer-binding.yaml",
            },
            {
                "title": "Configure IAM user kubeconfig and validate access",
                "body": "Use IAM credentials to access cluster and test allowed/denied actions.",
                "output": "User can manage default namespace workloads but cannot do admin tasks.",
                "details": (
                    "Configure AWS CLI with demo-eks-user credentials, update kubeconfig, and test "
                    "expected access pattern: allowed for pods/deployments/services in default, "
                    "denied for node deletion, RBAC changes, and other namespaces."
                ),
                "rationale": (
                    "Real-world problem: RBAC design is incomplete without negative tests. "
                    "Why this step: confirms enforced boundaries and avoids false assumptions. "
                    "How it helps: proves least-privilege behavior for audit readiness."
                ),
                "code": "aws configure\n"
                "aws eks update-kubeconfig --region ap-south-1 --name <your-cluster-name>\n"
                "kubectl get pods\n"
                "kubectl create deployment demo-nginx --image=nginx\n"
                "kubectl get services\n"
                "# Expected denied examples\n"
                "kubectl delete node <node-name>\n"
                "kubectl create clusterrole test-admin --verb=get --resource=pods\n"
                "kubectl get pods -n kube-system",
            },
        ],
        "deliverables": [
            {
                "title": "IAM user setup evidence",
                "body": "demo-eks-user created with AmazonEKSClusterPolicy attached.",
            },
            {
                "title": "aws-auth mapping proof",
                "body": "ConfigMap includes mapUsers entry with dev-group assignment.",
            },
            {
                "title": "RBAC manifests",
                "body": "developer-role and developer-binding applied in default namespace.",
            },
            {
                "title": "Access validation logs",
                "body": "Screenshots/outputs of allowed and denied kubectl actions.",
            },
        ],
        "validation": [
            "IAM user can authenticate to EKS via aws-auth mapping.",
            "dev-group can create/update/list/delete pods, services, and deployments in default namespace.",
            "User cannot delete nodes or modify cluster-level RBAC objects.",
            "User cannot access workloads in unauthorized namespaces.",
        ],
        "resources": [
            {
                "title": "EKS aws-auth ConfigMap",
                "body": "https://docs.aws.amazon.com/eks/latest/userguide/auth-configmap.html",
            },
            {
                "title": "Kubernetes RBAC",
                "body": "https://kubernetes.io/docs/reference/access-authn-authz/rbac/",
            },
            {
                "title": "EKS IAM basics",
                "body": "https://docs.aws.amazon.com/eks/latest/userguide/security-iam.html",
            },
            {
                "title": "RoleBinding reference",
                "body": "https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.29/#rolebinding-v1-rbac-authorization-k8s-io",
            },
        ],
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "No submission required",
        "form_helper": "Capture command output for allowed vs denied actions.",
        "sections": [
            {
                "title": "Key concepts",
                "items": [
                    {
                        "title": "Authentication bridge",
                        "body": "aws-auth maps IAM identities to Kubernetes users/groups.",
                    },
                    {
                        "title": "Authorization scope",
                        "body": "Role and RoleBinding enforce namespace-scoped least privilege.",
                    },
                    {
                        "title": "Negative testing",
                        "body": "Validate denied cluster-admin and cross-namespace operations.",
                    },
                ],
            },
            {
                "title": "Lab modules",
                "items": [
                    {"title": "Module 1", "body": "Create IAM user and attach EKS policy."},
                    {"title": "Module 2", "body": "Map user in aws-auth ConfigMap."},
                    {"title": "Module 3", "body": "Create namespace Role for developer actions."},
                    {"title": "Module 4", "body": "Bind Role to dev-group with RoleBinding."},
                    {"title": "Module 5", "body": "Configure kubeconfig and validate access controls."},
                ],
            },
            {
                "title": "Assessment prompts",
                "items": [
                    {
                        "title": "Why aws-auth is required",
                        "body": "Explain why IAM policy alone does not grant kubectl authorization.",
                    },
                    {
                        "title": "Role vs ClusterRole",
                        "body": "Describe when namespace role binding is preferred over cluster-wide access.",
                    },
                    {
                        "title": "Security posture check",
                        "body": "List three privileged commands that should fail for dev-group.",
                    },
                ],
            },
        ],
    },
    "lab6": {
        "id": "lab6",
        "code": "Lab 6",
        "title": "GitOps on EKS with Argo CD",
        "status": "Active",
        "summary": (
            "Convert an existing EKS cluster to GitOps using Argo CD "
            "without redeploying the cluster or changing application code."
        ),
        "tagline": (
            "Make Git the single source of truth, automate sync and drift "
            "correction, and prove rollback and promotion via commits."
        ),
        "facts": [
            {"title": "Level", "body": "Intermediate"},
            {"title": "Estimated time", "body": "2.5 hours"},
            {"title": "Primary focus", "body": "GitOps workflows + reconciliation"},
            {"title": "Stack", "body": "EKS, Argo CD, Git"},
        ],
        "steps": [
            {
                "title": "Validate cluster access",
                "body": "Confirm kubectl connectivity and namespaces.",
                "output": "Nodes and namespaces visible.",
                "details": (
                    "The cluster must already exist and be reachable using your "
                    "local kubeconfig."
                ),
                "code": "kubectl get nodes\nkubectl get ns",
            },
            {
                "title": "Validate GratitudeApp",
                "body": "Confirm the application is already running.",
                "output": "Pods and services are present.",
                "details": (
                    "No application code changes are allowed for this lab. "
                    "The GratitudeApp must be live before GitOps onboarding."
                ),
                "code": "kubectl get pods -A | grep gratitude\nkubectl get svc -A | grep gratitude",
            },
            {
                "title": "Install Argo CD",
                "body": "Deploy Argo CD into the cluster.",
                "output": "argocd pods running.",
                "details": (
                    "Install Argo CD in the argocd namespace using the upstream manifest."
                ),
                "code": "kubectl create namespace argocd\n\n"
                "kubectl apply -n argocd \\\n"
                "  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml\n\n"
                "kubectl -n argocd get pods",
            },
            {
                "title": "Access Argo CD UI",
                "body": "Port-forward and log in as admin.",
                "output": "Argo CD UI reachable.",
                "details": (
                    "Retrieve the initial admin password from the secret and use "
                    "port-forwarding to access the UI."
                ),
                "code": "kubectl -n argocd port-forward svc/argocd-server 8080:443\n\n"
                "kubectl -n argocd get secret argocd-initial-admin-secret \\\n"
                "  -o jsonpath=\"{.data.password}\" | base64 -d",
            },
            {
                "title": "Prepare GitOps repository",
                "body": "Create the GitOps repo structure for overlays.",
                "output": "Repo layout matches Kustomize overlay expectations.",
                "details": (
                    "After this step, no application manifests are applied directly "
                    "to the cluster outside GitOps tools."
                ),
                "code": "gitops-gratitudeapp/\n"
                "  apps/\n"
                "    gratitudeapp/\n"
                "      base/\n"
                "      overlays/\n"
                "        dev/\n"
                "        staging/",
            },
            {
                "title": "Create Argo CD Application",
                "body": "Point Argo CD at the dev overlay.",
                "output": "gratitudeapp-dev shows Healthy and Synced.",
                "details": (
                    "Use automated sync with prune and self-heal enabled. "
                    "Use a dedicated namespace for the dev environment."
                ),
                "code": "apiVersion: argoproj.io/v1alpha1\n"
                "kind: Application\n"
                "metadata:\n"
                "  name: gratitudeapp-dev\n"
                "  namespace: argocd\n"
                "spec:\n"
                "  source:\n"
                "    repoURL: https://github.com/<org>/gitops-gratitudeapp.git\n"
                "    targetRevision: main\n"
                "    path: apps/gratitudeapp/overlays/dev\n"
                "  destination:\n"
                "    server: https://kubernetes.default.svc\n"
                "    namespace: gratitude-dev\n"
                "  syncPolicy:\n"
                "    automated:\n"
                "      prune: true\n"
                "      selfHeal: true\n"
                "---\n"
                "kubectl apply -f app.yaml",
            },
            {
                "title": "Git-driven scaling",
                "body": "Change replicas from 2 to 4 via Git.",
                "output": "Argo CD syncs automatically.",
                "details": (
                    "Commit and push the replicas change in Git, then verify the "
                    "deployment size in gratitude-dev."
                ),
                "code": "kubectl -n gratitude-dev get deploy",
            },
            {
                "title": "Drift detection (Argo CD)",
                "body": "Manually scale and watch Argo CD self-heal.",
                "output": "Argo CD reverts drift.",
                "details": (
                    "Use kubectl scale to introduce drift and watch Argo CD "
                    "restore the desired state from Git."
                ),
                "code": "kubectl -n gratitude-dev scale deploy <service> --replicas=1",
            },
            {
                "title": "Rollback via Git",
                "body": "Introduce a broken config and revert using Git.",
                "output": "Rollout recovers on revert commit.",
                "details": (
                    "Change the image tag to a bad value, observe failure, and then "
                    "revert the commit. No kubectl rollback is allowed."
                ),
                "code": "git revert <bad-commit-sha>",
            },
            {
                "title": "Document Argo CD operations",
                "body": "Capture sync model, UI workflow, drift handling, and promotion strategy.",
                "output": "Operational notes completed.",
                "details": (
                    "Document your Argo CD observations based on lab results."
                ),
                "code": "Area | Argo CD notes\n"
                "Sync model | \n"
                "UI workflow | \n"
                "Drift handling | \n"
                "Promotion strategy | ",
            },
        ],
        "deliverables": [
            {
                "title": "Argo CD synced app",
                "body": "Screenshot showing Healthy and Synced state.",
            },
            {
                "title": "Git commit links",
                "body": "Scaling change, broken change, and rollback commit links.",
            },
        ],
        "validation": [
            "Argo CD auto-syncs and self-heals from drift.",
            "Rollbacks happen via Git only; no kubectl apply for workloads.",
            "Operational notes capture Argo CD trade-offs and workflow decisions.",
        ],
        "resources": [
            {
                "title": "Argo CD docs",
                "body": "https://argo-cd.readthedocs.io/en/stable/",
            },
            {
                "title": "GitOps on EKS",
                "body": "https://aws.amazon.com/blogs/containers/tag/gitops/",
            },
        ],
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "No submission required",
        "form_helper": "Capture screenshots and commit links for your report.",
        "sections": [
            {
                "title": "Constraints",
                "items": [
                    {
                        "title": "No cluster recreation",
                        "body": "Use the existing production-grade EKS cluster.",
                    },
                    {
                        "title": "No app code changes",
                        "body": "All changes are infrastructure and manifests only.",
                    },
                    {
                        "title": "Git-only changes",
                        "body": "No kubectl apply for application workloads after onboarding.",
                    },
                ],
            },
            {
                "title": "Expected outcomes",
                "items": [
                    {
                        "title": "Argo CD managed state",
                        "body": "Application resources reconciled from Git.",
                    },
                    {
                        "title": "Automated drift handling",
                        "body": "Argo CD self-heal validated.",
                    },
                    {
                        "title": "Rollback discipline",
                        "body": "Use Git revert to recover bad changes.",
                    },
                ],
            },
            {
                "title": "Timeline",
                "items": [
                    {"title": "0-15 min", "body": "Environment validation."},
                    {"title": "15-70 min", "body": "Argo CD installation and onboarding."},
                    {"title": "70-120 min", "body": "GitOps operations with Argo CD."},
                    {"title": "120-150 min", "body": "Rollback, drift, and validation."},
                ],
            },
        ],
    },
    "lab7": {
        "id": "lab7",
        "code": "Lab 7",
        "title": "EKS Networking Masterclass: AWS VPC CNI + Policies + Debugging",
        "status": "Active",
        "summary": (
            "Deep dive into AWS VPC CNI behavior, IP exhaustion, warm IP tuning, "
            "custom CNI policy enforcement, and production-grade troubleshooting."
        ),
        "tagline": (
            "Understand VPC-routable pod IPs, simulate IP exhaustion, optimize "
            "allocation, enforce NetworkPolicy, and debug CNI issues like an SRE."
        ),
        "facts": [
            {"title": "Level", "body": "Advanced"},
            {"title": "Estimated time", "body": "2.5-3 hours"},
            {"title": "Primary focus", "body": "EKS networking + policy enforcement"},
            {"title": "Stack", "body": "EKS, AWS VPC CNI, Cilium/Calico"},
        ],
        "steps": [
            {
                "title": "Baseline: inspect AWS VPC CNI",
                "body": "Confirm aws-node is running and review recent logs.",
                "output": "CNI daemonset healthy with recent log activity.",
                "details": (
                    "Concept: AWS VPC CNI allocates pod IPs from ENIs on each node. "
                    "Why: if aws-node is unhealthy, pods may not get IPs. "
                    "Approach: verify the daemonset and logs before making changes."
                ),
                "rationale": (
                    "Real-world problem: outages often start with silent CNI failures. "
                    "Why this step: early validation avoids chasing application bugs "
                    "when the network plane is the root cause. "
                    "How it helps: confirms the IPAM engine is healthy before scaling."
                ),
                "code": "kubectl -n kube-system get ds aws-node\n"
                "kubectl -n kube-system logs ds/aws-node -c aws-node --tail=50",
            },
            {
                "title": "Verify pod and node IPs",
                "body": "Confirm pods have VPC CIDR IPs and nodes show multiple ENIs.",
                "output": "Pod IPs match the VPC CIDR and nodes have VPC addresses.",
                "details": (
                    "Concept: pod IPs are first-class VPC addresses. "
                    "Why: VPC-routable IPs enable native routing but introduce IP limits. "
                    "Approach: compare pod IPs to the VPC CIDR and note node IPs."
                ),
                "rationale": (
                    "Real-world problem: mismatched subnets cause routing blackholes. "
                    "Why this step: validating CIDRs prevents misconfiguration later. "
                    "How it helps: ensures pods are reachable via VPC routing."
                ),
                "code": "kubectl get pods -o wide\nkubectl get nodes -o wide",
            },
            {
                "title": "Visualize IP allocation per node",
                "body": "Deploy a small workload and observe placement.",
                "output": "Pods spread across nodes with routable IPs.",
                "details": (
                    "Concept: each node attaches ENIs and allocates secondary IPs to pods. "
                    "Why: IP distribution affects scheduling and density. "
                    "Approach: deploy a small workload and inspect pod-to-node mapping."
                ),
                "rationale": (
                    "Real-world problem: uneven IP distribution creates hot nodes. "
                    "Why this step: placement visibility reveals node-level IP pressure. "
                    "How it helps: informs scaling and instance type decisions."
                ),
                "code": "kubectl apply -f https://k8s.io/examples/application/guestbook/redis-leader-deployment.yaml\n"
                "kubectl get pods -o wide",
            },
            {
                "title": "Simulate IP exhaustion",
                "body": "Over-schedule small pods to trigger IP shortage.",
                "output": "Pods stuck Pending and events show IP assignment issues.",
                "details": (
                    "Concept: instance types have ENI/IP limits that cap pod density. "
                    "Why: pods can remain Pending even with free CPU/RAM. "
                    "Approach: over-schedule to trigger IP allocation failure."
                ),
                "rationale": (
                    "Real-world problem: production outages from IP exhaustion are common. "
                    "Why this step: controlled failure makes the limits visible. "
                    "How it helps: teaches recognition of IPAM symptoms in events."
                ),
                "code": "kubectl create deploy ip-stress --image=busybox --replicas=300 -- sleep 3600\n"
                "kubectl get pods\n"
                "kubectl get events --sort-by=.lastTimestamp | tail -40",
            },
            {
                "title": "Inspect aws-node errors",
                "body": "Review CNI logs for IP allocation failures.",
                "output": "Log entries show IP exhaustion or ENI limits.",
                "details": (
                    "Concept: aws-node logs reflect IPAM behavior and failures. "
                    "Why: events alone do not show the precise IPAM error. "
                    "Approach: read CNI logs for ENI/IP exhaustion messages."
                ),
                "rationale": (
                    "Real-world problem: pending pods often lack clear root cause. "
                    "Why this step: logs provide exact failure reasons. "
                    "How it helps: speeds incident resolution with concrete evidence."
                ),
                "code": "kubectl -n kube-system logs ds/aws-node -c aws-node --tail=80",
            },
            {
                "title": "Tune warm IP targets",
                "body": "Increase warm IP pool to reduce allocation latency.",
                "output": "aws-node restarts and pre-allocates more IPs.",
                "details": (
                    "Concept: warm IPs are pre-allocated to reduce pod startup time. "
                    "Why: on-demand IP allocation can delay scheduling. "
                    "Approach: increase warm targets and restart aws-node."
                ),
                "rationale": (
                    "Real-world problem: burst traffic causes slow pod scaling. "
                    "Why this step: pre-allocating IPs removes a bottleneck. "
                    "How it helps: improves responsiveness during spikes."
                ),
                "code": "kubectl -n kube-system set env ds/aws-node WARM_IP_TARGET=15\n"
                "kubectl -n kube-system set env ds/aws-node MINIMUM_IP_TARGET=10\n"
                "kubectl -n kube-system rollout restart ds/aws-node",
            },
            {
                "title": "Validate post-tuning behavior",
                "body": "Check CNI logs and verify scheduling improves.",
                "output": "Logs show warm pool behavior and fewer Pending pods.",
                "details": (
                    "Concept: warm IP pool status is visible in CNI logs. "
                    "Why: tuning is ineffective if env vars are not applied. "
                    "Approach: verify logs and re-check pod scheduling."
                ),
                "rationale": (
                    "Real-world problem: config changes can be ignored silently. "
                    "Why this step: validates that tuning is active in the CNI. "
                    "How it helps: prevents false confidence in optimization."
                ),
                "code": "kubectl -n kube-system logs ds/aws-node -c aws-node --tail=50\n"
                "kubectl get pods | tail -n 20",
            },
            {
                "title": "Optional: enable prefix delegation",
                "body": "Increase pod density per node using prefix delegation.",
                "output": "Nodes support more pod IPs per ENI.",
                "details": (
                    "Concept: prefix delegation assigns IP prefixes instead of singles. "
                    "Why: higher pod density per ENI reduces IP exhaustion risk. "
                    "Approach: enable prefix delegation on supported EKS/CNI versions."
                ),
                "rationale": (
                    "Real-world problem: large clusters hit IP limits quickly. "
                    "Why this step: prefix delegation raises pod ceilings per node. "
                    "How it helps: reduces the need for rapid node scale-out."
                ),
                "code": "kubectl -n kube-system set env ds/aws-node ENABLE_PREFIX_DELEGATION=true\n"
                "kubectl -n kube-system rollout restart ds/aws-node",
            },
            {
                "title": "Install policy engine (Cilium or Calico)",
                "body": "Add NetworkPolicy support in chaining or policy-only mode.",
                "output": "Policy engine running alongside AWS VPC CNI.",
                "details": (
                    "Concept: AWS VPC CNI provides IPs but not policy enforcement. "
                    "Why: NetworkPolicy objects are ignored without a policy engine. "
                    "Approach: install Cilium (chaining) or Calico (policy-only)."
                ),
                "rationale": (
                    "Real-world problem: teams assume policies are enforced but they are not. "
                    "Why this step: adds the missing enforcement plane. "
                    "How it helps: enables least-privilege network segmentation."
                ),
                "code": "cilium status\nkubectl get pods -n kube-system | grep -E \"cilium|calico\"",
            },
            {
                "title": "Apply deny-all NetworkPolicy",
                "body": "Block all ingress and egress in the default namespace.",
                "output": "Traffic stops between pods unless explicitly allowed.",
                "details": (
                    "Concept: default deny establishes a zero-trust baseline. "
                    "Why: without it, implicit allow makes policy gaps invisible. "
                    "Approach: apply deny-all and then layer allow rules."
                ),
                "rationale": (
                    "Real-world problem: lateral movement after compromise. "
                    "Why this step: forces explicit connectivity decisions. "
                    "How it helps: reduces blast radius for breaches."
                ),
                "code": "apiVersion: networking.k8s.io/v1\n"
                "kind: NetworkPolicy\n"
                "metadata:\n"
                "  name: deny-all\n"
                "  namespace: default\n"
                "spec:\n"
                "  podSelector: {}\n"
                "  policyTypes:\n"
                "  - Ingress\n"
                "  - Egress",
            },
            {
                "title": "Allow frontend to backend only",
                "body": "Create a targeted allow policy for app traffic.",
                "output": "Frontend can reach backend; other traffic is blocked.",
                "details": (
                    "Concept: allow lists restrict traffic to explicit sources. "
                    "Why: least-privilege reduces lateral movement risk. "
                    "Approach: match labels for frontend and backend and test access."
                ),
                "rationale": (
                    "Real-world problem: unrestricted service access increases attack surface. "
                    "Why this step: documents the exact allowed paths. "
                    "How it helps: encodes service contracts into policy."
                ),
                "code": "apiVersion: networking.k8s.io/v1\n"
                "kind: NetworkPolicy\n"
                "metadata:\n"
                "  name: allow-frontend-to-backend\n"
                "  namespace: default\n"
                "spec:\n"
                "  podSelector:\n"
                "    matchLabels:\n"
                "      app: backend\n"
                "  ingress:\n"
                "  - from:\n"
                "    - podSelector:\n"
                "        matchLabels:\n"
                "          app: frontend\n"
                "  policyTypes:\n"
                "  - Ingress",
            },
            {
                "title": "Observe drops (Cilium)",
                "body": "Monitor denied traffic for evidence of enforcement.",
                "output": "Drop events visible in the Cilium monitor.",
                "details": (
                    "Concept: flow visibility confirms policy enforcement. "
                    "Why: logs prove drops when connectivity tests fail. "
                    "Approach: use Cilium monitor to view dropped traffic."
                ),
                "rationale": (
                    "Real-world problem: teams lack proof when debugging policies. "
                    "Why this step: provides verifiable evidence of blocked flows. "
                    "How it helps: speeds policy debugging and audit trails."
                ),
                "code": "cilium monitor --type drop",
            },
            {
                "title": "Troubleshooting checklist",
                "body": "Debug DNS, service routing, and IP allocation failures.",
                "output": "Root cause identified for common networking failures.",
                "details": (
                    "Concept: networking issues often span DNS, services, and IPAM. "
                    "Why: symptoms can look similar without structured checks. "
                    "Approach: inspect CNI logs, node details, and endpoints."
                ),
                "rationale": (
                    "Real-world problem: high-severity outages require fast triage. "
                    "Why this step: a consistent checklist reduces mean time to recovery. "
                    "How it helps: isolates DNS vs service vs IPAM issues quickly."
                ),
                "code": "kubectl -n kube-system logs ds/aws-node -c aws-node\n"
                "kubectl -n kube-system logs ds/aws-node -c aws-vpc-cni-init\n"
                "kubectl describe node <node>\n"
                "kubectl get endpoints -A",
            },
        ],
        "deliverables": [
            {
                "title": "IP exhaustion evidence",
                "body": "Events or logs showing pod scheduling blocked by IP limits.",
            },
            {
                "title": "Warm IP tuning proof",
                "body": "aws-node rollout and logs showing warm pool settings.",
            },
            {
                "title": "NetworkPolicy enforcement",
                "body": "Proof of deny-all and allow-only rules working.",
            },
            {
                "title": "Troubleshooting notes",
                "body": "Short write-up on root cause and fix for one failure.",
            },
        ],
        "validation": [
            "Pods show VPC-routable IPs and aws-node is healthy.",
            "IP exhaustion reproduces Pending pods with relevant events/logs.",
            "Warm IP tuning or prefix delegation improves scheduling behavior.",
            "NetworkPolicy enforcement verified with a policy engine.",
            "Troubleshooting commands identify DNS/service/IP issues.",
        ],
        "resources": [
            {
                "title": "AWS VPC CNI",
                "body": "https://docs.aws.amazon.com/eks/latest/userguide/managing-vpc-cni.html",
            },
            {
                "title": "CNI troubleshooting",
                "body": "https://docs.aws.amazon.com/eks/latest/userguide/troubleshooting.html",
            },
            {
                "title": "Cilium docs",
                "body": "https://docs.cilium.io/en/stable/",
            },
            {
                "title": "Calico policy-only",
                "body": "https://docs.tigera.io/calico/latest/network-policy",
            },
        ],
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "No submission required",
        "form_helper": "Capture logs and screenshots for your report.",
        "sections": [
            {
                "title": "Key concepts",
                "items": [
                    {
                        "title": "ENIs and IP limits",
                        "body": "Pod IPs are assigned from ENIs and constrained per instance type.",
                    },
                    {
                        "title": "Warm IP pool",
                        "body": "Warm IPs reduce pod startup latency during bursts.",
                    },
                    {
                        "title": "Policy enforcement",
                        "body": "AWS VPC CNI needs a policy engine for NetworkPolicies.",
                    },
                ],
            },
            {
                "title": "Lab modules",
                "items": [
                    {"title": "Module 1", "body": "Inspect AWS VPC CNI and pod IPs."},
                    {"title": "Module 2", "body": "Visualize IP allocation per node."},
                    {"title": "Module 3", "body": "Simulate IP exhaustion and events."},
                    {"title": "Module 4", "body": "Tune warm IP targets and restart CNI."},
                    {"title": "Module 5", "body": "Install Cilium or Calico for policy."},
                    {"title": "Module 6", "body": "Apply deny-all and allow rules."},
                    {"title": "Module 7", "body": "Observe drops with Cilium."},
                    {"title": "Module 8", "body": "Troubleshooting checklist round."},
                ],
            },
            {
                "title": "Assessment prompts",
                "items": [
                    {
                        "title": "Why pods pending?",
                        "body": "Explain ENI/IP exhaustion and instance type limits.",
                    },
                    {
                        "title": "SG for pods vs NetworkPolicy",
                        "body": "Compare AWS VPC security groups and K8s policies.",
                    },
                    {
                        "title": "Design for banking",
                        "body": "Separate pod subnets, SG for pods, and policy engine.",
                    },
                ],
            },
        ],
    },
    "lab8": {
        "id": "lab8",
        "code": "Lab 8",
        "title": "Prometheus & Grafana Advanced Dashboards: SLO, Capacity, and Incident Views",
        "status": "Active",
        "summary": (
            "Build production-grade Grafana dashboards from Prometheus metrics with "
            "recording rules, SLO burn-rate visualizations, and actionable alert panels."
        ),
        "tagline": (
            "Move beyond basic graphs: design opinionated dashboards for latency, "
            "errors, saturation, and capacity planning with strong query discipline."
        ),
        "facts": [
            {"title": "Level", "body": "Advanced"},
            {"title": "Estimated time", "body": "3.5-4.5 hours"},
            {"title": "Primary focus", "body": "PromQL + dashboard architecture"},
            {"title": "Stack", "body": "Prometheus, Grafana, kube-prometheus-stack"},
        ],
        "prerequisites": [
            "Working EKS cluster with kube-prometheus-stack installed in namespace monitoring.",
            "Access to Grafana editor role and Prometheus UI.",
            "A load tool available (hey or k6) and a reachable GratitudeApp endpoint.",
            "Basic knowledge of histogram metrics, rate/increase, and label filtering.",
        ],
        "learning_outcomes": [
            "Design audience-specific dashboards instead of one overloaded dashboard.",
            "Use recording rules to reduce expensive repeated PromQL in Grafana panels.",
            "Implement SLO burn-rate visualizations and map them to alert severity.",
            "Version-control dashboards as code with reviewable and reproducible changes.",
        ],
        "scoring_rubric": [
            {"title": "Observability contract quality", "body": "SLIs/SLOs are measurable and tied to user journeys.", "points": "15 pts"},
            {"title": "PromQL and recording rules", "body": "Queries are efficient, readable, and reusable.", "points": "20 pts"},
            {"title": "Dashboard architecture", "body": "Exec/Service/Capacity/Incident views are clear and actionable.", "points": "25 pts"},
            {"title": "SLO burn-rate and alert integration", "body": "Burn windows and runbook wiring are implemented correctly.", "points": "20 pts"},
            {"title": "Validation and dashboard-as-code", "body": "Load tests, screenshots, JSON exports, and Git history are complete.", "points": "20 pts"},
        ],
        "phases": [
            {
                "title": "Phase 1: Instrumentation and query foundation (45-60 min)",
                "body": "Lock down labels, metric quality, and recording rules before designing panels.",
                "checkpoint": "Prometheus rules are loaded and query latency is acceptable.",
            },
            {
                "title": "Phase 2: Dashboard architecture and implementation (90-120 min)",
                "body": "Build four dashboards with reusable variables, thresholds, and panel narratives.",
                "checkpoint": "All core panels render in <2 seconds for a 6h range.",
            },
            {
                "title": "Phase 3: Incident and load validation (45-60 min)",
                "body": "Run traffic scenarios and confirm dashboards reflect system behavior accurately.",
                "checkpoint": "Trend changes and alert states are visible across views.",
            },
            {
                "title": "Phase 4: Operationalization (30-40 min)",
                "body": "Export dashboards, store in Git, and document tradeoffs and known limits.",
                "checkpoint": "Dashboards can be reprovisioned from code.",
            },
        ],
        "steps": [
            {
                "title": "Define observability contract",
                "body": "Document service SLIs, SLO targets, and user journeys.",
                "output": "A written contract for availability, latency, traffic, and errors.",
                "duration": "20 min",
                "priority": "High",
                "points": "8",
                "checkpoints": [
                    "At least one business journey is mapped to each SLI.",
                    "Every SLI has a numeric target and measurement window.",
                ],
                "acceptance": [
                    "Contract includes owner, target, and reporting interval.",
                ],
                "pitfalls": [
                    "Using infrastructure metrics only without user-facing SLIs.",
                    "Defining SLOs without error budget interpretation.",
                ],
                "details": (
                    "Concept: dashboards should encode SLO intent, not random metrics. "
                    "Why: without an explicit contract, panels become noisy and unactionable. "
                    "Approach: map one business journey to technical SLIs."
                ),
                "rationale": (
                    "Real-world problem: many teams collect metrics but cannot answer "
                    "incident questions quickly. Why this step: aligns panels to decisions. "
                    "How it helps: dashboard consumers can triage in minutes."
                ),
                "code": "Category | SLI | Target\n"
                "Availability | success ratio | 99.9%\n"
                "Latency | p95 request duration | <300ms\n"
                "Errors | 5xx ratio | <0.1%\n"
                "Saturation | CPU throttling/memory pressure | trend only",
            },
            {
                "title": "Harden metric labeling",
                "body": "Standardize labels and remove high-cardinality pitfalls.",
                "output": "Stable labels for job, instance, namespace, pod, route, status.",
                "duration": "20 min",
                "priority": "High",
                "points": "8",
                "checkpoints": [
                    "Label schema for service and route is documented.",
                    "Unbounded labels are removed or normalized.",
                ],
                "acceptance": [
                    "No query relies on raw path/user/session labels.",
                ],
                "pitfalls": [
                    "Adding HTTP path with IDs as direct labels.",
                ],
                "details": (
                    "Concept: good labels are the foundation of reliable dashboards. "
                    "Why: high-cardinality labels cause slow queries and noisy panels. "
                    "Approach: avoid unbounded labels like user_id/session_id/path_raw."
                ),
                "rationale": (
                    "Real-world problem: Prometheus memory spikes from cardinality explosions. "
                    "Why this step: prevents cost and performance regressions. "
                    "How it helps: keeps dashboards fast during incidents."
                ),
                "code": "sum by (job, namespace, pod, status) (\n"
                "  rate(http_requests_total{namespace=\"gratitude\"}[5m])\n"
                ")",
            },
            {
                "title": "Create recording rules for expensive queries",
                "body": "Precompute request rate, error ratio, and latency quantiles.",
                "output": "Rule groups loaded and visible in Prometheus.",
                "duration": "25 min",
                "priority": "High",
                "points": "12",
                "checkpoints": [
                    "Rules appear under `Status -> Rules` in Prometheus.",
                    "Panel queries reference recorded series where applicable.",
                ],
                "acceptance": [
                    "Rule interval aligns with alert/dash refresh windows.",
                ],
                "pitfalls": [
                    "Computing histogram quantile from already aggregated percentiles.",
                    "Over-recording one-off metrics that do not need caching.",
                ],
                "details": (
                    "Concept: recording rules reduce repeated query cost in Grafana. "
                    "Why: dashboards with many raw aggregations become slow at scale. "
                    "Approach: precompute shared expressions used by multiple panels."
                ),
                "rationale": (
                    "Real-world problem: overloaded Prometheus under heavy dashboard usage. "
                    "Why this step: centralizes expensive calculations once per interval. "
                    "How it helps: improves panel load times and reliability."
                ),
                "code": "groups:\n"
                "- name: gratitudeapp.rules\n"
                "  interval: 30s\n"
                "  rules:\n"
                "  - record: service:http_rps:rate5m\n"
                "    expr: sum(rate(http_requests_total{namespace=\"gratitude\"}[5m])) by (service)\n"
                "  - record: service:http_5xx_ratio:rate5m\n"
                "    expr: |\n"
                "      sum(rate(http_requests_total{namespace=\"gratitude\",status=~\"5..\"}[5m])) by (service)\n"
                "      /\n"
                "      sum(rate(http_requests_total{namespace=\"gratitude\"}[5m])) by (service)\n"
                "  - record: service:http_p95_latency_seconds:5m\n"
                "    expr: |\n"
                "      histogram_quantile(0.95,\n"
                "        sum(rate(http_request_duration_seconds_bucket{namespace=\"gratitude\"}[5m])) by (le, service)\n"
                "      )",
            },
            {
                "title": "Design dashboard taxonomy",
                "body": "Create 4 dashboards: Executive, Service, Capacity, Incident.",
                "output": "Folders and naming conventions agreed.",
                "duration": "15 min",
                "priority": "High",
                "points": "7",
                "checkpoints": [
                    "Each dashboard has a primary audience and decision purpose.",
                    "Panel naming follows a consistent verb + metric format.",
                ],
                "acceptance": [
                    "No dashboard duplicates the same panel with only cosmetic changes.",
                ],
                "pitfalls": [
                    "Mixing executive and on-call detail in the same board.",
                ],
                "details": (
                    "Concept: different audiences need different panel density and context. "
                    "Why: one giant dashboard fails both executives and operators. "
                    "Approach: split by decision context and time horizon."
                ),
                "rationale": (
                    "Real-world problem: teams overload one dashboard and lose signal. "
                    "Why this step: enforces clarity per consumer type. "
                    "How it helps: faster decision-making under pressure."
                ),
                "code": "Folder: GratitudeApp\n"
                "1) Exec-SLO-Overview\n"
                "2) Service-Deep-Dive\n"
                "3) Capacity-and-Cost\n"
                "4) Incident-War-Room",
            },
            {
                "title": "Build reusable Grafana variables",
                "body": "Add datasource, environment, namespace, service, and pod variables.",
                "output": "Variables filter all relevant panels consistently.",
                "duration": "20 min",
                "priority": "Medium",
                "points": "7",
                "checkpoints": [
                    "Default values work with no manual selection.",
                    "Multi-select and `All` do not break query performance.",
                ],
                "acceptance": [
                    "Variables are used across all four dashboards consistently.",
                ],
                "pitfalls": [
                    "Chained variables causing empty values in some environments.",
                ],
                "details": (
                    "Concept: variables make one dashboard reusable across environments. "
                    "Why: duplicated dashboards drift and increase maintenance. "
                    "Approach: use query variables with sensible defaults and multi-select."
                ),
                "rationale": (
                    "Real-world problem: stale copies of dashboards for dev/stage/prod. "
                    "Why this step: one dashboard, many environments. "
                    "How it helps: keeps operational views consistent."
                ),
                "code": "label_values(kube_pod_info, namespace)\n"
                "label_values(http_requests_total{namespace=\"$namespace\"}, service)\n"
                "label_values(kube_pod_info{namespace=\"$namespace\"}, pod)",
            },
            {
                "title": "Implement RED and USE views",
                "body": "Create panels for Rate-Errors-Duration and Utilization-Saturation-Errors.",
                "output": "Service and node-level golden signals visible.",
                "duration": "35 min",
                "priority": "High",
                "points": "10",
                "checkpoints": [
                    "RED panels include requests/sec, error ratio, and p95 latency.",
                    "USE panels include CPU utilization, memory pressure, and throttling.",
                ],
                "acceptance": [
                    "At least one panel correlates service degradation with resource stress.",
                ],
                "pitfalls": [
                    "Using CPU usage alone without throttling or saturation context.",
                ],
                "details": (
                    "Concept: RED + USE gives balanced app and infrastructure signals. "
                    "Why: app-only dashboards miss resource saturation root causes. "
                    "Approach: pair service panels with node and pod resource context."
                ),
                "rationale": (
                    "Real-world problem: incidents escalate when teams chase the wrong layer. "
                    "Why this step: correlates user impact with infrastructure state. "
                    "How it helps: narrows blast radius quickly."
                ),
                "code": "sum(rate(container_cpu_usage_seconds_total{namespace=\"$namespace\"}[5m])) by (pod)\n"
                "sum(container_memory_working_set_bytes{namespace=\"$namespace\"}) by (pod)\n"
                "sum(rate(http_requests_total{namespace=\"$namespace\"}[5m])) by (service)",
            },
            {
                "title": "Add SLO burn-rate panels",
                "body": "Visualize fast and slow burn windows with clear thresholds.",
                "output": "Multi-window burn-rate chart and status table.",
                "duration": "30 min",
                "priority": "High",
                "points": "12",
                "checkpoints": [
                    "Short-window and long-window burn rates are both present.",
                    "Threshold lines for page and ticket levels are annotated.",
                ],
                "acceptance": [
                    "Burn-rate values map clearly to response urgency.",
                ],
                "pitfalls": [
                    "Relying on one window only, causing false positives or delayed detection.",
                ],
                "details": (
                    "Concept: burn-rate shows how quickly error budget is consumed. "
                    "Why: raw error percentages hide urgency over different windows. "
                    "Approach: implement short+long windows and annotate thresholds."
                ),
                "rationale": (
                    "Real-world problem: teams detect SLO risk too late. "
                    "Why this step: burn-rate gives early and credible warning. "
                    "How it helps: supports proportional incident response."
                ),
                "code": "# Example error budget burn (99.9% SLO => budget 0.001)\n"
                "(service:http_5xx_ratio:rate5m{service=\"$service\"}) / 0.001\n"
                "(sum(rate(http_requests_total{status=~\"5..\",service=\"$service\"}[1h]))\n"
                " / sum(rate(http_requests_total{service=\"$service\"}[1h]))) / 0.001",
            },
            {
                "title": "Integrate alerts into dashboards",
                "body": "Show firing and pending alerts with direct runbook links.",
                "output": "Incident dashboard includes current alert state and owner metadata.",
                "duration": "20 min",
                "priority": "High",
                "points": "8",
                "checkpoints": [
                    "Alert list panel is filtered by namespace/service/severity variables.",
                    "Runbook and owner annotations are visible in alert metadata.",
                ],
                "acceptance": [
                    "On-call can navigate from alert to runbook in one click.",
                ],
                "pitfalls": [
                    "Missing owner metadata, making escalations ambiguous.",
                ],
                "details": (
                    "Concept: dashboards must connect signal to action. "
                    "Why: separate alert and graph tools increase triage latency. "
                    "Approach: add alert list panel scoped by namespace/service/severity."
                ),
                "rationale": (
                    "Real-world problem: responders lose time finding runbooks and ownership. "
                    "Why this step: embeds operational context in one place. "
                    "How it helps: reduces mean time to mitigation."
                ),
                "code": "labels:\n"
                "  severity: page\n"
                "  service: gratitude-api\n"
                "  owner: platform\n"
                "annotations:\n"
                "  runbook: https://internal/wiki/gratitudeapi-incident",
            },
            {
                "title": "Build panel-level troubleshooting drilldowns",
                "body": "Add links from summary panels to endpoint, pod, and node deep dives.",
                "output": "Every critical summary panel has a drilldown path.",
                "duration": "20 min",
                "priority": "Medium",
                "points": "6",
                "checkpoints": [
                    "Service error panel links to endpoint breakdown panel.",
                    "Latency panel links to pod restart and resource panels.",
                ],
                "acceptance": [
                    "Drilldowns preserve selected variables and time range.",
                ],
                "pitfalls": [
                    "Linking to dashboards that reset context and lose incident timeline.",
                ],
                "details": (
                    "Concept: summary panels should provide a fast route to root-cause views. "
                    "Why: manual navigation during incidents burns critical minutes. "
                    "Approach: add dashboard links with URL parameters for context carry-over."
                ),
                "rationale": (
                    "Real-world problem: responders spend time searching instead of mitigating. "
                    "Why this step: creates deterministic investigation flow. "
                    "How it helps: lowers cognitive overhead in high-pressure incidents."
                ),
                "code": "https://grafana.example/d/service?var-namespace=$namespace&var-service=$service&from=$__from&to=$__to",
            },
            {
                "title": "Run load and validate dashboard behavior",
                "body": "Generate synthetic traffic and verify panel responsiveness.",
                "output": "Dashboards show expected trend changes under load.",
                "duration": "30 min",
                "priority": "High",
                "points": "10",
                "checkpoints": [
                    "Low/medium/high load scenarios are executed and timestamped.",
                    "Panel shifts are captured for throughput, latency, and error ratio.",
                ],
                "acceptance": [
                    "Team can explain at least one non-intuitive metric behavior under stress.",
                ],
                "pitfalls": [
                    "Using too short a test window to observe stable trends.",
                    "Running load without marking timeline events.",
                ],
                "details": (
                    "Concept: dashboards are software and need scenario-based tests. "
                    "Why: a dashboard that looks good at idle may fail under stress. "
                    "Approach: run low/medium/high traffic and capture panel snapshots."
                ),
                "rationale": (
                    "Real-world problem: untested dashboards mislead incident response. "
                    "Why this step: verifies that visuals track real system behavior. "
                    "How it helps: builds operator trust."
                ),
                "code": "hey -z 3m -c 20 https://<app-url>/\n"
                "hey -z 3m -c 80 https://<app-url>/\n"
                "kubectl top pod -n gratitude",
            },
            {
                "title": "Perform dashboard performance tuning",
                "body": "Measure panel query times and optimize slow or high-cost queries.",
                "output": "Dashboard load time and query costs reduced.",
                "duration": "20 min",
                "priority": "Medium",
                "points": "6",
                "checkpoints": [
                    "Top 3 slow panels identified via query inspector.",
                    "At least two queries moved to recording-rule-backed series.",
                ],
                "acceptance": [
                    "Average panel load time improved after optimization.",
                ],
                "pitfalls": [
                    "Over-aggregating too early and losing useful dimensions.",
                ],
                "details": (
                    "Concept: dashboard responsiveness matters during incident triage. "
                    "Why: slow panels delay decisions and degrade operator trust. "
                    "Approach: use Grafana query inspector and Prometheus query logs."
                ),
                "rationale": (
                    "Real-world problem: dashboards frequently time out when load spikes. "
                    "Why this step: eliminates expensive expressions from hot paths. "
                    "How it helps: keeps observability usable when it's needed most."
                ),
                "code": "sum(rate(http_requests_total{namespace=\"$namespace\"}[5m])) by (service)\n"
                "# Replace repeated heavy query with\n"
                "service:http_rps:rate5m{service=\"$service\"}",
            },
            {
                "title": "Provision dashboards as code",
                "body": "Export JSON and store in Git with reviewable changes.",
                "output": "Versioned dashboard definitions and provisioning config committed.",
                "duration": "25 min",
                "priority": "High",
                "points": "6",
                "checkpoints": [
                    "All four dashboards exported and committed in a deterministic folder layout.",
                    "Provisioning config references dashboard folder and JSON files.",
                ],
                "acceptance": [
                    "A fresh Grafana instance can load dashboards from the repo artifacts.",
                ],
                "pitfalls": [
                    "Committing UI-generated noise fields that create noisy diffs.",
                ],
                "details": (
                    "Concept: dashboard-as-code enables change control and rollbacks. "
                    "Why: manual UI edits are hard to audit and reproduce. "
                    "Approach: commit JSON, datasource templates, and folder provisioning."
                ),
                "rationale": (
                    "Real-world problem: dashboard drift across environments and teams. "
                    "Why this step: codifies dashboard lifecycle with CI review. "
                    "How it helps: repeatable and auditable observability."
                ),
                "code": "observability/\n"
                "  grafana/\n"
                "    provisioning/dashboards/dashboards.yaml\n"
                "    dashboards/exec-slo-overview.json\n"
                "    dashboards/service-deep-dive.json\n"
                "  prometheus/\n"
                "    recording-rules.yaml\n"
                "    alert-rules.yaml",
            },
            {
                "title": "Write an incident narrative from the dashboard set",
                "body": "Simulate a short outage and write a timeline using dashboard evidence.",
                "output": "One-page incident narrative with timestamps and dashboard screenshots.",
                "duration": "25 min",
                "priority": "Medium",
                "points": "10",
                "checkpoints": [
                    "Narrative includes detection time, probable cause, and mitigation action.",
                    "At least three panels are cited as evidence.",
                ],
                "acceptance": [
                    "Narrative is actionable for another engineer unfamiliar with the system.",
                ],
                "pitfalls": [
                    "Conclusions without metric evidence or timestamps.",
                ],
                "details": (
                    "Concept: dashboards are valuable only if they support real decisions. "
                    "Why: incident reports expose gaps in panel design and interpretation. "
                    "Approach: reconstruct a timeline from burn-rate, RED, and capacity signals."
                ),
                "rationale": (
                    "Real-world problem: teams have dashboards but weak post-incident learning. "
                    "Why this step: validates end-to-end usability of your observability stack. "
                    "How it helps: converts charts into operational practice."
                ),
                "code": "Template:\n"
                "T0 Detection:\n"
                "T+5m Triage signal:\n"
                "T+12m Mitigation:\n"
                "T+20m Recovery:\n"
                "Postmortem action items:",
            },
        ],
        "deliverables": [
            {
                "title": "SLO contract document",
                "body": "Defined SLIs/SLOs and mapped user journey.",
            },
            {
                "title": "Recording rule manifest",
                "body": "Prometheus rules for rate, error ratio, and p95 latency.",
            },
            {
                "title": "Four advanced dashboards",
                "body": "Executive, Service, Capacity, and Incident dashboards with variables.",
            },
            {
                "title": "Load validation evidence",
                "body": "Screenshots proving panel behavior under changing traffic levels.",
            },
            {
                "title": "Dashboards-as-code repo artifacts",
                "body": "Committed JSON/provisioning files and change log.",
            },
            {
                "title": "Incident narrative",
                "body": "A timeline-driven incident analysis using dashboard evidence.",
            },
        ],
        "validation": [
            "Dashboards answer SLO status, incident state, and capacity trend questions.",
            "Recording rules are used for expensive repeated expressions.",
            "Burn-rate panels show both short and long windows with thresholds.",
            "Alert context includes severity, ownership, and runbook links.",
            "Dashboard definitions are version-controlled and reproducible.",
            "Drilldown links preserve context and accelerate investigation paths.",
            "Dashboard query performance is tested and tuned.",
        ],
        "resources": [
            {
                "title": "Prometheus best practices",
                "body": "https://prometheus.io/docs/practices/naming/",
            },
            {
                "title": "PromQL functions",
                "body": "https://prometheus.io/docs/prometheus/latest/querying/functions/",
            },
            {
                "title": "Grafana dashboard best practices",
                "body": "https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/",
            },
            {
                "title": "SRE workbook (SLO alerts)",
                "body": "https://sre.google/workbook/alerting-on-slos/",
            },
            {
                "title": "Grafana observability-as-code",
                "body": "https://grafana.com/docs/grafana/latest/administration/provisioning/",
            },
        ],
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "No submission required",
        "form_helper": "Capture screenshots, PromQL queries, and JSON exports for your report.",
        "sections": [
            {
                "title": "Dashboard standards",
                "items": [
                    {
                        "title": "Time ranges",
                        "body": "Provide 15m, 1h, 6h, 24h, and 7d quick ranges for each board.",
                    },
                    {
                        "title": "Panel clarity",
                        "body": "Every panel includes unit, legend, and one-line interpretation.",
                    },
                    {
                        "title": "Threshold policy",
                        "body": "Use documented warning/critical thresholds tied to SLOs.",
                    },
                ],
            },
            {
                "title": "Advanced panel set",
                "items": [
                    {"title": "Top offenders", "body": "Top endpoints by p95 latency and error ratio."},
                    {"title": "Budget burn", "body": "Multi-window burn-rate panels and state table."},
                    {"title": "Capacity trend", "body": "CPU/memory saturation trend with headroom estimate."},
                    {"title": "Alert feed", "body": "Firing and pending alerts scoped by variables."},
                ],
            },
            {
                "title": "Assessment prompts",
                "items": [
                    {
                        "title": "Noise vs signal",
                        "body": "Explain one panel removed because it created noise.",
                    },
                    {
                        "title": "Cardinality control",
                        "body": "Show one metric label design change that reduced cardinality risk.",
                    },
                    {
                        "title": "Incident triage",
                        "body": "Describe how your Incident dashboard isolates probable root cause.",
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


def parse_concurrency_steps(raw_value):
    if not raw_value:
        return [1]
    steps = []
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            value = int(item)
        except ValueError:
            continue
        if value > 0:
            steps.append(value)
    return steps or [1]


def log_load(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[load] {timestamp} {message}", flush=True)


def build_hey_args(concurrency, duration_seconds):
    base_args = shlex_split(LOAD_HEY_ARGS) if LOAD_HEY_ARGS else []
    cleaned = []
    skip_next = False
    for token in base_args:
        if skip_next:
            skip_next = False
            continue
        if token in {"-c", "-z"}:
            skip_next = True
            continue
        cleaned.append(token)
    if duration_seconds > 0:
        cleaned += ["-z", f"{duration_seconds}s"]
    cleaned += ["-c", str(concurrency)]
    return [LOAD_HEY_PATH] + cleaned


def _load_worker(url, end_time, counters, lock):
    while time.time() < end_time:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                response.read(64)
            with lock:
                counters["ok"] += 1
        except Exception:
            with lock:
                counters["err"] += 1
        time.sleep(0.01)


def run_load_step_internal(url, concurrency, duration_seconds):
    end_time = time.time() + max(1, duration_seconds)
    counters = {"ok": 0, "err": 0}
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(concurrency):
            executor.submit(_load_worker, url, end_time, counters, lock)
    return counters


def run_load_step_hey(url, concurrency, duration_seconds):
    args = build_hey_args(concurrency, duration_seconds)
    timeout_seconds = max(10, duration_seconds + 30)
    try:
        result = subprocess.run(
            args + [url],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        log_load(f"hey not found at {LOAD_HEY_PATH}; falling back to internal load.")
        return run_load_step_internal(url, concurrency, duration_seconds)
    except subprocess.TimeoutExpired:
        log_load(f"hey timed out for {url} at concurrency {concurrency}.")
        return {"ok": 0, "err": 1}
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        log_load(f"hey failed for {url} (code {result.returncode}): {' | '.join(tail)}")
    return {"ok": 0, "err": 0}


def run_load_for_target(url, name, steps, duration_seconds):
    for concurrency in steps:
        log_load(f"{name}: load step start url={url} concurrency={concurrency}")
        if LOAD_TOOL == "hey":
            run_load_step_hey(url, concurrency, duration_seconds)
        else:
            counters = run_load_step_internal(url, concurrency, duration_seconds)
            log_load(
                f"{name}: load step done url={url} c={concurrency} "
                f"ok={counters['ok']} err={counters['err']}"
            )
        time.sleep(max(0, LOAD_STEP_PAUSE_SECONDS))


def run_load_loop():
    steps = parse_concurrency_steps(LOAD_CONCURRENCY_STEPS)
    while True:
        if not LOAD_TEST_ENABLED:
            time.sleep(max(5, LOAD_ROUND_PAUSE_SECONDS))
            continue
        targets = list_students(LOAD_TEST_LAB_ID)
        if not targets:
            time.sleep(max(5, LOAD_ROUND_PAUSE_SECONDS))
            continue
        for target in targets:
            url = target.get("url")
            name = target.get("name") or "target"
            if not url or not is_valid_url(url):
                log_load(f"{name}: invalid URL; skipped.")
                continue
            run_load_for_target(url, name, steps, LOAD_STEP_SECONDS)
        time.sleep(max(5, LOAD_ROUND_PAUSE_SECONDS))


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
LOAD_TEST_ENABLED = os.environ.get("LOAD_TEST_ENABLED", "false").lower() == "true"
LOAD_TEST_LAB_ID = os.environ.get("LOAD_TEST_LAB_ID", "lab4")
LOAD_TOOL = os.environ.get("LOAD_TOOL", "internal").lower()
LOAD_HEY_PATH = os.environ.get("LOAD_HEY_PATH", "hey")
LOAD_HEY_ARGS = os.environ.get("LOAD_HEY_ARGS", "")
LOAD_STEP_SECONDS = int(os.environ.get("LOAD_STEP_SECONDS", "60"))
LOAD_STEP_PAUSE_SECONDS = int(os.environ.get("LOAD_STEP_PAUSE_SECONDS", "5"))
LOAD_ROUND_PAUSE_SECONDS = int(os.environ.get("LOAD_ROUND_PAUSE_SECONDS", "30"))
LOAD_CONCURRENCY_STEPS = os.environ.get("LOAD_CONCURRENCY_STEPS", "1,5,10,25")


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


@app.get("/lab5")
def lab5():
    return redirect(url_for("lab_detail", lab_id="lab5"))


@app.get("/lab6")
def lab6():
    return redirect(url_for("lab_detail", lab_id="lab6"))


@app.get("/lab7")
def lab7():
    return redirect(url_for("lab_detail", lab_id="lab7"))


@app.get("/lab8")
def lab8():
    return redirect(url_for("lab_detail", lab_id="lab8"))


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
    if LOAD_TEST_ENABLED:
        load_thread = threading.Thread(target=run_load_loop, daemon=True)
        load_thread.start()
    app.run(host="0.0.0.0", port=port, debug=False)
