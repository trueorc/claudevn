"""Cognito user management service.

Provides admin operations for managing users in the Cognito User Pool:
invite, list, remove, and resend invitations.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from config import get_config

logger = logging.getLogger(__name__)

# Lazy-loaded boto3 client
_cognito_client = None


def _get_client():
    """Get or create the boto3 Cognito client."""
    global _cognito_client
    if _cognito_client is None:
        import boto3
        config = get_config().cognito
        _cognito_client = boto3.client(
            "cognito-idp",
            region_name=config.region,
        )
    return _cognito_client


def reset_client():
    """Reset the cached client (for testing)."""
    global _cognito_client
    _cognito_client = None


async def invite_user(email: str) -> dict:
    """Invite a user by email. Cognito sends them a temporary password."""
    config = get_config().cognito
    client = _get_client()

    try:
        response = client.admin_create_user(
            UserPoolId=config.user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
        user = response.get("User", {})
        return {
            "email": email,
            "status": user.get("UserStatus", "UNKNOWN"),
            "created": user.get("UserCreateDate", "").isoformat()
            if hasattr(user.get("UserCreateDate", ""), "isoformat")
            else str(user.get("UserCreateDate", "")),
        }
    except client.exceptions.UsernameExistsException:
        raise ValueError(f"User {email} already exists")
    except Exception as e:
        logger.error("Failed to invite user %s: %s", email, e)
        raise


async def list_users() -> list[dict]:
    """List all users in the Cognito User Pool."""
    config = get_config().cognito
    client = _get_client()

    users = []
    pagination_token = None

    while True:
        kwargs = {
            "UserPoolId": config.user_pool_id,
            "Limit": 60,
        }
        if pagination_token:
            kwargs["PaginationToken"] = pagination_token

        response = client.list_users(**kwargs)

        for user in response.get("Users", []):
            attrs = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
            users.append({
                "username": user["Username"],
                "email": attrs.get("email", ""),
                "status": user.get("UserStatus", "UNKNOWN"),
                "created": user.get("UserCreateDate").isoformat()
                if user.get("UserCreateDate")
                else None,
                "last_modified": user.get("UserLastModifiedDate").isoformat()
                if user.get("UserLastModifiedDate")
                else None,
                "enabled": user.get("Enabled", False),
            })

        pagination_token = response.get("PaginationToken")
        if not pagination_token:
            break

    return users


async def remove_user(username: str) -> bool:
    """Remove a user from the Cognito User Pool."""
    config = get_config().cognito
    client = _get_client()

    try:
        client.admin_delete_user(
            UserPoolId=config.user_pool_id,
            Username=username,
        )
        return True
    except client.exceptions.UserNotFoundException:
        return False
    except Exception as e:
        logger.error("Failed to remove user %s: %s", username, e)
        raise


async def resend_invite(username: str) -> dict:
    """Resend invitation email to a user with expired temporary password."""
    config = get_config().cognito
    client = _get_client()

    try:
        response = client.admin_create_user(
            UserPoolId=config.user_pool_id,
            Username=username,
            MessageAction="RESEND",
            DesiredDeliveryMediums=["EMAIL"],
        )
        user = response.get("User", {})
        return {
            "username": username,
            "status": user.get("UserStatus", "UNKNOWN"),
        }
    except client.exceptions.UserNotFoundException:
        raise ValueError(f"User {username} not found")
    except Exception as e:
        logger.error("Failed to resend invite for %s: %s", username, e)
        raise
