# Frame-driven human consent

[`circle_authority.py`](../circle_authority.py) is a standalone deterministic
event reducer for restricted mutations. An action waits as data in
`pending_registry`; the host keeps evaluating telemetry and advancing frames.
The reducer contains no clock reads, random UUID generation, file/network I/O,
sleep, asynchronous holds or private keys.

## State and event contract

| Event | Current action state | Result |
|---|---|---|
| `RestrictedActionEvent` with a fresh, unsigned envelope | Unregistered | `PENDING_SIGNATURE` |
| `HumanConsentEvent` with the matching UUID and valid master-key signature | `PENDING_SIGNATURE` | Apply the mutation once; `EXECUTED` on success |
| Matching consent with an invalid signature | `PENDING_SIGNATURE` | `REJECTED`; no mutation |
| Valid consent, but the mutation executor refuses/fails | `PENDING_SIGNATURE` | `REJECTED`; no automatic retry |
| Duplicate or rebound UUID proposal | Registered, including terminal states | Log and ignore; retain the original binding |
| Consent for an unknown or terminal UUID | Not pending | Log and ignore; do not retain authorization |
| Any number of frames without consent | `PENDING_SIGNATURE` | Remain pending; telemetry continues |

Pre-signed proposals, future-dated proposals and proposals beyond the pending
capacity are rejected. Each frame processes at most `max_events_per_frame`
events in FIFO order. Events injected by a callback are eligible next frame.
Frames start at zero and are contiguous; injected integer device timestamps
strictly increase. Ingress validation and event injection happen between steps
on the loop's owning thread. The event-count budget bounds dispatch work; it
does not provide a hard real-time deadline for arbitrary callbacks or payloads.

`Mutation` stores parameters as canonical JSON, and envelopes/records are frozen
dataclasses. Decoding parameters returns a fresh object. Both registries expose
read-only views. Terminal records retain UUID tombstones for the engine's
lifetime. The unsigned envelope contains the mutation, proposal device time,
state-history SHA-256 and action UUID; its signature slot starts as `None`.

## Cryptographic contract

The human signer reviews the **registered envelope** and signs precisely:

```python
signature = human_private_key.sign(action.action_id.bytes)
event = HumanConsentEvent(action.action_id, signature)
```

`verify_human_consent(event, registered_public_key)` is a pure function using
Ed25519 from `cryptography`. Textual UUIDs, other UUIDs, wrong-key signatures and
malformed signatures do not verify. Provision the human master public key
before constructing `CircleAuthority`; the authority has no signing key or
key rotation API. Keep the private key in the independent human signer.

**The signature authenticates the UUID, not the entire envelope or execution
frame.** UUIDs must never be reused or rebound, including after process restart
or across sessions sharing the key. The host must preserve the registered
envelope and terminal UUID records in durable, integrity-protected checkpoints
and replay storage. Use fresh UUIDs for new actions; record them as input rather
than generating them inside the deterministic loop. The engine prevents
rebinding within its lifetime. It cannot enforce global uniqueness or durable
at-most-once execution after a crash by itself. The history hash is a supplied
proposal snapshot, not a proof that the current state is unchanged at consent
time. The executor must revalidate any state-dependent preconditions before
committing a mutation.

## Minimal deterministic loop

The complete runnable example is
[`tools/run_authority_demo.py`](../tools/run_authority_demo.py):

```bash
pip install -r requirements.txt
python tools/run_authority_demo.py
python -m unittest discover -s tests -p test_circle_authority.py -v
```

| Frame | Event sequence | Restricted action | Simulated feedback level |
|---|---|---|---|
| 0 | Normal heart-rate telemetry | None | 0 |
| 1 | Telemetry, restricted proposal | `PENDING_SIGNATURE` | 0 |
| 2 | Telemetry | `PENDING_SIGNATURE` | 0 |
| 3 | Telemetry | `PENDING_SIGNATURE` | 0 |
| 4 | Telemetry, valid human consent | `EXECUTED` | 2 |
| 5 | Telemetry | Remains `EXECUTED` | 2 |

The demo has a fixed **test-only** key and UUID so repeated runs produce
byte-identical records. It mutates only a simulation dictionary. Real consent
must come from the human-controlled signer; do not reuse the demo credentials.

Construct `CircleAuthority(public_key, execute, observe)` with a deterministic
in-memory mutation reducer and a telemetry observer. Call
`authority.step(frame, timestamp_us, incoming_deque)` on every frame, including
empty frames. The executor receives the signed envelope, exact execution frame
and device timestamp. It must validate before atomically updating application
state. If it raises after partial effects, the engine cannot roll those back;
the failure is recorded and is never automatically retried. Observer failures
are logged without dropping the remaining frame's consent events. Neither
callback may perform blocking I/O. External transport and persistence belong
outside this deterministic reducer.

## Replay provenance and CIRCLE boundaries

Each `FrameResult.replay_payloads` item is a ready-to-write JSON string with
schema `circle-authority-replay/1`. Successful execution records contain:

- The full unsigned envelope, its SHA-256, original history hash and proposal time.
- `EXECUTED`, the accepted signature in base64, exact `execution_frame` and frame device time.
- The registered public-key fingerprint, sequence and preceding record hash.
- A SHA-256 of the record body (everything except `record_hash`).

Rejections and ignored consent attempts are also logged. Serialization uses
CIRCLE's sorted, compact, ASCII-escaped UTF-8 JSON convention with nonfinite
numbers refused. The chain detects changes when checked against a trusted
stored head; it is not an independently signed attestation of the frame.
Persistence must protect that head and retain the public-key registration.
The module itself does not make files immutable.

The host should append the strings unchanged to an **authority replay stream**
and include that stream in its evidence manifest. This is a separate versioned
record type; it must not be inserted as-is into `session.ndjson`, whose sensor
record schema has different required fields. For replay, record incoming event
arrival frames/FIFO order, device times, budgets, the initial application state
and the registered public key. Run the same inputs through a fresh authority
and fresh simulation state, then compare the emitted strings. Replaying against
live external side effects is outside this module's contract.

The existing physiological controller, experiment authorization and
`models/physiology/loop.py` actuator restrictions remain their own boundaries.
Cryptographic consent does not grant hardware or human actuation or close the
repository's engineering review gates. This addition supplies the requested
consent gate and runnable simulation example; it is not wired into every
existing actuator or protocol path.
