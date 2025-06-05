#!/bin/bash

# Define variables
VAULT_ADDR='http://127.0.0.1:8200'
VAULT_TOKEN='00000000-0000-0000-0000-000000000000'  # Replace with actual token
SSH_USER='user'  # Replace with the SSH user
VAULT_PATH='secret/data/ssh-password/{$SSH_USER}'  # Replace with your Vault path for the SSH password

SSH_HOST='localhost'  # Replace with the SSH host
SSH_PORT='2222'  # Replace with the SSH port (if not 22)

# Step 1: Fetch the password from Vault using curl
PASSWORD=$(curl -s --header "X-Vault-Token: $VAULT_TOKEN" \
    --request GET \
    $VAULT_ADDR/v1/$VAULT_PATH | jq -r '.data.data.password')

# Step 2: Check if the password was retrieved successfully
if [ -z "$PASSWORD" ]; then
  echo "Error: Failed to retrieve password from Vault."
  exit 1
fi

# Step 3: Use sshpass to pass the password to the SSH command
# Install sshpass if it's not already installed.
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -p $SSH_PORT $SSH_USER@$SSH_HOST

