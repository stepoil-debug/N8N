#!/usr/bin/env python3
"""Materializa o pacote versionado em .bootstrap/parts na raiz do repositório."""
from __future__ import annotations

import base64
import io
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS_DIR = ROOT / ".bootstrap" / "parts"
STAGING = ROOT / ".materialize-staging"


def safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if root != target and root not in target.parents:
            raise RuntimeError(f"Caminho inseguro no pacote: {member.name}")
        if member.issym() or member.islnk():
            raise RuntimeError(f"Links não são permitidos no pacote: {member.name}")
    archive.extractall(destination)


def main() -> int:
    parts = sorted(PARTS_DIR.glob("part*.b64"))
    if not parts:
        raise RuntimeError("Nenhuma parte encontrada em .bootstrap/parts")

    encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError("Falha ao decodificar o pacote base64") from exc

    if not payload.startswith(b"\x1f\x8b"):
        raise RuntimeError("O pacote reconstruído não é um tar.gz válido")

    shutil.rmtree(STAGING, ignore_errors=True)
    STAGING.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        safe_extract(archive, STAGING)

    source = STAGING
    children = list(STAGING.iterdir())
    if len(children) == 1 and children[0].is_dir():
        source = children[0]

    for item in source.iterdir():
        destination = ROOT / item.name
        if destination.name in {".git", ".bootstrap", ".materialize-staging"}:
            continue
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.move(str(item), str(destination))

    shutil.rmtree(STAGING, ignore_errors=True)
    shutil.rmtree(ROOT / ".bootstrap", ignore_errors=True)

    required = [
        ROOT / "README.md",
        ROOT / "docker-compose.yml",
        ROOT / "apps" / "document-api" / "Dockerfile",
        ROOT / "workflows",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Pacote incompleto; ausentes: " + ", ".join(missing))

    print(f"Projeto materializado com sucesso a partir de {len(parts)} partes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
