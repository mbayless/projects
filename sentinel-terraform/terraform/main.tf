data "azurerm_client_config" "current" {}

# Created by bootstrap/setup.sh so the pipeline only needs rights on this group.
data "azurerm_resource_group" "sentinel" {
  name = var.resource_group_name
}

resource "azurerm_log_analytics_workspace" "sentinel" {
  name                = var.workspace_name
  location            = data.azurerm_resource_group.sentinel.location
  resource_group_name = data.azurerm_resource_group.sentinel.name
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_in_days
  tags                = var.tags
}

resource "azurerm_sentinel_log_analytics_workspace_onboarding" "sentinel" {
  workspace_id = azurerm_log_analytics_workspace.sentinel.id
}

# Fills the AzureActivity table that the sample rules query.
resource "azurerm_monitor_diagnostic_setting" "activity_log" {
  count = var.connect_activity_log ? 1 : 0

  name                       = "send-activity-log-to-sentinel"
  target_resource_id         = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.sentinel.id

  dynamic "enabled_log" {
    for_each = toset([
      "Administrative",
      "Security",
      "ServiceHealth",
      "Alert",
      "Recommendation",
      "Policy",
      "Autoscale",
      "ResourceHealth",
    ])
    content {
      category = enabled_log.value
    }
  }
}
