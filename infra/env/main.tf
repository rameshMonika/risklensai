locals {
  name_prefix = "risklens"
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name_prefix}"
  location = var.location
}

module "network" {
  source = "../modules/network"

  name_prefix         = local.name_prefix
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
}

module "acr" {
  source = "../modules/acr"

  name_prefix         = local.name_prefix
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
}


module "postgres" {
  source = "../modules/postgres"

  name_prefix         = local.name_prefix
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location

  subnet_id              = module.network.postgres_subnet_id
  private_dns_zone_id    = module.network.postgres_private_dns_zone_id
  administrator_password = var.postgres_administrator_password

  # See infra/modules/postgres/main.tf's comment -- the DNS zone's *link* to
  # the VNet (a separate resource inside module.network) must exist before
  # this server can be created, and Terraform can't infer that ordering from
  # the zone ID reference alone.
  depends_on = [module.network]
}

# Azure AI Foundry. Its own region variable -- gpt-oss model availability is
# region-specific, so the account can sit in a different region than the rest
# of the stack (GlobalStandard routes inference globally anyway).
#
# account_name is "risklens-ai-foundry", NOT the old manually-created
# "risklens-foundry" (which lives in the now-destroyed rg-risklens-dev).
# Cognitive Services soft-deletes for 48h, so a fresh name avoids an
# `az cognitiveservices account purge` before this can apply.
module "openai" {
  source = "../modules/openai"

  name_prefix         = local.name_prefix
  account_name        = "risklens-ai-foundry"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.foundry_location
}

module "key_vault" {
  source = "../modules/key_vault"

  # Deliberately NOT the old "risklens-dev-rm3002" -- Key Vault soft-delete
  # would block recreating a vault with a name that was destroyed in the last
  # 90 days without an `az keyvault purge` first. A fresh name sidesteps it.
  name_prefix         = "${local.name_prefix}-rm7"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location

  secrets = {
    "jwt-secret"               = var.jwt_secret
    "internal-service-api-key" = var.internal_service_api_key
    "alpha-vantage-api-key"    = var.alpha_vantage_api_key
    "tavily-api-key"           = var.tavily_api_key
    "azure-openai-api-key"     = module.openai.primary_key
    "database-url"             = "postgresql+psycopg2://${module.postgres.administrator_login}:${urlencode(var.postgres_administrator_password)}@${module.postgres.fqdn}:5432/${module.postgres.database_name}?sslmode=require"
  }
}

module "container_apps_env" {
  source = "../modules/container_apps_env"

  name_prefix              = local.name_prefix
  resource_group_name      = azurerm_resource_group.this.name
  location                 = var.location
  infrastructure_subnet_id = module.network.aca_subnet_id
}


module "frontend" {
  source = "../modules/container_app"

  name                         = "frontend"
  resource_group_name          = azurerm_resource_group.this.name
  location                     = var.location
  container_app_environment_id = module.container_apps_env.id
  acr_login_server             = module.acr.login_server
  acr_id                       = module.acr.id

  image            = "${module.acr.login_server}/risklens-frontend:latest"
  target_port      = 80
  ingress_external = true
}

module "core_service" {
  source = "../modules/container_app"

  name                         = "core-service"
  resource_group_name          = azurerm_resource_group.this.name
  container_app_environment_id = module.container_apps_env.id
  location                     = var.location
  acr_login_server             = module.acr.login_server
  acr_id                       = module.acr.id

  image            = "${module.acr.login_server}/risklens-core-service:latest"
  target_port      = 8000
  ingress_external = true

  env_vars = {
    CORS_ORIGINS      = "[\"https://${module.frontend.fqdn}\"]"
    AGENT_SERVICE_URL = "https://${module.agent_service.fqdn}"
  }

  key_vault_id = module.key_vault.id
  key_vault_secret_refs = {
    "database-url"             = module.key_vault.secret_ids["database-url"]
    "jwt-secret"               = module.key_vault.secret_ids["jwt-secret"]
    "internal-service-api-key" = module.key_vault.secret_ids["internal-service-api-key"]
    "alpha-vantage-api-key"    = module.key_vault.secret_ids["alpha-vantage-api-key"]
  }
  secret_env_vars = {
    DATABASE_URL             = "database-url"
    JWT_SECRET               = "jwt-secret"
    INTERNAL_SERVICE_API_KEY = "internal-service-api-key"
    ALPHA_VANTAGE_API_KEY    = "alpha-vantage-api-key"
  }
}

module "agent_service" {
  source = "../modules/container_app"

  name                         = "agent-service"
  resource_group_name          = azurerm_resource_group.this.name
  location                     = var.location
  container_app_environment_id = module.container_apps_env.id
  acr_login_server             = module.acr.login_server
  acr_id                       = module.acr.id

  image            = "${module.acr.login_server}/risklens-agent-service:latest"
  target_port      = 8100
  ingress_external = false

  # The other apps run fine on the module defaults (0.25 vCPU / 0.5Gi). This
  # one loads PyTorch + a sentence-transformers model for the semantic router:
  # 0.5Gi OOMKills it during model load, and 0.25 vCPU makes the load slow.
  # min_replicas 1 keeps it warm -- with 0, the first request after a
  # scale-to-zero cold-starts torch (~40-60s) and core's HTTP call times out
  # ("Agent service unreachable").
  cpu          = 1.0
  memory       = "2Gi"
  min_replicas = 1

  env_vars = {
    LLM_PROVIDER             = "azure"
    AZURE_OPENAI_ENDPOINT    = module.openai.endpoint
    AZURE_OPENAI_DEPLOYMENT  = module.openai.deployment_name
    AZURE_OPENAI_API_VERSION = "2024-10-21"
  }

  key_vault_id = module.key_vault.id
  key_vault_secret_refs = {
    "internal-service-api-key" = module.key_vault.secret_ids["internal-service-api-key"]
    "tavily-api-key"           = module.key_vault.secret_ids["tavily-api-key"]
    "azure-openai-api-key"     = module.key_vault.secret_ids["azure-openai-api-key"]
  }
  secret_env_vars = {
    INTERNAL_SERVICE_API_KEY = "internal-service-api-key"
    TAVILY_API_KEY           = "tavily-api-key"
    AZURE_OPENAI_API_KEY     = "azure-openai-api-key"
  }
}
