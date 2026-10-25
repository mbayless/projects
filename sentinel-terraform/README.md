# Sentinel analytics rules as code

This repo deploys Microsoft Sentinel and its analytics rules with Terraform, through GitHub Actions. You write a rule as a small YAML file, open a pull request, review the plan, and merge. GitHub then deploys the rule to Sentinel.

```
rules/*.yaml  ──PR──▶  GitHub Actions: fmt, validate, plan (posted on the PR)
                         │
                       merge to main
                         ▼
                GitHub Actions: apply  ──OIDC──▶  Azure: Sentinel workspace + rules
```

GitHub signs in to Azure with OpenID Connect (OIDC). No passwords or client secrets are stored in GitHub.

## What's in the repo

| Path | What it does |
|---|---|
| `bootstrap/setup.sh` | One-time Azure setup: resource groups, state storage, the GitHub sign-in identity and its roles |
| `terraform/main.tf` | Log Analytics workspace, Sentinel onboarding, and the Azure Activity log connection |
| `terraform/rules.tf` | Turns every YAML file in `rules/` into a scheduled or NRT analytics rule |
| `rules/*.yaml` | Three sample rules that work on Azure Activity data |
| `rules/_template.yaml` | Copy this to write a new rule (files starting with `_` are skipped) |
| `../.github/workflows/sentinel.yml` | Plan on pull requests, apply on merge to `main` (at the `projects` repo root) |

## Sample rules

| Rule | Type | MITRE | Fires when |
|---|---|---|---|
| Many Azure resources deleted by one account | Scheduled, hourly | Impact, T1485 | One caller deletes 5+ resources in an hour |
| New Azure role assignment created | Scheduled, hourly | Privilege Escalation, Persistence, T1098 | Someone grants an RBAC role |
| Network security group rule changed | NRT, about every minute | Defense Evasion, T1562 | An NSG rule is created or changed |

All three use the `AzureActivity` table, which Terraform fills by connecting your subscription's Activity log. That way they work without any paid data connectors.

## Setup (about 30 minutes, once)

### 1. Install the tools on your Mac

```bash
brew install azure-cli terraform gh git
az login
gh auth login
```

### 2. Create the GitHub repo and push these files

```bash
cd sentinel-terraform
git init -b main
git add .
git commit -m "Sentinel analytics rules as code"
gh repo create sentinel-terraform --private --source=. --push
```

### 3. Run the Azure bootstrap

Replace `YOUR-GITHUB-USER` with your GitHub username.

```bash
chmod +x bootstrap/setup.sh
./bootstrap/setup.sh YOUR-GITHUB-USER/sentinel-terraform eastus
```

The script asks you to confirm the subscription, then creates everything and prints five values. If the GitHub CLI is signed in, it also saves them as repository variables and creates the `production` environment for you.

If it couldn't, add them by hand in GitHub under **Settings > Secrets and variables > Actions > Variables**: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `TF_STATE_RG`, `TF_STATE_STORAGE`. Then create an environment named `production` under **Settings > Environments**.

### 4. Deploy the first time

In GitHub, open **Actions > Sentinel analytics rules > Run workflow** on `main`. The Apply job creates the workspace, turns on Sentinel, connects the Activity log, and deploys the three rules.

Check it in the Defender portal (security.microsoft.com) under **Microsoft Sentinel > Configuration > Analytics**, or in the Azure portal under **Microsoft Sentinel > Analytics**.

Optional: under **Settings > Environments > production**, add yourself as a required reviewer. Every deployment then waits for your approval.

## Daily use: add or change a rule

```bash
git checkout -b rule/keyvault-deleted
cp rules/_template.yaml rules/keyvault-deleted.yaml
# edit the file: id, display_name, query, tactics, entities ...
git add rules/keyvault-deleted.yaml
git commit -m "Add Key Vault deletion rule"
git push -u origin rule/keyvault-deleted
gh pr create --fill
```

The pull request runs a plan and posts it as a comment. Read it: you should see `1 to add`. Merge the pull request and the Apply job deploys the rule.

- **Change a rule:** edit its YAML and open a pull request. The plan shows `1 to change`.
- **Turn a rule off:** set `enabled: false`.
- **Remove a rule:** delete its YAML file. The plan shows `1 to destroy`.
- **Test a query first:** paste it into **Logs** in the Sentinel workspace and run it.

Rules created by hand in the portal are not touched. Terraform only manages rules that come from this repo.

## Run Terraform from your Mac (optional)

```bash
cd terraform
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
terraform init \
  -backend-config="resource_group_name=rg-terraform-state" \
  -backend-config="storage_account_name=<TF_STATE_STORAGE value>"
terraform plan
```

This uses your `az login` session. Avoid running `apply` locally once the pipeline is in use, so the repo stays the source of truth.

## Security notes

- The GitHub identity can only sign in from this repo's pull requests and its `production` environment.
- It has **Contributor** and **Microsoft Sentinel Contributor** on the Sentinel resource group only, **Storage Blob Data Contributor** on the state storage account, and **Monitoring Contributor** on the subscription (needed for the Activity log connection). To drop that last role, set `CONNECT_ACTIVITY_LOG=false` when you run the bootstrap and set `connect_activity_log = false` in Terraform, then connect the Activity log in the portal yourself.
- Terraform state can contain resource details. It sits in a private storage account with key access turned off.

## Troubleshooting

| Error | Fix |
|---|---|
| `AADSTS700213: No matching federated identity record` | The repo name in the bootstrap must match exactly, and the apply job must use the `production` environment. Re-run the bootstrap with the right owner/repo. |
| `AuthorizationFailed` right after bootstrap | Role assignments can take a few minutes to apply. Re-run the job. |
| `One of the tables does not exist` on a rule | The table has no schema yet in the workspace. Connect its data source (or wait for the first Activity log events), then re-run. |
| `resource already exists` | A rule with that id was created another way. Delete it in the portal or pick a new id. |
| State lock error | A previous run was cancelled mid-apply. In the storage account, break the lease on `tfstate/sentinel.tfstate`. |

## Cost

Activity log data is small. New Sentinel workspaces usually qualify for a free trial period; check current Microsoft Sentinel pricing for your region. To remove everything, delete the `rg-sentinel-lab` and `rg-terraform-state` resource groups and the subscription diagnostic setting `send-activity-log-to-sentinel`.

## How this maps to SC-200

- Configure and manage scheduled and NRT analytics rules in Sentinel
- Map rules to MITRE ATT&CK tactics and techniques
- Collect Azure activity logs with diagnostic settings
- Specify Microsoft Sentinel roles
