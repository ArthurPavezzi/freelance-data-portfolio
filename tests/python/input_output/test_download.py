import json
from pathlib import Path

from input_output import download


def test_download_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = 0

    def fake_download(
        url: str,
        destination: Path,
    ) -> None:
        nonlocal calls

        calls += 1

        destination.write_bytes(
            b"synthetic-xls-content"
        )

    monkeypatch.setattr(
        download,
        "_download_to_path",
        fake_download,
    )

    first = download.download_mip(
        raw_root=tmp_path,
    )

    second = download.download_mip(
        raw_root=tmp_path,
    )

    assert calls == 1

    assert first.downloaded
    assert not second.downloaded

    assert (
        first.sha256
        == second.sha256
    )


def test_download_writes_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(
        url: str,
        destination: Path,
    ) -> None:
        destination.write_bytes(
            b"workbook"
        )

    monkeypatch.setattr(
        download,
        "_download_to_path",
        fake_download,
    )

    result = download.download_mip(
        raw_root=tmp_path,
    )

    manifest = json.loads(
        result.manifest.read_text(
            encoding="utf-8"
        )
    )

    assert (
        manifest["source"]
        == "IBGE"
    )

    assert (
        manifest["year"]
        == 2015
    )

    assert (
        manifest["level"]
        == 67
    )

    assert (
        manifest["sha256"]
        == result.sha256
    )

    assert (
        manifest["size_bytes"]
        == len(b"workbook")
    )
