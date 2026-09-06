variable "name_prefix" {
  type = string
}

variable "account_name" {
  description = <<-EOT
    Override for the Cognitive Services account name (also used as the custom
    subdomain). Defaults to "<name_prefix>-foundry". Set this to something new
    when recreating -- Cognitive Services has a 48h soft-delete, so reusing a
    just-deleted name needs `az cognitiveservices account purge` first.
  EOT
  type        = string
  default     = null
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  description = <<-EOT
    Foundry region. Kept as its own variable, separate from the main stack's
    location, because gpt-oss model availability is region-specific -- eastus2
    carries it, centralus may not. GlobalStandard routes inference globally
    regardless of where the account lives.
  EOT
  type        = string
}

variable "deployment_name" {
  type    = string
  default = "gpt-oss-120b"
}

variable "model_name" {
  type    = string
  default = "gpt-oss-120b"
}

variable "model_version" {
  type    = string
  default = "1"
}

variable "model_format" {
  description = <<-EOT
    gpt-oss is catalogued under "OpenAI-OSS", not "OpenAI" -- confirm with
    `az cognitiveservices account list-models`.
  EOT
  type        = string
  default     = "OpenAI-OSS"
}

variable "sku_capacity" {
  description = <<-EOT
    Thousands of tokens-per-minute for the GlobalStandard deployment. This is a
    rate limit only -- GlobalStandard bills per token, so headroom costs nothing.
  EOT
  type        = number
  default     = 50
}
