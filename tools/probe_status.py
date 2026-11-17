#!/usr/bin/env python3
"""Dump what Vestel's cloud returns for your own account, with secrets removed.

Run it once on your own computer (needs only the standard library):

    python3 tools/probe_status.py <refresh_token>

The refresh token is the one Home Assistant stores for this integration
(config entry data, ``refresh_token``). The script sends it only to Vestel's
login host, then prints the responses of the calls the official app makes
(see docs/protocol.md). Tokens, e-mail addresses and device ids are masked in
the output, so it is safe to paste into the integration's issue tracker.

Only the endpoints documented from the Smart Life APK are called, read-only.
"""
from __future__ import annotations

import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://hosted-kimlik.vestel.com.tr/oauth2/token"
API = "https://sh-native-api.homevsmart.com/"
# Public app-client values from the app's res/raw/amplifyconfiguration.json.
CLIENT_ID = "6tl8koi5fis9j7i3u3jnv15vr7"
CLIENT_SECRET = "mc4j2r13mctk8u46poaic9snm83khk458c8a1uupk6sqoqar90c"

SECRET_KEYS = re.compile(
    r"token|secret|password|mail|phone|mac$|serial|ssid|devicename|username|roomname|homename|deviceid|topic|usn", re.I
)
EMBEDDED_ID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[A-Z]{2,3}_[A-Z_]*[0-9a-fA-F]{16,}"
)
ID_LIKE = re.compile(r"^[0-9a-fA-F-]{16,}$")


def mask(value, key=""):
    if isinstance(value, dict):
        return {k: mask(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [mask(v, key) for v in value]
    if isinstance(value, str):
        if SECRET_KEYS.search(key) or ID_LIKE.match(value) or "@" in value:
            return "<masked>"
        return EMBEDDED_ID.sub("<id>", value)
    return value


def http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, body
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def refresh(refresh_token: str) -> str:
    basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    body = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": refresh_token}
    ).encode()
    status, text = http(
        "POST",
        TOKEN_URL,
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {basic}"},
        body,
    )
    if status != 200:
        sys.exit(f"Token refresh failed ({status}). The refresh token may have expired.")
    return json.loads(text)["id_token"]


def call(label: str, path: str, token: str):
    status, text = http("GET", API + path, {"Token": token, "Accept-Charset": "utf-8"})
    try:
        payload = mask(json.loads(text))
    except ValueError:
        payload = text[:300]
    print(f"\n### {label}  GET {EMBEDDED_ID.sub('<id>', re.sub(r'[0-9a-fA-F-]{16,}', '<id>', path))}  -> HTTP {status}")
    print(json.dumps(payload, indent=1, ensure_ascii=False)[:6000])


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    token = refresh(sys.argv[1].strip())

    status, text = http("GET", API + "v1.0/homes", {"Token": token})
    homes = json.loads(text) if status == 200 else {}
    print(f"### homes -> HTTP {status}; keys: {sorted(homes)[:10] if isinstance(homes, dict) else type(homes)}")
    home_ids = [h.get("homeId") or h.get("id") for h in (homes.get("items") or homes.get("homes") or [])
                if isinstance(h, dict)]
    for home_id in home_ids[:1]:
        call("devices of first home", f"v1.0/homes/{home_id}/devices", token)
        s, t = http("GET", API + f"v1.0/homes/{home_id}/devices", {"Token": token})
        try:
            items = json.loads(t)["items"]["homeappliances"]
        except (ValueError, KeyError, TypeError):
            items = []
        for dev in items:
            uuid = dev.get("deviceId")
            if not uuid:
                continue
            print(f"\n===== {dev.get('deviceType')} / {dev.get('variant')} / {dev.get('wifiCardType')} =====")
            call("last status", f"v1.0/homeappliances/{uuid}/status/all", token)
            call("HCA status", f"v1.0/appliances/{uuid}/status", token)
            call("legacy registers", f"v1.0/homeappliances/legacy/status?uuid={uuid}", token)
            call("HCA discovery", f"v1.0/appliances/{uuid}/discovery", token)


if __name__ == "__main__":
    main()
