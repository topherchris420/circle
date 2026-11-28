# First Light evidence

Everything here can be checked with [`tools/verify_first_light.py`](../../tools/verify_first_light.py),
which needs only Python 3.11. The method is in [`docs/first-light.md`](../../docs/first-light.md).

| Path | What it is |
| --- | --- |
| [`round-2/PREREGISTRATION.md`](round-2/PREREGISTRATION.md) | Criteria and test set, committed before the test ran |
| [`round-2/RESULT.md`](round-2/RESULT.md) · [`result.json`](round-2/result.json) | The pooled held-out test: 56 sessions, passed |
| [`round-2/calibration.json`](round-2/calibration.json) | The same pipeline on calibration people, where the bars came from |
| [`sessions/149055-072.zip`](sessions/149055-072.zip) | Illustration session, chosen after the test; `VERIFIED` alone |
| [`sessions/137025-054.zip`](sessions/137025-054.zip) | Preregistered page session; `PROTOCOL_FAIL` alone (no action) |
| [`benchmark.json`](benchmark.json) | Threshold calibration and the per-record held-out benchmark |
| [`round-1/`](round-1/README.md) | The first round, which failed a criterion; kept unchanged |

The recordings come from BUT PPG 2.0.0 (Brno University of Technology, PhysioNet, CC BY 4.0,
[doi:10.13026/tn53-8153](https://doi.org/10.13026/tn53-8153). The other 54 round-2 bundles are not stored; the round's command rebuilds
them from the public archive.

## Citation correction

PhysioNet's DOI for **BUT PPG 2.0.0** is [`10.13026/tn53-8153`](https://doi.org/10.13026/tn53-8153).
The archived round summaries, recording payloads, and sealed bundles may still carry
`10.13026/bvsb-mz80`. That string is a citation error, not a different dataset.
The version, source URL, archive hash, and numerical results are unchanged.
The verifier keeps the old string when reconstructing historical bundle metadata so
it can still compare the full reference against the sealed original. Newly generated
benchmark and round summaries use the corrected DOI.

## Live recordings

`live/` does not exist yet. No one has contributed a session from a physical camera. To add the
first, see [Add a recording](../../docs/first-light.md#add-a-recording). Failing bundles are as welcome as passing ones.
