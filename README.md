# Stop-and-Wait ARQ with CRC — Python file-transfer simulator

A Python implementation and experiment-suite demonstrating Stop-and-Wait ARQ with CRC-based error detection for reliable text and multimedia transfer. The project supports configurable bit-error simulation, detailed logging of transmission/reception/CRC/metrics, and automated test harnesses for reproducible experiments.

---

## Table of Contents
- About
- Files included
- Prerequisites
- Quick start (PowerShell)
- How the system works
- Validation and correctness checks
- Logs and expected outputs
- Troubleshooting
- Professional notes (CI, tests, samples)

---

## About
This project implements a Stop-and-Wait ARQ file-transfer system in Python that uses CRC checksums for per-chunk error detection. The sender divides data into fixed-size chunks, appends CRC32, and the server verifies each chunk, issuing ACK/NACK to trigger retransmission. The repo includes scripts to simulate bit errors, collect throughput/RTT/data-integrity metrics, and reproduce experiments on sample files.

Use this repository to run local experiments, inspect logs, reproduce result plots, or adapt the code for teaching and demonstrations on ARQ and CRC error-detection.

---

## Files included (and purpose)

Top-level
- `README.md` — this file (usage and validation).
- `LICENSE` — project license (e.g., MIT). Add as appropriate.
- `requirements.txt` — Python dependencies (minimal: `matplotlib`, `pytest`).
- `.gitignore` — recommended ignores (runtime logs, caches, large media).

`Codes/` (core source and helpers)
- `client.py` — sender program: chunking, CRC computation, optional error simulation, send chunk+CRC, wait ACK/NACK, retransmit.
- `server.py` — receiver program: receive chunk+CRC, verify CRC, ACK/NACK, reassemble and save files, compute metrics.
- `crc_utils.py` — CRC helper functions (CRC32 and CRC16-CCITT).
- `file_chunker.py` — yields fixed-size binary chunks for file transmission.
- `simple_test.py` — small demo script for single file transfer (manual run).
- `test_runner.py` — automated experiment harness (runs transfers across error rates).


`tests/`
- `tests/test_crc.py` — unit test for CRC functions (CI-friendly, no networking).

Other folders (runtime or large files — recommended to exclude from git)
- `Log Files/` — runtime logs (exclude from git).
- `Received Output/` — saved received files (exclude).
- `Test Samples/` — demo sample files; include only tiny samples in repo; move large files to Releases or use Git LFS.
- `Results/` — result plots (keep only small images used in paper).

---

## Prerequisites
- Python 3.10+ recommended.
- Git for version control.
- Optional: Git LFS if you want to include large media.
- On Windows (PowerShell) instructions below assume `powershell.exe` (Windows PowerShell).

Recommended contents of `requirements.txt` (adjust versions as needed):
```
matplotlib
pytest
```

---

## Quick start (PowerShell)
1. Open PowerShell in the repository root (where `Codes/` lives).
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

- When `client.py` prompts, enter the server IP (use `localhost` if running locally).
- Follow interactive prompts: provide a file path or text, enter bit-error probability per chunk (0 for none), then type `END` to close session.

Run the demo script (server must be running):

```powershell
python .\Codes\simple_test.py
```

Run the automated experiment runner (server must be running):

```powershell
python .\Codes\test_runner.py
```

Run unit tests:

```powershell
pytest -q
```

---

## How the system works (brief)
- `client.py` reads an input (text or file), chunks the data (default 1024 bytes), computes CRC32 for each chunk, optionally flips a random bit with user-specified probability, sends chunk+CRC to server, and waits for server ACK or NACK. Retries up to `MAX_RETRIES` are performed.
- `server.py` receives chunk+CRC, recomputes CRC32, compares with received CRC, replies `ACK: CRC32 valid` or `NACK: CRC32 error`. Correct chunks are buffered; upon receiving `EOT` the server writes the reconstructed file to `Received Output/`.
- Control markers used: `__END__` (session end) and `__EOT__` (end of transmission).
- Logs are written under `Log Files/Server Logs` and `Log Files/Client Logs` (transmission/reception/CRC/metrics).

---

## Validation and correctness checks
To verify a transfer completed correctly and the ARQ+CRC logic works, follow these steps after a transfer:

1. Check logs for ACKs and final metrics:
   - `Log Files/Server Logs/reception_log.txt` and `Log Files/Server Logs/crc_log.txt` should contain entries indicating CRC checks and ACKs.
   - `Log Files/Client Logs/transmission_log.txt` should show chunk send events and server responses.

2. Compare the original file and the received file using SHA256 (PowerShell):

```powershell
# compute hash of original file
Get-FileHash .\Test Samples\sample_image.jpg -Algorithm SHA256

# compute hash of received file (after a file transfer)
Get-FileHash .\Received Output\received_file.jpg -Algorithm SHA256
```

If hashes match exactly, the reconstruction is bit-for-bit identical — success.

3. Validate data integrity reported by scripts:
- The server/client log metrics include "Data Integrity Rate" and throughput. Open `Log Files/*/metrics_log.txt` to inspect values.
- `test_runner.py` aggregates test results into `test_results.txt` or `performance_results.txt`.

4. Validate CRC unit:
- Run unit tests:

```powershell
pytest tests/test_crc.py -q
```

This checks `crc_utils.py` outputs for known inputs and ensures CI can run quickly without networking.

5. Manual small test:
- Start server and client on `localhost`. Send a small sample file with error probability `0`. Confirm the SHA256 hashes match.

---

## Logs and expected outputs
- `transmission_log.txt` (client): chunk send times, error injection events, server responses, session start/end.
- `crc_log.txt` (client and server): CRC values sent/received and whether they matched.
- `metrics_log.txt` (client and server): throughput, total transmission time, Data Integrity Rate, avg RTT, SNR estimate.

---

## Troubleshooting
- Connection refused: confirm server is running and firewall allows TCP on port 65432. Use `localhost` when testing on the same machine.
- Large files: video samples >50 MB will be slow; use small samples for demos or remove them from repo and provide a download link or Releases.
- If `Received Output` is empty: check server logs for early connection close or `Incomplete data` messages.
- Permission errors on Windows: run PowerShell with appropriate permissions and ensure write permissions to `Log Files/` and `Received Output/`.

---

## Professional notes and CI suggestions
- Add `tests/test_crc.py` so CI (GitHub Actions) can run fast tests without network.
- Use `.gitignore` to exclude `Log Files/`, `Received Output/`, `__pycache__/`, `.venv/`, and large `Test Samples/` media.
- Use Git LFS or Releases for large media; include only small sample files in `Test Samples/` for demos.
- Add a minimal GitHub Actions workflow to run `pytest` and optional linter (no networking in CI).

---

## Contribution
If you accept contributions, add `CONTRIBUTING.md` describing how to run tests, code style, and how to open issues/PRs. Include a `LICENSE` file (MIT recommended) if you want others to reuse the code.

---

If you want, I can also add a ready `.gitignore`, `requirements.txt`, `tests/test_crc.py` and a minimal CI workflow to the repository. Let me know which additional files you'd like me to add now.
