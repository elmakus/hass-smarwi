#!/usr/bin/env python3
"""Manual GitHub-hosted-only synthetic A -> B -> matching A checkpoint acceptance.

Importing this module performs no I/O. Runtime internet is never enabled.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from zipfile import ZipFile

from scripts import build_release

ROOT = Path(__file__).resolve().parent.parent
A = "43c22f5a3c427aa46040f175f770d3dfd0f016b8"
B = "635017321dab8c29bbeff5f5223bfe9461cdffd1"
IMAGES = ("ghcr.io/home-assistant/home-assistant:2026.11.0", "eclipse-mosquitto:2.0")
ID = re.compile(r"[0-9a-f]{64}")
DIGEST = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}")
ENV_KEYS = {
    "PATH",
    "LANG",
    "LC_ALL",
    "TZ",
    "HOME",
    "TMPDIR",
    "S6_BEHAVIOUR_IF_STAGE2_FAILS",
    "S6_CMD_WAIT_FOR_SERVICES_MAXTIME",
    "S6_CMD_WAIT_FOR_SERVICES",
    "S6_SERVICES_READYTIME",
    "S6_SERVICES_GRACETIME",
    "UV_SYSTEM_PYTHON",
    "UV_EXTRA_INDEX_URL",
    "UV_INDEX_STRATEGY",
    "UV_NO_CACHE",
    "UV_COMPILE_BYTECODE",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
    "PIP_DISABLE_PIP_VERSION_CHECK",
    "PIP_EXTRA_INDEX_URL",
    "PIP_NO_CACHE_DIR",
    "PIP_ROOT_USER_ACTION",
    "PYTHON_VERSION",
    "PYTHON_SHA256",
    "DOWNLOAD_SHA256",
    "GPG_KEY",
    "GPG_KEYS",
    "VERSION",
    "S6_OVERLAY_VERSION",
    "S6_LOGGING",
}
NETWORK_PROBE = """set -eu
readlink /proc/self/ns/net
printf 'INTERFACES\\n'
ls -1 /sys/class/net
printf 'IPV4\\n'
cat /proc/net/route
printf 'IPV6\\n'
cat /proc/net/ipv6_route
"""
BROKER_START = """set -eu
rm -f /mosquitto/data/acceptance.exit
/usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf &
pid=$!
echo "$pid" > /mosquitto/data/acceptance.pid
set +e
wait "$pid"
result=$?
printf '%s' "$result" > /mosquitto/data/acceptance.exit
exit "$result"
"""
BROKER_STOP = """set -eu
pid=$(cat /mosquitto/data/acceptance.pid)
case "$pid" in ''|*[!0-9]*) exit 1;; esac
[ "$(readlink /proc/"$pid"/exe)" = /usr/sbin/mosquitto ]
kill -TERM "$pid"
"""


class Blocked(RuntimeError):
    """A safety, dependency or infrastructure gate was not established."""


def require(condition: object) -> None:
    """Fail closed without including private command output."""
    if not condition:
        raise Blocked("required gate not established")


def run(*args: str, timeout: int = 120) -> str:
    """Capture private command output; never echo it into public job logs."""
    return subprocess.run(
        args, check=True, capture_output=True, timeout=timeout, text=True
    ).stdout.strip()


def failure_location(error: Exception) -> dict:
    """Expose only a public source location, never messages, values or source lines."""
    frames = [
        frame
        for frame in traceback.extract_tb(error.__traceback__)
        if Path(frame.filename).resolve() == Path(__file__).resolve()
        and frame.name not in {"require", "run"}
    ]
    if not frames:
        return {"source": "external"}
    frame = frames[-1]
    return {
        "source": "scripts/hosted_acceptance.py",
        "function": frame.name,
        "line": frame.lineno,
    }


def sha(path: Path) -> str:
    """Hash bytes, not timestamps or manifest versions."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular_tree(root: Path) -> dict[str, str]:
    """Reject links/special files before copying, hashing or deleting a private tree."""
    require(root.is_dir() and not root.is_symlink())
    result = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode))
        if stat.S_ISREG(mode):
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def tree_hash(root: Path) -> str:
    """Publish only an aggregate checkpoint digest, never storage contents/names."""
    return hashlib.sha256(
        json.dumps(regular_tree(root), sort_keys=True).encode()
    ).hexdigest()


