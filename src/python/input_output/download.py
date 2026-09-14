from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

IBGE_BASE_URL = (
    "https://ftp.ibge.gov.br/"
    "Contas_Nacionais/"
    "Matriz_de_Insumo_Produto/"
)


SUPPORTED_RELEASES = {
    (2015, 67): (
        "Matriz_de_Insumo_Produto_2015_Nivel_67.xls"
    ),
}


@dataclass(frozen=True)
class DownloadResult:
    workbook: Path
    manifest: Path
    sha256: str
    downloaded: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _source_url(
    year: int,
    level: int,
) -> str:
    try:
        filename = SUPPORTED_RELEASES[
            (year, level)
        ]
    except KeyError as error:
        raise ValueError(
            "Unsupported IBGE MIP release: "
            f"year={year}, level={level}"
        ) from error

    return (
        f"{IBGE_BASE_URL}"
        f"{year}/"
        f"{filename}"
    )


def _download_to_path(
    url: str,
    destination: Path,
) -> None:
    temp_path = destination.with_suffix(
        destination.suffix + ".part"
    )

    try:
        with (
            urlopen(
                url,
                timeout=120,
            ) as response,
            temp_path.open("wb") as file,
        ):
            shutil.copyfileobj(
                response,
                file,
            )

        temp_path.replace(
            destination
        )

    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_manifest(
    *,
    manifest_path: Path,
    workbook_path: Path,
    url: str,
    year: int,
    level: int,
    sha256: str,
) -> None:
    manifest = {
        "dataset": (
            "IBGE Matriz de Insumo-Produto"
        ),
        "source": "IBGE",
        "year": year,
        "level": level,
        "source_url": url,
        "filename": workbook_path.name,
        "size_bytes": (
            workbook_path.stat().st_size
        ),
        "sha256": sha256,
        "downloaded_at_utc": (
            datetime.now(
                UTC
            ).isoformat()
        ),
    }

    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def download_mip(
    *,
    year: int = 2015,
    level: int = 67,
    raw_root: Path = Path(
        "data/raw/ibge_mip"
    ),
    force: bool = False,
) -> DownloadResult:
    filename = SUPPORTED_RELEASES.get(
        (year, level)
    )

    if filename is None:
        raise ValueError(
            "Unsupported IBGE MIP release: "
            f"year={year}, level={level}"
        )

    release_dir = (
        raw_root
        / str(year)
    )

    release_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    workbook_path = (
        release_dir
        / filename
    )

    manifest_path = (
        release_dir
        / "manifest.json"
    )

    url = _source_url(
        year,
        level,
    )

    # Fast idempotent path:
    # existing file + valid manifest hash.
    if (
        workbook_path.exists()
        and manifest_path.exists()
        and not force
    ):
        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        current_hash = sha256_file(
            workbook_path
        )

        if (
            current_hash
            == manifest.get("sha256")
        ):
            return DownloadResult(
                workbook=workbook_path,
                manifest=manifest_path,
                sha256=current_hash,
                downloaded=False,
            )

    _download_to_path(
        url,
        workbook_path,
    )

    checksum = sha256_file(
        workbook_path
    )

    _write_manifest(
        manifest_path=manifest_path,
        workbook_path=workbook_path,
        url=url,
        year=year,
        level=level,
        sha256=checksum,
    )

    return DownloadResult(
        workbook=workbook_path,
        manifest=manifest_path,
        sha256=checksum,
        downloaded=True,
    )


def main() -> None:
    result = download_mip()

    print(
        "IBGE MIP download"
    )
    print(
        f"Workbook: {result.workbook}"
    )
    print(
        f"Manifest: {result.manifest}"
    )
    print(
        f"SHA-256: {result.sha256}"
    )
    print(
        "Downloaded:"
        f" {result.downloaded}"
    )


if __name__ == "__main__":
    main()
