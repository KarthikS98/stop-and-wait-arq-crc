# Stop-and-Wait ARQ with CRC — Python file-transfer simulator

A compact, runnable Python implementation of Stop-and-Wait ARQ using CRC for per-chunk error detection. This repository contains the sender and receiver, CRC utilities, simple demo scripts, and a small unit test so a newcomer can clone and run the project locally.

---

## Important files (what to commit)
- `README.md` — this file (quick start and validation).
- `LICENSE` — project license (e.g., MIT).
- `requirements.txt` — runtime dependencies.
- `.gitignore` — ignore runtime logs, caches, and large media.

Codes/ (core source)
- `client.py` — sender: chunking, CRC32, optional error simulation, send chunk+CRC, wait ACK/NACK, retransmit.
- `server.py` — receiver: verify CRC, send ACK/NACK, buffer chunks, reconstruct/save files, log metrics.
- `crc_utils.py` — CRC helpers (CRC32 and CRC16-CCITT).
- `file_chunker.py` — file chunking helper.
- `simple_test.py` — small demo for one transfer.
- `test_runner.py` — automated test harness (reproducible experiments).

Tests
- `tests/test_crc.py` — unit test for CRC functions (keeps CI fast and network-free).

Do NOT commit runtime folders and large media:
- `Log Files/`, `Received Output/`, large files in `Test Samples/`, `__pycache__/`.

---

## Quick start (PowerShell)
1. Open PowerShell in the repository root (where `Codes/` is).
2. Create and activate a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Run the server (one terminal):

```powershell
python .\Codes\server.py
```

4. Run the client (another terminal):

```powershell
python .\Codes\client.py
```

- Use `localhost` for server IP when testing locally.
- Enter file path or text at the client prompt; set bit-error probability per chunk (0 for none); type `END` to finish the session.

Run the demo script (server must be running):

```powershell
python .\Codes\simple_test.py
```

Run unit tests:

```powershell
pytest -q
```

---

## Quick validation checklist
1. Run one transfer with error probability `0` and verify SHA256 hashes of original and received files match:

```powershell
Get-FileHash .\Test Samples\sample_image.jpg -Algorithm SHA256
Get-FileHash .\Received Output\received_file.jpg -Algorithm SHA256
```

2. Inspect logs for ACKs/NACKs and metrics in `Log Files/`.
3. Run `pytest` to ensure the CRC unit test passes.

If these pass, the ARQ+CRC implementation is working and file reconstruction is correct.

---

## Troubleshooting (short)
- Connection refused: ensure server is running and port 65432 is not blocked by firewall.
- Empty `Received Output`: check server logs for `Incomplete data` or early disconnect messages.
- Large-file tests: use small samples for local demos; host large files via Releases or external storage.

---

## Notes
- Keep logs and received files out of git; include only small sample data for demos.
- Add `tests/test_crc.py` and a minimal CI workflow to run tests on push/PR if you want continuous validation.

