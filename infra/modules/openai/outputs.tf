output "endpoint" {
  description = <<-EOT
    The OpenAI-style endpoint the app is configured against
    (https://<name>.openai.azure.com/). Constructed rather than read from
    azurerm_cognitive_account.endpoint, which returns the
    .cognitiveservices.azure.com form -- both route /openai/... paths, but the
    app + local .env were tested against this one.
  EOT
  value       = "https://${azurerm_cognitive_account.this.custom_subdomain_name}.openai.azure.com/"
}

output "primary_key" {
  value     = azurerm_cognitive_account.this.primary_access_key
  sensitive = true
}

output "deployment_name" {
  value = azurerm_cognitive_deployment.this.name
}

output "account_id" {
  value = azurerm_cognitive_account.this.id
}
