import socket
import os
import random
import time
from crc_utils import crc32
from file_chunker import file_chunker

PORT = 65432
CHUNK_SIZE = 1024
TIMEOUT = 3  # seconds
MAX_RETRIES = 5
END_SIGNAL = b'__END__'
EOT_SIGNAL = b'__EOT__'
LOG_DIR = 'Log Files/Client Logs'
LOG_FILE = os.path.join(LOG_DIR, 'transmission_log.txt')
CRC_LOG_FILE = os.path.join(LOG_DIR, 'crc_log.txt')
METRICS_LOG_FILE = os.path.join(LOG_DIR, 'metrics_log.txt')

server_ip = input('Enter the server IP address: ').strip()

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    s.connect((server_ip, PORT))
    print(f"Successfully connected to server at {server_ip}:{PORT}")
except Exception as e:
    print(f"Failed to connect to server at {server_ip}:{PORT}. Error: {e}")
    exit(1)

# Create log directory and clear logs only when client is actually run
os.makedirs(LOG_DIR, exist_ok=True)
open(LOG_FILE, 'w').close()
open(CRC_LOG_FILE, 'w').close()
open(METRICS_LOG_FILE, 'w').close()

def is_file(path):
    return os.path.isfile(path)

def get_chunks(input_data, is_binary_file):
    if is_binary_file:
        return list(file_chunker(input_data, CHUNK_SIZE))
    else:
        data = input_data.encode()
        return [data[i:i+CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]

def flip_random_bit(data):
    if not data:
        return data
    idx = random.randint(0, len(data) - 1)
    bit = 1 << random.randint(0, 7)
    flipped = bytearray(data)
    flipped[idx] ^= bit
    return bytes(flipped)

def log_event(logf, msg):
    logf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")
    logf.flush()

def log_crc(crcf, chunk_num, crc):
    crcf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Chunk {chunk_num}: CRC sent: {crc:08X}\n")
    crcf.flush()

def log_metrics(metricsf, metrics_lines):
    for line in metrics_lines:
        metricsf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")
    metricsf.flush()

with s, \
     open(LOG_FILE, 'a') as logf, \
     open(CRC_LOG_FILE, 'a') as crcf, \
     open(METRICS_LOG_FILE, 'a') as metricsf:
    while True:
        input_data = input('Enter text or file path (or type END to finish): ').strip()
        if input_data.upper() == 'END':
            s.sendall(END_SIGNAL)
            print('Session ended by user.')
            log_event(logf, 'Session ended by user.')
            break
        is_binary_file = is_file(input_data)
        if is_binary_file:
            print(f"Detected file input: {input_data}")
            file_type = os.path.splitext(input_data)[1].lower()
            print(f"File type: {file_type}")
        else:
            print("Detected text input.")
        chunks = get_chunks(input_data, is_binary_file)
        total_chunks = len(chunks)
        print(f"Total chunks to send: {total_chunks}")
        # Error simulation
        error_prob = input('Enter bit error probability per chunk (0 for none): ').strip()
        try:
            error_prob = float(error_prob)
        except ValueError:
            error_prob = 0.0
        log_event(logf, f"Transmission started: {input_data} | Chunks: {total_chunks} | Error prob: {error_prob}")
        chunk_num = 0
        total_bytes_acked = 0
        total_chunks_sent = 0
        unique_chunks_acked = set()
        start_time = time.time()
        chunk_rtts = []
        # SNR counters
        total_bits_sent = 0
        error_bits = 0
        while chunk_num < total_chunks:
            chunk = chunks[chunk_num]
            retries = 0
            while retries < MAX_RETRIES:
                crc = crc32(chunk)
                log_crc(crcf, chunk_num, crc)
                send_chunk = chunk
                # Simulate random bit error
                bit_error_introduced = False
                if error_prob > 0 and random.random() < error_prob:
                    send_chunk = flip_random_bit(send_chunk)
                    log_event(logf, f"Chunk {chunk_num}: Bit error introduced.")
                    bit_error_introduced = True
                send_time = time.time()
                s.sendall(send_chunk + crc.to_bytes(4, 'big'))
                log_event(logf, f"Chunk {chunk_num}: Sent (retry {retries+1})")
                total_chunks_sent += 1
                total_bits_sent += len(send_chunk) * 8
                if bit_error_introduced:
                    error_bits += 8  # 1 bit flipped per chunk
                try:
                    resp = s.recv(1024)
                    ack_time = time.time()
                    resp_decoded = resp.decode()
                    log_event(logf, f"Chunk {chunk_num}: Server response: {resp_decoded}")
                    if resp_decoded.startswith('ACK'):
                        chunk_num += 1
                        total_bytes_acked += len(chunk)
                        unique_chunks_acked.add(chunk_num)
                        chunk_rtts.append(ack_time - send_time)
                        break
                    else:
                        log_event(logf, f"Chunk {chunk_num}: NACK received. Retrying.")
                except socket.timeout:
                    log_event(logf, f"Chunk {chunk_num}: Timeout waiting for ACK/NACK. Retrying.")
                retries += 1
            else:
                print(f"Chunk {chunk_num}: Failed after {MAX_RETRIES} attempts. Aborting.")
                log_event(logf, f"Chunk {chunk_num}: Failed after {MAX_RETRIES} attempts. Aborting.")
                break
        end_time = time.time()
        s.sendall(EOT_SIGNAL)
        print('Transmission complete for this message/file.')
        log_event(logf, f"Transmission complete for {input_data}.")
        # Metrics
        duration = end_time - start_time if end_time > start_time else 1
        throughput = total_bytes_acked / duration
        data_integrity_rate = (len(unique_chunks_acked) / total_chunks_sent) if total_chunks_sent else 0
        avg_rtt = sum(chunk_rtts) / len(chunk_rtts) if chunk_rtts else 0
        # SNR calculation
        if error_bits == 0:
            snr_db = 'Infinity'
        else:
            correct_bits = total_bits_sent - error_bits
            snr = correct_bits / error_bits if error_bits > 0 else 0
            snr_db = f"{10 * (snr if snr > 0 else 0):.2f}" if snr > 0 else '0.00'
            import math
            if snr > 0:
                snr_db = f"{10 * math.log10(snr):.2f}"
            else:
                snr_db = '0.00'
        snr_line = f"Simulated SNR: {snr_db} dB (Total bits: {total_bits_sent}, Error bits: {error_bits})"
        print(snr_line)
        metrics_lines = [
            f"Total transmission time: {duration:.4f} seconds",
            f"Throughput: {throughput:.2f} bytes/sec",
            f"Data Integrity Rate: {data_integrity_rate:.4f}",
            f"Average RTT: {avg_rtt:.4f} seconds",
            snr_line
        ]
        for line in metrics_lines:
            print(line)
        log_metrics(metricsf, metrics_lines) 