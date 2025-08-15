# Stop-and-Wait ARQ with CRC — Python file-transfer simulator

A computer-networking project that implements Stop-and-Wait ARQ with CRC-based error detection to reliably transfer files (text and multimedia) between a client and a server. The project provides both CLI and GUI front-ends, configurable bit-error simulation (BER), and detailed performance logging (throughput, SNR, data-integrity).

Features
- Stop-and-Wait ARQ sender and receiver with CRC32 error detection
- GUI front-ends: `client_gui.py` and `server_gui.py` for easy demo and testing
- File chunking and retransmission logic (handles text, images, audio, video)
- Configurable BER to simulate noisy channels and observe retransmissions
- Detailed logs: transmission events, CRC checks, metrics (throughput, RTT, SNR)
- Works on a single machine or across two machines on the same local network

Files included (important)
- `Codes/client_gui.py` — client GUI (select files, set BER, connect to server, send)
- `Codes/server_gui.py` — server GUI (listen, show reception, save received files)
- `Codes/client.py` / `Codes/server.py` — CLI sender/receiver (optional)
- `Codes/crc_utils.py` — CRC implementations (CRC32 and CRC16 helper)
- `Codes/file_chunker.py` — file chunking helper

Software requirements
- Python 3.10+ (recommended)
- tkinter (usually bundled with Python)
- Minimal Python packages: matplotlib, pytest

Usage (GUI) — single laptop
1. Start the server GUI in one terminal:

```powershell
python .\Codes\server_gui.py
```

2. Start the client GUI in another terminal:

```powershell
python .\Codes\client_gui.py
```

3. In the client GUI:
- Enter server IP and click connect.
- Click `Browse` to select a test file from your computer.
- Set BER (bit-error rate) to simulate noise; use `0` for a clean channel.
- Click `Start Transmission` to start the transfer.

4. After transmission finishes the server will save the received file under `Received Output/` and both sides write logs under `Log Files/`.

Usage (GUI) — two laptops on same WiFi
1. On the server laptop, run:

```powershell
python .\Codes\server_gui.py
```

2. On the client laptop, ensure both laptops are connected to the same local network (same WiFi). Run:

```powershell
python .\Codes\client_gui.py
```

3. In the client GUI: enter the server laptop's IPv4 address (find it with `ipconfig` on Windows), set BER, choose the file, then `Connect` and `Send`.

Notes:
- Both machines must be on the same local network and port 65432 should be reachable (allow Python through the firewall if prompted).
- The client GUI sends chunk+CRC for each chunk; the server replies with ACK or NACK and reconstructs the file after all chunks are received.

Simulating noise (BER)
- Use the BER control in the client GUI to introduce random single-bit flips per chunk.
- Observe retransmissions in the client `transmission_log.txt` and CRC mismatches in the server `crc_log.txt`.
- Increase BER to see throughput drop and retransmissions increase; set BER to `0` for baseline comparisons.

Troubleshooting
- Connection refused: ensure server GUI is running and firewall allows port 65432.
- Wrong server IP: on the server run `ipconfig` and use the IPv4 address on the client.
- Received file missing or corrupted: try BER = 0, check logs for early disconnects or `Incomplete data` messages.
- GUI not appearing: ensure `tkinter` is installed and your Python distribution includes it.

Common parameters to tune (in code)
- `CHUNK_SIZE` — size of each chunk (default 1024 bytes)
- `MAX_RETRIES` — how many times the client retries a chunk
- `TIMEOUT` — socket recv timeout in seconds

Project license
This project is licensed under the MIT License — see `LICENSE`.

Author
Karthik S

