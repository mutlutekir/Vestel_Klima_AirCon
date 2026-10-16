"""Unit tests for VestelAcApi._parse_status and the AC code builders.

These are the pure, side-effect-free parts of api.py. The status decoder
must keep working for real AC payloads (regression guard - the upstream
maintainer has a real AC) and must no longer crash on non-AC appliances
like fridges (the bug this change fixes: KeyError 'ACGENSI' broke the
whole integration when any non-AC device was on the account).
"""

import pytest

from custom_components.vestel_ac.api import (
    VestelAcApi,
    fridge_door_states,
    fridge_flag,
    fridge_modes,
    fridge_temp_display,
    fridge_temperatures,
    is_fridge_payload,
)

TEMP_OFFSET = 32736


def _fridge_payload(**overrides) -> dict:
    """A real Vestel fridge status payload (captured from a live device).

    All fields are RF* / Wi-Fi related and there is no ACGENSI anywhere -
    exactly the shape that used to blow the coordinator up with
    KeyError: 'ACGENSI'.
    """
    payload = {
        "RFCLOCK": "00000",
        "RFCOOER": "00000",
        "RFDCOOL": "00000",
        "RFDEFEC": "00000",
        "RFDOORA": "00003",
        "RFMODEA": "00000",
        "RFSSAVE": "00000",
        "RFTEMSE": "00530",
        "WIFIRSS": "00055",
        "WIFISET": "00000",
    }
    payload.update(overrides)
    return payload


def _ac_payload(**overrides) -> dict:
    """A realistic AC status payload, values matching the README's
    reverse-engineered examples."""
    payload = {
        "ACGENSI": "00017",  # cool (1) + fan2 (2 << 3)
        "ACTEMOT": str(TEMP_OFFSET + 22),
        "ACROOTE": "24",
        "ACFANPO": "00050",  # "normal" baseline from the README
        "ACOFFTV": "02047",  # timer disabled
    }
    payload.update(overrides)
    return payload


class TestAcPayloads:
    def test_full_ac_payload_is_fully_decoded(self):
        status = VestelAcApi._parse_status(_ac_payload())
        assert status["is_ac"] is True
        assert status["on"] is True
        assert status["mode"] == "cool"
        assert status["fan"] == "fan2"
        assert status["temp"] == 22
        assert status["room_temp"] == 24
        assert status["fanpo_raw"] == 50
        assert status["turbo"] is False
        assert status["sleep"] is False
        assert status["ionizer"] is False
        assert status["eco"] is False
        assert status["auto_off_enabled"] is False
        assert status["raw"] == _ac_payload()

    def test_off_mode(self):
        status = VestelAcApi._parse_status(_ac_payload(ACGENSI="00005"))
        assert status["is_ac"] is True
        assert status["on"] is False
        assert status["mode"] == "off"

    def test_heat_mode_and_fan_speeds(self):
        status = VestelAcApi._parse_status(_ac_payload(ACGENSI="00028"))  # heat(4) + fan3(3<<3=24)
        assert status["mode"] == "heat"
        assert status["fan"] == "fan3"

    def test_fanpo_special_modes(self):
        # README "verified special modes": baseline 00050 + one flag bit.
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00178"))["sleep"] is True
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00306"))["ionizer"] is True
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00562"))["eco"] is True
        assert VestelAcApi._parse_status(_ac_payload(ACFANPO="00051"))["turbo"] is True

    def test_louver_positions(self):
        status = VestelAcApi._parse_status(_ac_payload(ACFANPO="00060"))  # swing
        assert status["vertical"] == 6
        assert status["horizontal"] == 3

    def test_auto_off_time(self):
        # README example: 14:18 -> 00590.
        status = VestelAcApi._parse_status(_ac_payload(ACOFFTV="00590"))
        assert status["auto_off_enabled"] is True
        assert status["auto_off_hour"] == 14
        assert status["auto_off_minute"] == 18


