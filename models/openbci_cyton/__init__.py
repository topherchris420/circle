"""OpenBCI Cyton adapter: a real biosignal board at CIRCLE's ingestion boundary.

The Cyton (github.com/OpenBCI/OpenBCI_Cyton_Library) is an 8-channel ADS1299
biopotential board, 16 channels with the Daisy module, that streams 250 samples
per second through a radio dongle. This adapter brings it in under CIRCLE's
evidence rules and makes it its own electronic phantom:

  protocol    what the board sends and accepts, pinned to the firmware, radio,
              and datasheet revisions inspected; the commands CIRCLE refuses
  framing     the dongle's byte stream split into checked packets and text
  streams     packets into CIRCLE pieces: unwrapped sample indices, exact GAPs
              (past counter wraps, by the sample clock), marked discontinuities
  bridge      configure, read the ADC's registers back, stream through pump()
              into the Ingestor, restore the board, export a lawful session
  analysis    the phantom scorecard (internal test signals and shorted inputs
              against the datasheet), channel quality, ECG R peaks and RMSSD
  simulator   a deterministic Cyton, radios, and USB port with known truth

pyserial is needed only to talk to a real dongle. Nothing here is imported by
the core, and the Cyton cannot drive the closed loop: the input contract refuses
it, and each session records why.
"""
