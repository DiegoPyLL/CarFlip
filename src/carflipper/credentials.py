"""
Manejo seguro de credenciales:
- Cloud (USE_SECRETS_MANAGER=true): AWS Secrets Manager via boto3
- Local (USE_SECRETS_MANAGER=false): variables de entorno (FERNET_KEY, FACEBOOK_EMAIL, etc.)

Cookies de sesión: cifradas con Fernet y guardadas en PostgreSQL (sin cambios).
"""

import json
import os

from cryptography.fernet import Fernet
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from carflipper.database.models import SessionCookie

_fernet_key: bytes | None = None


# ── Provider de secretos ──────────────────────────────────────────────────────

def _get_secret_from_aws(secret_name: str) -> dict:
    """Recupera un secreto JSON desde AWS Secrets Manager."""
    import boto3
    from carflipper.config import settings

    client = boto3.client("secretsmanager", region_name=settings.aws_region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


def _full_secret_name(name: str) -> str:
    from carflipper.config import settings
    return f"{settings.secrets_manager_prefix}/{name}"


# ── Clave Fernet ──────────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """Obtiene la clave de cifrado Fernet desde Secrets Manager o variable de entorno."""
    global _fernet_key
    if _fernet_key:
        return Fernet(_fernet_key)

    from carflipper.config import settings

    if settings.use_secrets_manager:
        secret = _get_secret_from_aws(_full_secret_name("fernet-key"))
        _fernet_key = secret["fernet_key"].encode()
        logger.debug("Clave Fernet cargada desde AWS Secrets Manager")
    else:
        raw = os.environ.get("FERNET_KEY")
        if not raw:
            # Generar clave nueva y mostrar instrucción (solo en dev)
            _fernet_key = Fernet.generate_key()
            logger.warning(
                "FERNET_KEY no definida. Se generó una clave temporal. "
                "Agrégala a tu .env para persistir cookies entre ejecuciones: "
                f"FERNET_KEY={_fernet_key.decode()}"
            )
        else:
            _fernet_key = raw.encode()
            logger.debug("Clave Fernet cargada desde variable de entorno")

    return Fernet(_fernet_key)


# ── Credenciales de sitios (usuario / contraseña) ────────────────────────────

def get_credentials(source: str) -> tuple[str, str] | None:
    """Retorna (email, password) o None si no están configuradas."""
    from carflipper.config import settings

    if settings.use_secrets_manager:
        try:
            secret = _get_secret_from_aws(_full_secret_name(source))
            return secret["email"], secret["password"]
        except Exception as exc:
            logger.warning(f"No se encontraron credenciales para {source} en Secrets Manager: {exc}")
            return None
    else:
        prefix = source.upper()
        email = os.environ.get(f"{prefix}_EMAIL")
        password = os.environ.get(f"{prefix}_PASSWORD")
        if email and password:
            return email, password
        return None


def set_credentials(source: str, email: str, password: str) -> None:
    """Guarda credenciales. En cloud mode: AWS Secrets Manager. En local: muestra instrucción."""
    from carflipper.config import settings

    if settings.use_secrets_manager:
        import boto3
        client = boto3.client("secretsmanager", region_name=settings.aws_region)
        secret_name = _full_secret_name(source)
        payload = json.dumps({"email": email, "password": password})
        try:
            client.put_secret_value(SecretId=secret_name, SecretString=payload)
            logger.info(f"Credenciales actualizadas en Secrets Manager: {secret_name}")
        except client.exceptions.ResourceNotFoundException:
            client.create_secret(Name=secret_name, SecretString=payload)
            logger.info(f"Credenciales creadas en Secrets Manager: {secret_name}")
    else:
        prefix = source.upper()
        logger.info(
            f"En modo local, agrega estas líneas a tu .env:\n"
            f"  {prefix}_EMAIL={email}\n"
            f"  {prefix}_PASSWORD={password}"
        )


def delete_credentials(source: str) -> None:
    """Elimina credenciales. En cloud mode: marca el secreto para eliminación."""
    from carflipper.config import settings

    if settings.use_secrets_manager:
        import boto3
        client = boto3.client("secretsmanager", region_name=settings.aws_region)
        try:
            client.delete_secret(
                SecretId=_full_secret_name(source),
                RecoveryWindowInDays=7,
            )
            logger.info(f"Secreto marcado para eliminación en 7 días: {_full_secret_name(source)}")
        except Exception as exc:
            logger.warning(f"No se pudo eliminar el secreto para {source}: {exc}")
    else:
        prefix = source.upper()
        logger.info(f"Elimina {prefix}_EMAIL y {prefix}_PASSWORD de tu .env")


def list_configured_sources() -> dict[str, bool]:
    """Retorna {source: tiene_credenciales} para los sitios conocidos."""
    from carflipper.config import settings

    sources = ["facebook", "yapo", "chileautos", "autosusados", "mercadolibre"]
    result = {}

    for source in sources:
        if settings.use_secrets_manager:
            try:
                _get_secret_from_aws(_full_secret_name(source))
                result[source] = True
            except Exception:
                result[source] = False
        else:
            prefix = source.upper()
            result[source] = bool(os.environ.get(f"{prefix}_EMAIL"))

    return result


# ── Cookies de sesión (cifradas en PostgreSQL) ────────────────────────────────

async def save_cookies(session: AsyncSession, source: str, cookies: list[dict]) -> None:
    """Cifra y persiste cookies de sesión del browser en la DB."""
    fernet = _get_fernet()
    raw = json.dumps(cookies).encode()
    encrypted = fernet.encrypt(raw)

    result = await session.execute(select(SessionCookie).where(SessionCookie.source == source))
    row = result.scalar_one_or_none()
    if row:
        row.encrypted_cookies = encrypted
    else:
        session.add(SessionCookie(source=source, encrypted_cookies=encrypted))
    await session.commit()
    logger.debug(f"Cookies guardadas para {source}")


async def load_cookies(session: AsyncSession, source: str) -> list[dict] | None:
    """Carga y descifra cookies de sesión desde la DB."""
    result = await session.execute(select(SessionCookie).where(SessionCookie.source == source))
    row = result.scalar_one_or_none()
    if not row or not row.encrypted_cookies:
        return None
    fernet = _get_fernet()
    raw = fernet.decrypt(row.encrypted_cookies)
    return json.loads(raw.decode())