class TestNonAcPayloads:
    def test_unknown_payload_returns_raw_only(self):
        # No AC* and no RF* fields: neither AC nor fridge, but the payload
        # must still survive as "raw" (this used to crash the coordinator).
        payload = {"SOMETHING": "004", "OTHER": "007"}
        status = VestelAcApi._parse_status(payload)
        assert status["is_ac"] is False
        assert status["is_fridge"] is False
        assert status["raw"] is payload
        assert "mode" not in status

    def test_empty_payload(self):
        status = VestelAcApi._parse_status({})
        assert status["is_ac"] is False
        assert status["is_fridge"] is False

    def test_acgeni_without_required_fields_does_not_crash(self):
        status = VestelAcApi._parse_status({"ACGENSI": "00017"})
        assert status["is_ac"] is False
        assert status["raw"] == {"ACGENSI": "00017"}

    def test_malformed_values_do_not_crash(self):
        status = VestelAcApi._parse_status(
            _ac_payload(ACGENSI="not-a-number", ACTEMOT="x")
        )
        assert status["is_ac"] is False


# Real RFTEMSE calibration points captured from a live Vestel fridge:
# (cooler °C, freezer °C, raw RFTEMSE string).
RFTEMSE_CALIBRATION = (
    (2, -16, "00528"),
    (2, -18, "00530"),
    (2, -20, "00532"),
    (2, -22, "00534"),
    (2, -24, "00536"),
    (4, -16, "01040"),
    (4, -18, "01042"),
    (4, -20, "01044"),
    (4, -22, "01046"),
    (4, -24, "01048"),
    (5, -16, "01296"),
    (5, -18, "01298"),
    (5, -20, "01300"),
    (5, -22, "01302"),
    (5, -24, "01304"),
)


class TestFridgeTemperatures:
    """RFTEMSE packs both setpoints into one integer: high byte = cooler,
    low byte = absolute freezer temperature."""

    @pytest.mark.parametrize("cooler,freezer,raw", RFTEMSE_CALIBRATION)
    def test_calibration_table_round_trips(self, cooler, freezer, raw):
        assert fridge_temperatures(raw) == {
            "cooler": cooler,
            "freezer": freezer,
        }

    def test_decode_is_bit_packed_not_decimal_halves(self):
        # 01300 splits as decimal 013|00 but really is 0x514 = 5 | 20.
        assert fridge_temperatures("01300") == {"cooler": 5, "freezer": -20}
        assert fridge_temperatures(1300) == {"cooler": 5, "freezer": -20}

    def test_unknown_and_malformed_are_none(self):
        assert fridge_temperatures(None) is None
        assert fridge_temperatures("--") is None
        assert fridge_temperatures("not-a-number") is None
        assert fridge_temperatures("-1") is None

    def test_temperatures_flow_through_parse_status(self):
        status = VestelAcApi._parse_status(_fridge_payload(RFTEMSE="01304"))
        assert status["is_fridge"] is True
        assert status["fridge"]["cooler_temp"] == 5
        assert status["fridge"]["freezer_temp"] == -24
        assert status["fridge"]["temp_raw"] == "01304"

    def test_default_fixture_decodes(self):
        # The captured fixture ships RFTEMSE=00530 -> +2 / -18 °C.
        status = VestelAcApi._parse_status(_fridge_payload())
        assert status["fridge"]["cooler_temp"] == 2
        assert status["fridge"]["freezer_temp"] == -18

    def test_missing_rftemse_is_unknown(self):
        payload = _fridge_payload()
        del payload["RFTEMSE"]
        status = VestelAcApi._parse_status(payload)
        assert status["is_fridge"] is True
        assert status["fridge"]["cooler_temp"] is None
        assert status["fridge"]["freezer_temp"] is None
        assert status["fridge"]["temp_raw"] is None

    def test_non_numeric_rftemse_does_not_break_door(self):
        status = VestelAcApi._parse_status(_fridge_payload(RFTEMSE="--"))
        assert status["is_fridge"] is True
        assert status["fridge"]["cooler_temp"] is None
        assert status["fridge"]["fridge_door_open"] is False


