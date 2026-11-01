# A honeypot: a small VM whose only open port is a fake SSH server (Cowrie).
# Bots find it within minutes. Every login attempt and command they type goes to
# Sentinel as a Syslog event (facility local0, process "cowrie", message = Cowrie's JSON).
#
#   internet ──:22──▶ Cowrie (Docker) ──JSON──▶ logger ──syslog──▶ Azure Monitor Agent ──▶ Sentinel

locals {
  tags = merge(var.tags, { role = "honeypot" })
}

# --- Network: its own VNet, so nothing else is reachable from it -----------------

resource "azurerm_virtual_network" "honeypot" {
  name                = "vnet-honeypot"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = ["10.50.0.0/24"]
  tags                = local.tags
}

resource "azurerm_subnet" "honeypot" {
  name                 = "snet-honeypot"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.honeypot.name
  address_prefixes     = ["10.50.0.0/26"]
}

# Only port 22 (Cowrie) is open. The real SSH server listens on 22222, which the
# default rules block, so it can't be reached from the internet.
resource "azurerm_network_security_group" "honeypot" {
  name                = "nsg-honeypot"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = local.tags

  security_rule {
    name                       = "allow-fake-ssh-from-internet"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "honeypot" {
  subnet_id                 = azurerm_subnet.honeypot.id
  network_security_group_id = azurerm_network_security_group.honeypot.id
}

resource "azurerm_public_ip" "honeypot" {
  name                = "pip-honeypot"
  location            = var.location
  resource_group_name = var.resource_group_name
  allocation_method   = "Static"
  sku                 = "Standard"
  tags                = local.tags
}

resource "azurerm_network_interface" "honeypot" {
  name                = "nic-honeypot"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = local.tags

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.honeypot.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.honeypot.id
  }
}

# --- The VM -------------------------------------------------------------------

# Azure requires an SSH key. Nobody logs in with it (the real SSH isn't reachable);
# use "az vm run-command" to look inside.
resource "tls_private_key" "admin" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "azurerm_linux_virtual_machine" "honeypot" {
  name                  = "vm-honeypot"
  location              = var.location
  resource_group_name   = var.resource_group_name
  size                  = var.vm_size
  admin_username        = "azureuser"
  network_interface_ids = [azurerm_network_interface.honeypot.id]
  tags                  = local.tags

  admin_ssh_key {
    username   = "azureuser"
    public_key = tls_private_key.admin.public_key_openssh
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  # The Azure Monitor Agent signs in to Azure with this identity.
  identity {
    type = "SystemAssigned"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    cowrie_image  = var.cowrie_image
    fake_hostname = var.fake_hostname
  }))
}

resource "azurerm_dev_test_global_vm_shutdown_schedule" "nightly" {
  count = var.shutdown_time == null ? 0 : 1

  virtual_machine_id    = azurerm_linux_virtual_machine.honeypot.id
  location              = var.location
  enabled               = true
  daily_recurrence_time = var.shutdown_time
  timezone              = var.shutdown_timezone
  tags                  = local.tags

  notification_settings {
    enabled = false
  }
}

# --- Logs to Sentinel -----------------------------------------------------------

resource "azurerm_virtual_machine_extension" "ama" {
  name                       = "AzureMonitorLinuxAgent"
  virtual_machine_id         = azurerm_linux_virtual_machine.honeypot.id
  publisher                  = "Microsoft.Azure.Monitor"
  type                       = "AzureMonitorLinuxAgent"
  type_handler_version       = "1.0"
  auto_upgrade_minor_version = true
  automatic_upgrade_enabled  = true
  tags                       = local.tags
}

# Collect syslog facility local0 (only Cowrie writes there) into the Syslog table.
resource "azurerm_monitor_data_collection_rule" "cowrie" {
  name                = "dcr-honeypot-cowrie"
  location            = var.location
  resource_group_name = var.resource_group_name
  kind                = "Linux"
  description         = "Cowrie honeypot events (syslog local0) to the Sentinel workspace."
  tags                = local.tags

  destinations {
    log_analytics {
      name                  = "sentinel"
      workspace_resource_id = var.workspace_id
    }
  }

  data_flow {
    streams      = ["Microsoft-Syslog"]
    destinations = ["sentinel"]
  }

  data_sources {
    syslog {
      name           = "cowrie"
      facility_names = ["local0"]
      log_levels     = ["Info", "Notice", "Warning", "Error", "Critical", "Alert", "Emergency"]
      streams        = ["Microsoft-Syslog"]
    }
  }
}

resource "azurerm_monitor_data_collection_rule_association" "cowrie" {
  name                    = "cowrie-to-sentinel"
  target_resource_id      = azurerm_linux_virtual_machine.honeypot.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.cowrie.id
}
