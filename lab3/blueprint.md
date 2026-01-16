# Lab 3 Blueprint: Advanced CI/CD on GitHub Actions -> ECR -> EKS

This blueprint is the authoritative reference for Lab 3. It preserves all
advanced requirements (self-hosted runner, dynamic matrices, reusable
workflows, SonarQube + Trivy, and OIDC auth).

## Target outcome
Build a production-grade pipeline that:
1) Detects which services changed (or builds all on demand)
2) Fans out in parallel: build -> test -> SonarQube -> Trivy -> push to ECR
3) Fans in to deploy to EKS after all images are ready
4) Uses GitHub OIDC (no long-lived AWS keys)
5) Runs on a self-hosted runner with Docker, kubectl, helm, awscli

Services/images:
- client
- api-gateway
- entries
- moods-api
- moods-service
- server
- stats-api
- stats-service
- files-service

## Architecture
GitHub Actions
- orchestrator.yml (top-level)
  - detect changes
  - build matrix
  - call reusable-build.yml in parallel
  - call reusable-deploy.yml once

AWS
- ECR repos per service
- EKS cluster (ingress-nginx + CSI driver)
- IAM role for GitHub Actions via OIDC

Runner machine
- EC2 instance with Docker Buildx, awscli, kubectl, helm
- Optional: trivy + sonar-scanner CLI

## What makes it advanced
- Reusable workflows (workflow_call)
- Dynamic matrices (paths-filter + fromJSON)
- Concurrency controls
- Artifact passing/outputs
- Environment protection rules
- OIDC role assumption
- Caching strategies and optional sidecars

## Part A: AWS + Runner setup

A1) EKS + ECR baseline
- Follow README prerequisites for EKS, CSI driver, ingress
- Create ECR repos:
  - gratitudeapp-client
  - gratitudeapp-api-gateway
  - gratitudeapp-entries
  - gratitudeapp-moods-api
  - gratitudeapp-moods-service
  - gratitudeapp-server
  - gratitudeapp-stats-api
  - gratitudeapp-stats-service
  - gratitudeapp-files-service

A2) GitHub Actions -> AWS auth (OIDC)
- IAM role trust: GitHub OIDC provider
- Policies: minimal ECR push + eks:DescribeCluster
- GitHub secrets:
  - AWS_REGION
  - AWS_ACCOUNT_ID
  - EKS_CLUSTER_NAME
  - AWS_ROLE_TO_ASSUME

A3) Self-hosted runner
- EC2 (t3.large+ for parallel builds)
- Install: Docker + Buildx, awscli v2, kubectl, helm
- Register runner with labels: self-hosted, linux, x64, gratitude-runner
- Manage state: disk cleanup, workspace hygiene, concurrency limits

## Part B: Workflow design

Create:
- .github/workflows/orchestrator.yml
- .github/workflows/reusable-build.yml
- .github/workflows/reusable-deploy.yml

1) orchestrator.yml
- Detect changes via dorny/paths-filter
- Build dynamic matrix via fromJSON
- Fan-out parallel builds
- Fan-in deploy to EKS
- workflow_dispatch inputs: build_all, deploy
- concurrency group to prevent stampedes

2) reusable-build.yml
- OIDC auth
- Build image (no push yet)
- SonarQube scan (remote server)
- Trivy fs + image scan
- Push to ECR only if gates pass

3) reusable-deploy.yml
- OIDC auth + update kubeconfig
- kubectl apply k8s/
- kubectl set image per deployment
- rollout verification
- GitHub environment protection for prod

## Part C: Multi-workflow calling
Level 1 (required): workflow_call
- Orchestrator calls reusable-build per service
- Orchestrator calls reusable-deploy once

Level 2 (extension): workflow_run
- Deploy only after orchestrator completes
- Gate on workflow_run.conclusion == success

## Lab exercises
1) Selective builds: change only moods-api and confirm one build
2) Security gate: make Trivy fail on HIGH to block push
3) Parallelism tuning: set max-parallel and observe runner load
4) Promotion workflow: staging auto, prod manual approval
5) Immutable releases: push release tags + save digests
6) Dockerfile filter: build only when Dockerfile or shared libs change

## Notes for GratitudeApp
- Deployment is manifest-driven via k8s/
- ECR repo names and build contexts are standardized in README
