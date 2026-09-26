variable "project_id" {
  type    = string
  default = "sso-lab-demo"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "github_repository" {
  description = "owner/name of the repo allowed to deploy."
  type        = string
  default     = "jwjjj1983/sso-lab"
}

variable "github_repository_id" {
  description = "Numeric GitHub repo id. Trusting the id (not just the name) means a deleted-and-recreated repo with the same name cannot deploy."
  type        = string
  default     = "1389697044"
}

variable "initial_image" {
  description = "Image for the very first apply, before CI has pushed one. CI owns the image afterwards."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "max_instances" {
  description = "Hard cap per service: bounds cost and abuse on a public demo."
  type        = number
  default     = 3
}
