# Settings for this lab. Terraform loads *.auto.tfvars files automatically,
# locally and in GitHub Actions.

# The Cowrie honeypot VM: open to the internet on port 22, shuts down at 11 pm Eastern.
# Set to false (and open a pull request) to delete it.
enable_honeypot = true
