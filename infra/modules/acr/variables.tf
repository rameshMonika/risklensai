variable "name_prefix" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "sku" {
  description = "Basic is enough for 2 low-traffic images at this project's scale."
  type        = string
  default     = "Basic"
}
