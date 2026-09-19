from __future__ import annotations

import unittest
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

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
from ribeira_platform.api import Settings
from ribeira_platform.security import NetworkPolicy, SSRFBlocked


class IamAndSecurityTests(unittest.TestCase):
    @staticmethod
    def _oidc_token(
        private_key,
        *,
        kid: str = "rotation-a",
        omit_exp: bool = False,
        omit_iat: bool = False,
        omit_nbf: bool = False,
        omit_sub: bool = False,
        **claims: object,
    ) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, object] = {
            "sub": "user-1",
            "iss": "https://issuer.example",
            "aud": "ribeira-api",
            "iat": now,
            "nbf": now - timedelta(seconds=10),
            "exp": now + timedelta(minutes=5),
        }
        for claim, omit in {
            "exp": omit_exp,
            "iat": omit_iat,
            "nbf": omit_nbf,
            "sub": omit_sub,
        }.items():
            if omit:
                payload.pop(claim)
        payload.update(claims)
        return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})

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
                "nbf": datetime.now(timezone.utc) - timedelta(seconds=10),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            private_key,
            algorithm="RS256",
        )
        context = provider.authenticate(token)
        self.assertEqual(context.subject, "user-1")
        # OIDC proves identity only. Tenant and role claims cannot grant
        # application authority without a local active membership.
        self.assertIsNone(context.tenant_id)
        self.assertEqual(context.roles, frozenset())
        self.assertEqual(context.issuer, "https://issuer.example")
        with self.assertRaises(AuthenticationError):
            provider.authenticate("not-a-jwt")

    def test_jwks_rotation_cache_and_unknown_key_are_explicit(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
        jwk["kid"] = "rotation-a"

        class Response:
            def read(self) -> bytes:
                return json.dumps({"keys": [jwk]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_: object) -> None:
                return None

        provider = JwtIdentityProvider(
            jwks_url="https://issuer.example/jwks",
            issuer="https://issuer.example",
            audience="ribeira-api",
            jwks_refresh_seconds=0,
        )
        token = self._oidc_token(private_key)
        with patch("ribeira_platform.iam.urlopen", return_value=Response()):
            self.assertEqual(provider.authenticate(token).subject, "user-1")
        # A temporary IdP failure does not invalidate a token whose signing key
        # is still cached inside the configured TTL.
        with patch("ribeira_platform.iam.urlopen", side_effect=OSError("offline")):
            self.assertEqual(
                provider.authenticate(token).issuer, "https://issuer.example"
            )
            with self.assertRaises(AuthenticationError):
                provider.authenticate(self._oidc_token(private_key, kid="unknown"))

    def test_oidc_rejects_wrong_issuer_audience_expiry_and_signature(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
        provider = JwtIdentityProvider(
            public_key=public_key,
            issuer="https://issuer.example",
            audience="ribeira-api",
        )
        invalid = (
            self._oidc_token(private_key, iss="https://wrong.example"),
            self._oidc_token(private_key, aud="wrong-audience"),
            self._oidc_token(
                private_key, exp=datetime.now(timezone.utc) - timedelta(seconds=1)
            ),
        )
        for token in invalid:
            with self.assertRaises(AuthenticationError):
                provider.authenticate(token)
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(AuthenticationError):
            provider.authenticate(self._oidc_token(other_key))

    def test_oidc_audience_array_and_claim_failures_are_verified(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
        provider = JwtIdentityProvider(
            public_key=public_key,
            issuer="https://issuer.example",
            audience="ribeira-api",
        )
        now = datetime.now(timezone.utc)

        self.assertEqual(
            provider.authenticate(
                self._oidc_token(
                    private_key,
                    aud=["ribeira-api", "https://issuer.example/userinfo"],
                )
            ).subject,
            "user-1",
        )
        self.assertEqual(
            provider.authenticate(
                self._oidc_token(private_key, aud="ribeira-api")
            ).subject,
            "user-1",
        )

        invalid_claims = (
            (
                ["https://other.example", "https://issuer.example/userinfo"],
                "JWT_AUDIENCE_INVALID",
            ),
            ("https://other.example", "JWT_AUDIENCE_INVALID"),
            ([], "JWT_AUDIENCE_INVALID"),
            ({"unexpected": "value"}, "JWT_AUDIENCE_INVALID"),
        )
        for audience, failure_code in invalid_claims:
            with self.assertRaisesRegex(
                AuthenticationError, "invalid bearer token"
            ) as caught:
                provider.authenticate(self._oidc_token(private_key, aud=audience))
            self.assertEqual(caught.exception.failure_code, failure_code)

        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        invalid_tokens = (
            (self._oidc_token(other_key), "JWT_SIGNATURE_INVALID"),
            (
                self._oidc_token(private_key, iss="https://wrong.example"),
                "JWT_ISSUER_INVALID",
            ),
            (
                self._oidc_token(private_key, exp=now - timedelta(seconds=1)),
                "JWT_EXPIRED",
            ),
            (
                self._oidc_token(private_key, nbf=now + timedelta(minutes=5)),
                "JWT_NBF_INVALID",
            ),
            (self._oidc_token(private_key, sub=""), "JWT_SUB_INVALID"),
        )
        for token, failure_code in invalid_tokens:
            with self.assertRaisesRegex(
                AuthenticationError, "invalid bearer token"
            ) as caught:
                provider.authenticate(token)
            self.assertEqual(caught.exception.failure_code, failure_code)

    def test_oidc_optional_nbf_and_auth0_shape_are_accepted(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
        provider = JwtIdentityProvider(
            public_key=public_key,
            issuer="https://issuer.example",
            audience="ribeira-api",
        )
        now = datetime.now(timezone.utc)

        self.assertEqual(
            provider.authenticate(self._oidc_token(private_key, omit_nbf=True)).subject,
            "user-1",
        )
        self.assertEqual(
            provider.authenticate(self._oidc_token(private_key, nbf=now)).subject,
            "user-1",
        )
        context = provider.authenticate(
            self._oidc_token(
                private_key,
                omit_nbf=True,
                aud=["ribeira-api", "https://issuer.example/userinfo"],
                sub="provider|fixture-subject",
                azp="fixture-public-client",
                scope="openid profile email",
            )
        )
        self.assertEqual(context.subject, "provider|fixture-subject")

        invalid_tokens = (
            self._oidc_token(private_key, nbf=now + timedelta(minutes=5)),
            self._oidc_token(private_key, nbf="invalid"),
            self._oidc_token(private_key, omit_exp=True),
            self._oidc_token(private_key, omit_sub=True),
        )
        for token in invalid_tokens:
            with self.assertRaises(AuthenticationError):
                provider.authenticate(token)

        self.assertEqual(
            provider.authenticate(self._oidc_token(private_key, omit_iat=True)).subject,
            "user-1",
        )

    def test_production_configuration_rejects_development_authentication(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RIBEIRA_ENV": "production",
                "RIBEIRA_AUTH_MODE": "development",
                "RIBEIRA_DEV_AUTH_TOKEN": "test-only",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError):
                Settings.from_env()

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
