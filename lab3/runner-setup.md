# Runner Setup (Self-Hosted GitHub Actions)

This guide is for a Linux runner machine (EC2 or VM).

## 1) Install Tools
- Docker
- Git
- AWS CLI v2
- kubectl
- jq

Verify:
- `docker --version`
- `git --version`
- `aws --version`
- `kubectl version --client`

## 2) Register the Runner
In the GitHub repo:
- Settings -> Actions -> Runners -> New self-hosted runner
- Follow the download + configure steps for Linux

## 3) Permissions
Ensure the runner can:
- Reach SonarQube (network + token)
- Push to ECR
- Access EKS

Recommended:
- Use instance role or OIDC role with least-privilege
- Store no long-lived static AWS keys on the runner

## 4) EKS Access
Option A (instance role):
- Ensure the instance role has `eks:DescribeCluster`
- Add the instance role to the cluster auth configmap

Option B (kubeconfig secret):
- Store a base64 kubeconfig in `KUBECONFIG_B64` GitHub secret
- Decode in the workflow before `kubectl`

## 5) SonarQube Access
- Create a project and token in SonarQube
- Store `SONAR_HOST_URL` and `SONAR_TOKEN` in GitHub secrets

## 6) Validate Runner
- Trigger a simple workflow to confirm the runner is active
- Verify it can login to ECR and reach the cluster
