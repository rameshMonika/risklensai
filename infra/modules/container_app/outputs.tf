output "fqdn" {
  value = azurerm_container_app.this.ingress[0].fqdn
}

output "principal_id" {
  value = azurerm_user_assigned_identity.this.principal_id
}

