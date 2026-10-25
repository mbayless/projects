terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # No backend block: this folder keeps its state in a local file
  # (state-storage/terraform.tfstate). It creates the storage account that the
  # main terraform/ folder keeps its state in, so it can't use that storage itself.
}

provider "azurerm" {
  features {}

  # The storage account has shared keys turned off, so sign in with your
  # az login session for anything inside it.
  storage_use_azuread = true
}
