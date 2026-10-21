terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # resource_group_name and storage_account_name are passed with -backend-config.
  # Authentication comes from the environment: ARM_USE_OIDC in GitHub Actions,
  # your az login session on your Mac.
  backend "azurerm" {
    container_name   = "tfstate"
    key              = "sentinel.tfstate"
    use_azuread_auth = true
  }
}

provider "azurerm" {
  features {}

  # The bootstrap script registers the providers we need. The pipeline
  # identity has no subscription-wide rights to register them itself.
  resource_provider_registrations = "none"
  storage_use_azuread             = true
}
