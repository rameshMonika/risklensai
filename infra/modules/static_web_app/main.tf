# The React SPA is static -- a CDN-fronted host, not a container. Azure Static
# Web Apps gives managed TLS, a global edge, SPA fallback routing (via
# frontend/public/staticwebapp.config.json), and a deployment token for CI.
#
# The resource is created empty; it serves a placeholder until the first
# `swa deploy ./dist --deployment-token <api_key>` uploads the build. That
# deploy is a manual step for now and a GitLab CI job later -- it does NOT
# run from Terraform.

resource "azurerm_static_web_app" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = var.sku_tier
  sku_size            = var.sku_tier
}
