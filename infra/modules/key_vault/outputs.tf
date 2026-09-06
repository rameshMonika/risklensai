output "id" {
  value = azurerm_key_vault.this.id
}

output "uri" {
  value = azurerm_key_vault.this.vault_uri
}

output "secret_ids" {
  description = "Map of secret name -> its versionless Key Vault secret ID, for wiring into Container Apps' secret refs."
  value       = { for name, secret in azurerm_key_vault_secret.this : name => secret.versionless_id }
}
