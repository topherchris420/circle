"""Acquisition boundary: how device records from any source reach the closed loop.

CIRCLE's pipeline and controller read one representation, the RawSession of
device records (models/physiology/streams.py), and the closed loop runs against
any HardwareSource that produces it (models/physiology/loop.py). This package
supplies the sources that are not the twin:

  ingest      StreamChunk, the validating Ingestor, and LinkMonitor
  live        IngestingSource (a device's deliveries into the loop) and pump()
  simulator   SimulatedLink: deterministic link faults over any source
  recorded    RecordedSource: an exported evidence bundle as a source
  records     session records for an acquisition the input contract refused

Nothing here imports the twin or its scoring. Hardware-specific adapters (for
example models/muse_gadget) build on this package; the core never imports them.
"""
