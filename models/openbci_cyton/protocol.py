"""What an OpenBCI Cyton sends and accepts, as inspected at pinned revisions.

Sources (every constant below names the line of source it mirrors):

  firmware   github.com/OpenBCI/OpenBCI_Cyton_Library, commit 24e1c42 (2025-07-24),
             library version 3.1.5, MIT. OpenBCI_32bit_Library.cpp and
             OpenBCI_32bit_Library_Definitions.h.
  radio      github.com/OpenBCI/OpenBCI_Radios, commit 389a831 (2025-07-10), MIT.
             The RFduino on the board and the one in the USB dongle.
  ADC        Texas Instruments ADS1299 datasheet SBAS499C (July 2012, revised
             January 2017): register maps, test signals, noise, oscillator.

What travels, end to end. On every ADS1299 data-ready the PIC32 writes 33 bytes
to the board's radio: 'A' (0x41), an 8-bit sample counter, eight 24-bit
big-endian two's-complement channel codes, six auxiliary bytes, and a stop byte
0xC0 | packet type (sendChannelDataSerial). The board radio forwards a complete
33-byte stream packet only; a packet that lost a byte on the PIC's UART is
discarded there (bufferStreamAddChar). The dongle writes each stream packet to
USB as 0xA0, the 31 data bytes, and the stop byte (bufferStreamFlush). So the
host sees 0xA0 where the board sent 'A', and a packet the air or the UART lost
is simply absent: the 8-bit counter is the only record of it.

The counter restarts at 0 whenever the ADS1299 is (re)started (startADS), which
happens on 'b' and on every "stream-safe" setting change made while streaming
(streamSafeChannelSettingsForChannel and friends stop and restart the ADC).

Text from the board (command replies, the soft-reset banner) and from the dongle
(link messages) arrives on the same byte stream, ending in the EOT "$$$"
(sendEOT; the dongle's printEOT). While the board streams, most replies are
suppressed (`if (!streaming)`), so a setting changed mid-stream is visible only
as a restarted counter.

The firmware has two quirks CIRCLE records rather than hides:
  * The soft-reset banner prints "Firmware: v3.1.2" while 'V' answers "v3.1.5"
    (boardReset vs processChar at the pinned commit). Version comes from 'V'.
  * Marker mode stores the marker's character code, not its digit value:
    "`5" puts 53 in AUX1 (processInsertMarker: markerValue = c), although the
    v3.0.0 changelog says int(n).
"""

from __future__ import annotations

from dataclasses import dataclass

LIBRARY_REPOSITORY = "https://github.com/OpenBCI/OpenBCI_Cyton_Library"
LIBRARY_COMMIT = "24e1c4269b60c3bec6d831bca03cae42f267b3c6"
LIBRARY_VERSION = "3.1.5"
RADIOS_REPOSITORY = "https://github.com/OpenBCI/OpenBCI_Radios"
RADIOS_COMMIT = "389a831abb2159273e6d15c1daa0ae62989cc211"
DATASHEET = "TI ADS1299 datasheet SBAS499C (July 2012, revised January 2017)"
PROTOCOL_REFERENCE = (f"OpenBCI_Cyton_Library {LIBRARY_COMMIT[:7]} (v{LIBRARY_VERSION}, MIT), "
                      f"OpenBCI_Radios {RADIOS_COMMIT[:7]} (MIT), {DATASHEET}")

# ------------------------------------------------------------------ the wire
BAUD_RATE = 115200                    # OPENBCI_BAUD_RATE; the dongle's default (OPENBCI_BAUD_RATE_DEFAULT)
PACKET_SIZE = 33                      # OPENBCI_PACKET_SIZE
START_BYTE = 0xA0                     # dongle: bufferStreamFlush writes 0xA0 (OPENBCI_STREAM_BYTE_START)
BOARD_START_BYTE = 0x41               # board: OPENBCI_BOP 'A', replaced by the dongle
STOP_NIBBLE = 0xC0                    # PCKT_END | packet type; the radio accepts any 0xCX (isATailByte)
CHANNELS_PER_ADS = 8                  # OPENBCI_ADS_CHANS_PER_BOARD
AUX_BYTES = 6                         # OPENBCI_NUMBER_BYTES_AUX
EOT = b"$$$"                          # sendEOT
MULTI_CHAR_TIMEOUT_S = 1.0            # MULTI_CHAR_COMMAND_TIMEOUT_MS: send multi-char commands in one write
DONGLE_COMMS_TIMEOUT_MS = 270         # OPENBCI_TIMEOUT_COMMS_MS: dongle declares the board unreachable

