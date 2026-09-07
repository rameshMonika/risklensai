variable "location" {
  description = "Region for the main stack (RG, network, ACR, Postgres, Key Vault, Container Apps)."
  type        = string
  default     = "centralus"
}

variable "foundry_location" {
  description = "Region for the Azure AI Foundry account. Separate from `location` because gpt-oss model availability is region-specific."
  type        = string
  default     = "eastus2"
}

variable "postgres_administrator_password" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}

variable "internal_service_api_key" {
  type      = string
  sensitive = true
}

variable "alpha_vantage_api_key" {
  type      = string
  sensitive = true
}

variable "tavily_api_key" {
  type      = string
  sensitive = true
}

variable "langsmith_api_key" {
  description = "LangSmith API key for LangGraph tracing (agent-service). Get one at https://smith.langchain.com/settings."
  type        = string
  sensitive   = true
}