def archive_members(archive: Path, license_bytes: bytes) -> dict[str, bytes]:
    """Accept only builder-shaped regular flat files, with no links or traversal."""
    result = {}
    with ZipFile(archive) as zipped:
        require(len(zipped.infolist()) <= 100)
        for info in zipped.infolist():
            path = PurePosixPath(info.filename)
            parts = path.parts
            allowed = (
                len(parts) == 1
                and (path.suffix == ".py" or path.name in {"manifest.json", "LICENSE"})
            ) or (
                len(parts) == 2
                and (
                    (parts[0] == "translations" and path.suffix == ".json")
                    or (parts[0] == "brand" and path.suffix == ".png")
                )
            )
            require(
                allowed
                and info.filename == path.as_posix()
                and not path.is_absolute()
                and ".." not in parts
                and "\\" not in info.filename
            )
            require(
                info.filename not in result
                and not info.is_dir()
                and info.file_size <= 2_000_000
            )
            require(stat.S_IFMT(info.external_attr >> 16) in (0, stat.S_IFREG))
            result[info.filename] = zipped.read(info)
    require(
        {
            "__init__.py",
            "manifest.json",
            "translations/en.json",
            "brand/icon.png",
            "LICENSE",
        }
        <= result.keys()
    )
    manifest = json.loads(result["manifest.json"])
    require(manifest["domain"] == "smarwi" and manifest["version"] == "0.4.0.dev0")
    require(result["LICENSE"] == license_bytes)
    return result


def install(archive: Path, config: Path, license_bytes: bytes) -> str:
    """Replace only a stopped sandbox's integration, removing every stale file."""
    members = archive_members(archive, license_bytes)
    parent = config / "custom_components"
    require(config.is_dir() and not config.is_symlink())
    parent.mkdir(exist_ok=True)
    require(not parent.is_symlink())
    target = parent / "smarwi"
    if target.exists() or target.is_symlink():
        regular_tree(target)
        shutil.rmtree(target)
    target.mkdir()
    for name, content in members.items():
        path = target / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
    require(
        regular_tree(target)
        == {
            name: hashlib.sha256(content).hexdigest()
            for name, content in members.items()
        }
    )
    return tree_hash(target)


def network_observation(text: str) -> str:
    """Require one loopback interface and no usable IPv4/IPv6 external route."""
    # run() strips the marker's newline when the final route table is empty.
    text = text.rstrip("\n") + "\n"
    namespace, rest = text.split("\nINTERFACES\n")
    require(re.fullmatch(r"net:\[[0-9]+\]", namespace))
    interfaces, rest = rest.split("IPV4\n")
    require(interfaces.split() == ["lo"])
    ipv4, ipv6 = rest.split("IPV6\n")
    require(ipv4.splitlines()[0].split()[:2] == ["Iface", "Destination"])
    for row in ipv4.splitlines()[1:]:
        fields = row.split()
        require(
            fields[0] == "lo" and fields[1] == "0000007F" and fields[2] == "00000000"
        )
    for row in ipv6.splitlines():
        fields = row.split()
        # Linux includes unreachable default routes (no RTF_UP) on lo.
        require(len(fields) == 10 and fields[-1] == "lo")
        destination, prefix, flags = fields[0], int(fields[1], 16), int(fields[8], 16)
        require(not flags & 1 or (destination == "0" * 31 + "1" and prefix == 128))
        require(fields[4] == "0" * 32)
    return namespace


