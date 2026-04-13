"""
User Service for authentication and access control.

Features:
- User CRUD operations
- Password hashing and verification (werkzeug)
- is_admin boolean for global admin access
"""

from typing import Dict, List, Optional
from werkzeug.security import generate_password_hash, check_password_hash

from database.session import SessionLocal
from database.models import User


class UserService:
    """Service for managing users and authentication."""

    def __init__(self):
        pass

    def _get_session(self):
        """Get database session."""
        return SessionLocal()

    def _hash_password(self, password: str) -> str:
        """Hash a password for storage."""
        return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        return check_password_hash(password_hash, password)

    def _user_to_dict(self, user: User) -> Dict[str, any]:
        """Convert User model to dict (excludes password_hash)."""
        return user.to_dict()

    # ── User CRUD ──

    def get_user(self, username: str) -> Optional[Dict[str, any]]:
        """Get user by username."""
        session = self._get_session()
        try:
            user = session.query(User).filter_by(username=username).first()
            return self._user_to_dict(user) if user else None
        finally:
            session.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, any]]:
        """Get user by ID."""
        session = self._get_session()
        try:
            user = session.query(User).filter_by(id=user_id).first()
            return self._user_to_dict(user) if user else None
        finally:
            session.close()

    def get_all_users(self) -> List[Dict[str, any]]:
        """Get all users."""
        session = self._get_session()
        try:
            users = session.query(User).order_by(User.created_at).all()
            return [self._user_to_dict(u) for u in users]
        finally:
            session.close()

    def create_user(
        self,
        username: str,
        password: str,
        is_admin: bool = False,
    ) -> Optional[Dict[str, any]]:
        """
        Create a new user.

        Returns user dict if created, None if username exists.
        """
        session = self._get_session()
        try:
            existing = session.query(User).filter_by(username=username).first()
            if existing:
                return None

            user = User(
                username=username,
                password_hash=self._hash_password(password),
                is_admin=is_admin,
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            return self._user_to_dict(user)
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def update_user(
        self,
        username: str,
        new_password: str = None,
        is_admin: bool = None,
    ) -> Optional[Dict[str, any]]:
        """Update user fields. Returns updated user dict or None."""
        session = self._get_session()
        try:
            user = session.query(User).filter_by(username=username).first()
            if not user:
                return None

            if new_password:
                user.password_hash = self._hash_password(new_password)
            if is_admin is not None:
                user.is_admin = is_admin

            session.commit()
            session.refresh(user)

            return self._user_to_dict(user)
        except Exception:
            session.rollback()
            return None
        finally:
            session.close()

    def delete_user(self, username: str) -> bool:
        """Delete a user. Returns True if deleted, False if not found."""
        session = self._get_session()
        try:
            user = session.query(User).filter_by(username=username).first()
            if not user:
                return False

            # Don't allow deleting yourself if only admin
            admins = session.query(User).filter_by(is_admin=True).all()
            if user.is_admin and len(admins) <= 1:
                return False  # Last admin cannot be deleted

            session.delete(user)
            session.commit()
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()

    # ── Authentication ──

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, any]]:
        """
        Authenticate user with username and password.

        Returns user dict if credentials are valid, None otherwise.
        """
        session = self._get_session()
        try:
            user = session.query(User).filter_by(username=username).first()
            if not user:
                return None
            if not self._verify_password(password, user.password_hash):
                return None

            return self._user_to_dict(user)
        finally:
            session.close()

    def has_users(self) -> bool:
        """Check if at least one user exists in database."""
        session = self._get_session()
        try:
            count = session.query(User).count()
            return count > 0
        finally:
            session.close()


# Global user service instance
user_service = UserService()
