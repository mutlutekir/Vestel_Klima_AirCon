# Vestel cloud protocol notes

Facts below were taken from the Vestel "Smart Life" / "Evin Aklı" Android app
(package `com.smarthome.core.main`, version 3.2413.29) by inspecting its
decompiled classes and bundled assets. Each item names where it came from.
Nothing here is copied from another open-source project.

## Authentication

- Cognito hosted UI at `hosted-kimlik.vestel.com.tr`, OAuth2 authorization code
  flow with PKCE, redirect `evinakli://signin`.
  Source: `res/raw/amplifyconfiguration.json` (`Auth.Default.OAuth`).
- Scopes: `profile phone openid email aws.cognito.signin.user.admin`. Same file.
- Token refresh: standard Cognito `/oauth2/token`, `grant_type=refresh_token`.
- App client id and secret are in the same file (see `const.py`).

## REST API

Base URL `https://sh-native-api.homevsmart.com/`
(`buildconfig/NetworkConfigImpl.java`). JSON bodies, `Content-Type: application/json; charset=utf-8`.

| Method | Path | Source |
|---|---|---|
| GET | `v1.0/homes` | `RetrofitMyHomeRestAPI` |
| GET | `v1.0/homes/{homeId}/devices` | same |
| POST | `v1.0/customer/devices/{uuid}/legacy/command` | same |
| GET | `v1.0/homeappliances/{uuid}/status/all` | `RequestPathAndParamsRest`; used for EV chargers and fridges. **Observed:** HTTP 400 `Device type is unsupported` for an AC |
| GET | `v1.0/appliances/{uuid}/discovery` | generic "HCA" API (`LockDeviceApi`) |
| GET | `v1.0/appliances/{uuid}/status` | same |
| POST | `v1.0/appliances/{uuid}/command` | same |

Auth header on REST calls: `Token: <Cognito ID token>`, plus `Accept-Charset: utf-8`
(`DefaultHeadersInterceptor`). A second interceptor sends the access token instead.

The device list response has `items.homeappliances[]` (`DevicesListModelWrapper`).
Each item has `deviceId`, `deviceType`, `deviceName`, `wifiCardType`, `variant`,
`oemBrand`, `isActive`, `roomId`, `mac`, ... (`DeviceItemModel`).

### Command request body

Fields (`DeviceCommandRequest`): `wifi_card_type`, `device_type`, `brand`, `message`.

- `brand` is the constant `"Vestel"` (`AWSInteractor.H0`).
- `device_type` and `wifi_card_type` come from the device record.
- `message` is the string `{"cmd" : "c:<uuid>,<NAME><VALUE>"}`
  (`CloudPublishToCommandMapper`), where `NAME` is the 7-letter command name and
  `VALUE` a zero-padded 5 digit decimal.

## Packing command values

`ACCloudDomainToCloudEntity.a()`: fields are listed from the least significant
one; each is written in binary padded to its width, the pieces are joined and
the result is printed as `%05d` decimal.

| Command | Fields, LSB first (width in bits) |
|---|---|
| `ACGENSI` | mode (3), fan speed (3) |
| `ACTEMOT` | temperature (4), auto-on hour (5), auto-on minute (6) |
| `ACFANPO` | turbo (1), vertical louver (3), horizontal louver (3), sleep (1), ionizer (1), eco (1) |
| `ACOFFTV` | auto-off hour (5), auto-off minute (6) |
| `ACQOFFT` | quick-off hour (5), minute (6) |
| `ACSTCLK` | clock hour (5), minute (6) |

Other command names seen in `ACCloudCommands`: `ACROOTE`, `ACERROR`, `ACVERSI`,
`ACUVSET`, `ACRGBON`, `ACRGBBR`, `ACRGBST`, `ACPOLPM`, `ACPOLVC`, `ACSAFRS`,
`ACPSCLP`, `ACOAFLP`, `ACERRTW`, `ACWARNG`, `ACEXERR`, `ACCMODE`.

The bundled capability files `assets/demo_ac_flora_*.json` list the same bit
positions and the value tables (mode 0-5, fan 0-5, louver off/1-6).
Note: they give the auto-off minute a width of 5, which disagrees with the 6 bits
the app itself uses when it packs `ACOFFTV`; the packing code is authoritative.