def validate_container(
    info: dict,
    image: dict,
    network: str,
    mounts: dict[str, tuple[Path, bool]],
    user: str,
) -> None:
    """Enforce exact mounts/environment and restrictive host/network settings."""
    host, config = info["HostConfig"], info["Config"]
    require(info["State"]["Running"] and info["Image"] == image["Id"])
    require(host["NetworkMode"] == network and config["User"] == user)
    require(host["ReadonlyRootfs"] and not host["Privileged"])
    require(host["CapDrop"] == ["ALL"] and not host["CapAdd"])
    require("no-new-privileges=true" in host["SecurityOpt"])
    require(
        not host["Devices"]
        and not host.get("DeviceRequests")
        and not host.get("DeviceCgroupRules")
    )
    require(
        host["PidMode"] == ""
        and host["IpcMode"] == "private"
        and not host.get("UTSMode")
        and host.get("CgroupnsMode") != "host"
    )
    require(
        not host["PortBindings"]
        and not host["PublishAllPorts"]
        and not host["ExtraHosts"]
        and not host["Links"]
    )
    require(
        not host["Dns"]
        and not host["DnsOptions"]
        and not host["DnsSearch"]
        and not host.get("VolumesFrom")
    )
    require(
        host["PidsLimit"] == 256
        and host["Memory"] == 3 * 1024**3
        and host["NanoCpus"] == 2_000_000_000
    )
    require(
        host["RestartPolicy"]["Name"] == "no"
        and host["Tmpfs"] == {"/tmp": "rw,noexec,nosuid,size=128m,mode=1777"}
    )
    require(
        not info["NetworkSettings"]["Ports"]
        or all(value is None for value in info["NetworkSettings"]["Ports"].values())
    )
    networks = info["NetworkSettings"]["Networks"]
    require(set(networks) == ({"none"} if network == "none" else set()))
    require(
        all(
            not value.get("IPAddress")
            and not value.get("GlobalIPv6Address")
            and not value.get("Gateway")
            and not value.get("IPv6Gateway")
            for value in networks.values()
        )
    )
    observed = {}
    for mount in info["Mounts"]:
        if mount["Type"] == "tmpfs":
            require(mount["Destination"] == "/tmp" and mount["RW"])
            continue
        require(mount["Type"] == "bind" and mount["Propagation"] == "rprivate")
        observed[mount["Destination"]] = (Path(mount["Source"]), mount["RW"])
    require(observed == mounts)
    expected_env = dict(item.split("=", 1) for item in image["Config"].get("Env", []))
    require(expected_env.keys() <= ENV_KEYS)
    require(
        not any(
            re.search(r"token|password|secret|credential|proxy", key, re.I)
            for key in expected_env
        )
    )
    expected_env.update(HOME="/tmp", TMPDIR="/tmp", PYTHONDONTWRITEBYTECODE="1")
    require(config["Env"] is not None and len(config["Env"]) == len(expected_env))
    require(dict(item.split("=", 1) for item in config["Env"]) == expected_env)


def sanitize_smoke(value: dict, stage: str) -> dict:
    """Copy only explicitly asserted synthetic observations, never native responses."""
    require(stage in {"A", "B", "restored-A"})
    require(
        set(value)
        == {
            "identity",
            "window",
            "features",
            "closed_zero",
            "nonclosed_unknown",
            "open_1_received",
            "reload_identity",
            "terminal_position",
            "restored_retained_before_publish",
        }
    )
    require(value["features"] == 240)
    require(value["terminal_position"] == ("open" if stage == "B" else "closed"))
    require(value["restored_retained_before_publish"] is (stage == "restored-A"))
    for key in (
        "window",
        "closed_zero",
        "nonclosed_unknown",
        "open_1_received",
        "reload_identity",
    ):
        require(value[key] is True)
    identity = value["identity"]
    require(
        set(identity)
        == {"id", "entity_id", "unique_id", "config_entry_id", "device_id"}
    )
    require(identity["unique_id"] == "offline_serial_cover")
    require(
        all(
            isinstance(text, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", text)
            for text in identity.values()
        )
    )
    return {
        "identity_sha256": hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode()
        ).hexdigest(),
        **{key: value[key] for key in value if key != "identity"},
    }