class TestFridgeModes:
    """RFMODEA is a bit field of independent modes (reverse engineered on a
    real fridge), RFCLOCK / RFSSAVE are plain on/off flags."""

    @pytest.mark.parametrize(
        "raw,expected",
        (
            ("00000", {}),
            ("00002", {"fast_freeze": True}),
            ("00004", {"fast_cool": True}),
            ("00006", {"fast_cool": True, "fast_freeze": True}),
            ("00008", {"holiday": True}),
            ("00016", {"eco": True}),
            ("00030", {"fast_freeze": True, "fast_cool": True,
                       "holiday": True, "eco": True}),
        ),
    )
    def test_mode_bits(self, raw, expected):
        modes = fridge_modes(raw)
        assert modes == {
            "fast_freeze": expected.get("fast_freeze", False),
            "fast_cool": expected.get("fast_cool", False),
            "holiday": expected.get("holiday", False),
            "eco": expected.get("eco", False),
        }

    def test_modes_accept_ints_and_unpadded_strings(self):
        assert fridge_modes("8") == {
            "fast_freeze": False, "fast_cool": False,
            "holiday": True, "eco": False,
        }
        assert fridge_modes(16)["eco"] is True

    def test_unknown_and_malformed_modes_are_none(self):
        assert fridge_modes(None) is None
        assert fridge_modes("--") is None
        assert fridge_modes("not-a-number") is None

    def test_flags(self):
        assert fridge_flag("00000") is False
        assert fridge_flag("00001") is True
        assert fridge_flag("1") is True
        assert fridge_flag(None) is None
        assert fridge_flag("--") is None

    def test_modes_and_flags_flow_through_parse_status(self):
        status = VestelAcApi._parse_status(
            _fridge_payload(RFMODEA="00030", RFCLOCK="00001", RFSSAVE="00001")
        )
        fridge = status["fridge"]
        assert fridge["mode_raw"] == "00030"
        assert fridge["fast_cool"] is True
        assert fridge["fast_freeze"] is True
        assert fridge["holiday"] is True
        assert fridge["eco"] is True
        assert fridge["child_lock"] is True
        assert fridge["child_lock_raw"] == "00001"
        assert fridge["screen_saver"] is True
        assert fridge["screen_saver_raw"] == "00001"

    def test_default_fixture_has_everything_off(self):
        # The captured fixture ships RFMODEA/RFCLOCK/RFSSAVE = 00000.
        fridge = VestelAcApi._parse_status(_fridge_payload())["fridge"]
        assert fridge["fast_cool"] is False
        assert fridge["fast_freeze"] is False
        assert fridge["holiday"] is False
        assert fridge["eco"] is False
        assert fridge["child_lock"] is False
        assert fridge["screen_saver"] is False

    def test_missing_mode_field_is_unknown(self):
        payload = _fridge_payload()
        del payload["RFMODEA"]
        del payload["RFCLOCK"]
        fridge = VestelAcApi._parse_status(payload)["fridge"]
        assert fridge["holiday"] is None
        assert fridge["eco"] is None
        assert fridge["child_lock"] is None
        # The door/temperature decode is unaffected.
        assert fridge["fridge_door_open"] is False
        assert fridge["cooler_temp"] == 2


class TestFridgeTempDisplay:
    """What the panel shows: eco -> "E" for both, holiday -> no cooler."""

    def test_normal_shows_setpoints(self):
        fridge = VestelAcApi._parse_status(_fridge_payload())["fridge"]
        assert fridge_temp_display(fridge, "cooler") == 2
        assert fridge_temp_display(fridge, "freezer") == -18

    def test_eco_shows_e_for_both(self):
        fridge = VestelAcApi._parse_status(_fridge_payload(RFMODEA="00016"))["fridge"]
        assert fridge_temp_display(fridge, "cooler") == "E"
        assert fridge_temp_display(fridge, "freezer") == "E"

    def test_holiday_hides_cooler_but_keeps_freezer(self):
        fridge = VestelAcApi._parse_status(_fridge_payload(RFMODEA="00008"))["fridge"]
        assert fridge_temp_display(fridge, "cooler") is None
        assert fridge_temp_display(fridge, "freezer") == -18

    def test_eco_wins_over_holiday(self):
        fridge = VestelAcApi._parse_status(_fridge_payload(RFMODEA="00024"))["fridge"]
        assert fridge_temp_display(fridge, "cooler") == "E"
        assert fridge_temp_display(fridge, "freezer") == "E"

    def test_numeric_setpoints_stay_available(self):
        # The overrides are display-only: the decoded numbers remain in the
        # status dict for automation.
        fridge = VestelAcApi._parse_status(_fridge_payload(RFMODEA="00016"))["fridge"]
        assert fridge["cooler_temp"] == 2
        assert fridge["freezer_temp"] == -18


