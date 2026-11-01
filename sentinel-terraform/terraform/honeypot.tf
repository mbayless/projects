# A honeypot that real bots attack, feeding Sentinel's Syslog table.
# Turned on in lab.auto.tfvars. See modules/honeypot/main.tf for how it works.
module "honeypot" {
  source = "./modules/honeypot"
  count  = var.enable_honeypot ? 1 : 0

  resource_group_name = data.azurerm_resource_group.sentinel.name
  location            = data.azurerm_resource_group.sentinel.location
  workspace_id        = azurerm_log_analytics_workspace.sentinel.id
  tags                = var.tags
}

output "honeypot_public_ip" {
  description = "Bots attack this IP on port 22. Empty when the honeypot is off."
  value       = one(module.honeypot[*].public_ip)
}
