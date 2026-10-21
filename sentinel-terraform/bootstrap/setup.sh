#!/usr/bin/env bash
# One-time Azure setup for the Sentinel Terraform pipeline.
#
# Usage: ./bootstrap/setup.sh OWNER/REPO [LOCATION]
#   e.g. ./bootstrap/setup.sh octocat/sentinel-terraform eastus
#
# Optional environment variables:
#   SENTINEL_RG            (default rg-sentinel-lab)
#   STATE_RG               (default rg-terraform-state)
#   APP_NAME               (default github-sentinel-terraform)
#   CONNECT_ACTIVITY_LOG   (default true; false skips Monitoring Contributor on the subscription)
#
# Safe to re-run: existing resources are reused.

set -euo pipefail

REPO="${1:-}"
LOCATION="${2:-eastus}"
SENTINEL_RG="${SENTINEL_RG:-rg-sentinel-lab}"
STATE_RG="${STATE_RG:-rg-terraform-state}"
APP_NAME="${APP_NAME:-github-sentinel-terraform}"
CONNECT_ACTIVITY_LOG="${CONNECT_ACTIVITY_LOG:-true}"
STATE_CONTAINER="tfstate"

if [[ -z "$REPO" || "$REPO" != */* ]]; then
  echo "Usage: $0 OWNER/REPO [LOCATION]" >&2
  exit 1
fi

step() { printf '\n==> %s\n' "$*"; }

# --- Subscription -----------------------------------------------------------
SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
SUBSCRIPTION_NAME="$(az account show --query name -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"

echo "Subscription: $SUBSCRIPTION_NAME ($SUBSCRIPTION_ID)"
echo "Tenant:       $TENANT_ID"
echo "GitHub repo:  $REPO"
echo "Location:     $LOCATION"
read -r -p "Continue with this subscription? [y/N] " answer
[[ "$answer" =~ ^[Yy]$ ]] || { echo "Stopped. Pick another with: az account set --subscription <id>"; exit 1; }

step "Registering resource providers"
for ns in Microsoft.OperationalInsights Microsoft.SecurityInsights Microsoft.OperationsManagement Microsoft.Insights Microsoft.Storage; do
  az provider register --namespace "$ns" --output none
done

# --- Resource groups --------------------------------------------------------
step "Creating resource groups"
az group create --name "$SENTINEL_RG" --location "$LOCATION" --output none
az group create --name "$STATE_RG" --location "$LOCATION" --output none

# --- State storage ----------------------------------------------------------
step "Creating Terraform state storage"
STORAGE_NAME="$(az storage account list --resource-group "$STATE_RG" \
  --query "[?tags.purpose=='terraform-state'] | [0].name" -o tsv)"
if [[ -z "$STORAGE_NAME" ]]; then
  STORAGE_NAME="sttfstate$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 8)"
  az storage account create \
    --name "$STORAGE_NAME" \
    --resource-group "$STATE_RG" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --min-tls-version TLS1_2 \
    --allow-blob-public-access false \
    --allow-shared-key-access false \
    --tags purpose=terraform-state \
    --output none
fi
STORAGE_ID="$(az storage account show --name "$STORAGE_NAME" --resource-group "$STATE_RG" --query id -o tsv)"

az storage account blob-service-properties update \
  --account-name "$STORAGE_NAME" --resource-group "$STATE_RG" \
  --enable-versioning true --output none

# Management-plane create, so it works with shared keys turned off.
az storage container-rm create \
  --storage-account "$STORAGE_NAME" --resource-group "$STATE_RG" \
  --name "$STATE_CONTAINER" --public-access off --output none 2>/dev/null || true

# --- GitHub sign-in identity ------------------------------------------------
step "Creating the GitHub sign-in identity"
APP_ID="$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)"
if [[ -z "$APP_ID" ]]; then
  APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
fi
SP_OBJECT_ID="$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv)"
if [[ -z "$SP_OBJECT_ID" ]]; then
  SP_OBJECT_ID="$(az ad sp create --id "$APP_ID" --query id -o tsv)"
fi

add_federated_credential() {
  local name="$1" subject="$2"
  if az ad app federated-credential list --id "$APP_ID" --query "[?name=='$name'].name" -o tsv | grep -q .; then
    return
  fi
  az ad app federated-credential create --id "$APP_ID" --output none --parameters "{
    \"name\": \"$name\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$subject\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }"
}
# Pull requests run the plan; the production environment runs the apply.
add_federated_credential "github-pull-request" "repo:${REPO}:pull_request"
add_federated_credential "github-env-production" "repo:${REPO}:environment:production"

# --- Roles ------------------------------------------------------------------
step "Assigning roles"
SENTINEL_RG_ID="$(az group show --name "$SENTINEL_RG" --query id -o tsv)"

assign_role() {
  local role="$1" scope="$2" assignee="$3" type="$4"
  if az role assignment list --assignee "$assignee" --role "$role" --scope "$scope" --query "[0].id" -o tsv | grep -q .; then
    return
  fi
  # A brand-new service principal can take a moment to replicate.
  for attempt in 1 2 3 4 5; do
    if az role assignment create --assignee-object-id "$assignee" --assignee-principal-type "$type" \
         --role "$role" --scope "$scope" --output none 2>/dev/null; then
      return
    fi
    echo "  waiting for the identity to replicate ($attempt/5)..."
    sleep 15
  done
  echo "Could not assign '$role' on $scope" >&2
  exit 1
}

assign_role "Contributor" "$SENTINEL_RG_ID" "$SP_OBJECT_ID" ServicePrincipal
assign_role "Microsoft Sentinel Contributor" "$SENTINEL_RG_ID" "$SP_OBJECT_ID" ServicePrincipal
assign_role "Storage Blob Data Contributor" "$STORAGE_ID" "$SP_OBJECT_ID" ServicePrincipal
if [[ "$CONNECT_ACTIVITY_LOG" == "true" ]]; then
  assign_role "Monitoring Contributor" "/subscriptions/$SUBSCRIPTION_ID" "$SP_OBJECT_ID" ServicePrincipal
fi

# Lets you run terraform plan from your Mac with az login.
ME="$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)"
if [[ -n "$ME" ]]; then
  assign_role "Storage Blob Data Contributor" "$STORAGE_ID" "$ME" User
fi

# --- GitHub repository settings ---------------------------------------------
step "Saving repository variables in GitHub"
GH_DONE=false
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if gh variable set AZURE_CLIENT_ID       --repo "$REPO" --body "$APP_ID" &&
     gh variable set AZURE_TENANT_ID       --repo "$REPO" --body "$TENANT_ID" &&
     gh variable set AZURE_SUBSCRIPTION_ID --repo "$REPO" --body "$SUBSCRIPTION_ID" &&
     gh variable set TF_STATE_RG           --repo "$REPO" --body "$STATE_RG" &&
     gh variable set TF_STATE_STORAGE      --repo "$REPO" --body "$STORAGE_NAME" &&
     gh api --method PUT "repos/$REPO/environments/production" --silent; then
    GH_DONE=true
  fi
fi

cat <<EOF

Done. Repository variables:

  AZURE_CLIENT_ID       = $APP_ID
  AZURE_TENANT_ID       = $TENANT_ID
  AZURE_SUBSCRIPTION_ID = $SUBSCRIPTION_ID
  TF_STATE_RG           = $STATE_RG
  TF_STATE_STORAGE      = $STORAGE_NAME

EOF

if [[ "$GH_DONE" == "true" ]]; then
  echo "Saved these in $REPO and created the 'production' environment."
else
  echo "Could not update GitHub. Add the values above under Settings > Secrets and variables >"
  echo "Actions > Variables, and create an environment named 'production' under Settings > Environments."
fi
