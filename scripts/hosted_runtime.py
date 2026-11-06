#!/usr/bin/env python3
"""Sandbox-only application control and native HA/MQTT acceptance (never on import)."""

import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

CONFIG = Path("/config")
ORIGIN = "http://127.0.0.1:8123"
TOPIC = "ion/offline_remote/%offline_serial"
STATUS = "cid:Offline fixture\nfix:1\npos:{}\nro:0\ns:250"


def require(condition: object) -> None:
    """Abort without disclosing native responses or credentials."""
    if not condition:
        raise RuntimeError("sandbox assertion failed")


def dependencies() -> dict[str, str]:
    """Check installed distributions without installing anything."""
    expected = {
        "homeassistant": "2026.11.0",
        "paho-mqtt": "2.1.0",
        "aiohttp": "3.14.5",
        "aiohasupervisor": "0.8.1",
    }
    actual = {name: importlib.metadata.version(name) for name in expected}
    require(actual == expected)
    # Import the actual clients/flow dependencies before either listener starts.
    import aiohttp  # noqa: F401, PLC0415
    import paho.mqtt.client  # noqa: F401, PLC0415
    import homeassistant.components.mqtt.config_flow  # noqa: F401, PLC0415

    return {**actual, "python": sys.version.split()[0]}


def application() -> None:
    """Track a foreground stock HA process; SIGTERM uses HA's native shutdown."""
    exit_file = CONFIG / "acceptance.exit"
    exit_file.unlink(missing_ok=True)
    with (CONFIG / "acceptance-private.log").open("ab") as log:
        process = subprocess.Popen(
            [
                "python3",
                "-P",
                "-m",
                "homeassistant",
                "--config",
                "/config",
                "--skip-pip",
            ],
            stdout=log,
            stderr=log,
        )
        (CONFIG / "acceptance.pid").write_text(str(process.pid))
        code = process.wait()
        exit_file.write_text(str(code))


def stop() -> None:
    """Signal only the tracked HA application and require a clean bounded exit."""
    pid = int((CONFIG / "acceptance.pid").read_text())
    command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    require(
        command[1:]
        == [b"-P", b"-m", b"homeassistant", b"--config", b"/config", b"--skip-pip", b""]
    )
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 90
    while not (CONFIG / "acceptance.exit").exists():
        require(time.monotonic() < deadline)
        time.sleep(0.2)
    require((CONFIG / "acceptance.exit").read_text() == "0")


