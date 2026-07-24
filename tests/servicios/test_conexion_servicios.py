"""Tests de integración: cada servicio externo del .env existe, conecta y responde.

Complementa a `tests/BD/test_conexion_db.py`, que cubre Postgres y la REST API
de Supabase. Aquí se verifican Cloudflare R2, el CDN público y Groq.

Ejecutar con: pytest -m integration -v tests/servicios/test_conexion_servicios.py
"""

import asyncio
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.integration

_PLACEHOLDERS = ("tu_account_id", "tu_access_key", "tu_secret_key")

_TIMEOUT = 15


def _configurado(*variables: str) -> bool:
    """True si todas las variables existen, no están vacías y no son placeholders."""
    valores = [os.getenv(v, "").strip() for v in variables]
    return all(valores) and not any(v in _PLACEHOLDERS for v in valores)


_tiene_r2 = _configurado(
    "R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"
)
_tiene_cdn = _configurado("CDN_BASE_URL")
_tiene_groq = _configurado("GROQ_API_KEY")

skip_sin_r2 = pytest.mark.skipif(
    not _tiene_r2, reason="Credenciales R2 ausentes o con valores placeholder"
)
skip_sin_cdn = pytest.mark.skipif(not _tiene_cdn, reason="CDN_BASE_URL no configurada")
skip_sin_groq = pytest.mark.skipif(not _tiene_groq, reason="GROQ_API_KEY no configurada")


# ── Cloudflare R2 ────────────────────────────────────────────────────────────


@skip_sin_r2
async def test_r2_bucket_accesible():
    """El cliente R2 del proyecto autentica y el bucket configurado existe."""
    from carflip.storage.r2 import cliente_objetos

    async with cliente_objetos() as cliente:
        respuesta = await cliente.head_bucket(Bucket=os.environ["R2_BUCKET"])

    assert respuesta["ResponseMetadata"]["HTTPStatusCode"] == 200


@skip_sin_r2
async def test_r2_listado_responde():
    """R2 devuelve un listado de objetos — confirma permisos de lectura, no solo auth."""
    from carflip.storage.r2 import cliente_objetos

    async with cliente_objetos() as cliente:
        respuesta = await cliente.list_objects_v2(
            Bucket=os.environ["R2_BUCKET"], MaxKeys=1
        )

    assert respuesta["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert "KeyCount" in respuesta


@skip_sin_r2
@skip_sin_cdn
async def test_r2_round_trip_por_cdn():
    """Sube un objeto, lo sirve por el CDN y lo borra — valida la cadena completa.

    Es el único test que ejercita el camino real del pipeline de fotos:
    escritura con el token, dominio público conectado al bucket y lectura pública.
    """
    import uuid

    from carflip.storage.r2 import cliente_objetos, url_publica

    clave = f"_healthcheck/{uuid.uuid4().hex}.txt"
    contenido = b"carflip-healthcheck"
    bucket = os.environ["R2_BUCKET"]

    async with cliente_objetos() as cliente:
        try:
            await cliente.put_object(
                Bucket=bucket, Key=clave, Body=contenido, ContentType="text/plain"
            )

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                for intento in range(5):
                    respuesta = await client.get(url_publica(clave))
                    if respuesta.status_code == 200:
                        break
                    await asyncio.sleep(2)  # el custom domain tarda en propagar

            assert respuesta.status_code == 200, (
                f"CDN devolvió {respuesta.status_code} para un objeto recién subido"
            )
            assert respuesta.content == contenido
        finally:
            await cliente.delete_object(Bucket=bucket, Key=clave)


# ── CDN público ──────────────────────────────────────────────────────────────


@skip_sin_cdn
async def test_cdn_responde():
    """El dominio del CDN resuelve y responde HTTP (404 incluido: el host está vivo)."""
    base = os.environ["CDN_BASE_URL"].strip().rstrip("/")

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        respuesta = await client.get(base)

    assert respuesta.status_code < 500, f"CDN devolvió {respuesta.status_code}"


# ── Groq ─────────────────────────────────────────────────────────────────────


@skip_sin_groq
async def test_groq_api_key_valida():
    """La API key autentica y Groq lista los modelos disponibles."""
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY'].strip()}"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        respuesta = await client.get(
            "https://api.groq.com/openai/v1/models", headers=headers
        )

    assert respuesta.status_code == 200, f"Groq devolvió {respuesta.status_code}"
    assert respuesta.json()["data"], "Groq no devolvió ningún modelo"


@skip_sin_groq
async def test_groq_modelo_configurado_existe():
    """GROQ_MODEL está entre los modelos que la cuenta puede usar."""
    modelo = os.environ["GROQ_MODEL"].strip()
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY'].strip()}"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        respuesta = await client.get(
            "https://api.groq.com/openai/v1/models", headers=headers
        )

    disponibles = [m["id"] for m in respuesta.json()["data"]]
    assert modelo in disponibles, f"{modelo} no está disponible. Opciones: {disponibles}"


@skip_sin_groq
async def test_groq_completion_responde():
    """Groq genera una respuesta real con el modelo configurado."""
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY'].strip()}"}
    payload = {
        "model": os.environ["GROQ_MODEL"].strip(),
        "messages": [{"role": "user", "content": "Responde solo: ok"}],
        "max_tokens": 5,
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        respuesta = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
        )

    assert respuesta.status_code == 200, f"Groq devolvió {respuesta.status_code}"
    contenido = respuesta.json()["choices"][0]["message"]["content"]
    assert contenido.strip(), "Groq respondió vacío"


# ── Config ───────────────────────────────────────────────────────────────────


def test_settings_carga_valores_del_env():
    """`settings` lee el .env — sin esto ningún módulo del proyecto conecta a nada."""
    from carflip.config import settings

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.groq_api_key == os.getenv("GROQ_API_KEY", "").strip()
    assert settings.r2_bucket == os.getenv("R2_BUCKET", "").strip()
    assert settings.cdn_base_url == os.getenv("CDN_BASE_URL", "").strip()
