import socket
import os
import time
from crc_utils import crc32

HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)
CHUNK_SIZE = 1024
END_SIGNAL = b'__END__'
EOT_SIGNAL = b'__EOT__'
LOG_DIR = 'Log Files/Server Logs'
OUTPUT_DIR = 'Received Output'
LOG_FILE = os.path.join(LOG_DIR, 'reception_log.txt')
CRC_LOG_FILE = os.path.join(LOG_DIR, 'crc_log.txt')
METRICS_LOG_FILE = os.path.join(LOG_DIR, 'metrics_log.txt')


# Helper to guess file type from first chunk (very basic)
def guess_file_extension(chunk):
    if chunk.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if chunk.startswith(b'\x89PNG'):
        return '.png'
    if chunk.startswith(b'GIF8'):
        return '.gif'
    if chunk.startswith(b'BM'):
        return '.bmp'
    if chunk[4:8] == b'ftyp':
        return '.mp4'
    if chunk[:4] == b'RIFF' and chunk[8:12] == b'WAVE':
        return '.wav'
    if chunk[:4] == b'ID3' or chunk[-128:-125] == b'TAG':
        return '.mp3'
    return '.bin'

def log_event(logf, msg):
    logf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")
    logf.flush()

def log_crc(crcf, chunk_num, recv_crc, calc_crc, match):
    crcf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Chunk {chunk_num}: CRC received: {recv_crc:08X}, CRC calculated: {calc_crc:08X}, Match: {match}\n")
    crcf.flush()

def log_metrics(metricsf, metrics_lines):
    for line in metrics_lines:
        metricsf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")
    metricsf.flush()

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    # Create log directory and clear logs only when server is actually run
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    open(LOG_FILE, 'w').close()
    open(CRC_LOG_FILE, 'w').close()
    open(METRICS_LOG_FILE, 'w').close()
    with open(LOG_FILE, 'a') as logf, open(CRC_LOG_FILE, 'a') as crcf, open(METRICS_LOG_FILE, 'a') as metricsf:
        s.bind((HOST, PORT))
        s.listen()
        print(f"Server listening on {HOST}:{PORT}")
        conn, addr = s.accept()
        with conn:
            print('Connected by', addr)
            while True:
                chunk_num = 0
                received_chunks = []
                is_binary = None
                output_path = None
                file_ext = None
                end_signal_received = False
                total_chunks_received = 0
                unique_chunks_received = set()
                total_bytes_received = 0
                # SNR counters
                total_bits_received = 0
                error_bits = 0
                start_time = None
                while True:
                    data = conn.recv(CHUNK_SIZE + 4)
                    if not data:
                        break
                    if data == END_SIGNAL:
                        print('End signal received. Session closed.')
                        log_event(logf, 'End signal received. Session closed.')
                        end_signal_received = True
                        break
                    if data == EOT_SIGNAL:
                        # Save file/message immediately after EOT
                        if received_chunks:
                            full_data = b''.join(received_chunks)
                            end_time = time.time()
                            if is_binary:
                                output_path = os.path.join(OUTPUT_DIR, f'received_file{file_ext}')
                                with open(output_path, 'wb') as f:
                                    f.write(full_data)
                                print(f'Full binary file received and saved as: {output_path}')
                                log_event(logf, f'Full binary file received and saved as: {output_path}')
                            else:
                                try:
                                    print('Full message received:', full_data.decode())
                                    log_event(logf, f'Full message received: {full_data.decode()}')
                                except Exception as e:
                                    print('Could not decode received data as text:', e)
                                    log_event(logf, f'Could not decode received data as text: {e}')
                            # Metrics
                            duration = (end_time - start_time) if (end_time and start_time and end_time > start_time) else 1
                            throughput = total_bytes_received / duration
                            data_integrity_rate = (len(unique_chunks_received) / total_chunks_received) if total_chunks_received else 0
                            # SNR calculation
                            if error_bits == 0:
                                snr_db = 'Infinity'
                            else:
                                correct_bits = total_bits_received - error_bits
                                snr = correct_bits / error_bits if error_bits > 0 else 0
                                snr_db = f"{10 * (snr if snr > 0 else 0):.2f}" if snr > 0 else '0.00'
                                import math
                                if snr > 0:
                                    snr_db = f"{10 * math.log10(snr):.2f}"
                                else:
                                    snr_db = '0.00'
                            snr_line = f"Empirical SNR: {snr_db} dB (Total bits: {total_bits_received}, Error bits: {error_bits})"
                            print(snr_line)
                            metrics_lines = [
                                f"Total transmission time: {duration:.4f} seconds",
                                f"Throughput: {throughput:.2f} bytes/sec",
                                f"Data Integrity Rate: {data_integrity_rate:.4f}",
                                snr_line
                            ]
                            for line in metrics_lines:
                                print(line)
                            log_metrics(metricsf, metrics_lines)
                        print('Reception complete for this message/file. Waiting for next...')
                        break  # Reset for next transmission
                    if len(data) < 5:
                        print(f'Chunk {chunk_num}: Incomplete data received.')
                        log_event(logf, f'Chunk {chunk_num}: Incomplete data received.')
                        conn.sendall(b'NACK: Incomplete data')
                        break
                    chunk, recv_crc_bytes = data[:-4], data[-4:]
                    recv_crc = int.from_bytes(recv_crc_bytes, 'big')
                    calc_crc = crc32(chunk)
                    total_chunks_received += 1
                    total_bits_received += len(chunk) * 8
                    match = (recv_crc == calc_crc)
                    log_crc(crcf, chunk_num, recv_crc, calc_crc, match)
                    if match:
                        if is_binary is None:
                            try:
                                chunk.decode()
                                is_binary = False
                            except Exception:
                                is_binary = True
                                file_ext = guess_file_extension(chunk)
                        if start_time is None:
                            start_time = time.time()
                        received_chunks.append(chunk)
                        total_bytes_received += len(chunk)
                        unique_chunks_received.add(chunk_num)
                        conn.sendall(b'ACK: CRC32 valid')
                        log_event(logf, f'Chunk {chunk_num}: CRC32 valid (ACK)')
                    else:
                        error_bits += len(chunk) * 8
                        conn.sendall(b'NACK: CRC32 error')
                        log_event(logf, f'Chunk {chunk_num}: CRC32 error (NACK)')
                    chunk_num += 1
                if end_signal_received:
                    break 