async def smoke(progress: dict, stage: str) -> dict:
    """Use native onboarding, config flows, registry, reload, states and service APIs."""
    import aiohttp  # noqa: PLC0415
    import paho.mqtt.client as mqtt  # noqa: PLC0415
    from paho.mqtt.enums import CallbackAPIVersion  # noqa: PLC0415

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10), trust_env=False
    ) as session:
        token = None

        async def request(method, path, data=None, *, form=False):
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            kwargs = {"data" if form else "json": data} if data is not None else {}
            async with session.request(
                method, ORIGIN + path, headers=headers, **kwargs
            ) as response:
                require(response.status == 200)
                return await response.json()

        async def until(operation, predicate):
            deadline = time.monotonic() + 120
            while True:
                try:
                    value = await operation()
                    if predicate(value):
                        return value
                except (aiohttp.ClientError, TimeoutError, RuntimeError):
                    pass
                require(time.monotonic() < deadline)
                await asyncio.sleep(0.25)

        await until(
            lambda: request("GET", "/api/onboarding"),
            lambda value: isinstance(value, list),
        )
        progress["phase"] = "authentication"
        private = CONFIG / "acceptance-auth.json"
        if private.exists():
            auth = json.loads(private.read_text())
            grant = {
                "grant_type": "refresh_token",
                "refresh_token": auth["refresh_token"],
                "client_id": ORIGIN,
            }
        else:
            onboarding = await request(
                "POST",
                "/api/onboarding/users",
                {
                    "name": "Synthetic acceptance",
                    "username": "offline_acceptance",
                    "password": secrets.token_urlsafe(32),
                    "client_id": ORIGIN,
                    "language": "en",
                },
            )
            grant = {
                "grant_type": "authorization_code",
                "code": onboarding["auth_code"],
                "client_id": ORIGIN,
            }
        auth = await request("POST", "/auth/token", grant, form=True)
        token = auth["access_token"]
        if "refresh_token" in auth:
            private.write_text(json.dumps({"refresh_token": auth["refresh_token"]}))
            private.chmod(0o600)
        core = await until(
            lambda: request("GET", "/api/config"),
            lambda value: value.get("state") == "RUNNING",
        )
        require(core["version"] == "2026.11.0")
        progress["phase"] = "configuration"

        async def flow(domain, step, fields):
            result = await request(
                "POST", "/api/config/config_entries/flow", {"handler": domain}
            )
            require(
                result["type"] == "form"
                and result["step_id"] == step
                and not result.get("errors")
            )
            result = await request(
                "POST", "/api/config/config_entries/flow/" + result["flow_id"], fields
            )
            require(result["type"] == "create_entry")

        entries = await request("GET", "/api/config/config_entries/entry")
        if not any(entry["domain"] == "mqtt" for entry in entries):
            await flow(
                "mqtt",
                "broker",
                {
                    "broker": "127.0.0.1",
                    "port": 1883,
                    "protocol": "5",
                    "other_settings": {
                        "set_client_cert": False,
                        "set_ca_cert": "off",
                        "transport": "tcp",
                    },
                },
            )
        if not any(entry["domain"] == "smarwi" for entry in entries):
            await flow("smarwi", "user", {"remote_id": "offline_remote"})
        entries = await until(
            lambda: request("GET", "/api/config/config_entries/entry"),
            lambda value: all(
                sum(e["domain"] == domain and e["state"] == "loaded" for e in value)
                == 1
                for domain in ("mqtt", "smarwi")
            ),
        )
        entry_id = next(e["entry_id"] for e in entries if e["domain"] == "smarwi")
        async with session.ws_connect(
            ORIGIN + "/api/websocket", receive_timeout=10
        ) as ws:
            require((await ws.receive_json())["type"] == "auth_required")
            await ws.send_json({"type": "auth", "access_token": token})
            require((await ws.receive_json())["type"] == "auth_ok")
            sequence = 0

            async def registry():
                nonlocal sequence
                sequence += 1
                await ws.send_json(
                    {"id": sequence, "type": "config/entity_registry/list"}
                )
                result = await ws.receive_json()
                require(result["id"] == sequence and result["success"] is True)
                return [
                    e
                    for e in result["result"]
                    if e["config_entry_id"] == entry_id
                    and e["entity_id"].startswith("cover.")
                ]

            client = mqtt.Client(CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
            connected = asyncio.Event()
            subscribed = asyncio.Event()
            loop = asyncio.get_running_loop()
            commands = []
            retained_status = []

            def on_connect(c, u, f, reason, p):
                if reason == 0:
                    loop.call_soon_threadsafe(connected.set)

            def on_subscribe(c, u, mid, reasons, properties):
                if reasons and all(
                    reason == 0 or reason == 1 or reason == 2 for reason in reasons
                ):
                    loop.call_soon_threadsafe(subscribed.set)

            client.on_connect = on_connect
            client.on_subscribe = on_subscribe

            def received(c, u, message):
                if message.topic == TOPIC + "/cmd":
                    loop.call_soon_threadsafe(
                        commands.append, message.payload.decode("utf-8")
                    )
                elif message.topic == TOPIC + "/status" and message.retain:
                    loop.call_soon_threadsafe(
                        retained_status.append, message.payload.decode("utf-8")
                    )

            client.on_message = received
            require(client.connect("127.0.0.1", 1883, 30) == 0)
            client.loop_start()
            try:
                await asyncio.wait_for(connected.wait(), 10)
                require(
                    client.subscribe([(TOPIC + "/cmd", 2), (TOPIC + "/status", 1)])[0]
                    == 0
                )
                await asyncio.wait_for(subscribed.wait(), 10)

                async def publish(suffix, payload):
                    receipt = client.publish(
                        TOPIC + suffix, payload, qos=1, retain=True
                    )
                    await asyncio.to_thread(receipt.wait_for_publish, 10)
                    require(receipt.is_published())

                async def telemetry(position):
                    await publish("/online", "1")
                    await publish("/status", STATUS.format(position))

                progress["phase"] = "assertions"
                if stage == "restored-A":
                    await until(
                        lambda: asyncio.sleep(0, result=list(retained_status)),
                        lambda value: bool(value)
                        and all(payload == STATUS.format("c") for payload in value),
                    )
                else:
                    await telemetry("c")
                covers = await until(registry, lambda value: len(value) == 1)
                cover = covers[0]
                require(cover["unique_id"] == "offline_serial_cover")
                identity = {
                    key: cover[key]
                    for key in (
                        "id",
                        "entity_id",
                        "unique_id",
                        "config_entry_id",
                        "device_id",
                    )
                }
                entity_id = cover["entity_id"]

                async def state():
                    return await request("GET", "/api/states/" + entity_id)

                def valid(value, position):
                    attributes = value["attributes"]
                    return (
                        value["state"] not in ("unavailable", "unknown")
                        and attributes.get("device_class") == "window"
                        and attributes.get("supported_features") == 240
                        and attributes.get("current_tilt_position") == position
                    )

                await until(
                    state, lambda value: valid(value, 0) and value["state"] == "closed"
                )
                await telemetry("o")
                await until(
                    state, lambda value: valid(value, None) and value["state"] == "open"
                )
                commands.clear()
                await request(
                    "POST",
                    "/api/services/cover/set_cover_tilt_position",
                    {"entity_id": entity_id, "tilt_position": 1},
                )
                await until(
                    lambda: asyncio.sleep(0, result=list(commands)),
                    lambda value: value.count("open;1") == 1,
                )
                # Reload performs native unload/setup; then prove one registry and active cover.
                result = await request(
                    "POST", f"/api/config/config_entries/entry/{entry_id}/reload"
                )
                require(result.get("require_restart") is False)
                terminal = "open" if stage == "B" else "closed"
                await telemetry("o" if stage == "B" else "c")
                await until(
                    state,
                    lambda value: valid(value, None if stage == "B" else 0)
                    and value["state"] == terminal,
                )
                covers = await registry()
                require(
                    len(covers) == 1
                    and all(covers[0][key] == value for key, value in identity.items())
                )
                states = await request("GET", "/api/states")
                require(
                    [
                        s["entity_id"]
                        for s in states
                        if s["entity_id"].startswith("cover.")
                    ]
                    == [entity_id]
                )
                require(
                    commands.count("open;1") == 1
                    and all(command in ("lcfa", "open;1") for command in commands)
                )
                return {
                    "identity": identity,
                    "window": True,
                    "features": 240,
                    "closed_zero": True,
                    "nonclosed_unknown": True,
                    "open_1_received": True,
                    "reload_identity": True,
                    "terminal_position": terminal,
                    "restored_retained_before_publish": stage == "restored-A",
                }
            finally:
                client.disconnect()
                client.loop_stop()


def main() -> None:
    """Dispatch only explicit sandbox commands; suppress sensitive exception text."""
    command = ""
    progress = {"phase": "startup"}
    try:
        command = sys.argv[1]
        if command == "inert":
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            while True:
                signal.pause()
        elif command == "dependencies":
            signal.alarm(30)
            sys.stdout.write(json.dumps(dependencies()))
        elif command == "application":
            application()
        elif command == "stop":
            signal.alarm(110)
            stop()
        elif command == "smoke":
            # Bound even third-party client thread joins; no native mutation is retried.
            signal.alarm(450)
            stage = sys.argv[2]
            require(stage in {"A", "B", "restored-A"})
            sys.stdout.write(json.dumps(asyncio.run(smoke(progress, stage))))
        else:
            raise RuntimeError("unknown command")
    except Exception:
        if command == "smoke":
            sys.stdout.write(
                json.dumps(
                    {
                        "status": "failed"
                        if progress["phase"] == "assertions"
                        else "blocked",
                        "phase": progress["phase"],
                    }
                )
            )
        sys.stderr.write(
            "Sandbox check blocked/failed; private diagnostics remain disposable.\n"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
