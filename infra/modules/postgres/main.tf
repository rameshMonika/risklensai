resource "azurerm_postgresql_flexible_server" "this" {
  name                = "psql-${var.name_prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  version             = var.postgres_version

  delegated_subnet_id = var.subnet_id
  private_dns_zone_id = var.private_dns_zone_id

  administrator_login    = var.administrator_login
  administrator_password = var.administrator_password

  sku_name              = var.sku_name
  storage_mb            = var.storage_mb
  backup_retention_days = var.backup_retention_days

  # No public access at all -- reachable only from inside the VNet
  # (core-service's subnet). agent-service has no route to it, matching
  # CLAUDE.md's "no DB access" rule at the network layer, not just in code.
  public_network_access_enabled = false
  lifecycle {
    ignore_changes = [zone]
  }

}

resource "azurerm_postgresql_flexible_server_database" "this" {
  name      = var.database_name
  server_id = azurerm_postgresql_flexible_server.this.id
}
