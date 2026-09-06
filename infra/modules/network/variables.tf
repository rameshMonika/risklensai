variable "name_prefix" {
  description = "Prefix for all resource names in this module, e.g. \"risklens\"."
  type        = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "address_space" {
  description = "VNet address space."
  type        = string
  default     = "10.0.0.0/16"
}

variable "aca_subnet_prefix" {
  description = "Subnet for the Container Apps Environment. Azure requires /23 or larger for the Consumption + Dedicated workload profile plan."
  type        = string
  default     = "10.0.0.0/23"
}

variable "postgres_subnet_prefix" {
  description = "Delegated subnet for Postgres Flexible Server's VNet integration."
  type        = string
  default     = "10.0.2.0/24"
}
