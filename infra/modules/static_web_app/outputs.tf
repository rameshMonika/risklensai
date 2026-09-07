output "default_host_name" {
  value = azurerm_static_web_app.this.default_host_name
}

output "url" {
  value = "https://${azurerm_static_web_app.this.default_host_name}"
}

output "api_key" {
  description = "Deployment token -- pass to `swa deploy --deployment-token` (locally or as a masked GitLab CI variable)."
  value       = azurerm_static_web_app.this.api_key
  sensitive   = true
}
