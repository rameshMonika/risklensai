terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 5.3"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.13"
    }
  }

  backend "azurerm" {
    resource_group_name  = "rg-risklens-tfstate"
    storage_account_name = "strisklenstfstaterm3002" # the account created in infra/bootstrap/README.md
    container_name       = "tfstate"
    key                  = "risklens.tfstate"
  }
}

provider "azurerm" {
  features {}
}
