output "resource_group_name" {
  description = "TF_STATE_RG in GitHub."
  value       = azurerm_resource_group.state.name
}

output "storage_account_name" {
  description = "TF_STATE_STORAGE in GitHub."
  value       = azurerm_storage_account.state.name
}

output "storage_account_id" {
  value = azurerm_storage_account.state.id
}

output "container_name" {
  value = azurerm_storage_container.state.name
}
