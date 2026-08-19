import logging
import asyncio
import httpx
from typing import Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from src.config import settings

logger = logging.getLogger("hag.vault")


class VaultClient:

    def __init__(self):
        self.vault_endpoint = settings.VAULT_ENDPOINT
        self.current_private_key: Optional[str] = settings.JWT_PRIVATE_KEY
        self.current_public_key: Optional[str] = settings.JWT_PUBLIC_KEY
        self._rotation_task: Optional[asyncio.Task] = None
        self._ensure_keys()

    def _ensure_keys(self):
        """Generate default RSA keypair if not configured via env or vault."""
        if not self.current_private_key or not self.current_public_key:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            priv_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")
            pub_pem = (
                private_key.public_key()
                .public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                .decode("utf-8")
            )
            self.current_private_key = priv_pem
            self.current_public_key = pub_pem
            logger.info("Generated default RSA keypair for JWT security.")

    async def fetch_keys_from_vault(self) -> Tuple[Optional[str], Optional[str]]:
        """Call Vault at VAULT_ENDPOINT for JWT key rotation."""
        if not self.vault_endpoint:
            return None, None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.vault_endpoint.rstrip('/')}/v1/keys")
                if resp.status_code == 200:
                    data = resp.json()
                    priv = data.get("private_key") or data.get("jwt_private_key")
                    pub = data.get("public_key") or data.get("jwt_public_key")
                    if priv and pub:
                        logger.info("Successfully fetched updated JWT keys from Vault.")
                        return priv, pub
                # Try key rotation endpoint
                resp_rot = await client.post(f"{self.vault_endpoint.rstrip('/')}/v1/keys/rotate")
                if resp_rot.status_code == 200:
                    data = resp_rot.json()
                    priv = data.get("private_key") or data.get("jwt_private_key")
                    pub = data.get("public_key") or data.get("jwt_public_key")
                    if priv and pub:
                        logger.info("Successfully rotated JWT keys via Vault.")
                        return priv, pub
        except Exception as e:
            logger.debug("Vault endpoint unreachable (%s), retaining current keys.", e)
        return None, None

    async def rotate_keys(self) -> bool:
        """Explicitly trigger key rotation."""
        priv, pub = await self.fetch_keys_from_vault()
        if priv and pub:
            self.current_private_key = priv
            self.current_public_key = pub
            return True
        return False

    async def _rotation_loop(self, interval_seconds: int = 3600):
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.rotate_keys()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in Vault key rotation loop: %s", e)

    def start_rotation_task(self, interval_seconds: int = 3600):
        if self._rotation_task is None or self._rotation_task.done():
            self._rotation_task = asyncio.create_task(self._rotation_loop(interval_seconds))

    def stop_rotation_task(self):
        if self._rotation_task and not self._rotation_task.done():
            self._rotation_task.cancel()

    def get_private_key(self) -> str:
        return self.current_private_key

    def get_public_key(self) -> str:
        return self.current_public_key


vault_client = VaultClient()
