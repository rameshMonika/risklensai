resource "azurerm_container_registry" "this" {
  # ACR names are alphanumeric only, no hyphens -- unlike most other Azure
  # resources here.
  name                = replace("acr${var.name_prefix}", "-", "")
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku

  # No admin username/password -- Container Apps authenticate via managed
  # identity + an AcrPull role assignment instead (see the container_app
  # module), same reasoning as avoiding stored API keys where Azure gives
  # us an identity-based alternative.
  admin_enabled = false
}
