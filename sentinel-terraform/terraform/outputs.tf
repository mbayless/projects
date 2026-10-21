output "workspace_name" {
  value = azurerm_log_analytics_workspace.sentinel.name
}

output "workspace_id" {
  value = azurerm_log_analytics_workspace.sentinel.id
}

output "analytics_rules" {
  description = "Rule id => display name for every rule deployed from rules/."
  value = merge(
    { for id, r in azurerm_sentinel_alert_rule_scheduled.rule : id => "${r.display_name} (scheduled)" },
    { for id, r in azurerm_sentinel_alert_rule_nrt.rule : id => "${r.display_name} (NRT)" },
  )
}
