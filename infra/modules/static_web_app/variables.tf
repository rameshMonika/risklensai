variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  description = <<-EOT
    Azure Static Web Apps is only offered in a handful of regions:
    westus2, centralus, eastus2, westeurope, eastasia. The main stack's
    centralus is fine.
  EOT
  type        = string
}

variable "sku_tier" {
  description = "Free covers a single-maintainer project (100 GB/mo egress, custom domains, no SLA). Standard adds SLA + BYO backends + more."
  type        = string
  default     = "Free"
}
