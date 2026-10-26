#!/usr/bin/env bash
# Close Microsoft Sentinel incidents created more than N days ago.
#
# Usage: scripts/close-old-incidents.sh [--dry-run] [DAYS]
#   e.g. scripts/close-old-incidents.sh --dry-run 14    list what would be closed
#
# Optional environment variables:
#   DAYS          (default 14)
#   DRY_RUN       (default false; true only lists)
#   SENTINEL_RG   (default rg-sentinel-lab)
#   WORKSPACE     (default law-sentinel-lab)
#
# Closing keeps the incident, its alerts, entities and comments; it only leaves
# the active queue. Runs daily from .github/workflows/sentinel-close-old-incidents.yml.
# Needs az (signed in) and jq.

set -euo pipefail

DAYS="${DAYS:-14}"
DRY_RUN="${DRY_RUN:-false}"
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    ''|*[!0-9]*) echo "Usage: $0 [--dry-run] [DAYS]" >&2; exit 1 ;;
    *) DAYS="$arg" ;;
  esac
done
SENTINEL_RG="${SENTINEL_RG:-rg-sentinel-lab}"
WORKSPACE="${WORKSPACE:-law-sentinel-lab}"
API_VERSION="2024-03-01"

SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
INCIDENTS_URL="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$SENTINEL_RG/providers/Microsoft.OperationalInsights/workspaces/$WORKSPACE/providers/Microsoft.SecurityInsights/incidents"
COMMENT="Auto-closed: created more than $DAYS days ago (scripts/close-old-incidents.sh)."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# Collect every open incident older than the cutoff, following nextLink pages.
url="$INCIDENTS_URL?api-version=$API_VERSION"
: >"$tmp/old.jsonl"
while [[ -n "$url" ]]; do
  az rest --method get --url "$url" -o json >"$tmp/page.json"
  jq -c --argjson days "$DAYS" '
    .value[]
    | select(.properties.status != "Closed")
    | select((.properties.createdTimeUtc | sub("\\.[0-9]+"; "") | fromdateiso8601) < (now - $days * 86400))
  ' "$tmp/page.json" >>"$tmp/old.jsonl"
  url="$(jq -r '.nextLink // empty' "$tmp/page.json")"
done

count="$(wc -l <"$tmp/old.jsonl" | tr -d ' ')"
echo "Workspace:  $WORKSPACE ($SENTINEL_RG)"
echo "Open incidents created more than $DAYS days ago: $count"
jq -r '"  #\(.properties.incidentNumber)  \(.properties.createdTimeUtc[0:10])  \(.properties.severity)  \(.properties.title)"' \
  "$tmp/old.jsonl"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Dry run: nothing closed."
  exit 0
fi

# PUT replaces the incident, so send its current fields back with the new status.
# The etag makes the update fail, rather than overwrite, if someone changed it meanwhile.
closed=0 failed=0
while IFS= read -r incident <&3; do
  id="$(jq -r '.id' <<<"$incident")"
  number="$(jq -r '.properties.incidentNumber' <<<"$incident")"
  jq --arg comment "$COMMENT" '{
    etag,
    properties: ((.properties | {title, severity, description, owner, labels} | with_entries(select(.value != null)))
                 + {status: "Closed", classification: "Undetermined", classificationComment: $comment})
  }' <<<"$incident" >"$tmp/body.json"
  if az rest --method put --url "https://management.azure.com$id?api-version=$API_VERSION" \
       --body @"$tmp/body.json" --output none; then
    echo "  closed #$number"
    closed=$((closed + 1))
  else
    echo "  could not close #$number (error above)" >&2
    failed=$((failed + 1))
  fi
done 3<"$tmp/old.jsonl"

echo "Closed $closed, failed $failed."
[[ "$failed" -eq 0 ]]
