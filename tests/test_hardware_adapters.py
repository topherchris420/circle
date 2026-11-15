"""Hardware-agnostic adapters: the contract holds for BrainFlow and LSL fakes."""

from __future__ import annotations

import unittest

from models.hardware_adapters import (ADAPTER_SDK_VERSION, BrainFlowAdapter, LSLAdapter, REQUIRED_STREAMS)


class FakeBrainFlowShim:
    """The BrainFlow surface CIRCLE touches: channel-major data with names."""

    board_name = "fake-board"

    def __init__(self, channels: list[str], rows: int):
        import random
        self.rng = random.Random(11)
        self._names = channels
        self._rows = rows

    def get_channel_names(self) -> list[str]:
        return list(self._names)

    def get_board_data(self):
        times = [100.0 + i * 0.01 for i in range(self._rows)]
        data = [times]
        for _ in self._names:
            data.append([self.rng.uniform(-1, 1) for _ in range(self._rows)])
        return data


class FakeLSLInlet:
    def __init__(self, rate_hz: float, seconds: float, seed: int):
        import random
        self.rng = random.Random(seed)
        self.count = int(rate_hz * seconds)
        self.rate = rate_hz

    def pull_chunk(self):
        values = [[self.rng.uniform(0, 1)] for _ in range(self.count)]
        stamps = [50.0 + i / self.rate for i in range(self.count)]
        return values, stamps


class BrainFlowAdapterTest(unittest.TestCase):
    def test_frames_follow_the_contract(self):
        shim = FakeBrainFlowShim(["eda_ch", "ppg_ch", "ax", "ay", "az"], rows=50)
        adapter = BrainFlowAdapter(shim, {"eda": ("eda_ch",), "ppg": ("ppg_ch",), "imu": ("ax", "ay", "az")})
        frames = adapter.samples()
        self.assertGreater(len(frames), 100)
        for frame in frames:
            self.assertIn(frame.stream, REQUIRED_STREAMS)
            self.assertGreater(frame.device_time_us, 0)
            self.assertTrue(all(isinstance(v, float) for v in frame.values))
        # Ordering is contract-stable: by device time, then stream, then sequence.
        keys = [(f.device_time_us, f.stream, f.sequence) for f in frames]
        self.assertEqual(keys, sorted(keys))

    def test_a_board_missing_a_stream_is_refused_by_name(self):
        shim = FakeBrainFlowShim(["eeg_ch"], rows=10)
        adapter = BrainFlowAdapter(shim, {"eda": ("eeg_ch",)})
        refusal = adapter.refusal()
        self.assertIn("MISSING_STREAM:ppg", refusal)
        self.assertIn("MISSING_STREAM:imu", refusal)
        self.assertNotIn("MISSING_STREAM:eda", refusal)

    def test_capabilities_state_their_limits(self):
        shim = FakeBrainFlowShim(["eda_ch"], rows=5)
        adapter = BrainFlowAdapter(shim, {"eda": ("eda_ch",)})
        caps = adapter.capabilities()
        self.assertEqual(caps.provenance, "BRAINFLOW")
        self.assertTrue(caps.limitations)


class LSLAdapterTest(unittest.TestCase):
    def test_chunks_become_contract_frames(self):
        inlet = FakeLSLInlet(rate_hz=100.0, seconds=2.0, seed=3)
        adapter = LSLAdapter({"ppg": ("ppg-outlet", inlet, "PPG")})
        frames = adapter.samples()
        self.assertEqual(len(frames), 200)
        self.assertTrue(all(frame.stream == "ppg" for frame in frames))
        stamps = [f.device_time_us for f in frames]
        self.assertEqual(stamps, sorted(stamps))

    def test_refusal_for_outlets_without_needed_streams(self):
        adapter = LSLAdapter({"eeg": ("eeg-outlet", FakeLSLInlet(10, 1, 1), "EEG")})
        self.assertEqual(sorted(adapter.refusal()), ["MISSING_STREAM:eda", "MISSING_STREAM:imu", "MISSING_STREAM:ppg"])

    def test_sdk_version_is_pinned(self):
        self.assertRegex(ADAPTER_SDK_VERSION, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
