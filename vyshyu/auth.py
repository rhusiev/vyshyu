"""Verify "Sign in with Google" credentials."""

from __future__ import annotations

from collections.abc import Callable

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# Takes the credential the Google button returned, gives back the account's stable id
GoogleVerifier = Callable[[str], str]


class InvalidCredentialError(Exception):
    """Google did not vouch for the credential."""


def google_verifier(client_id: str) -> GoogleVerifier:
    """Return a verifier for ID tokens issued to this OAuth client."""
    transport = google_requests.Request()

    def verify(credential: str) -> str:
        try:
            claims = id_token.verify_oauth2_token(credential, transport, client_id)
        except ValueError as exc:
            raise InvalidCredentialError(str(exc)) from exc
        return claims["sub"]

    return verify
