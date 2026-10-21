variable "resource_group_name" {
  description = "Resource group for the Sentinel workspace. Created by bootstrap/setup.sh."
  type        = string
  default     = "rg-sentinel-lab"
}

variable "workspace_name" {
  description = "Name of the Log Analytics workspace that Sentinel runs on."
  type        = string
  default     = "law-sentinel-lab"
}

variable "retention_in_days" {
  description = "Log retention. The first 90 days are included with Sentinel."
  type        = number
  default     = 90
}

variable "connect_activity_log" {
  description = "Send the subscription Activity log to the workspace. Needs Monitoring Contributor on the subscription."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default = {
    project    = "sentinel-terraform"
    managed_by = "terraform"
  }
}
