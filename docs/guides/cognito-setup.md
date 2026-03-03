# Cognito User Pool Setup Guide

This guide covers deploying and configuring the AWS Cognito User Pool for ClaudeVN UI authentication.

## Overview

ClaudeVN uses AWS Cognito for user authentication. The setup is admin-invite only — there is no self-registration. Users are invited by existing administrators and receive an email with a temporary password.

## Quick Start (Automated)

The setup script handles deployment, user creation, and docker-compose configuration in one step:

```bash
# Development setup
./scripts/setup-cognito.sh --admin-email admin@example.com

# With a specific AWS profile
./scripts/setup-cognito.sh --admin-email admin@example.com --profile personal

# Production setup
./scripts/setup-cognito.sh --admin-email admin@example.com --environment production --serving-url https://claudevn.example.com

# Preview what would happen
./scripts/setup-cognito.sh --admin-email admin@example.com --dry-run
```

After the script completes, restart docker-compose:

```bash
docker compose down && docker compose up -d
```

To revert to bypass mode (and optionally delete the Cognito stack):

```bash
# Revert to bypass and delete the Cognito stack
./scripts/teardown-cognito.sh

# Revert to bypass but keep the stack for later
./scripts/teardown-cognito.sh --keep-stack
```

## Prerequisites

- AWS CLI configured with appropriate credentials
- Permissions: `cognito-idp:*` on the target account

## Manual Setup

If you prefer to set things up manually, follow the steps below.

## Deploy the User Pool

The CloudFormation template is at `deploy/cloud/cognito-user-pool.yaml`.

### Development Pool

```bash
aws cloudformation deploy \
  --template-file deploy/cloud/cognito-user-pool.yaml \
  --stack-name claudevn-cognito-dev \
  --parameter-overrides \
    Environment=dev \
    ServingUrl=http://localhost:8002
```

### Production Pool

```bash
aws cloudformation deploy \
  --template-file deploy/cloud/cognito-user-pool.yaml \
  --stack-name claudevn-cognito-prod \
  --parameter-overrides \
    Environment=production \
    ServingUrl=https://your-domain.com
```

## Get Stack Outputs

After deployment, retrieve the values needed for serving configuration:

```bash
aws cloudformation describe-stacks \
  --stack-name claudevn-cognito-dev \
  --query 'Stacks[0].Outputs' \
  --output table
```

This returns:
- **UserPoolId** → `COGNITO_USER_POOL_ID`
- **AppClientId** → `COGNITO_APP_CLIENT_ID`
- **Region** → `COGNITO_REGION`

## Configure Serving

Configuration depends on which deployment mode you are using.

### Remote Serving Hub (`docker-compose.serving.yml`)

Copy the example file and fill in the values from the stack outputs:

```bash
cp .env.serving.example .env.serving
```

```bash
# .env.serving
AUTH_MODE=cognito
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_REGION=us-east-1
```

`AUTH_MODE` is always `cognito` in this configuration.

### Full Local Stack (`docker-compose.yml`)

The full local stack defaults to `AUTH_MODE=bypass` so no Cognito setup is required for local development. To enable Cognito, create a `.env` file in the project root:

```bash
# .env
AUTH_MODE=cognito
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_REGION=us-east-1
```

In bypass mode, all API requests are treated as authenticated with a development user.

### Non-Docker Deployments

Set the variables directly in the serving environment or in `serving/.env`:

```bash
AUTH_MODE=cognito
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_REGION=us-east-1
```

## Create the First User

After deploying the pool, create the initial admin user via AWS CLI:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username admin@example.com \
  --user-attributes '[{"Name":"email","Value":"admin@example.com"},{"Name":"email_verified","Value":"true"}]' \
  --desired-delivery-mediums EMAIL
```

The user will receive an email with a temporary password. On first login they will be prompted to set a permanent password.

## Parameters Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `Environment` | `dev` | `dev` or `production` |
| `TemporaryPasswordValidityDays` | `7` | Days before temp passwords expire |
| `AccessTokenValidityMinutes` | `60` | Access token lifetime |
| `RefreshTokenValidityDays` | `30` | Refresh token lifetime |
| `ServingUrl` | `http://localhost:8002` | URL included in invitation emails |

## Production Considerations

- The production pool enables **Advanced Security Mode** (adaptive authentication)
- **Deletion protection** is enabled for production pools
- Consider using a custom domain for the Cognito endpoints if needed
- Ensure the serving instance has AWS credentials with `cognito-idp:Admin*` permissions if user management (`COGNITO_ADMIN_ENABLED=true`) is required
