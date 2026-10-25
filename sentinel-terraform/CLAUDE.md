# CLAUDE.md

Microsoft Sentinel and its analytics rules, deployed with Terraform. See README.md for the full design and the GitHub Actions pipeline.

## How I want to work

I'm learning Terraform and Azure. I run the commands myself in the VS Code terminal.

- Explain what a command does and what to look for in its output. Don't run it for me unless I ask.
- Never run `terraform apply`, `terraform destroy`, or any `az` command that creates, changes, or deletes something in Azure without asking me first.
- Read-only commands (`terraform validate`, `terraform plan`, `az ... show`, `az ... list`) are fine to run when you need to check something.

## Layout

| Path | What it is |
|---|---|
| `terraform/` | All Terraform code. Run every `terraform` command from here. |
| `rules/*.yaml` | One file per analytics rule. `terraform/rules.tf` turns each into a Sentinel rule. Files starting with `_` are skipped. |
| `state-storage/` | Terraform that creates the storage account for Terraform state. Its own state stays local (`state-storage/terraform.tfstate`). Run once, before the bootstrap. |
| `bootstrap/setup.sh` | One-time Azure setup for the GitHub pipeline: identity, roles, repo variables. Reads the storage account from `state-storage/`. |
| `../.github/workflows/sentinel.yml` | Plan on pull request, apply on merge. Lives at the `projects` repo root so GitHub runs it. |

## Running locally (current setup)

Two local-only files in `terraform/` are gitignored by `*_override.tf`:

- `backend_override.tf` keeps Terraform state on disk (`terraform/terraform.tfstate`) instead of Azure storage.
- `provider_override.tf` sets the Azure subscription ID.

In GitHub Actions these files don't exist, so the pipeline uses the azurerm backend and `ARM_SUBSCRIPTION_ID` from repo variables.

Sign-in uses the `az login` session. If a command says you're not logged in, run `az login` again.

## Progress

Done (2026-10-20):

- Moved this folder into the `projects` repo (github.com/mbayless/projects, default branch `main`). It's not committed yet.
- Installed the Azure CLI and signed in.
- Created resource group `rg-sentinel-lab` in eastus. It's empty.
- Local `terraform plan` works: **6 to add, 0 to change, 0 to destroy**. Nothing has been applied.

Decision: **deploy through GitHub Actions, not a local apply.** Keep using `terraform plan` locally to learn, but let the pipeline do every apply. Because nothing was ever applied locally, there's no local state to move.

## Next steps: set up GitHub Actions

**1. Install the GitHub CLI and sign in.** The bootstrap uses it to save the repo variables for you. Without it you'd type five values into GitHub by hand.

```bash
brew install gh
gh auth login
```

**2. Check you're signed in to Azure on the right subscription.**

```bash
az account show --query "{name:name, id:id}" -o table
```

**3a. Create the state storage with Terraform** from `sentinel-terraform/state-storage/`. Its own state stays on your Mac (`state-storage/terraform.tfstate`, gitignored). Don't delete that file: it's how Terraform knows it owns the storage account.

`rg-terraform-state` already exists from the first bootstrap run (2026-10-25), so import it once before the apply:

```bash
cd ~/Desktop/Shannon_GitHub/projects/sentinel-terraform/state-storage
terraform init
terraform import azurerm_resource_group.state /subscriptions/63a23dcb-26d9-400f-8584-e47597a6c631/resourceGroups/rg-terraform-state
terraform plan     # expect 4 to add: random suffix, storage account, tfstate container, your role
terraform apply
```

**3b. Run the bootstrap** from `sentinel-terraform/`. It reads the storage account name from `state-storage/`, asks you to confirm the subscription, then:

- registers the Azure resource providers,
- reuses `rg-sentinel-lab`,
- creates the `github-sentinel-terraform` sign-in identity, which only trusts pull requests and the `production` environment of `mbayless/projects`,
- gives that identity its roles, including access to the state storage,
- saves `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `TF_STATE_RG`, `TF_STATE_STORAGE` as repo variables and creates the `production` environment.

```bash
cd ~/Desktop/Shannon_GitHub/projects/sentinel-terraform
./bootstrap/setup.sh mbayless/projects eastus
```

Read the output: each `==>` line is one stage. It prints the five values at the end. Safe to re-run if it stops partway.

**4. Add yourself as a required reviewer** in GitHub: **projects repo > Settings > Environments > production > Required reviewers**. Every apply then waits for you to click Approve. Do this before step 6.

**5. Move the workflow to the repo root.** Done 2026-10-25. It's now at `projects/.github/workflows/sentinel.yml`, because GitHub only runs workflows from the repo root. Its paths, working directory and plan-comment file all start with `sentinel-terraform/`.

**6. Commit on a branch and open a pull request.** Don't push straight to `main`: a push to `main` runs the Apply job.

```bash
cd ~/Desktop/Shannon_GitHub/projects
git checkout -b sentinel-pipeline
git add .github sentinel-terraform
git status            # check: no tfstate, tfplan, plan.txt or *_override.tf files
git commit -m "Add Sentinel Terraform pipeline"
git push -u origin sentinel-pipeline
gh pr create --fill
```

The Plan job runs on the PR and posts the plan as a comment. Expect **6 to add, 0 to change, 0 to destroy**, the same as the local plan. If the plan fails, the job log in the **Actions** tab shows why.

**7. Merge the PR.** That push to `main` starts the Apply job. It waits for your approval (step 4), then creates the resources. Watch it under **Actions**.

**8. Check the result** in the Azure portal under **Microsoft Sentinel > Analytics**. All three rules should be there. Rules only fire once Activity log data arrives, which can take 10 to 15 minutes.

**9. Point your local Terraform at the shared state** so local plans see what the pipeline built. In `sentinel-terraform/terraform`:

```bash
rm backend_override.tf
terraform init -reconfigure \
  -backend-config="resource_group_name=rg-terraform-state" \
  -backend-config="storage_account_name=$(terraform -chdir=../state-storage output -raw storage_account_name)"
terraform plan
```

Expect `No changes.` From now on, `terraform plan` locally is for learning and checking only. Changes go through a pull request. Keep `provider_override.tf`: it only sets the subscription ID.

## Not done yet

- **Cost.** The workspace has no daily data cap (`daily_quota_gb = -1`). Fine for Activity-log data. Revisit before connecting bigger data sources.
- **Cleanup.** To remove everything, delete the resources through the pipeline or with a local `terraform destroy` against the shared state, then `az group delete -n rg-sentinel-lab`, and `terraform destroy` in `state-storage/` for the state storage. The `github-sentinel-terraform` app registration stays in Entra ID until you delete it.
