"""User registration and authentication service."""

import hashlib
import hmac
import json
import logging
import secrets
import time
import base64
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from models.user import User, UserRole

logger = logging.getLogger(__name__)

# JWT-like token validity (7 days)
TOKEN_VALIDITY_SECONDS = 7 * 24 * 3600


class UserService:
    """Manages user registration, authentication, and sessions.

    Uses Redis for persistent storage and a simple HMAC-based token
    scheme (not full JWT to avoid heavy dependencies).
    """

    def __init__(self, redis_client=None, secret_key: Optional[str] = None):
        self._redis = redis_client
        self._secret_key = secret_key or secrets.token_hex(32)
        # In-memory user cache: {user_id: User}
        self._users: Dict[str, User] = {}
        # Username index: {username: user_id}
        self._username_index: Dict[str, str] = {}

    def _redis_key(self, user_id: str) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}user:{user_id}"

    def _username_index_key(self) -> str:
        prefix = getattr(self._redis, '_prefix', 'claudevn:') if self._redis else 'claudevn:'
        return f"{prefix}user_index:username"

    async def initialize(self) -> None:
        """Load users from Redis."""
        await self._load_from_redis()
        logger.info(f"User service initialized with {len(self._users)} user(s)")

    async def auto_provision_from_file(self, usernames: list[str]) -> int:
        """Auto-provision profiles for users from the credential file.

        Creates Redis profiles for any usernames not already registered.
        Does NOT store passwords — only creates the app-side profile.

        Args:
            usernames: List of usernames from the credential file

        Returns:
            Number of newly provisioned users
        """
        provisioned = 0
        for username in usernames:
            if username in self._username_index:
                continue

            # First user becomes owner, rest are members
            role = UserRole.OWNER if len(self._users) == 0 else UserRole.MEMBER

            user = User(
                username=username,
                role=role,
            )
            self._users[user.user_id] = user
            self._username_index[username] = user.user_id
            await self._save_user_to_redis(user)
            provisioned += 1
            logger.info(f"Auto-provisioned user '{username}' (role={role.value})")

        if provisioned > 0:
            await self._save_username_index_to_redis()

        return provisioned

    async def register(self, username: str, email: Optional[str] = None) -> tuple[User, str]:
        """Register a new user.

        First registered user automatically gets owner role.

        Args:
            username: Unique display name
            email: Optional contact email

        Returns:
            Tuple of (User, token_string)

        Raises:
            ValueError: If username is already taken
        """
        if username in self._username_index:
            raise ValueError(f"Username '{username}' is already taken")

        # First user becomes owner
        role = UserRole.OWNER if len(self._users) == 0 else UserRole.MEMBER

        user = User(
            username=username,
            email=email,
            role=role,
            last_login=datetime.now(timezone.utc),
        )

        self._users[user.user_id] = user
        self._username_index[username] = user.user_id

        await self._save_user_to_redis(user)
        await self._save_username_index_to_redis()

        token = self._create_token(user.user_id)

        logger.info(f"Registered user '{username}' (role={role.value}, id={user.user_id})")
        return user, token

    async def login(self, username: str, password: Optional[str] = None) -> tuple[User, str]:
        """Log in an existing user.

        In local auth mode, verifies password against the credential file.
        In bypass mode, password is ignored.

        Args:
            username: Display name
            password: Password (required in local auth mode)

        Returns:
            Tuple of (User, token_string)

        Raises:
            ValueError: If username not found or credentials invalid
        """
        # In local mode, verify credentials against the file
        from config import get_config
        config = get_config().cognito
        if config.auth_mode == "local":
            from services.local_auth_provider import get_local_auth_provider
            provider = get_local_auth_provider()
            if not provider:
                raise ValueError("Local auth provider not initialized")
            if not password:
                raise ValueError("Password is required in local auth mode")
            if not provider.verify(username, password):
                raise ValueError("Invalid username or password")

        user_id = self._username_index.get(username)
        if not user_id:
            raise ValueError(f"User '{username}' not found")

        user = self._users.get(user_id)
        if not user:
            raise ValueError(f"User '{username}' not found")

        user.last_login = datetime.now(timezone.utc)
        await self._save_user_to_redis(user)

        token = self._create_token(user.user_id)

        logger.info(f"User '{username}' logged in")
        return user, token

    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return self._users.get(user_id)

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        user_id = self._username_index.get(username)
        if user_id:
            return self._users.get(user_id)
        return None

    async def update_user(
        self,
        user_id: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Optional[User]:
        """Update user profile.

        Args:
            user_id: User ID
            username: New username (must be unique)
            email: New email

        Returns:
            Updated user or None if not found

        Raises:
            ValueError: If new username is taken
        """
        user = self._users.get(user_id)
        if not user:
            return None

        if username and username != user.username:
            if username in self._username_index:
                raise ValueError(f"Username '{username}' is already taken")
            # Remove old index entry
            del self._username_index[user.username]
            user.username = username
            self._username_index[username] = user_id
            await self._save_username_index_to_redis()

        if email is not None:
            user.email = email

        await self._save_user_to_redis(user)
        return user

    async def list_users(self) -> list[User]:
        """List all users."""
        return list(self._users.values())

    def is_owner(self, user_id: str) -> bool:
        """Check if user has owner role."""
        user = self._users.get(user_id)
        return user is not None and user.role == UserRole.OWNER

    def verify_token(self, token: str) -> Optional[str]:
        """Verify a session token and return the user_id.

        Args:
            token: The token string

        Returns:
            user_id if valid, None if invalid or expired
        """
        try:
            parts = token.split(".")
            if len(parts) != 2:
                return None

            payload_b64, signature = parts
            expected_sig = hmac.new(
                self._secret_key.encode(),
                payload_b64.encode(),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_sig):
                return None

            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
            if time.time() > payload.get("exp", 0):
                return None

            user_id = payload.get("sub")
            if user_id not in self._users:
                return None

            return user_id
        except Exception:
            return None

    def _create_token(self, user_id: str) -> str:
        """Create a session token for a user."""
        payload = {
            "sub": user_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + TOKEN_VALIDITY_SECONDS,
        }
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b"=").decode()

        signature = hmac.new(
            self._secret_key.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()

        return f"{payload_b64}.{signature}"

    # =========================================================================
    # Redis persistence
    # =========================================================================

    async def _save_user_to_redis(self, user: User) -> None:
        if not self._redis:
            return
        try:
            key = self._redis_key(user.user_id)
            data = user.model_dump_json()
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Failed to save user to Redis: {e}")

    async def _save_username_index_to_redis(self) -> None:
        if not self._redis:
            return
        try:
            key = self._username_index_key()
            data = json.dumps(self._username_index)
            await self._redis._redis.set(key, data)
        except Exception as e:
            logger.error(f"Failed to save username index to Redis: {e}")

    async def _load_from_redis(self) -> None:
        if not self._redis:
            return
        try:
            # Load username index
            index_key = self._username_index_key()
            index_data = await self._redis._redis.get(index_key)
            if index_data:
                raw = index_data.decode() if isinstance(index_data, bytes) else index_data
                self._username_index = json.loads(raw)

            # Load each user
            for username, user_id in self._username_index.items():
                user_key = self._redis_key(user_id)
                user_data = await self._redis._redis.get(user_key)
                if user_data:
                    raw = user_data.decode() if isinstance(user_data, bytes) else user_data
                    user = User.model_validate_json(raw)
                    self._users[user.user_id] = user

            logger.info(f"Loaded {len(self._users)} user(s) from Redis")
        except Exception as e:
            logger.warning(f"Failed to load users from Redis: {e}")


# Module-level singleton
_user_service: Optional[UserService] = None


def get_user_service() -> Optional[UserService]:
    """Get the global user service instance."""
    return _user_service


def set_user_service(service: Optional[UserService]) -> None:
    """Set the global user service instance."""
    global _user_service
    _user_service = service
