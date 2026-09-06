variable "name_prefix" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "sku_name" {
  type    = string
  default = "standard"
}

variable "secrets" {
  description = "Map of secret name -> value to create in this vault. Real values belong in an untracked *.auto.tfvars file or a TF_VAR_secrets env var -- never committed to git."
  type        = map(string)
  default     = {}
}