class TestFridgePayloads:
    """Fridges share the status endpoint but not the field set - they are
    detected by the RF* prefix and currently expose the door and the
    decoded setpoints."""

    def test_fridge_payload_is_detected(self):
        payload = _fridge_payload()
        status = VestelAcApi._parse_status(payload)
        assert status["is_ac"] is False
        assert status["is_fridge"] is True
        assert status["raw"] is payload
        # No AC-only keys leaked into a fridge record.
        assert "mode" not in status
        assert "temp" not in status

    def test_both_doors_closed(self):
        # 00003 (0b11): both doors closed - the normal resting state.
        status = VestelAcApi._parse_status(_fridge_payload(RFDOORA="00003"))
        assert status["fridge"]["fridge_door_open"] is False
        assert status["fridge"]["freezer_door_open"] is False
        assert status["fridge"]["door_raw"] == "00003"

    def test_fridge_door_open(self):
        # 00001 (0b01): observed while the fridge door was open and the
        # appliance was alarming (bit 1 clear = fridge door open).
        status = VestelAcApi._parse_status(_fridge_payload(RFDOORA="00001"))
        assert status["fridge"]["fridge_door_open"] is True
        assert status["fridge"]["freezer_door_open"] is False

    def test_freezer_door_open(self):
        # 00002 (0b10): observed while the freezer door was open
        # (bit 0 clear = freezer door open).
        status = VestelAcApi._parse_status(_fridge_payload(RFDOORA="00002"))
        assert status["fridge"]["fridge_door_open"] is False
        assert status["fridge"]["freezer_door_open"] is True

    def test_door_bits_map_to_doors_independently(self):
        # One bit per door: bit 1 -> fridge, bit 0 -> freezer.
        assert fridge_door_states("00003") == {"fridge": False, "freezer": False}
        assert fridge_door_states("00001") == {"fridge": True, "freezer": False}
        assert fridge_door_states("00002") == {"fridge": False, "freezer": True}
        assert fridge_door_states("00000") == {"fridge": True, "freezer": True}

    def test_missing_door_field_is_unknown(self):
        payload = _fridge_payload()
        del payload["RFDOORA"]
        status = VestelAcApi._parse_status(payload)
        assert status["is_fridge"] is True
        assert status["fridge"]["fridge_door_open"] is None
        assert status["fridge"]["freezer_door_open"] is None
        assert fridge_door_states(None) is None
        assert fridge_door_states("not-a-number") is None

    def test_is_fridge_payload_helper(self):
        assert is_fridge_payload(_fridge_payload()) is True
        assert is_fridge_payload({"ACGENSI": "00017"}) is False
        assert is_fridge_payload({}) is False

    def test_non_ac_fridge_fields_do_not_crash(self):
        # A fridge reporting a non-numeric value on one field must not
        # take the door decode down with it.
        status = VestelAcApi._parse_status(_fridge_payload(RFDOORA="--"))
        assert status["is_fridge"] is True
        assert status["fridge"]["fridge_door_open"] is None
        assert status["fridge"]["freezer_door_open"] is None


class TestAcCodeBuilders:
    """Guard the AC command encoding - the upstream maintainer's real AC
    must keep receiving exactly the codes it receives today."""

    def test_build_gensi(self):
        assert VestelAcApi._build_gensi("cool", "fan2") == "ACGENSI00017"
        assert VestelAcApi._build_gensi("heat", "auto") == "ACGENSI00004"
        assert VestelAcApi._build_gensi("off", "auto") == "ACGENSI00005"

    def test_build_gensi_rejects_bad_input(self):
        with pytest.raises(ValueError):
            VestelAcApi._build_gensi("nope")

    def test_build_temot(self):
        assert VestelAcApi._build_temot(22) == f"ACTEMOT{TEMP_OFFSET + 22}"
        with pytest.raises(ValueError):
            VestelAcApi._build_temot(17)
        with pytest.raises(ValueError):
            VestelAcApi._build_temot(31)

    def test_build_field_pads_to_five_digits(self):
        assert VestelAcApi._build_field("ACFANPO", 562) == "ACFANPO00562"
        assert VestelAcApi._build_field("ACOFFTV", 590) == "ACOFFTV00590"