# PACKET_TYPE enum (OpenBCI_32bit_Library.h); the stop byte is 0xC0 | type.
PACKET_ACCEL, PACKET_RAW_AUX, PACKET_USER_DEFINED = 0, 1, 2
PACKET_ACCEL_TIME_SET, PACKET_ACCEL_TIME_SYNC = 3, 4
PACKET_RAW_AUX_TIME_SET, PACKET_RAW_AUX_TIME_SYNC = 5, 6
PACKET_TYPE_NAMES = {0: "ACCEL", 1: "RAW_AUX", 2: "USER_DEFINED", 3: "ACCEL_TIME_SET", 4: "ACCEL_TIME_SYNC",
                     5: "RAW_AUX_TIME_SET", 6: "RAW_AUX_TIME_SYNC"}
TIME_STAMPED_TYPES = (PACKET_ACCEL_TIME_SET, PACKET_ACCEL_TIME_SYNC, PACKET_RAW_AUX_TIME_SET, PACKET_RAW_AUX_TIME_SYNC)
# sendTimeWithAccelSerial: one accelerometer axis per packet, chosen by sampleCounter % 10.
TIME_SYNC_AXIS_BY_COUNTER_MOD_10 = {7: 0, 8: 1, 9: 2}   # ACCEL_AXIS_X/Y/Z

# BOARD_MODE enum; set with "/<digit>" (processIncomingBoardMode), queried with "//".
BOARD_MODES = {0: "default", 1: "debug", 2: "analog", 3: "digital", 4: "marker", 5: "BLE"}
BOARD_MODE_CODES = {name: code for code, name in BOARD_MODES.items()}
# setBoardMode: the accelerometer is on only in default mode; the other modes send auxData (RAW_AUX packets).
ACCEL_BOARD_MODES = ("default",)

# SAMPLE_RATE enum; "~<digit>" (processIncomingSampleRate). Streaming over the radio is forced to 250 SPS:
# processChar('b') calls streamSafeSetSampleRate(SAMPLE_RATE_250) unless the command came from the WiFi shield.
SAMPLE_RATE_CODES = {0: 16000, 1: 8000, 2: 4000, 3: 2000, 4: 1000, 5: 500, 6: 250}
STREAM_RATE_HZ = 250
DAISY_RATE_HZ = 125                   # ADS_writeChannelDataAvgDaisy: board and daisy alternate, each averaged

# ----------------------------------------------------------------- the ADC
VREF_V = 4.5                          # CONFIG3 0b11101100 (initialize_ads): internal reference buffer on; datasheet 4.5 V
ADC_MAX_CODE = 2 ** 23 - 1            # 24-bit two's complement; OpenBCI's scale divides by 2^23 - 1
ADC_MIN_CODE = -(2 ** 23)
GAINS = (1, 2, 4, 6, 8, 12, 24)       # datasheet PGA gain settings
DEFAULT_GAIN = 24                     # initialize_ads: defaultChannelSettings[GAIN_SET] = ADS_GAIN24


def microvolts_per_count(gain: int) -> float:
    """Input-referred microvolts per ADC count: VREF / gain / (2^23 - 1)."""
    if gain not in GAINS:
        raise ValueError(f"the ADS1299 has no gain {gain}")
    return VREF_V / gain / ADC_MAX_CODE * 1e6


FCLK_HZ = 2_048_000                   # datasheet: internal oscillator, nominal
OSCILLATOR_TOLERANCE_25C = 0.005      # datasheet: internal clock accuracy at 25 degC, +-0.5 %
OSCILLATOR_TOLERANCE_FULL = 0.025     # datasheet: -40 to 85 degC, +-2.5 %
CLOCKS_PER_SAMPLE_250 = 2 * 4096      # CONFIG1 DR=110: fMOD / 4096 with fMOD = fCLK / 2
NOMINAL_PERIOD_US = 1e6 / STREAM_RATE_HZ

