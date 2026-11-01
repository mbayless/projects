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
  description = "VM size. B1ms (1 vCPU, 2 GB) runs Cowrie and the Azure Monitor Agent comfortably."
  type        = string
  default     = "Standard_B1ms"
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
