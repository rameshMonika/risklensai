variable "name_prefix" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "subnet_id" {
  description = "The delegated Postgres subnet from the network module."
  type        = string
}

variable "private_dns_zone_id" {
  description = "The private DNS zone from the network module, linked to the same VNet."
  type        = string
}

variable "administrator_login" {
  type    = string
  default = "risklensadmin"
}

variable "administrator_password" {
  type = string
}

variable "postgres_version" {
  type    = string
  default = "16"
}

variable "sku_name" {
  description = "Burstable B1ms is enough at this project's scale; override for more."
  type        = string
  default     = "B_Standard_B1ms"
}

variable "storage_mb" {
  type    = number
  default = 32768
}

variable "backup_retention_days" {
  type    = number
  default = 7
}

variable "database_name" {
  type    = string
  default = "risklens"
}
