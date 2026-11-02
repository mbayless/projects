# Re-adopt resources that exist in Azure but are missing from the shared state.
#
# Why: the first pipeline applies (2026-10-25) saved state in the old storage account
# sttfstateir60x19h. Renaming the state storage deleted that account and the state
# with it, so Terraform no longer knew it owned these. An import block tells Terraform
# "this already exists, take it over" instead of trying to create it again.
#
# After the next successful apply these are all in the state again, and these blocks
# do nothing. Delete this file in a later pull request.

locals {
  workspace_import_id = "${data.azurerm_resource_group.sentinel.id}/providers/Microsoft.OperationalInsights/workspaces/${var.workspace_name}"
}

import {
  to = azurerm_log_analytics_workspace.sentinel
  id = local.workspace_import_id
}

import {
  to = azurerm_sentinel_log_analytics_workspace_onboarding.sentinel
  id = "${local.workspace_import_id}/providers/Microsoft.SecurityInsights/onboardingStates/default"
}

import {
  to = azurerm_monitor_diagnostic_setting.activity_log[0]
  id = "/subscriptions/${data.azurerm_client_config.current.subscription_id}|send-activity-log-to-sentinel"
}

import {
  for_each = toset(["mass-resource-deletion", "role-assignment-created"])
  to       = azurerm_sentinel_alert_rule_scheduled.rule[each.key]
  id       = "${local.workspace_import_id}/providers/Microsoft.SecurityInsights/alertRules/${each.key}"
}

# Added 2026-11-01: the first apply showed this rule also already exists.
import {
  to = azurerm_sentinel_alert_rule_nrt.rule["nsg-rule-changed"]
  id = "${local.workspace_import_id}/providers/Microsoft.SecurityInsights/alertRules/nsg-rule-changed"
}