## Appliance families

`ACCloudCommands`, `WMCloudCommands`, `WDCloudCommands`, `TDCloudCommands`,
`DWCloudCommands`, `OVCloudCommands`, `RFCloudCommands`, `FDCloudCommands` list the
command names per family (AC, washing machine, washer-dryer, tumble dryer,
dishwasher, oven, refrigerator, fridge-freezer). They use the same message format
as above. `assets/demo_hca_*_{discovery,status}.json` show the generic HCA
discovery/status documents (`components[].settings[]` / `status[]` with keys such
as `Climate.HVAC.Setting.Mode`).

## Observed on a real account (tools/probe_status.py, Nov 2026)

AC with variant `FLORA#MELTEM#EB-`, wifi card `HM07`.

- Device item: `deviceId` `WG_AC_<hex>`, `deviceType` `AC`, `wifiCardType` `HM07`,
  `connected`, `variant`, `pubTopic`/`subTopic`. TVs are listed under `televisions`.
- `GET v1.0/appliances/{id}/status` answers
  `{"properties": {"settings": [...], "status": [...], "errors": [...], "commands": [...]}, "message": "Success.", "status": 200}`
  where every entry is `{"item": name, "value": v}`.
  - settings: `Mode` (PowerOff, Auto, Cooling, Heating, Dehumidifying, Ventilating),
    `Temperature` (degrees), `Fan.Speed` (Auto, Speed1-5), `Fan.VerticalSwing` /
    `Fan.HorizontalSwing` (Off, Pos1-Pos6), `Fan.Turbo`, `Fan.SleepMode`, `Fan.Ionizer`,
    `Fan.Eco`, `UVC`, `AutoOff.Hour/Minute/Cancel`, `AutoOn.*`, `QuickOffTime.*`, `Clock.*`.
  - status: `RoomTemperature`, `Wifi.SignalRSS`, `Connection.SignalRSS`, `Warning`,
    `SoftwareInfo.*`, `RemainingQuickOffTime.*`, `CurrentMode`.
  - `CurrentMode` keeps the last running mode while the unit is off (`Mode: PowerOff`,
    `CurrentMode: Heating`), so it cannot tell on from off; `Mode` can.
  - The document follows changes the unit reports itself (a remote-control change showed
    up in `Mode` and `Temperature` within minutes). After commands sent through
    `legacy/command` the unit changed state but `Mode` kept its old value.
  - errors: 18 booleans (`NoError`, `GasLeakageError`, ...).
  - A timer that is not set shows hour 31 (all five bits set).
- `GET v1.0/appliances/{id}/discovery` lists the settings with `commandName`, bit
  `position` and `length`, plus `displayWorkarounds` (for example horizontal swing is
  forced to `Off` in cooling and heating on this model).

## Live state through AWS IoT (from the APK; being verified)

The app does not rely on the REST status document for the unit's live state. It reads the
IoT thing shadow (`AWSIotDataClient.getThingShadow`) and subscribes to topics on
`aa8u5ipzaqyfu-ats.iot.eu-west-1.amazonaws.com`. Credentials come from the app's Cognito
identity pool (`amplifyconfiguration.json`, `CredentialsProvider/CognitoIdentity`), exchanged
for the Cognito ID token. The shadow's reported state is read from `state.reported.status`.
`tools/probe_shadow.py` performs one read. On a real unit the shadow only holds connectivity
data (`status: connected`, `wifiSwVersion`, ...), identical with the unit on and off, so the live
state has to come from MQTT. The app subscribes to `Vestel/<customerId>/<wifiCard>/<type>/<uuid>/from`
(and publishes to `.../to`); the device record also lists `.../fromJson` and `.../toJson`.
MQTT runs over WebSocket on port 443 with a SigV4-presigned `/mqtt` URL (service
`iotdevicegateway`), client id = Cognito identity id. `tools/probe_mqtt.py` listens to the topics.

## Not yet established

- The body of `POST v1.0/appliances/{uuid}/command` for appliances other than locks.
  Commands currently go through `legacy/command`, whose body is known.
- Status and command details for appliance families other than AC.