class Sandbox:
    """Own only exact job-created IDs and one freshly created scratch tree."""

    def __init__(self, root: Path):
        """Initialize inert bookkeeping, without executing Docker."""
        self.root = root
        self.ids = []
        self.specs = []
        self.pending_names = []
        self.namespace = None

    def create(
        self,
        image: dict,
        network: str,
        mounts: dict[str, tuple[Path, bool]],
        user: str,
        command: list[str],
    ) -> str:
        """Create stopped containers, record ownership, then start only inert PID 1."""
        args = [
            "docker",
            "create",
            "--pull=never",
            "--network",
            network,
            "--user",
            user,
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            "--ipc=private",
            "--pids-limit=256",
            "--memory=3g",
            "--cpus=2",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=128m,mode=1777",
            "--env=HOME=/tmp",
            "--env=TMPDIR=/tmp",
            "--env=PYTHONDONTWRITEBYTECODE=1",
        ]
        for destination, (source, writable) in mounts.items():
            args += [
                "--mount",
                f"type=bind,src={source},dst={destination}"
                + ("" if writable else ",readonly"),
            ]
        args += ["--entrypoint", command[0], image["Id"], *command[1:]]
        cidfile = self.root / f"container-{len(self.ids)}.cid"
        name = f"{self.root.name}-{len(self.ids)}"
        self.pending_names.append(name)
        args[2:2] = [
            "--cidfile",
            str(cidfile),
            "--name",
            name,
            "--label",
            f"io.smarwi.acceptance={self.root.name}",
        ]
        try:
            container = run(*args)
        finally:
            # A timed-out create may still have created the container.
            if cidfile.exists():
                created = cidfile.read_text().strip()
                require(ID.fullmatch(created))
                self.ids.append(created)
                self.pending_names.remove(name)
        require(ID.fullmatch(container) and self.ids[-1] == container)
        self.specs.append((container, image, network, mounts, user))
        run("docker", "start", container)
        return container

    def preflight(self) -> dict:
        """Recheck both containers and their unchanged exact shared namespace."""
        namespaces = []
        for container, image, network, mounts, user in self.specs:
            info = json.loads(run("docker", "inspect", container))[0]
            validate_container(info, image, network, mounts, user)
            require(
                info["Path"] == ("python3" if container == self.ids[0] else "/bin/sh")
            )
            for source, _ in mounts.values():
                regular_tree(source)
            require(
                run("docker", "exec", container, "/bin/sh", "-c", "id -u; id -g")
                == user.replace(":", "\n")
            )
            security = run(
                "docker", "exec", container, "/bin/sh", "-c", "cat /proc/self/status"
            )
            fields = dict(line.split(":", 1) for line in security.splitlines())
            require(
                all(
                    int(fields[key].strip(), 16) == 0
                    for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
                )
            )
            require(fields["NoNewPrivs"].strip() == "1")
            namespaces.append(
                network_observation(
                    run("docker", "exec", container, "/bin/sh", "-c", NETWORK_PROBE)
                )
            )
        require(len(namespaces) == 2 and namespaces[0] == namespaces[1])
        if self.namespace is None:
            self.namespace = namespaces[0]
        require(namespaces[0] == self.namespace)
        return {
            "namespace_identical_unchanged": True,
            "only_loopback": True,
            "no_external_routes": True,
            "exact_network_modes": True,
            "mount_environment_allowlist": True,
            "nonroot_readonly_no_caps": True,
        }

    def cleanup(self) -> dict:
        """Remove only owned IDs and scratch, trying all resources after a failure."""
        results = []
        unresolved_create = False
        for name in self.pending_names:
            try:
                info = json.loads(run("docker", "inspect", name))[0]
                require(
                    info["Name"] == "/" + name
                    and info["Config"]["Labels"]["io.smarwi.acceptance"]
                    == self.root.name
                )
                require(ID.fullmatch(info["Id"]))
                self.ids.append(info["Id"])
            except (
                OSError,
                subprocess.SubprocessError,
                Blocked,
                ValueError,
                KeyError,
                IndexError,
                TypeError,
            ):
                # Missing inspect cannot prove an ambiguous create never completed.
                unresolved_create = True
        for container in reversed(self.ids):
            try:
                require(ID.fullmatch(container))
                run("docker", "rm", "--force", "--volumes", container)
                # Inspect failure alone is not proof of absence: list exact IDs too.
                remaining = run(
                    "docker", "ps", "--all", "--no-trunc", "--format", "{{.ID}}"
                )
                results.append(container not in remaining.splitlines())
            except (OSError, subprocess.SubprocessError, Blocked):
                results.append(False)
        try:
            shutil.rmtree(self.root)
            results.append(not self.root.exists())
        except OSError:
            results.append(False)
        return {
            "status": "passed" if all(results) and not unresolved_create else "failed",
            "unresolved_create": unresolved_create,
            "containers_removed": sum(results[:-1]),
            "scratch_removed": results[-1],
        }


