#!/usr/bin/env python3
"""Read the AWS IoT "thing shadow" of your own air conditioner (read-only).

The Smart Life app reads the unit's live state from AWS IoT, not from the REST
status document, which can lag by minutes. This script does the same read once so
we can see what it contains. Standard library only:

    python3 tools/probe_shadow.py <refresh_token>

Steps (all taken from the app's own configuration and code, see docs/protocol.md):
1. refresh the Cognito ID token (same as tools/probe_status.py),
2. trade it for temporary AWS credentials through the app's Cognito identity pool,
3. sign (SigV4) a GET of ``/things/<name>/shadow`` on the IoT data endpoint.

The temporary credentials are never printed. Device ids and topics are masked, so
the output is safe to paste.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0] if "/" in __file__ else ".")
from probe_status import API, EMBEDDED_ID, http, mask, refresh  # noqa: E402

REGION = "eu-west-1"
# Public values from the app's res/raw/amplifyconfiguration.json and its IoT client.
IDENTITY_POOL = "eu-west-1:bb1ff9a2-6db0-4f3f-b630-62a9fc3bfbda"
USER_POOL = "cognito-idp.eu-west-1.amazonaws.com/eu-west-1_EgDdXOayO"
IOT_HOST = "aa8u5ipzaqyfu-ats.iot.eu-west-1.amazonaws.com"


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sigv4_headers(method: str, host: str, path: str, creds: dict, *, region: str,
                  service: str, now: datetime.datetime | None = None, payload: bytes = b"") -> dict:
    """Return the headers for an AWS Signature Version 4 request without a query string."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    headers = {"host": host, "x-amz-date": amz_date}
    if creds.get("SessionToken"):
        headers["x-amz-security-token"] = creds["SessionToken"]
    signed = ";".join(sorted(headers))
    canonical = "\n".join([
        method, urllib.parse.quote(path, safe="/-_.~"), "",
        "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)), signed,
        hashlib.sha256(payload).hexdigest(),
    ])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + creds["SecretKey"]).encode(), day), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={creds['AccessKeyId']}/{scope}, SignedHeaders={signed}, Signature={signature}"
    )
    return headers


def cognito(target: str, body: dict) -> dict:
    status, text = http(
        "POST", f"https://cognito-identity.{REGION}.amazonaws.com/",
        {"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": f"AWSCognitoIdentityService.{target}"},
        json.dumps(body).encode(),
    )
    if status != 200:
        sys.exit(f"Cognito identity call {target} failed (HTTP {status}): {mask_text(text)[:300]}")
    return json.loads(text)


def aws_credentials(id_token: str) -> dict:
    logins = {USER_POOL: id_token}
    identity = cognito("GetId", {"IdentityPoolId": IDENTITY_POOL, "Logins": logins})["IdentityId"]
    return cognito("GetCredentialsForIdentity", {"IdentityId": identity, "Logins": logins})["Credentials"]


def mask_text(text: str) -> str:
    text = EMBEDDED_ID.sub("<id>", text)
    text = re.sub(r"\b\d{12}\b", "<account>", text)
    return re.sub(r"[0-9a-fA-F-]{16,}", "<id>", text)


def shape(topic: str) -> str:
    """Show a topic's structure with id-like segments hidden."""
    return "/".join(p if not (len(p) >= 8 and re.search(r"\d", p)) else "<id>" for p in topic.split("/"))


def get_shadow(creds: dict, name: str) -> tuple[int, str]:
    path = f"/things/{name}/shadow"
    headers = sigv4_headers("GET", IOT_HOST, path, creds, region=REGION, service="iotdata")
    return http("GET", f"https://{IOT_HOST}{path}", headers)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    id_token = refresh(sys.argv[1].strip())
    status, text = http("GET", API + "v1.0/homes", {"Token": id_token})
    homes = json.loads(text) if status == 200 else {}
    home_id = next((h.get("homeId") or h.get("id") for h in (homes.get("items") or []) if isinstance(h, dict)), None)
    status, text = http("GET", API + f"v1.0/homes/{home_id}/devices", {"Token": id_token})
    try:
        devices = [d for d in json.loads(text)["items"]["homeappliances"] if d.get("deviceType") == "AC"]
    except (ValueError, KeyError, TypeError):
        devices = []
    if not devices:
        sys.exit(f"No air conditioner found (devices call returned HTTP {status}).")
    creds = aws_credentials(id_token)
    print("Got temporary AWS credentials from the Cognito identity pool.")

    for dev in devices[:1]:
        names: list[str] = [dev["deviceId"]]
        for key in ("pubTopic", "subTopic"):
            topic = dev.get(key) or ""
            print(f"{key} shape: {shape(topic) or '(none)'}")
            names += [p for p in topic.split("/") if len(p) >= 8 and re.search(r"\d", p)]
        for name in dict.fromkeys(names):
            code, body = get_shadow(creds, name)
            label = "deviceId" if name == dev["deviceId"] else "topic segment"
            print(f"\n### shadow of {label} ({shape(name)})  -> HTTP {code}")
            try:
                print(json.dumps(mask(json.loads(body)), indent=1, ensure_ascii=False)[:6000])
            except ValueError:
                print(mask_text(body)[:400])


if __name__ == "__main__":
    main()
