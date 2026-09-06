# Terraform state backend — one-time setup

This is **not** applied via the Terraform in `infra/modules` / `infra/env` — it
can't be. `infra/env` needs an `azurerm` remote state backend to exist *before*
`terraform init` runs against it, so the storage account holding that state has
to be created some other way first. Run this once per Azure subscription, by
hand, with `az login` already done.

There is a single environment (`infra/env`). An earlier draft assumed separate
dev/prod stacks; that was dropped — one deployment, one state file.

## 1. Create the resource group + storage account

Storage account names must be globally unique across all of Azure, lowercase
letters/numbers only, 3-24 characters.

    az group create \
      --name rg-risklens-tfstate \
      --location eastus

    az storage account create \
      --name strisklenstfstaterm3002 \
      --resource-group rg-risklens-tfstate \
      --location eastus \
      --sku Standard_LRS \
      --encryption-services blob

    az storage container create \
      --name tfstate \
      --account-name strisklenstfstaterm3002 \
      --auth-mode login

(If you pick a different account name, update `storage_account_name` in
`infra/env/backend.tf` to match.)

## 2. Register the resource providers the stack uses

One-time per subscription:

    az provider register --namespace Microsoft.CognitiveServices --wait
    az provider register --namespace Microsoft.App --wait
    az provider register --namespace Microsoft.DBforPostgreSQL --wait

## 3. Then

    cd infra/env
    terraform init
    terraform plan
    terraform apply

`infra/env/secrets.auto.tfvars` (gitignored) supplies the secret variables:
`postgres_administrator_password`, `jwt_secret`, `internal_service_api_key`,
`alpha_vantage_api_key`, `tavily_api_key`. The Azure AI Foundry key is not among
them — Terraform reads it straight off the `openai` module and writes it into
Key Vault.
