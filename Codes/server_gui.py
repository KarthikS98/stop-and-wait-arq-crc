import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import os
import time
import socket
from crc_utils import crc32
import socket
from PIL import Image, ImageTk
import sys
import platform
import subprocess
import pygame

PORT = 65432
CHUNK_SIZE = 1024
END_SIGNAL = b'__END__'
EOT_SIGNAL = b'__EOT__'
ABORT_SIGNAL = b'__ABORT__'
LOG_DIR = 'Log Files/Server Logs'
OUTPUT_DIR = 'Received Output'
LOG_FILE = os.path.join(LOG_DIR, 'reception_log.txt')
CRC_LOG_FILE = os.path.join(LOG_DIR, 'crc_log.txt')
METRICS_LOG_FILE = os.path.join(LOG_DIR, 'metrics_log.txt')

class ServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('Stop-and-Wait ARQ Server')
        self.server_thread = None
        self.running = False
        self.conn = None
        self.setup_widgets()

    def setup_widgets(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=10, pady=10, fill='x')
        tk.Button(frame, text='Start Server', command=self.start_server).grid(row=0, column=0, pady=5)
        tk.Button(frame, text='Stop Server', command=self.stop_server).grid(row=0, column=1, pady=5)
        self.status_label = tk.Label(frame, text='Server not running')
        self.status_label.grid(row=0, column=2, padx=10)
        tk.Button(frame, text='Performance Logs', command=self.show_logs_window).grid(row=0, column=3, padx=10)
        self.log_area = scrolledtext.ScrolledText(self.root, width=90, height=25, state='disabled')
        self.log_area.pack(padx=10, pady=10)
        self.preview_btn = tk.Button(frame, text='Show Received File', command=self.open_big_preview)
        self.preview_btn.grid(row=0, column=4, padx=10)
        self.audio_loaded = False

    def log(self, msg):
        self.log_area.config(state='normal')
        self.log_area.insert('end', msg + '\n')
        self.log_area.see('end')
        self.log_area.config(state='disabled')

    def clear_logs(self):
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', 'end')
        self.log_area.config(state='disabled')

    def start_server(self):
        if self.running:
            messagebox.showinfo('Info', 'Server already running.')
            return
        self.clear_logs()
        self.running = True
        self.status_label.config(text='Server running...')
        self.server_thread = threading.Thread(target=self.run_server, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        self.running = False
        self.status_label.config(text='Server stopped')
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
        self.log('Server stopped by user.')

    def run_server(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        open(LOG_FILE, 'w').close()
        open(CRC_LOG_FILE, 'w').close()
        open(METRICS_LOG_FILE, 'w').close()
        def log_event(msg):
            self.log(msg)
            with open(LOG_FILE, 'a') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")
        def log_crc(chunk_num, recv_crc, calc_crc, match):
            line = f"Chunk {chunk_num}: CRC received: {recv_crc:08X}, CRC calculated: {calc_crc:08X}, Match: {match}"
            self.log(line)
            with open(CRC_LOG_FILE, 'a') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")
        def log_metrics(metrics_lines):
            with open(METRICS_LOG_FILE, 'a') as f:
                for line in metrics_lines:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")
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
        def show_status_message(message, color):
            self.log_area.config(state='normal')
            self.log_area.insert('end', message + '\n')
            self.log_area.tag_add('status', 'end-2l', 'end-1l')
            self.log_area.tag_config('status', foreground=color, font=('Arial', 12, 'bold'))
            self.log_area.see('end')
            self.log_area.config(state='disabled')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', PORT))
            s.listen()
            self.log(f"Server listening on 0.0.0.0:{PORT}")
            while self.running:
                try:
                    s.settimeout(1.0)
                    self.conn, addr = s.accept()
                except socket.timeout:
                    continue
                with self.conn:
                    self.log(f'Connected by {addr}')
                    session_active = True
                    while self.running and session_active:
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
                        crc_log_cleared = False
                        while self.running:
                            try:
                                # For mp3, check for extension metadata
                                if file_ext is None:
                                    peek = self.conn.recv(8, socket.MSG_PEEK)
                                    if peek.startswith(b'.mp3'):
                                        ext_bytes = self.conn.recv(8)
                                        file_ext = ext_bytes.strip().decode()
                                        continue
                                data = self.conn.recv(CHUNK_SIZE + 4)
                            except Exception:
                                break
                            if not data:
                                break
                            if data == ABORT_SIGNAL:
                                log_event('Transfer failed. Client aborted transmission.')
                                show_status_message('Transfer failed.', 'red')
                                self.last_received_file = None
                                received_chunks = []
                                break
                            # Clear CRC log at the start of a new transmission (first chunk)
                            if not crc_log_cleared and len(data) >= 5 and data != END_SIGNAL and data != EOT_SIGNAL:
                                open(CRC_LOG_FILE, 'w').close()
                                crc_log_cleared = True
                            if data == END_SIGNAL:
                                self.log('End signal received. Session closed.')
                                log_event('End signal received. Session closed.')
                                end_signal_received = True
                                session_active = False
                                break
                            if data == EOT_SIGNAL:
                                if received_chunks:
                                    # Clear all log files before each new transmission except CRC log
                                    open(LOG_FILE, 'w').close()
                                    open(METRICS_LOG_FILE, 'w').close()
                                    self.clear_logs()  # Clear GUI log area
                                    full_data = b''.join(received_chunks)
                                    end_time = time.time()
                                    if is_binary:
                                        # Only save and show 'complete' if all chunks were received
                                        if chunk_num == total_chunks_received:
                                            output_path = os.path.join(OUTPUT_DIR, f'received_file{file_ext}')
                                            with open(output_path, 'wb') as f:
                                                f.write(full_data)
                                            log_event(f'Full binary file received and saved as: {output_path}')
                                            self.last_received_file = output_path
                                            self.show_file_preview(output_path)
                                            # If audio, ensure preview button will play audio
                                            audio_exts = ['.wav', '.mp3']
                                            if file_ext in audio_exts:
                                                self.preview_btn.config(command=lambda: self.open_big_preview('audio'))
                                            show_status_message('Transfer complete.', 'green')
                                        else:
                                            log_event('Transfer failed. Incomplete file received.')
                                            show_status_message('Transfer failed.', 'red')
                                            self.last_received_file = None
                                    elif not is_binary:
                                        try:
                                            log_event('Full message received: ' + full_data.decode())
                                            self.hide_file_preview()
                                            show_status_message('Transfer complete.', 'green')
                                        except Exception as e:
                                            log_event(f'Could not decode received data as text: {e}')
                                            self.hide_file_preview()
                                            show_status_message('Transfer failed.', 'red')
                                    duration = (end_time - start_time) if (end_time and start_time and end_time > start_time) else 1
                                    throughput = total_bytes_received / duration
                                    data_integrity_rate = (len(unique_chunks_received) / total_chunks_received) if total_chunks_received else 0
                                    import math
                                    if error_bits == 0:
                                        snr_db = 'Infinity'
                                    else:
                                        correct_bits = total_bits_received - error_bits
                                        snr = correct_bits / error_bits if error_bits > 0 else 0
                                        snr_db = f"{10 * math.log10(snr):.2f}" if snr > 0 else '0.00'
                                    snr_line = f"SNR: {snr_db} dB (Total bits: {total_bits_received}, Error bits: {error_bits})"
                                    metrics_lines = [
                                        f"Total transmission time: {duration:.4f} seconds",
                                        f"Throughput: {throughput:.2f} bytes/sec",
                                        f"Data Integrity Rate: {data_integrity_rate:.4f}",
                                        snr_line
                                    ]
                                    # Remove metrics display from main log area
                                    log_metrics(metrics_lines)  # Only logs to file, not to main log area
                                    show_status_message('Transfer complete.', 'green')
                                else:
                                    show_status_message('Transfer failed.', 'red')
                                self.log('Reception complete for this message/file. Waiting for next...')
                                break
                            if len(data) < 5:
                                self.log(f'Chunk {chunk_num}: Incomplete data received.')
                                log_event(f'Chunk {chunk_num}: Incomplete data received.')
                                show_status_message('Transfer failed.', 'red')
                                break
                            chunk, recv_crc_bytes = data[:-4], data[-4:]
                            recv_crc = int.from_bytes(recv_crc_bytes, 'big')
                            calc_crc = crc32(chunk)
                            total_chunks_received += 1
                            total_bits_received += len(chunk) * 8
                            match = (recv_crc == calc_crc)
                            log_crc(chunk_num, recv_crc, calc_crc, match)
                            if match:
                                if is_binary is None:
                                    try:
                                        chunk.decode()
                                        is_binary = False
                                    except Exception:
                                        is_binary = True
                                        if file_ext is None:
                                            file_ext = guess_file_extension(chunk)
                                if start_time is None:
                                    start_time = time.time()
                                received_chunks.append(chunk)
                                total_bytes_received += len(chunk)
                                unique_chunks_received.add(chunk_num)
                                try:
                                    self.conn.sendall(b'ACK: CRC32 valid')
                                except Exception:
                                    pass
                                log_event(f'Chunk {chunk_num}: CRC32 valid (ACK)')
                            else:
                                error_bits += len(chunk) * 8
                                try:
                                    self.conn.sendall(b'NACK: CRC32 error')
                                except Exception:
                                    pass
                                log_event(f'Chunk {chunk_num}: CRC32 error (NACK)')
                            chunk_num += 1
                        if end_signal_received:
                            break
                self.log('Connection closed. Waiting for next client...')

    def show_logs_window(self):
        logs_win = tk.Toplevel(self.root)
        logs_win.title('Performance Logs')
        tab_control = None
        try:
            from tkinter import ttk
            tab_control = ttk.Notebook(logs_win)
        except ImportError:
            tab_control = None
        def read_log_file(path):
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            return '(No log found)'
        logs = [
            ('Reception Log', LOG_FILE),
            ('CRC Log', CRC_LOG_FILE),
            ('Metrics Log', METRICS_LOG_FILE)
        ]
        if tab_control:
            for name, path in logs:
                tab = tk.Frame(tab_control)
                text = scrolledtext.ScrolledText(tab, width=100, height=30)
                text.insert('1.0', read_log_file(path))
                text.config(state='disabled')
                text.pack(expand=True, fill='both')
                tab_control.add(tab, text=name)
            tab_control.pack(expand=True, fill='both')
        else:
            for name, path in logs:
                label = tk.Label(logs_win, text=name, font=('Arial', 12, 'bold'))
                label.pack()
                text = scrolledtext.ScrolledText(logs_win, width=100, height=10)
                text.insert('1.0', read_log_file(path))
                text.config(state='disabled')
                text.pack()

    def show_file_preview(self, path):
        ext = os.path.splitext(path)[1].lower()
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        audio_exts = ['.wav', '.mp3']
        video_exts = ['.mp4', '.avi', '.mov', '.mkv']
        # No need to hide the button; it's always visible
        if ext in image_exts:
            self.preview_btn.config(command=lambda: self.open_big_preview('image'))
        elif ext in audio_exts:
            self.preview_btn.config(command=lambda: self.open_big_preview('audio'))
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(path)
                self.audio_loaded = True
            except Exception:
                self.audio_loaded = False
        elif ext in video_exts:
            self.preview_btn.config(command=lambda: self.open_big_preview('video'))
            self.audio_loaded = False
        else:
            self.preview_btn.config(command=self.open_big_preview)

    def hide_file_preview(self):
        # No need to hide the button; it's always visible
        self.audio_loaded = False

    def open_big_preview(self, mode=None):
        if not hasattr(self, 'last_received_file') or not self.last_received_file or not os.path.exists(self.last_received_file):
            messagebox.showinfo('No File', 'No file received. Please transmit first.')
            return
        path = self.last_received_file
        ext = os.path.splitext(path)[1].lower()
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        audio_exts = ['.wav', '.mp3']
        video_exts = ['.mp4', '.avi', '.mov', '.mkv']
        if not mode:
            if ext in image_exts:
                mode = 'image'
            elif ext in audio_exts:
                mode = 'audio'
            elif ext in video_exts:
                mode = 'video'
        if mode == 'image':
            win = tk.Toplevel(self.root)
            win.title('Image Preview')
            try:
                img = Image.open(path)
                img.thumbnail((600, 600))
                tk_img = ImageTk.PhotoImage(img)
                label = tk.Label(win, image=tk_img)
                label.image = tk_img
                label.pack()
            except Exception as e:
                tk.Label(win, text=f'Could not open image: {e}').pack()
        elif mode == 'audio':
            win = tk.Toplevel(self.root)
            win.title('Audio Player')
            btn_frame = tk.Frame(win)
            btn_frame.pack(pady=20)
            def play():
                try:
                    pygame.mixer.init()
                    pygame.mixer.music.load(path)
                    pygame.mixer.music.play()
                except Exception as e:
                    messagebox.showerror('Error', f'Could not play audio: {e}')
            def pause():
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.pause()
                except Exception:
                    pass
            def stop():
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass
            play_btn = tk.Button(btn_frame, text='Play', command=play)
            pause_btn = tk.Button(btn_frame, text='Pause', command=pause)
            stop_btn = tk.Button(btn_frame, text='Stop', command=stop)
            play_btn.pack(side='left', padx=10)
            pause_btn.pack(side='left', padx=10)
            stop_btn.pack(side='left', padx=10)
        elif mode == 'video':
            try:
                if platform.system() == 'Windows':
                    os.startfile(path)
                elif platform.system() == 'Darwin':
                    subprocess.call(['open', path])
                else:
                    subprocess.call(['xdg-open', path])
            except Exception as e:
                messagebox.showerror('Error', f'Could not play video: {e}')

    def play_received_file(self):
        if not hasattr(self, 'last_received_file'):
            return
        path = self.last_received_file
        ext = os.path.splitext(path)[1].lower()
        audio_exts = ['.wav', '.mp3']
        video_exts = ['.mp4', '.avi', '.mov', '.mkv']
        if ext in audio_exts:
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
            except Exception as e:
                messagebox.showerror('Error', f'Could not play audio: {e}')
        elif ext in video_exts:
            try:
                if platform.system() == 'Windows':
                    os.startfile(path)
                elif platform.system() == 'Darwin':
                    subprocess.call(['open', path])
                else:
                    subprocess.call(['xdg-open', path])
            except Exception as e:
                messagebox.showerror('Error', f'Could not play video: {e}')

    def pause_audio(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.pause()
        except Exception:
            pass

    def stop_audio(self):
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

if __name__ == '__main__':
    root = tk.Tk()
    app = ServerGUI(root)
    root.mainloop() 