def packages(root: Path) -> dict:
    """Use the current unchanged builder on clean exact tracked A/B checkouts."""
    require(
        run("git", "-C", str(ROOT), "show", f"{B}:scripts/build_release.py")
        == (ROOT / "scripts/build_release.py").read_text().strip()
    )
    result = {}
    original = build_release.ROOT
    try:
        for label, commit in (("A", A), ("B", B)):
            checkout = root / ("source-" + label)
            run(
                "git",
                "clone",
                "--quiet",
                "--shared",
                "--no-checkout",
                str(ROOT),
                str(checkout),
            )
            run("git", "-C", str(checkout), "checkout", "--quiet", "--detach", commit)
            require(run("git", "-C", str(checkout), "rev-parse", "HEAD") == commit)
            require(not run("git", "-C", str(checkout), "status", "--porcelain"))
            output = root / label / "smarwi.zip"
            build_release.ROOT = checkout
            build_release.build_release(output, "0.4.0.dev0")
            license_bytes = (checkout / "LICENSE").read_bytes()
            members = archive_members(output, license_bytes)
            for name, content in members.items():
                source = (
                    checkout / "LICENSE"
                    if name == "LICENSE"
                    else checkout / "custom_components/smarwi" / name
                )
                require(source.read_bytes() == content)
            result[label] = {
                "source": commit,
                "archive_sha256": sha(output),
                "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
            }
        require(result["A"]["license_sha256"] == result["B"]["license_sha256"])
        require(
            (root / "source-A/custom_components/smarwi/manifest.json").read_bytes()
            == (root / "source-B/custom_components/smarwi/manifest.json").read_bytes()
        )
    finally:
        build_release.ROOT = original
    return result


def restore_contents(source: Path, target: Path) -> None:
    """Restore all stopped-state bytes while preserving the bind-mounted root inode."""
    regular_tree(source)
    regular_tree(target)
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(source, target, dirs_exist_ok=True)
    require(regular_tree(source) == regular_tree(target))


def acquire_images() -> list[dict]:
    """Resolve stock tags before runtime and use only immutable local IDs thereafter."""
    images = []
    for tag in IMAGES:
        run("docker", "pull", tag, timeout=600)
        info = json.loads(run("docker", "image", "inspect", tag))[0]
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", info["Id"]))
        require(info["Os"] == "linux" and info["Architecture"] == "amd64")
        digests = [
            d
            for d in info["RepoDigests"]
            if d.startswith(tag.rsplit(":", 1)[0] + "@") and DIGEST.fullmatch(d)
        ]
        require(len(digests) == 1)
        pinned = json.loads(run("docker", "image", "inspect", digests[0]))[0]
        require(pinned["Id"] == info["Id"])
        info["acceptance_digest"] = digests[0]
        images.append(info)
    return images


