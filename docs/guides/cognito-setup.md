# Cognito User Pool Setup Guide

This guide covers deploying and configuring the AWS Cognito User Pool for ClaudeVN UI authentication.

## Overview

ClaudeVN uses AWS Cognito for user authentication. The setup is admin-invite only — there is no self-registration. Users are invited by existing administrators and receive an email with a temporary password.

## Prerequisites

- AWS CLI configured with appropriate credentials
- Permissions: `cognito-idp:*` on the target account

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

Set these environment variables in your serving `.env` file:

```bash
AUTH_MODE=cognito
COGNITO_USER_POOL_ID=us-east-1_xxxxxxxxx
COGNITO_APP_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
COGNITO_REGION=us-east-1
```

For local development without Cognito:

```bash
AUTH_MODE=bypass
```

In bypass mode, all API requests are treated as authenticated with a development user. No Cognito configuration is required.

## Create the First User

After deploying the pool, create the initial admin user via AWS CLI:

```bash
aws cognito-idp admin-create-user \
  --user-pool-id us-east-1_xxxxxxxxx \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com Name=email_verified,Value=true \
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
