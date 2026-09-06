variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "container_app_environment_id" {
  type = string
}

variable "image" {
  type = string
}

variable "target_port" {
  type = number
}

variable "ingress_external" {
  description = "true = publicly reachable (frontend, core-service); false = internal-only within the Container Apps Environment (agent-service)."
  type        = bool
}

variable "cpu" {
  type    = number
  default = 0.25
}

variable "memory" {
  type    = string
  default = "0.5Gi"
}

variable "min_replicas" {
  type    = number
  default = 0
}

variable "max_replicas" {
  type    = number
  default = 3
}

variable "env_vars" {
  description = "Plain (non-secret) env vars: name -> value."
  type        = map(string)
  default     = {}
}

variable "secret_env_vars" {
  description = "Env vars whose value comes from a Key Vault-backed secret defined via key_vault_secret_refs: env var name -> the secret block's name (see key_vault_secret_refs)."
  type        = map(string)
  default     = {}
}

variable "key_vault_secret_refs" {
  description = "Map of this app's internal secret name -> the Key Vault secret's versionless ID (from the key_vault module's secret_ids output)."
  type        = map(string)
  default     = {}
}

variable "acr_login_server" {
  type = string
}

variable "acr_id" {
  type = string
}

variable "key_vault_id" {
  description = "Only needed if key_vault_secret_refs is non-empty -- grants this app's identity Key Vault Secrets User on it."
  type        = string
  default     = null
}

variable "location" {
  type = string
}