def lifecycle(sandbox: Sandbox, images: list[dict], report: dict) -> None:
    """Run the single approved same-version replacement/checkpoint recovery sequence."""
    root = sandbox.root
    config, broker = root / "config", root / "broker"
    inputs = root / "input"
    inputs.mkdir()
    shutil.copyfile(ROOT / "scripts/hosted_runtime.py", inputs / "runtime.py")
    for path in (config, broker / "config", broker / "data", broker / "log"):
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
    (config / "configuration.yaml").write_text("""homeassistant:
  name: Synthetic acceptance
  latitude: 0
  longitude: 0
  elevation: 0
  unit_system: metric
  time_zone: UTC
  country: GB
http:
  server_host: 127.0.0.1
api:
websocket_api:
config:
onboarding:
""")
    (broker / "config/mosquitto.conf").write_text(
        "listener 1883 127.0.0.1\nallow_anonymous true\npersistence true\npersistence_location /mosquitto/data/\nlog_dest file /mosquitto/log/broker-private.log\n"
    )
    license_bytes = (root / "source-A/LICENSE").read_bytes()
    report["packages"]["A"]["installed_sha256"] = install(
        root / "A/smarwi.zip", config, license_bytes
    )
    require(os.getuid() > 0 and os.getgid() > 0)
    user = f"{os.getuid()}:{os.getgid()}"
    ha = sandbox.create(
        images[0],
        "none",
        {"/input": (inputs, False), "/config": (config, True)},
        user,
        ["python3", "-P", "/input/runtime.py", "inert"],
    )
    mosquitto = sandbox.create(
        images[1],
        "container:" + ha,
        {
            "/mosquitto/config": (broker / "config", False),
            "/mosquitto/data": (broker / "data", True),
            "/mosquitto/log": (broker / "log", True),
        },
        user,
        [
            "/bin/sh",
            "-c",
            "trap 'exit 0' TERM INT; while :; do sleep 60 & wait $!; done",
        ],
    )
    report["containment"] = sandbox.preflight()
    for container in (ha, mosquitto):
        for table in ("tcp", "tcp6", "udp", "udp6"):
            require(
                len(
                    run(
                        "docker",
                        "exec",
                        container,
                        "/bin/sh",
                        "-c",
                        f"cat /proc/net/{table}",
                    ).splitlines()
                )
                == 1
            )
    report["containment"]["no_preflight_listeners"] = True
    # Inert processes are the only processes before this dependency gate.
    versions = json.loads(
        run("docker", "exec", ha, "python3", "-P", "/input/runtime.py", "dependencies")
    )
    require(
        set(versions)
        == {"homeassistant", "paho-mqtt", "aiohttp", "aiohasupervisor", "python"}
    )
    require(all(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", v) for v in versions.values()))
    broker_version = run("docker", "exec", mosquitto, "/usr/sbin/mosquitto", "-h")
    match = re.search(r"mosquitto version (2\.0\.[0-9]+)", broker_version)
    if match is None:
        raise Blocked("broker version not established")
    report["versions"].update(versions, mosquitto=match[1])
    baseline = None
    checkpoint = root / "checkpoint"

    def stop_apps():
        run(
            "docker",
            "exec",
            ha,
            "python3",
            "-P",
            "/input/runtime.py",
            "stop",
            timeout=110,
        )
        run("docker", "exec", mosquitto, "/bin/sh", "-c", BROKER_STOP)
        deadline = time.monotonic() + 30
        while not (broker / "data/acceptance.exit").exists():
            require(time.monotonic() < deadline)
            time.sleep(0.2)
        require((broker / "data/acceptance.exit").read_text() == "0")
        require(
            not run(
                "docker",
                "exec",
                ha,
                "/bin/sh",
                "-c",
                "test ! -e /proc/$(cat /config/acceptance.pid)/cmdline",
            )
        )
        sandbox.preflight()

    for row in report["stages"]:
        stage = row["stage"]
        row["containment"] = sandbox.preflight()
        run("docker", "exec", "--detach", mosquitto, "/bin/sh", "-c", BROKER_START)
        # The native MQTT flow and client establish actual broker readiness.
        run(
            "docker",
            "exec",
            "--detach",
            ha,
            "python3",
            "-P",
            "/input/runtime.py",
            "application",
        )
        row["phase"] = "native-client"
        try:
            output = run(
                "docker",
                "exec",
                ha,
                "python3",
                "-P",
                "/input/runtime.py",
                "smoke",
                stage,
                timeout=480,
            )
        except subprocess.CalledProcessError as error:
            failure = json.loads(error.stdout)
            require(set(failure) == {"status", "phase"})
            require(
                failure["phase"]
                in {"startup", "authentication", "configuration", "assertions"}
            )
            require(
                failure["status"]
                == ("failed" if failure["phase"] == "assertions" else "blocked")
            )
            row.update(failure)
            raise Blocked("native client did not complete") from None
        row["status"] = "failed"
        row["phase"] = "assertions"
        observed = sanitize_smoke(json.loads(output), stage)
        if baseline is None:
            baseline = observed["identity_sha256"]
        require(observed["identity_sha256"] == baseline)
        row.update(observed)
        stop_apps()
        row["installed_sha256"] = tree_hash(config / "custom_components/smarwi")
        require(
            row["installed_sha256"]
            == report["packages"]["B" if stage == "B" else "A"]["installed_sha256"]
        )
        row["clean_application_stop"] = True
        row["status"] = "passed"
        if stage == "A":
            checkpoint.mkdir()
            for name, path in (("config", config), ("broker", broker)):
                regular_tree(path)
                shutil.copytree(path, checkpoint / name)
            require(
                (checkpoint / "broker/data/mosquitto.db").is_file()
                and (checkpoint / "broker/data/mosquitto.db").stat().st_size > 0
            )
            report["checkpoint"] = {
                "status": "passed",
                "broker_persistence_file": True,
                **{
                    name + "_sha256": tree_hash(checkpoint / name)
                    for name in ("config", "broker")
                },
            }
            report["packages"]["B"]["installed_sha256"] = install(
                root / "B/smarwi.zip", config, license_bytes
            )
        elif stage == "B":
            # Preserve bind-mounted directory inodes; restore their complete contents.
            restore_contents(checkpoint / "config", config)
            # These three broker directories are separately bind-mounted.
            require(
                {path.name for path in broker.iterdir()} == {"config", "data", "log"}
            )
            for name in ("config", "data", "log"):
                restore_contents(checkpoint / "broker" / name, broker / name)
            for name, path in (("config", config), ("broker", broker)):
                require(tree_hash(path) == report["checkpoint"][name + "_sha256"])
            report["restore"] = {
                "status": "passed",
                "mechanism": "matching-full-stopped-sandbox-checkpoint",
                "config_exact": True,
                "broker_exact": True,
                "integration_A_exact": regular_tree(config / "custom_components/smarwi")
                == regular_tree(checkpoint / "config/custom_components/smarwi"),
            }
    report["containment_final"] = sandbox.preflight()


def main() -> None:
    """Gate hosted execution, sanitize evidence and always dispose exact resources."""
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    require(
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    )
    require(
        os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and os.environ.get("RUNNER_OS") == "Linux"
        and os.environ.get("RUNNER_ARCH") == "X64"
    )
    require(Path("/etc/os-release").read_text().find('VERSION_ID="24.04"') >= 0)
    evidence = ROOT / "hosted-evidence"
    evidence.mkdir(exist_ok=False)
    report = {
        "status": "blocked",
        "sources": {"A": A, "B": B},
        "stages": [
            {"stage": stage, "status": "blocked", "phase": "not-started"}
            for stage in ("A", "B", "restored-A")
        ],
        "checkpoint": {"status": "blocked"},
        "restore": {"status": "blocked"},
        "versions": {},
        "firmware": "not-applicable-synthetic-only",
    }
    scratch = Path(tempfile.mkdtemp(prefix="smarwi-hosted-"))
    sandbox = Sandbox(scratch)
    success = False
    try:
        require(
            not os.environ.get("DOCKER_HOST")
            and not os.environ.get("DOCKER_TLS_VERIFY")
        )
        endpoint = json.loads(
            run(
                "docker",
                "context",
                "inspect",
                "--format",
                "{{json .Endpoints.docker.Host}}",
            )
        )
        require(endpoint == "unix:///var/run/docker.sock")
        daemon = json.loads(run("docker", "info", "--format", "{{json .}}"))
        require(
            daemon["Name"] == os.uname().nodename
            and daemon["OSType"] == "linux"
            and daemon["Architecture"] == "x86_64"
        )
        require("Ubuntu 24.04" in daemon["OperatingSystem"])
        report["runner"] = {
            "os": "ubuntu-24.04",
            "architecture": "x86_64",
            "local_docker_daemon": True,
            "hosted_environment_gate": True,
        }
        docker = run("docker", "version", "--format", "{{.Server.Version}}")
        require(
            re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", docker)
            and int(docker.split(".")[0]) >= 23
        )
        report["versions"]["docker"] = docker
        report["packages"] = packages(scratch)
        images = acquire_images()
        report["images"] = [
            {
                "digest": image["acceptance_digest"],
                "id": image["Id"],
                "platform": "linux/amd64",
            }
            for image in images
        ]
        lifecycle(sandbox, images, report)
        success = True
    except Exception as error:
        # Never print exceptions, raw inspect, HTTP, broker logs, or storage.
        report["failure_location"] = failure_location(error)
        report["status"] = (
            "failed"
            if any(row["status"] == "failed" for row in report["stages"])
            else "blocked"
        )
    finally:
        report["cleanup"] = sandbox.cleanup()
        success = success and report["cleanup"]["status"] == "passed"
        if success:
            report["status"] = "passed"
        elif report["cleanup"]["status"] != "passed":
            report["status"] = "failed"
        (evidence / "report.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n"
        )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
