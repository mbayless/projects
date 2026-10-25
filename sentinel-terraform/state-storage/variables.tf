variable "resource_group_name" {
  description = "Resource group for the Terraform state storage."
  type        = string
  default     = "rg-terraform-state"
}

variable "location" {
  description = "Azure region for the state storage."
  type        = string
  default     = "eastus"
}

variable "container_name" {
  description = "Blob container the main terraform/ folder keeps its state in. Must match versions.tf there."
  type        = string
  default     = "tfstate"
}

variable "tags" {
  description = "Tags added to every resource."
  type        = map(string)
  default = {
    project    = "sentinel-terraform"
    managed_by = "terraform"
    purpose    = "terraform-state"
  }
}
