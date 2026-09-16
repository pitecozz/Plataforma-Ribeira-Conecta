from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ribeira_platform.iam import (
    AuthContext,
    AuthenticationError,
    AuthorizationError,
    AuthorizationPolicy,
    JwtIdentityProvider,
)
from ribeira_platform.security import NetworkPolicy, SSRFBlocked


class IamAndSecurityTests(unittest.TestCase):
    def test_jwt_claims_and_invalid_token(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key().public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        )
        provider = JwtIdentityProvider(
            public_key=public_key,
            issuer="https://issuer.example",
            audience="ribeira-api",
        )
        token = jwt.encode(
            {
                "sub": "user-1",
                "tid": "tenant-a",
                "roles": ["ANALYST"],
                "iss": "https://issuer.example",
                "aud": "ribeira-api",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            private_key,
            algorithm="RS256",
        )
        context = provider.authenticate(token)
        self.assertEqual(context.subject, "user-1")
        self.assertEqual(context.tenant_id, "tenant-a")
        with self.assertRaises(AuthenticationError):
            provider.authenticate("not-a-jwt")

    def test_default_deny_and_tenant_match(self) -> None:
        policy = AuthorizationPolicy()
        context = AuthContext("user", "tenant-a", roles=frozenset({"VIEWER"}))
        policy.require(context, "property:read", tenant_id="tenant-a")
        with self.assertRaises(AuthorizationError):
            policy.require(context, "property:write", tenant_id="tenant-a")
        with self.assertRaises(AuthorizationError):
            policy.require(context, "property:read", tenant_id="tenant-b")

    def test_private_and_metadata_networks_are_blocked(self) -> None:
        policy = NetworkPolicy(
            allowed_hosts=frozenset({"127.0.0.1", "169.254.169.254"})
        )
        with self.assertRaises(SSRFBlocked):
            policy.validate("http://127.0.0.1:8080/provider")
        with self.assertRaises(SSRFBlocked):
            policy.validate("http://169.254.169.254/latest/meta-data")


if __name__ == "__main__":
    unittest.main()
