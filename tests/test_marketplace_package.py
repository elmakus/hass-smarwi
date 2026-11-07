"""Offline native ZIP prepare/write contract, not public install or persistence."""

from collections.abc import AsyncIterator
from io import BytesIO
import json
from pathlib import Path
import socket
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.components.lovelace import LOVELACE_DATA, LovelaceData
from homeassistant.components.lovelace.resources import ResourceYAMLCollection
from homeassistant.components.marketplace.base import MarketplaceManager
from homeassistant.components.marketplace.exceptions import MarketplaceError
from homeassistant.components.marketplace.repositories.integration import (
    IntegrationRepository,
)
from homeassistant.components.marketplace.utils.url import RemoteFile
from homeassistant.core import HomeAssistant

from scripts import build_release

SOURCE_ROOT = Path(__file__).resolve().parent.parent
FULL_NAME = "elmakus/hass-smarwi"


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block even loopback sockets, server startup and DNS, as service tests do."""

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("Marketplace package tests must not use sockets or DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        monkeypatch.setattr(socket.socket, name, fail)
    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(socket, "getaddrinfo", fail)


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Configure the official hass fixture before it creates its instance."""
    return str(tmp_path)


@pytest.fixture
def release(tmp_path: Path) -> Path:
    """Build the real candidate from the current Git-tracked integration source."""
    manifest = json.loads(
        (SOURCE_ROOT / "custom_components/smarwi/manifest.json").read_bytes()
    )
    metadata = json.loads((SOURCE_ROOT / "hacs.json").read_bytes())
    return build_release.build_release(
        tmp_path / "release" / metadata["filename"], manifest["version"]
    )


@pytest.fixture
async def repository(
    hass: HomeAssistant,
    tmp_path: Path,
    release: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[IntegrationRepository, dict[str, bytes]]]:
    """Use native manager/repository objects; replace only remote response bytes."""
    assert Path(hass.config.config_dir) == tmp_path
    hass.data[LOVELACE_DATA] = LovelaceData(
        resource_mode="yaml",
        dashboards={},
        resources=ResourceYAMLCollection([]),
        yaml_dashboards={},
    )
    manager = MarketplaceManager(hass, MockConfigEntry(domain="marketplace"))
    repository = IntegrationRepository(manager, FULL_NAME)
    manifest = json.loads(
        (SOURCE_ROOT / "custom_components/smarwi/manifest.json").read_bytes()
    )
    repository.data.domain = manifest["domain"]
    version = manifest["version"]
    raw = f"https://raw.githubusercontent.com/{FULL_NAME}/{version}"
    responses = {
        f"{raw}/hacs.json": (SOURCE_ROOT / "hacs.json").read_bytes(),
        f"{raw}/custom_components/smarwi/manifest.json": (
            SOURCE_ROOT / "custom_components/smarwi/manifest.json"
        ).read_bytes(),
        f"https://github.com/{FULL_NAME}/releases/download/{version}/{release.name}": release.read_bytes(),
    }
    requested = []

    async def download(remote_file: RemoteFile, **kwargs: object) -> bytes:
        bases = manager.endpoints.bases(remote_file.endpoint)
        assert len(bases) == 1
        url = f"{bases[0]}/{remote_file.path}"
        if url not in responses:
            pytest.fail(f"Unexpected Marketplace download: {url}")
        requested.append(url)
        return responses[url]

    monkeypatch.setattr(manager, "async_download_file", AsyncMock(side_effect=download))
    yield repository, responses
    assert requested == list(responses)


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Compare complete file sets, including stale or nested files."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("replacement", [False, True], ids=["first", "replacement"])
async def test_native_marketplace_writes_exact_release(
    repository: tuple[IntegrationRepository, dict[str, bytes]],
    release: Path,
    tmp_path: Path,
    replacement: bool,
) -> None:
    """Actual flat ZIP bytes survive native extraction; replacement drops stale files."""
    repo, _ = repository
    destination = tmp_path / "custom_components/smarwi"
    if replacement:
        destination.mkdir(parents=True)
        (destination / "stale.py").write_bytes(b"old source")
        (destination / "manifest.json").write_bytes(b"old manifest")
    with ZipFile(release) as archive:
        expected = {name: archive.read(name) for name in archive.namelist()}
    version = json.loads(expected["manifest.json"])["version"]
    download = await repo._async_prepare_catalog_install(version, commit=False)
    assert Path(repo.content.path.local) == destination
    await repo._async_write_content(download)
    assert tree_bytes(destination) == expected
    assert not list((tmp_path / ".storage/marketplace_backups").iterdir())


@pytest.mark.parametrize(
    ("invalid", "existing", "error_key"),
    [
        ("domain", True, "installed_manifest_other_domain"),
        ("version", True, "installed_manifest_without_version"),
        ("layout", False, "installed_manifest_unusable"),
    ],
)
async def test_native_marketplace_rejects_written_content(
    repository: tuple[IntegrationRepository, dict[str, bytes]],
    release: Path,
    tmp_path: Path,
    invalid: str,
    existing: bool,
    error_key: str,
) -> None:
    """Native validation restores old bytes or removes a failed first install."""
    repo, responses = repository
    destination = tmp_path / "custom_components/smarwi"
    old = {"manifest.json": b"old manifest", "nested/stale.py": b"old source"}
    if existing:
        for name, content in old.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    with ZipFile(release) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["manifest.json"])
    version = manifest["version"]
    if invalid != "layout":
        manifest[invalid] = "other_domain" if invalid == "domain" else "not a version"
        members["manifest.json"] = json.dumps(manifest).encode()
    broken = BytesIO()
    with ZipFile(broken, "w") as archive:
        for name, content in members.items():
            archive.writestr(f"smarwi/{name}" if invalid == "layout" else name, content)
    asset_url = (
        f"https://github.com/{FULL_NAME}/releases/download/{version}/{release.name}"
    )
    responses[asset_url] = broken.getvalue()
    download = await repo._async_prepare_catalog_install(version, commit=False)
    assert Path(repo.content.path.local) == destination
    with pytest.raises(MarketplaceError) as caught:
        await repo._async_write_content(download)
    assert caught.value.translation_key == error_key
    if existing:
        assert tree_bytes(destination) == old
    else:
        assert not destination.exists()
    assert not list((tmp_path / ".storage/marketplace_backups").iterdir())
