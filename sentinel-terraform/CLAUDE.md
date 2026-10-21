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
| `bootstrap/setup.sh` | One-time Azure setup for the GitHub pipeline. Not run yet. |
| `.github/workflows/sentinel.yml` | Plan on pull request, apply on merge. Does not run from here yet (see "Not done yet"). |

## Running locally (current setup)

Two local-only files in `terraform/` are gitignored by `*_override.tf`:

- `backend_override.tf` keeps Terraform state on disk (`terraform/terraform.tfstate`) instead of Azure storage.
- `provider_override.tf` sets the Azure subscription ID.

In GitHub Actions these files don't exist, so the pipeline uses the azurerm backend and `ARM_SUBSCRIPTION_ID` from repo variables.

Sign-in uses the `az login` session. If a command says you're not logged in, run `az login` again.

## Progress

Done (2026-10-20):

- Moved this folder into the `projects` repo (github.com/mbayless/projects). It's not committed yet.
- Installed the Azure CLI and signed in.
- Created resource group `rg-sentinel-lab` in eastus. It's empty.
- `terraform plan` works: **6 to add, 0 to change, 0 to destroy**. Saved as `terraform/tfplan`, readable copy in `terraform/plan.txt`.

## Next steps

Run these from `sentinel-terraform/terraform` in the VS Code terminal.

**1. Check you're still signed in to the right subscription.**

```bash
az account show --query "{name:name, id:id}" -o table
```

**2. Register the Azure resource providers.** The Terraform code turns off automatic registration, so this has to happen first or the apply fails. It's free and takes a few minutes.

```bash
for ns in Microsoft.OperationalInsights Microsoft.SecurityInsights Microsoft.OperationsManagement Microsoft.Insights; do
  az provider register --namespace "$ns"
done
```

Check until all four say `Registered`:

```bash
for ns in Microsoft.OperationalInsights Microsoft.SecurityInsights Microsoft.OperationsManagement Microsoft.Insights; do
  echo "$ns: $(az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null)"
done
```

**3. Make a fresh plan and read it.** Yesterday's `tfplan` should still work, but a new one confirms nothing changed overnight.

```bash
terraform plan -out=tfplan
```

Look for `Plan: 6 to add, 0 to change, 0 to destroy.` Anything to change or destroy means something is different from yesterday. Stop and find out why.

**4. Apply the saved plan.** This creates the real resources. Applying a saved plan file doesn't ask "yes" again, because you already reviewed it.

```bash
terraform apply tfplan
```

**5. Check the result.**

```bash
terraform output
terraform state list
```

Then look in the Azure portal under **Microsoft Sentinel > Analytics**. All three rules should be there. Rules only fire once Activity log data arrives, which can take 10 to 15 minutes.

## Not done yet

- **Workflow location.** GitHub only runs workflows in `.github/workflows/` at the repo root. To use the pipeline, move `sentinel.yml` to `projects/.github/workflows/` and prefix its paths with `sentinel-terraform/`.
- **Bootstrap.** `bootstrap/setup.sh` creates the state storage account and the GitHub sign-in identity. Its arguments are `<owner>/<repo> <region>`. This repo is `mbayless/projects`, not the `sentinel-terraform` name the README uses.
- **Moving state to Azure.** After the bootstrap, delete `terraform/backend_override.tf` and run `terraform init -migrate-state` with the two `-backend-config` values. Otherwise the pipeline won't know about resources already created locally.
- **Cost.** The workspace has no daily data cap (`daily_quota_gb = -1`). Fine for Activity-log data. Revisit before connecting bigger data sources.
- **Cleanup.** To remove everything: `terraform destroy`, then `az group delete -n rg-sentinel-lab`.
