# Infrastructure

GCP project `sso-lab-demo`, region `us-central1`. A $50/month budget alert is configured on the billing account.

| Resource | Purpose |
|---|---|
| Cloud Run `sso-lab-idp`, `sso-lab-app-a`, `sso-lab-app-b` | One image, three roles. Public, scale to zero, max 3 instances each |
| Firestore `(default)` | Lab sessions and traces; TTL on `expires_at` deletes them after 24 h |
| Artifact Registry `sso-lab` | Images; keeps the 10 most recent, deletes others after 30 days |
| SA `sso-lab-run` | Runtime identity: Firestore read/write only |
| SA `sso-lab-deployer` + WIF pool `github` | GitHub Actions deploys from `main` of this repo only; no keys |

Service URLs are deterministic (`https://sso-lab-<actor>-<project number>.us-central1.run.app`), so each
service is told the others' URLs at deploy time. Requests that arrive on Cloud Run's other hostname are
redirected to that canonical URL.

## Credentials

Terraform uses Application Default Credentials, which on a work laptop may be a different Google account.
Run it with a token from the account that owns `sso-lab-demo` instead, which leaves ADC alone:

```bash
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token --account jwjjj1983@gmail.com)
```

The token lasts an hour.

## First-time setup

```bash
# 1. State bucket (once)
gcloud storage buckets create gs://sso-lab-demo-tfstate \
  --project sso-lab-demo --location us-central1 --uniform-bucket-level-access
gcloud storage buckets update gs://sso-lab-demo-tfstate --versioning

# 2. Infrastructure (first apply runs Google's hello image until CI deploys ours)
cd infra/terraform
terraform init
terraform apply

# 3. Let GitHub Actions deploy
terraform output -json github_vars | jq -r 'to_entries[] | "\(.key) \(.value)"' |
  while read -r name value; do gh variable set "$name" --body "$value" --repo jwjjj1983/sso-lab; done

# 4. Deploy: push to main, or run the Deploy workflow by hand
gh workflow run deploy.yml --repo jwjjj1983/sso-lab
terraform output urls
```

## Day to day

- Merging to `main` builds the image and rolls it out (IdP first, then App B, then App A).
- Terraform owns everything except the running image; `ignore_changes` keeps it from rolling back deploys.
