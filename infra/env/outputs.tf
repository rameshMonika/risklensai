output "frontend_url" {
  value = module.frontend.url
}

output "frontend_deploy_token" {
  description = "Static Web Apps deployment token for `swa deploy` / GitLab CI."
  value       = module.frontend.api_key
  sensitive   = true
}

output "core_service_url" {
  value = "https://${module.core_service.fqdn}"
}

output "acr_login_server" {
  value = module.acr.login_server
}

output "foundry_endpoint" {
  value = module.openai.endpoint
}
