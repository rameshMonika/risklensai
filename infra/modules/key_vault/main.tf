# Needed for the vault's tenant_id -- pulled from whoever's authenticated
# (via az login) when Terraform runs, not hardcoded.
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "this" {
  name                = "kv-${var.name_prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = var.sku_name

  # RBAC authorization, not the older access-policy list -- each Container
  # App's managed identity gets a "Key Vault Secrets User" role assignment
  # instead (wired up per-app in envs/*/main.tf, once those identities
  # exist), consistent with the AcrPull-via-identity approach in the acr
  # module rather than a stored credential.
  rbac_authorization_enabled = true
}

resource "azurerm_role_assignment" "current_user_secrets_officer" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}


resource "azurerm_key_vault_secret" "this" {
  for_each = var.secrets

  name         = each.key
  value        = each.value
  key_vault_id = azurerm_key_vault.this.id
  depends_on   = [azurerm_role_assignment.current_user_secrets_officer]

}
