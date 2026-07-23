"""Test de integración: auditoría de seguridad de la imagen Docker con Docker Scout.

Un único escaneo SARIF alimenta un test por categoría de severidad (critical,
high, medium, low, unspecified). La condición de logro es que la imagen no
tenga ninguna vulnerabilidad en los paquetes de PyPI, que son los que se
controlan desde uv.lock. Los demás ecosistemas (deb de la imagen base, cargo
en binarios embebidos como uv, generic como el node de Playwright) no se
corrigen desde este repositorio, por lo que quedan fuera del gate, pero el
escaneo completo se vuelca en reports/auditoria_imagen.json con el listado de
módulos afectados, severidades y versiones de fix.

Requiere el plugin Docker Scout (incluido en Docker Desktop), sesión iniciada
en Docker Hub y la imagen construida:

    docker build -t carflip:ci -f docker/Dockerfile .

Si Docker Desktop no está corriendo, el test intenta iniciarlo y espera a que
el daemon responda antes de continuar.

Ejecutar con: pytest -m integration -v tests/test_auditoria_imagen.py
"""

import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

IMAGEN = "carflip:ci"
REPORTE = Path(__file__).resolve().parent.parent / "reports" / "auditoria_imagen.json"

SEVERIDADES = ("critical", "high", "medium", "low", "unspecified")
_ORDEN = {severidad: i for i, severidad in enumerate(SEVERIDADES)}

DOCKER_DESKTOP = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
ESPERA_DOCKER_SEGUNDOS = 120


def _docker_corriendo() -> bool:
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _asegurar_docker_corriendo() -> bool:
    """Si el daemon no responde, intenta iniciar Docker Desktop y espera a que levante."""
    if _docker_corriendo():
        return True
    if sys.platform != "win32" or not DOCKER_DESKTOP.exists():
        return False
    subprocess.Popen([str(DOCKER_DESKTOP)])
    limite = time.monotonic() + ESPERA_DOCKER_SEGUNDOS
    while time.monotonic() < limite:
        time.sleep(3)
        if _docker_corriendo():
            return True
    return False


def _requisito_faltante() -> str | None:
    if shutil.which("docker") is None:
        return "requiere Docker instalado"
    if not _asegurar_docker_corriendo():
        return f"requiere Docker Desktop corriendo (no respondió tras {ESPERA_DOCKER_SEGUNDOS}s de espera)"
    if subprocess.run(["docker", "image", "inspect", IMAGEN], capture_output=True).returncode != 0:
        return f"requiere la imagen construida: docker build -t {IMAGEN} -f docker/Dockerfile ."
    if subprocess.run(["docker", "scout", "version"], capture_output=True).returncode != 0:
        return "requiere el plugin Docker Scout"
    return None


def _partes_purl(purl: str) -> tuple[str, str, str]:
    """Descompone un purl `pkg:tipo/[namespace/]paquete@version[?...]`."""
    tipo, _, resto = purl.removeprefix("pkg:").partition("/")
    resto = resto.split("?")[0]
    ruta, _, version = resto.rpartition("@")
    if not ruta:
        ruta, version = resto, ""
    return tipo, ruta.split("/")[-1], version


def _a_hallazgo(regla: dict, ubicacion: str) -> dict:
    props = regla["properties"]
    purls = props.get("purls") or ["pkg:?/?"]
    tipo, paquete, version = _partes_purl(purls[0])
    fix = props.get("fixed_version")  # Scout usa el literal "not fixed" cuando no hay fix
    return {
        "paquete": paquete,
        "version": version,
        "tipo": tipo,
        "ubicacion": ubicacion,
        "id": regla["id"],
        "severidad": props.get("cvssV3_severity", "UNSPECIFIED").lower(),
        "rango_afectado": props.get("affected_version"),
        "fix": fix if fix and fix != "not fixed" else None,
        "url": regla.get("helpUri"),
    }


def _escribir_reporte(hallazgos: list[dict]) -> None:
    REPORTE.parent.mkdir(exist_ok=True)
    contenido = {
        "imagen": IMAGEN,
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "total": len(hallazgos),
        "vulnerabilidades": hallazgos,
    }
    REPORTE.write_text(json.dumps(contenido, indent=2, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module")
def hallazgos(tmp_path_factory) -> list[dict]:
    """Escanea la imagen una sola vez, genera el reporte JSON y entrega los hallazgos."""
    falta = _requisito_faltante()
    if falta:
        pytest.skip(falta)

    sarif = tmp_path_factory.mktemp("scout") / "scout.sarif.json"
    resultado = subprocess.run(
        ["docker", "scout", "cves", IMAGEN, "--format", "sarif", "--output", str(sarif)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if resultado.returncode != 0:
        pytest.fail(f"Docker Scout no pudo completar el escaneo:\n{resultado.stdout}{resultado.stderr}")

    corrida = json.loads(sarif.read_text(encoding="utf-8"))["runs"][0]
    ubicaciones: dict[str, str] = {}
    for res in corrida["results"]:
        if res.get("locations"):
            uri = res["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            ubicaciones.setdefault(res["ruleId"], uri)
    lista = sorted(
        (_a_hallazgo(regla, ubicaciones.get(regla["id"], "")) for regla in corrida["tool"]["driver"]["rules"]),
        key=lambda h: (_ORDEN.get(h["severidad"], len(SEVERIDADES)), h["paquete"]),
    )
    _escribir_reporte(lista)
    return lista


@pytest.mark.parametrize("severidad", SEVERIDADES)
def test_sin_vulnerabilidades_pypi(severidad: str, hallazgos: list[dict]):
    """La imagen no debe tener vulnerabilidades de esta severidad en paquetes de PyPI.

    Solo se evalúan los paquetes dentro de /app/ (los que instala uv.lock):
    Scout indexa por capas, así que también reporta restos de la imagen base
    (ej. un wheel de pip cacheado en /root/.cache) que no son corregibles
    desde este repositorio y ni siquiera existen en el filesystem final.
    """
    afectados = [
        h
        for h in hallazgos
        if h["tipo"] == "pypi" and h["severidad"] == severidad and h["ubicacion"].startswith("/app/")
    ]
    detalle = "\n".join(
        f"  {h['paquete']} {h['version']}: {h['id']} (fix: {h['fix'] or 'sin fix'})"
        for h in afectados
    )
    assert not afectados, f"Vulnerabilidades {severidad} en paquetes PyPI de {IMAGEN}:\n{detalle}"
