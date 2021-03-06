"""Data models required by the auth module"""
import uuid
import secrets
from datetime import datetime, timedelta

from typing import (
    Optional,
    Dict,
    Any
)
from attr import attrs, attrib

# pylint: disable=too-few-public-methods


@attrs(slots=True)
class AccessToken:
    """Represents the access token"""
    token: str = attrib()
    expiration: datetime = attrib()


@attrs(slots=True)
class RefreshToken:
    """Represents the refresh token"""
    client_id: Optional[str] = attrib()
    client_name: Optional[str] = attrib()
    user: Optional["User"] = attrib()
    access_token_expiration: timedelta = attrib()
    token: str = attrib(factory=lambda: secrets.token_hex(64))
    id: str = attrib(factory=lambda: uuid.uuid4().hex)
    jwt_key: str = attrib(factory=lambda: secrets.token_hex(64))


@attrs(slots=True)
class AuthorizationCode:
    """Represents the authorization code"""
    access_token_expiration: timedelta = attrib()
    client_id: Optional[str] = attrib()
    state: Optional[str] = attrib()
    user: Optional["User"] = attrib()
    expiration: Optional[datetime] = attrib(default=timedelta(seconds=60))
    creation_date: datetime = attrib(factory=datetime.now)
    code: str = attrib(factory=lambda: secrets.token_hex(64))

    @property
    def expired(self) -> bool:
        """Returns whether the authorization code is expired"""
        return datetime.now() > self.creation_date + self.expiration


@attrs(slots=True)
class User:
    """Represents a user"""
    name: Optional[str] = attrib()
    owner: bool = attrib(default=False)
    salted_password: str = attrib(default=None)
    credentials: Dict[str, "Credentials"] = attrib(default={})
    system_generated: bool = attrib(default=False)
    id: str = attrib(factory=lambda: uuid.uuid4().hex)


@attrs(slots=True)
class Credentials:
    """Represents credentials"""
    user: User = attrib()
    provider: str = attrib()
    data: Any = attrib()
    credential_id: Optional[str] = attrib(factory=lambda: uuid.uuid4().hex)
