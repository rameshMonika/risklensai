variable "name_prefix" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "infrastructure_subnet_id" {
  description = "The ACA subnet from the network module."
  type        = string
}
