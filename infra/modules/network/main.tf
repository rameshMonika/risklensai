resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.name_prefix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  address_space       = [var.address_space]
}

# Delegated to Microsoft.App/environments -- this is what lets the Container
# Apps Environment (agent-service's internal-only ingress lives here, see
# infra/modules/container_apps_env) sit inside this VNet at all.
resource "azurerm_subnet" "aca" {
  name                 = "snet-aca-${var.name_prefix}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.aca_subnet_prefix]

  delegation {
    name = "aca-delegation"
    service_delegation {
      name    = "Microsoft.App/environments"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Delegated to Microsoft.DBforPostgreSQL/flexibleServers -- Postgres Flexible
# Server's VNet-integrated mode (public network access disabled, see
# infra/modules/postgres) requires its own delegated subnet, separate from
# the Container Apps one above.
resource "azurerm_subnet" "postgres" {
  name                 = "snet-postgres-${var.name_prefix}"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.postgres_subnet_prefix]

  delegation {
    name = "postgres-delegation"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Postgres Flexible Server's VNet integration requires a private DNS zone
# linked to this VNet -- without it, core-service would have no way to
# resolve the server's private hostname.
resource "azurerm_private_dns_zone" "postgres" {
  name                = "privatelink.postgres.database.azure.com"
  resource_group_name = var.resource_group_name
}

resource "azurerm_private_dns_zone_virtual_network_link" "postgres" {
  name                = "pdnslink-postgres-${var.name_prefix}"
  private_dns_zone_id = azurerm_private_dns_zone.postgres.id
  virtual_network_id  = azurerm_virtual_network.this.id
}

