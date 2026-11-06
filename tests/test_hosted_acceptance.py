"""Dependency-free security/helper tests: never start Docker, sockets or applications."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import stat
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from scripts import hosted_acceptance as hosted


class HostedAcceptanceTests(unittest.TestCase):
    """Exercise trust boundaries with private local files and fake inspect data."""

    def setUp(self) -> None:
        """Make one private disposable tree, without app or network side effects."""
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "config"
        self.config.mkdir()
        self.archive = self.root / "smarwi.zip"
        self.members = {
            "__init__.py": b"# synthetic\n",
            "manifest.json": json.dumps(
                {"domain": "smarwi", "version": "0.4.0.dev0"}
            ).encode(),
            "translations/en.json": b"{}",
            "brand/icon.png": b"synthetic image",
            "LICENSE": b"synthetic license",
        }

    def write_archive(self, extra=None) -> None:
        """Build only local synthetic input bytes."""
        with ZipFile(self.archive, "w") as archive:
            for name, content in self.members.items():
                archive.writestr(name, content)
            if extra:
                archive.writestr(*extra)

    def test_imports_are_inert(self) -> None:
        """Import both scripts while all subprocess and socket creation is forbidden."""
        with (
            patch.object(subprocess, "run", side_effect=AssertionError),
            patch.object(subprocess, "Popen", side_effect=AssertionError),
            patch.object(socket, "socket", side_effect=AssertionError),
        ):
            for name in ("hosted_acceptance", "hosted_runtime"):
                spec = importlib.util.spec_from_file_location(
                    name, hosted.ROOT / "scripts" / f"{name}.py"
                )
                self.assertIsNotNone(spec)
                assert spec is not None and spec.loader is not None
                spec.loader.exec_module(importlib.util.module_from_spec(spec))

    def test_install_verifies_bytes_and_removes_stale_files(self) -> None:
        """Replace a complete integration without retaining prior-version files."""
        target = self.config / "custom_components/smarwi"
        target.mkdir(parents=True)
        (target / "stale.py").write_text("stale")
        self.write_archive()
        digest = hosted.install(self.archive, self.config, self.members["LICENSE"])
        self.assertEqual(digest, hosted.tree_hash(target))
        self.assertEqual(
            {
                path.relative_to(target).as_posix(): path.read_bytes()
                for path in target.rglob("*")
                if path.is_file()
            },
            self.members,
        )
        self.assertFalse((target / "stale.py").exists())

    def test_archive_rejects_unsafe_names_and_links(self) -> None:
        """Reject traversal, absolute paths, duplicate members, links and special files."""
        for name in (
            "../outside.py",
            "/outside.py",
            "translations/../outside.json",
            "C:\\outside.py",
            "brand//x.png",
            "brand/./x.png",
            "unexpected/settings.json",
        ):
            with self.subTest(name=name):
                self.write_archive((name, b"unsafe"))
                with self.assertRaises(hosted.Blocked):
                    hosted.archive_members(self.archive, self.members["LICENSE"])
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFDIR):
            with self.subTest(mode=mode):
                info = ZipInfo("link.py")
                info.create_system = 3
                info.external_attr = (mode | 0o777) << 16
                self.write_archive((info, b"outside"))
                with self.assertRaises(hosted.Blocked):
                    hosted.archive_members(self.archive, self.members["LICENSE"])
        self.write_archive()
        with ZipFile(self.archive, "a") as archive, self.assertWarns(UserWarning):
            archive.writestr("__init__.py", b"duplicate")
        with self.assertRaises(hosted.Blocked):
            hosted.archive_members(self.archive, self.members["LICENSE"])

    def test_invalid_license_manifest_and_missing_file_are_rejected(self) -> None:
        """Same-version source identity and license are mandatory, not normalized."""
        for change in (
            {"LICENSE": b"wrong"},
            {"manifest.json": b'{"domain":"smarwi","version":"9.0"}'},
            {"manifest.json": b'{"domain":"other","version":"0.4.0.dev0"}'},
        ):
            with self.subTest(change=change):
                original = self.members.copy()
                self.members.update(change)
                self.write_archive()
                with self.assertRaises(hosted.Blocked):
                    hosted.archive_members(self.archive, b"synthetic license")
                self.members = original
        del self.members["__init__.py"]
        self.write_archive()
        with self.assertRaises(hosted.Blocked):
            hosted.archive_members(self.archive, self.members["LICENSE"])

    def test_symlinked_config_or_integration_never_touches_outside(self) -> None:
        """Do not follow existing links when replacing an integration."""
        self.write_archive()
        outside = self.root / "outside"
        outside.mkdir()
        marker = outside / "keep.py"
        marker.write_text("preserve")
        parent = self.config / "custom_components"
        parent.mkdir()
        (parent / "smarwi").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(hosted.Blocked):
            hosted.install(self.archive, self.config, self.members["LICENSE"])
        (parent / "smarwi").unlink()
        parent.rmdir()
        parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(hosted.Blocked):
            hosted.install(self.archive, self.config, self.members["LICENSE"])
        self.assertEqual(marker.read_text(), "preserve")

    def test_restore_preserves_mount_inode_and_exact_stopped_contents(self) -> None:
        """Matching checkpoint restore removes stale files, including nested state."""
        saved = self.root / "saved"
        saved.mkdir()
        (saved / ".storage").mkdir()
        (saved / ".storage/state").write_text("synthetic private checkpoint")
        (self.config / "stale").mkdir()
        (self.config / "stale/state").write_text("newer state")
        inode = self.config.stat().st_ino
        hosted.restore_contents(saved, self.config)
        self.assertEqual(self.config.stat().st_ino, inode)
        self.assertEqual(hosted.tree_hash(self.config), hosted.tree_hash(saved))
        self.assertFalse((self.config / "stale").exists())
        (self.config / "link").symlink_to(saved)
        with self.assertRaises(hosted.Blocked):
            hosted.restore_contents(saved, self.config)

    def test_network_requires_loopback_and_no_external_routes(self) -> None:
        """Reject IPv4/IPv6 egress and namespace/interface ambiguity."""
        good = (
            "net:[123]\nINTERFACES\nlo\nIPV4\nIface Destination Gateway Flags\nIPV6\n"
        )
        self.assertEqual(hosted.network_observation(good), "net:[123]")
        unreachable = (
            "0" * 32
            + " 00 "
            + "0" * 32
            + " 00 "
            + "0" * 32
            + " ffffffff 00000001 00000000 00200200 lo\n"
        )
        self.assertEqual(hosted.network_observation(good + unreachable), "net:[123]")
        for bad in (
            good.replace("lo\nIPV4", "lo\neth0\nIPV4"),
            good.replace("Flags\n", "Flags\neth0 00000000 0100000A 0003\n"),
            good + unreachable.replace("00200200", "00000001"),
            good.replace("net:[123]", "net:host"),
        ):
            with self.subTest(bad=bad), self.assertRaises(hosted.Blocked):
                hosted.network_observation(bad)

    def fixture_inspect(self):
        """Return the minimum exact expected private Docker inspect shape."""
        image = {"Id": "sha256:" + "a" * 64, "Config": {"Env": ["PATH=/usr/bin:/bin"]}}
        mounts = {"/config": (self.config, True)}
        info = {
            "State": {"Running": True},
            "Image": image["Id"],
            "Config": {
                "User": "1001:1001",
                "Env": [
                    "PATH=/usr/bin:/bin",
                    "HOME=/tmp",
                    "TMPDIR=/tmp",
                    "PYTHONDONTWRITEBYTECODE=1",
                ],
            },
            "HostConfig": {
                "NetworkMode": "none",
                "ReadonlyRootfs": True,
                "Privileged": False,
                "CapDrop": ["ALL"],
                "CapAdd": None,
                "SecurityOpt": ["no-new-privileges=true"],
                "Devices": [],
                "PidMode": "",
                "IpcMode": "private",
                "PortBindings": {},
                "PublishAllPorts": False,
                "ExtraHosts": [],
                "Links": None,
                "Dns": [],
                "DnsOptions": [],
                "DnsSearch": [],
                "PidsLimit": 256,
                "Memory": 3 * 1024**3,
                "NanoCpus": 2_000_000_000,
                "RestartPolicy": {"Name": "no"},
                "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=128m,mode=1777"},
            },
            "NetworkSettings": {
                "Ports": {},
                "Networks": {"none": {"IPAddress": "", "Gateway": ""}},
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Propagation": "rprivate",
                    "Destination": "/config",
                    "Source": str(self.config),
                    "RW": True,
                }
            ],
        }
        return info, image, mounts

    def test_container_guards_reject_dangerous_docker_settings(self) -> None:
        """No ports, privileges, capabilities, host namespaces, sockets or tokens."""
        info, image, mounts = self.fixture_inspect()
        hosted.validate_container(info, image, "none", mounts, "1001:1001")
        for key, value in {
            "NetworkMode": "bridge",
            "ReadonlyRootfs": False,
            "Privileged": True,
            "CapAdd": ["NET_ADMIN"],
            "CapDrop": [],
            "SecurityOpt": [],
            "Devices": [{"PathOnHost": "/dev/mem"}],
            "PidMode": "host",
            "IpcMode": "host",
            "CgroupnsMode": "host",
            "UTSMode": "host",
            "PortBindings": {"8123/tcp": [{}]},
            "PublishAllPorts": True,
            "ExtraHosts": ["host.docker.internal:host-gateway"],
            "Links": ["forwarder"],
            "Dns": ["8.8.8.8"],
            "VolumesFrom": ["other"],
            "DeviceRequests": [{"Count": -1}],
            "DeviceCgroupRules": ["a *:* rwm"],
        }.items():
            bad = deepcopy(info)
            bad["HostConfig"][key] = value
            with self.subTest(key=key), self.assertRaises(hosted.Blocked):
                hosted.validate_container(bad, image, "none", mounts, "1001:1001")
        for field, value in (
            ("User", "0:0"),
            ("Env", info["Config"]["Env"] + ["GITHUB_TOKEN=synthetic-secret"]),
        ):
            bad = deepcopy(info)
            bad["Config"][field] = value
            with self.subTest(field=field), self.assertRaises(hosted.Blocked):
                hosted.validate_container(bad, image, "none", mounts, "1001:1001")
        bad = deepcopy(info)
        bad["Mounts"].append(
            {
                "Type": "bind",
                "Propagation": "rprivate",
                "Destination": "/var/run/docker.sock",
                "Source": "/var/run/docker.sock",
                "RW": True,
            }
        )
        with self.assertRaises(hosted.Blocked):
            hosted.validate_container(bad, image, "none", mounts, "1001:1001")
        image["Config"]["Env"].append("HTTP_PROXY=synthetic-forwarder")
        with self.assertRaises(hosted.Blocked):
            hosted.validate_container(info, image, "none", mounts, "1001:1001")

    def test_sanitized_evidence_rejects_unknown_fields_and_private_values(self) -> None:
        """Export only allowlisted assertions and an aggregate synthetic identity hash."""
        value = {
            "identity": {
                "id": "synthetic-id",
                "entity_id": "cover.offline_fixture",
                "unique_id": "offline_serial_cover",
                "config_entry_id": "01SYNTHETICENTRY",
                "device_id": "synthetic-device",
            },
            "features": 240,
            "window": True,
            "closed_zero": True,
            "nonclosed_unknown": True,
            "open_1_received": True,
            "reload_identity": True,
        }
        safe = hosted.sanitize_smoke(value)
        self.assertNotIn("identity", safe)
        self.assertNotIn("synthetic-id", json.dumps(safe))
        for bad in (
            {**value, "token": "private"},
            {**value, "features": 255},
            {**value, "window": False},
            {**value, "identity": {**value["identity"], "id": "Bearer secret"}},
        ):
            with self.assertRaises(hosted.Blocked):
                hosted.sanitize_smoke(bad)

    def test_cleanup_attempts_all_owned_ids_after_failure(self) -> None:
        """Never prune globally or stop cleanup after one exact-ID removal fails."""
        sandbox = hosted.Sandbox(self.config)
        sandbox.ids = ["a" * 64, "b" * 64]
        calls = []

        def fake_run(*args, **kwargs):
            calls.append(args)
            if args[:3] == ("docker", "rm", "--force") and args[-1] == "b" * 64:
                raise subprocess.CalledProcessError(1, "synthetic removal")
            return ""

        with patch.object(hosted, "run", side_effect=fake_run):
            outcome = sandbox.cleanup()
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["containers_removed"], 1)
        self.assertTrue(outcome["scratch_removed"])
        self.assertEqual(
            [call[-1] for call in calls if call[1] == "rm"], ["b" * 64, "a" * 64]
        )
        self.assertTrue(all("prune" not in call for call in calls))

    def test_missing_cid_recovers_only_exact_owned_name(self) -> None:
        """Resolve an ambiguous create by its reserved name and ownership label."""
        sandbox = hosted.Sandbox(self.config)
        sandbox.pending_names = ["reserved-synthetic-name"]
        calls = []

        def fake_run(*args, **kwargs):
            calls.append(args)
            if args[1] == "inspect":
                return json.dumps(
                    [
                        {
                            "Id": "d" * 64,
                            "Name": "/reserved-synthetic-name",
                            "Config": {
                                "Labels": {"io.smarwi.acceptance": self.config.name}
                            },
                        }
                    ]
                )
            return ""

        with patch.object(hosted, "run", side_effect=fake_run):
            outcome = sandbox.cleanup()
        self.assertEqual(outcome["status"], "passed")
        self.assertEqual([call[-1] for call in calls if call[1] == "rm"], ["d" * 64])

    def test_unresolved_create_is_not_clean_disposal(self) -> None:
        """Missing/invalid inspection never authorizes broad deletion or a pass."""
        sandbox = hosted.Sandbox(self.config)
        sandbox.pending_names = ["reserved-synthetic-name"]
        with patch.object(hosted, "run", return_value="[]") as mocked:
            outcome = sandbox.cleanup()
        self.assertEqual(outcome["status"], "failed")
        self.assertTrue(outcome["unresolved_create"])
        self.assertEqual(mocked.call_count, 1)
        self.assertTrue(outcome["scratch_removed"])

    def test_timed_out_create_keeps_exact_id_for_cleanup(self) -> None:
        """Record a created ID even when the Docker CLI outcome is ambiguous."""
        sandbox = hosted.Sandbox(self.config)

        def fake_run(*args, **kwargs):
            cidfile = Path(args[args.index("--cidfile") + 1])
            cidfile.write_text("c" * 64)
            raise subprocess.TimeoutExpired("synthetic create", 120)

        with (
            patch.object(hosted, "run", side_effect=fake_run),
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            sandbox.create(
                {"Id": "sha256:" + "a" * 64},
                "none",
                {},
                "1001:1001",
                ["python3", "inert"],
            )
        self.assertEqual(sandbox.ids, ["c" * 64])


if __name__ == "__main__":
    unittest.main()
