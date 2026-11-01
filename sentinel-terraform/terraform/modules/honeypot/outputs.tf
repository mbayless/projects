output "public_ip" {
  description = "The honeypot's public IP. Bots attack it on port 22."
  value       = azurerm_public_ip.honeypot.ip_address
}

output "vm_name" {
  value = azurerm_linux_virtual_machine.honeypot.name
}