# Internal test signals (datasheet CONFIG2; library configureInternalTestSignal writes 0b11010000 | amp | freq).
# The square wave and the ADC share fCLK, so its period is an exact number of samples whatever the
# oscillator's error: fCLK / 2^21 -> 2^21 / 8192 = 256 samples; fCLK / 2^20 -> 128 samples (at 250 SPS).
TEST_SIGNAL_PERIOD_SAMPLES = {"SLOW": 2 ** 21 // CLOCKS_PER_SAMPLE_250, "FAST": 2 ** 20 // CLOCKS_PER_SAMPLE_250}
TEST_SIGNAL_ACCURACY = 0.02           # datasheet electrical characteristics: test signal accuracy +-2 %
# The datasheet states the amplitude twice, inconsistently: the CONFIG2 table gives
# k * -(VREFP - VREFN) / 2400 (1.875 mV per k at the Cyton's 4.5 V reference); the electrical table gives
# +-1 and +-2 mV. CIRCLE judges only what both agree on (the 2x setting is twice the 1x) and reports the rest.
TEST_SIGNAL_AMPLITUDE_REGISTER_TABLE_V = {1: VREF_V / 2400, 2: 2 * VREF_V / 2400}
TEST_SIGNAL_AMPLITUDE_ELECTRICAL_TABLE_V = {1: 1e-3, 2: 2e-3}
# datasheet Table 4 (5 V analog supply, 4.5 V reference, gain 24, 250 SPS, -3 dB at 65 Hz, input shorted)
NOISE_GAIN24_250SPS_UVRMS = 0.14
NOISE_GAIN24_250SPS_UVPP = 0.98

# Lead-off: boardReset calls configureLeadOffDetection(LOFF_MAG_6NA, LOFF_FREQ_31p2HZ). No serial command
# changes the magnitude; "z" only switches the P and N lead-off current sources of one channel.
LEAD_OFF_CURRENT_A = 6e-9             # OPENBCI_LEAD_OFF_DRIVE_AMPS; datasheet accuracy +-20 %
LEAD_OFF_FREQUENCY_HZ = 31.2          # LOFF_FREQ_31p2HZ (datasheet: fCLK / 2^16)

# ---------------------------------------------------------- accelerometer
# initialize_accel(SCALE_4G): CTRL_REG4 = 0x10 | 0x08, +-4 g, high-resolution; axis words are the LIS3DH's
# left-justified 16-bit outputs (LIS3DH_read16), 12 significant bits at 2 mg per digit -> 2 mg / 16 per count.
ACCEL_G_PER_COUNT = 0.002 / 16
ACCEL_FULL_SCALE_G = 4.0
ACCEL_RATE_HZ = 25                    # processChar('b'): enable_accel(RATE_25HZ)
# sendChannelData: after an ACCEL packet the axis words are zeroed (LIS3DH_zeroAxisData), so a packet carries
# a reading only when the LIS3DH had a new one; an all-zero triple means "no new reading". A true reading of
# exactly (0, 0, 0) would be indistinguishable; under gravity it is not expected, and it is never invented.

# ---------------------------------------------------------- analog/digital
# updateChannelData: analog mode reads A5, A6 and (without a WiFi shield) A7, 10-bit (PIC32 ADC) into AUX1..3;
# digital mode packs D11<<8|D12, D13<<8|D17, D18. Marker mode puts the marker's character code in AUX1 once.
ANALOG_PINS = ("a5_d11", "a6_d12", "a7_d13")
ANALOG_MAX_CODE = 1023
DIGITAL_PINS = ("d11", "d12", "d13", "d17", "d18")

# --------------------------------------------------------------- commands
START_STREAMING = b"b"                # OPENBCI_STREAM_START
STOP_STREAMING = b"s"                 # OPENBCI_STREAM_STOP
SOFT_RESET = b"v"                     # OPENBCI_MISC_SOFT_RESET: banner, then "$$$"
QUERY_VERSION = b"V"                  # OPENBCI_GET_VERSION: "v3.1.5$$$"
QUERY_REGISTERS = b"?"                # OPENBCI_MISC_QUERY_REGISTER_SETTINGS (only while not streaming)
CHANNELS_DEFAULT = b"d"               # OPENBCI_CHANNEL_DEFAULT_ALL_SET
REPORT_DEFAULTS = b"D"                # OPENBCI_CHANNEL_DEFAULT_ALL_REPORT: "060110$$$"
DAISY_REMOVE = b"c"                   # OPENBCI_CHANNEL_MAX_NUMBER_8
DAISY_ATTACH = b"C"                   # OPENBCI_CHANNEL_MAX_NUMBER_16: answers "16$$$" or "8$$$"
TIME_STAMPS_ON = b"<"                 # OPENBCI_TIME_SET
TIME_STAMPS_OFF = b">"                # OPENBCI_TIME_STOP
DONGLE_SYS_UP = bytes([0xF0, 0x07])   # OpenBCI_Radios: OPENBCI_HOST_PRIVATE_CMD_KEY, OPENBCI_HOST_CMD_SYS_UP

CHANNEL_SELECT = "12345678QWERTYUI"   # OPENBCI_CHANNEL_CMD_CHANNEL_1..16 (inside "x...X" and "z...Z")
CHANNEL_OFF = "12345678qwertyui"      # OPENBCI_CHANNEL_OFF_1..16
CHANNEL_ON = "!@#$%^&*QWERTYUI"       # OPENBCI_CHANNEL_ON_1..16
GAIN_CHARS = {1: "0", 2: "1", 4: "2", 6: "3", 8: "4", 12: "5", 24: "6"}   # OPENBCI_CHANNEL_CMD_GAIN_*
INPUT_TYPES = {"NORMAL": "0", "SHORTED": "1", "BIAS_MEAS": "2", "MVDD": "3", "TEMP": "4", "TESTSIG": "5",
               "BIAS_DRP": "6", "BIAS_DRN": "7"}                         # OPENBCI_CHANNEL_CMD_ADC_*


@dataclass(frozen=True)
class TestSignal:
    """One of the all-channel test conditions (activateAllChannelsToTestCondition)."""

    command: bytes
    input_type: str
    amplitude_k: int | None      # 1x or 2x of the datasheet amplitude, or None (inputs shorted)
    frequency: str | None        # SLOW, FAST, DC, or None


TEST_SIGNALS = {
    "shorted": TestSignal(b"0", "SHORTED", None, None),          # OPENBCI_TEST_SIGNAL_CONNECT_TO_GROUND
    "pulse-1x-slow": TestSignal(b"-", "TESTSIG", 1, "SLOW"),
    "pulse-1x-fast": TestSignal(b"=", "TESTSIG", 1, "FAST"),
    "dc": TestSignal(b"p", "TESTSIG", 2, "DC"),                    # 'p' sets ADSTESTSIG_AMP_2X with DC
    "pulse-2x-slow": TestSignal(b"[", "TESTSIG", 2, "SLOW"),
    "pulse-2x-fast": TestSignal(b"]", "TESTSIG", 2, "FAST"),
}


def channel_settings(channel: int, *, power_down: bool = False, gain: int = DEFAULT_GAIN, input_type: str = "NORMAL",
                     bias: bool = True, srb2: bool = True, srb1: bool = False) -> bytes:
    """"x (CHANNEL, POWER_DOWN, GAIN_SET, INPUT_TYPE_SET, BIAS_SET, SRB2_SET, SRB1_SET) X", nine characters.

    Defaults are the firmware's own (initialize_ads). Sent while streaming, the firmware stops and restarts the
    ADC to apply it, which restarts the sample counter.
    """
    if not 1 <= channel <= 16:
        raise ValueError("channels are numbered 1 to 16")
    if gain not in GAIN_CHARS:
        raise ValueError(f"the ADS1299 has no gain {gain}")
    if input_type not in INPUT_TYPES:
        raise ValueError(f"unknown input type {input_type!r}")
    body = (CHANNEL_SELECT[channel - 1] + ("1" if power_down else "0") + GAIN_CHARS[gain] + INPUT_TYPES[input_type]
            + "".join("1" if v else "0" for v in (bias, srb2, srb1)))
    return b"x" + body.encode("ascii") + b"X"


def lead_off(channel: int, p_input: bool, n_input: bool) -> bytes:
    """"z (CHANNEL, PCHAN, NCHAN) Z": switch one channel's 6 nA, 31.2 Hz lead-off current sources."""
    if not 1 <= channel <= 16:
        raise ValueError("channels are numbered 1 to 16")
    return b"z" + (CHANNEL_SELECT[channel - 1] + ("1" if p_input else "0") + ("1" if n_input else "0")).encode() + b"Z"


def board_mode(name: str) -> bytes:
    if name not in BOARD_MODE_CODES:
        raise ValueError(f"unknown board mode {name!r}")
    return b"/" + str(BOARD_MODE_CODES[name]).encode()


def sample_rate(hz: int) -> bytes:
    codes = {rate: code for code, rate in SAMPLE_RATE_CODES.items()}
    if hz not in codes:
        raise ValueError(f"the Cyton has no sample rate {hz} Hz")
    return b"~" + str(codes[hz]).encode()


def marker(code: int) -> bytes:
    """"`<char>": in marker board mode the character's code appears in AUX1 of the next packet, once."""
    if not 1 <= code <= 0x7F:
        raise ValueError("a marker is one ASCII character; code 0 would be indistinguishable from no marker")
    return b"`" + bytes([code])


# --------------------------------------------------------- CIRCLE's allowlist
# CIRCLE sends only commands whose effect it records. Refused, with reasons:
_REFUSED = {
    **{c: "SD-card logging writes data CIRCLE does not hold or hash" for c in "GHJKLASFaj"},
    **{c: "the WiFi shield changes the transport and the streaming rate" for c in "{}:;"},
}
_REFUSED_BOARD_MODES = {"debug": "debug mode opens a second serial port outside the session",
                        "BLE": "BLE mode changes the board's UART to 9600 baud and breaks the dongle link"}


def command_refusal(command: bytes) -> str | None:
    """Why CIRCLE would not send this one command unit (None: it may)."""
    if not command:
        return "empty command"
    if command == DONGLE_SYS_UP:
        return None
    if command[0] == 0xF0:
        return "dongle radio commands other than the system-up probe change the radio channel, poll time, or baud"
    text = command.decode("latin-1")
    head = text[0]
    if len(text) == 1:
        if head in _REFUSED:
            return _REFUSED[head]
        if head in "bsvV?dDcC<>" or head in CHANNEL_OFF or head in CHANNEL_ON or \
                any(head == t.command.decode() for t in TEST_SIGNALS.values()):
            return None
        return f"{head!r} is not a command CIRCLE sends"
    if head == "x" and len(text) == 9 and text[-1] == "X" and text[1] in CHANNEL_SELECT and text[2] in "01" \
            and text[3] in GAIN_CHARS.values() and text[4] in INPUT_TYPES.values() and set(text[5:8]) <= set("01"):
        return None
    if head == "z" and len(text) == 5 and text[-1] == "Z" and text[1] in CHANNEL_SELECT and set(text[2:4]) <= set("01"):
        return None
    if head == "/" and len(text) == 2:
        mode = BOARD_MODES.get(int(text[1])) if text[1].isdigit() else None
        if mode is None and text[1] != "/":
            return f"board mode {text[1]!r} does not exist"
        return _REFUSED_BOARD_MODES.get(mode or "")
    if head == "~" and len(text) == 2:
        if text[1] == "~" or text[1] == "6":
            return None
        return "rates above 250 SPS cannot stream over the dongle; the firmware forces 250 on 'b' anyway"
    if head == "`" and len(text) == 2 and 1 <= command[1] <= 0x7F:
        return None
    return f"{text!r} is not a well-formed command CIRCLE sends"


# ------------------------------------------------------------------ replies
SOFT_RESET_BANNER_PREFIX = "OpenBCI V3 8-16 channel"      # boardReset


@dataclass(frozen=True)
class Banner:
    """The soft-reset banner, parsed (boardReset)."""

    ads_id: int | None
    daisy_ads_id: int | None
    lis3dh_id: int | None
    banner_firmware: str | None

    @property
    def daisy(self) -> bool:
        return self.daisy_ads_id is not None


ADS1299_ID = 0x3E                     # ADS_ID
LIS3DH_ID = 0x33                      # WHO_AM_I


def parse_banner(text: str) -> Banner | None:
    if SOFT_RESET_BANNER_PREFIX not in text:
        return None

    def hex_after(label: str) -> int | None:
        at = text.find(label)
        if at < 0:
            return None
        word = text[at + len(label):].split("\n", 1)[0].strip()
        try:
            return int(word, 16)
        except ValueError:
            return None

    firmware = None
    if "Firmware: " in text:
        firmware = text.split("Firmware: ", 1)[1].split("\n", 1)[0].strip()
    return Banner(hex_after("On Board ADS1299 Device ID: 0x"), hex_after("On Daisy ADS1299 Device ID: 0x"),
                  hex_after("LIS3DH Device ID: 0x"), firmware)


# ------------------------------------------------------------ register dump
# "?" (printAllRegisters) prints, per ADS1299, one line per register from RREGS with verbosity on:
# "<NAME>, <address hex>, <value hex>, b7, b6, ..., b0", under "Board ADS Registers" / "Daisy ADS Registers",
# then "LIS3DH Registers". Only sent while not streaming.
REGISTER_NAMES = ("ADS_ID", "CONFIG1", "CONFIG2", "CONFIG3", "LOFF", *[f"CH{i}SET" for i in range(1, 9)], "BIAS_SENSP",
                  "BIAS_SENSN", "LOFF_SENSP", "LOFF_SENSN", "LOFF_FLIP", "LOFF_STATP", "LOFF_STATN", "GPIO", "MISC1",
                  "MISC2", "CONFIG4")
VERIFIED_REGISTERS = ("ADS_ID", "CONFIG1", "CONFIG2", *[f"CH{i}SET" for i in range(1, 9)])   # each ADC, every segment
_GAIN_BY_CODE = {0: 1, 1: 2, 2: 4, 3: 6, 4: 8, 5: 12, 6: 24}
_INPUT_BY_CODE = {int(code): name for name, code in INPUT_TYPES.items()}
_DATA_RATE_BY_CODE = {code: rate for code, rate in SAMPLE_RATE_CODES.items()}


@dataclass(frozen=True)
class ChannelRegister:
    """CHnSET as the ADC holds it (datasheet CHnSET; writeChannelSettings composes it)."""

    power_down: bool
    gain: int | None
    input_type: str
    srb2: bool

    @classmethod
    def decode(cls, value: int) -> "ChannelRegister":
        return cls(bool(value & 0x80), _GAIN_BY_CODE.get((value >> 4) & 0x07), _INPUT_BY_CODE.get(value & 0x07, "?"),
                   bool(value & 0x08))


def channel_register_value(power_down: bool, gain: int, input_type: str, srb2: bool) -> int:
    code = {g: c for c, g in _GAIN_BY_CODE.items()}[gain]
    return (0x80 if power_down else 0) | code << 4 | (0x08 if srb2 else 0) | int(INPUT_TYPES[input_type])


@dataclass(frozen=True)
class AdsRegisters:
    """One ADS1299's registers read back over "?"."""

    values: dict[str, int]

    @property
    def device_id(self) -> int | None:
        return self.values.get("ADS_ID")

    @property
    def data_rate_hz(self) -> int | None:
        value = self.values.get("CONFIG1")
        return None if value is None else _DATA_RATE_BY_CODE.get(value & 0x07)

    @property
    def test_signal(self) -> dict[str, object] | None:
        value = self.values.get("CONFIG2")
        if value is None:
            return None
        freq = {0: "SLOW", 1: "FAST", 3: "DC"}.get(value & 0x03, "RESERVED")
        return {"internal": bool(value & 0x10), "amplitude_k": 2 if value & 0x04 else 1, "frequency": freq}

    def channels(self) -> list[ChannelRegister]:
        return [ChannelRegister.decode(self.values[f"CH{i}SET"]) for i in range(1, 9) if f"CH{i}SET" in self.values]


def parse_register_dump(text: str) -> dict[str, AdsRegisters]:
    """{"board": ..., "daisy": ...} from a "?" reply; lines that do not parse are skipped, never guessed."""
    out: dict[str, AdsRegisters] = {}
    section: str | None = None
    values: dict[str, int] = {}
    for line in text.replace("\r", "").split("\n"):
        stripped = line.strip()
        heading = {"Board ADS Registers": "board", "Daisy ADS Registers": "daisy", "LIS3DH Registers": None}
        if stripped in heading:
            if section and values:
                out[section] = AdsRegisters(dict(values))
            section, values = heading[stripped], {}
            continue
        if section is None:
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) == 11 and parts[0] in REGISTER_NAMES:
            try:
                address, value = int(parts[1], 16), int(parts[2], 16)
            except ValueError:
                continue
            if address == REGISTER_NAMES.index(parts[0]) and 0 <= value <= 0xFF:
                values[parts[0]] = value
    if section and values:
        out[section] = AdsRegisters(dict(values))
    return out


def register_dump_lines(values: dict[str, int]) -> str:
    """The lines RREGS prints for these registers (used by the simulator)."""
    lines = []
    for address, name in enumerate(REGISTER_NAMES):
        if name in values:
            value = values[name]
            bits = ", ".join(str((value >> (7 - j)) & 1) for j in range(8))
            lines.append(f"{name}, {address:02X}, {value:02X}, {bits}\n")
    return "".join(lines)
