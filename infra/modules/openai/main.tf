# Azure AI Foundry: an AIServices account plus a serverless (GlobalStandard,
# pay-per-token) deployment of OpenAI's gpt-oss-120b. The agent service's
# guardrail + Answer/Report nodes call this instead of Groq once
# LLM_PROVIDER=azure (see agent_service/src/agent_service/core/llm.py).
#
# gpt-oss-20b has no serverless SKU on Azure (managed-compute GPU only), which
# is why prod uses 120b -- same OpenAI open-weight family, same Chat
# Completions + function-calling + structured-output support.

locals {
  account_name = coalesce(var.account_name, "${var.name_prefix}-foundry")
}

resource "azurerm_cognitive_account" "this" {
  name                = local.account_name
  resource_group_name = var.resource_group_name
  location            = var.location
  kind                = "AIServices"
  sku_name            = "S0"

  # A custom subdomain is what makes the token-authenticated
  # https://<name>.openai.azure.com/ endpoint work (and is required for
  # AAD auth / most Foundry features).
  custom_subdomain_name = local.account_name
}

resource "azurerm_cognitive_deployment" "this" {
  name                 = var.deployment_name
  cognitive_account_id = azurerm_cognitive_account.this.id

  model {
    format  = var.model_format
    name    = var.model_name
    version = var.model_version
  }

  sku {
    name     = "GlobalStandard"
    capacity = var.sku_capacity
  }
}
