output "frontend_url" {
  value = "https://${module.frontend.fqdn}"
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
