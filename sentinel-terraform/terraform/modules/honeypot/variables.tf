variable "resource_group_name" {
  description = "Resource group for the honeypot."
  type        = string
}

variable "location" {
  description = "Azure region."
  type        = string
}

variable "workspace_id" {
  description = "Resource ID of the Log Analytics workspace Sentinel runs on. Cowrie events go here."
  type        = string
}

variable "vm_size" {
  description = "VM size. B-series sizes are blocked for this subscription in eastus (2026-11-01), so D2as_v4 (2 vCPU, 8 GB)."
  type        = string
  default     = "Standard_D2as_v4"
}

variable "cowrie_image" {
  description = "Cowrie container image. Pinned so a new release can't change the log format by surprise."
  type        = string
  default     = "cowrie/cowrie:3.1.2"
}

variable "fake_hostname" {
  description = "Hostname the fake shell shows to attackers."
  type        = string
  default     = "web-prod-02"
}

variable "shutdown_time" {
  description = "Daily shutdown time, HHMM (24 h). null keeps the VM running around the clock."
  type        = string
  default     = "2300"
}

variable "shutdown_timezone" {
  description = "Windows time zone name for shutdown_time."
  type        = string
  default     = "Eastern Standard Time"
}

variable "tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default     = {}
}
