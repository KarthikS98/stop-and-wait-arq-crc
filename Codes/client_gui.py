import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import threading
import os
import time
import random
from crc_utils import crc32
from file_chunker import file_chunker
import socket
from PIL import Image, ImageTk
import sys
import platform
import subprocess
import pygame


CHUNK_SIZE = 1024

TIMEOUT = 3
MAX_RETRIES = 5
END_SIGNAL = b'__END__'
EOT_SIGNAL = b'__EOT__'
ABORT_SIGNAL = b'__ABORT__'
LOG_DIR = 'Log Files/Client Logs'
LOG_FILE = os.path.join(LOG_DIR, 'transmission_log.txt')
CRC_LOG_FILE = os.path.join(LOG_DIR, 'crc_log.txt')
METRICS_LOG_FILE = os.path.join(LOG_DIR, 'metrics_log.txt')
PORT = 65432
class ClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title('Stop-and-Wait ARQ Client')
        self.file_path = None
        self.is_binary_file = False
        self.server_ip = tk.StringVar()
        self.error_prob = tk.StringVar(value='0')
        self.input_text = tk.StringVar()
        self.connected = False
        self.s = None
        self.transmitting = False
        self.send_choice = tk.StringVar(value='text')
        self.setup_widgets()

    def setup_widgets(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=10, pady=10, fill='x')

        tk.Label(frame, text='Server IP:').grid(row=0, column=0, sticky='e')
        self.ip_entry = tk.Entry(frame, textvariable=self.server_ip, width=20)
        self.ip_entry.grid(row=0, column=1, sticky='w')
        self.connect_btn = tk.Button(frame, text='Connect', command=self.connect_to_server)
        self.connect_btn.grid(row=0, column=2, padx=5)

        # Send choice (disabled until connected)
        self.choice_frame = tk.Frame(frame)
        self.choice_frame.grid(row=1, column=0, columnspan=3, sticky='w', pady=5)
        self.text_radio = tk.Radiobutton(self.choice_frame, text='Send Text', variable=self.send_choice, value='text', command=self.update_send_choice, state='disabled')
        self.text_radio.pack(side='left')
        self.file_radio = tk.Radiobutton(self.choice_frame, text='Send File', variable=self.send_choice, value='file', command=self.update_send_choice, state='disabled')
        self.file_radio.pack(side='left')

        # Text input (hidden until chosen)
        self.text_label = tk.Label(frame, text='Text to Send:')
        self.text_entry = tk.Entry(frame, textvariable=self.input_text, width=40)
        self.text_entry.bind('<KeyRelease>', self.on_text_entry)

        # File input (hidden until chosen)
        self.file_btn = tk.Button(frame, text='Choose File', command=self.choose_file)
        self.file_label = tk.Label(frame, text='No file selected')
        self.preview_btn = tk.Button(frame, text='', command=self.open_big_preview)
        self.preview_btn.grid(row=3, column=2, padx=5, sticky='w')
        self.preview_btn.config(state='disabled')
        self.audio_loaded = False

        # Error probability (disabled until input provided)
        tk.Label(frame, text='Error Probability:').grid(row=4, column=0, sticky='e')
        self.error_entry = tk.Entry(frame, textvariable=self.error_prob, width=10, state='disabled')
        self.error_entry.grid(row=4, column=1, sticky='w')

        # Start/End buttons
        self.start_btn = tk.Button(frame, text='Start Transmission', command=self.start_transmission, state='disabled')
        self.start_btn.grid(row=5, column=0, pady=5)
        tk.Button(frame, text='End Session', command=self.end_session).grid(row=5, column=1, pady=5, sticky='w')
        tk.Button(frame, text='Performance Logs', command=self.show_logs_window).grid(row=5, column=2, pady=5, sticky='w')

        self.log_area = scrolledtext.ScrolledText(self.root, width=80, height=20, state='disabled')
        self.log_area.pack(padx=10, pady=10)

    def connect_to_server(self):
        ip = self.server_ip.get().strip()
        if not ip:
            messagebox.showerror('Error', 'Please enter the server IP address.')
            return
        # Only validate IP format, do not open/close socket here
        import socket as pysocket
        try:
            pysocket.inet_aton(ip)
        except Exception:
            self.connected = False
            messagebox.showerror('Error', 'Invalid IP address format.')
            return
        # Create log directory and clear logs only when connecting
        os.makedirs(LOG_DIR, exist_ok=True)
        open(LOG_FILE, 'w').close()
        open(CRC_LOG_FILE, 'w').close()
        open(METRICS_LOG_FILE, 'w').close()
        # Create and connect the persistent socket
        try:
            if self.s:
                self.s.close()
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.settimeout(TIMEOUT)
            self.s.connect((ip, PORT))
        except Exception as e:
            self.connected = False
            messagebox.showerror('Error', f'Failed to connect to server: {e}')
            return
        self.connected = True
        self.log('Connected to server at ' + ip)
        self.text_radio.config(state='normal')
        self.file_radio.config(state='normal')
        self.connect_btn.config(state='disabled')
        self.ip_entry.config(state='disabled')
        self.update_send_choice()

    def update_send_choice(self):
        # Hide all input fields first
        self.text_label.grid_forget()
        self.text_entry.grid_forget()
        self.file_btn.grid_forget()
        self.file_label.grid_forget()
        self.error_entry.config(state='disabled')
        self.start_btn.config(state='disabled')
        self.input_text.set('')
        self.file_path = None
        self.is_binary_file = False
        self.file_label.config(text='No file selected')
        self.hide_file_preview()
        if self.send_choice.get() == 'text':
            self.text_label.grid(row=2, column=0, sticky='e')
            self.text_entry.grid(row=2, column=1, sticky='w')
            self.preview_btn.config(state='disabled')
        elif self.send_choice.get() == 'file':
            self.file_btn.grid(row=3, column=0, pady=5)
            self.file_label.grid(row=3, column=1, sticky='w')

    def on_text_entry(self, event=None):
        if self.input_text.get():
            self.file_path = None
            self.is_binary_file = False
            self.file_label.config(text='No file selected')
            self.error_entry.config(state='normal')
            self.start_btn.config(state='normal')
            self.hide_file_preview()
        else:
            self.error_entry.config(state='disabled')
            self.start_btn.config(state='disabled')
            self.hide_file_preview()

    def choose_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.file_path = path
            self.is_binary_file = True
            self.file_label.config(text=os.path.basename(path))
            self.input_text.set('')  # Clear text if file is chosen
            self.error_entry.config(state='normal')
            self.start_btn.config(state='normal')
            self.show_file_preview(path)
        else:
            self.file_path = None
            self.is_binary_file = False
            self.file_label.config(text='No file selected')
            self.error_entry.config(state='disabled')
            self.start_btn.config(state='disabled')
            self.hide_file_preview()

    def show_file_preview(self, path):
        ext = os.path.splitext(path)[1].lower()
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        audio_exts = ['.wav', '.mp3']
        video_exts = ['.mp4', '.avi', '.mov', '.mkv']
        self.preview_btn.config(state='disabled')
        if ext in image_exts:
            self.preview_btn.config(text='View Image', command=lambda: self.open_big_preview('image'))
            self.preview_btn.config(state='normal')
        elif ext in audio_exts:
            self.preview_btn.config(text='Play Audio', command=lambda: self.open_big_preview('audio'))
            self.preview_btn.config(state='normal')
            try:
                pygame.mixer.init()
                pygame.mixer.music.load(path)
                self.audio_loaded = True
            except Exception:
                self.audio_loaded = False
        elif ext in video_exts:
            self.preview_btn.config(text='Play Video', command=lambda: self.open_big_preview('video'))
            self.preview_btn.config(state='normal')
            self.audio_loaded = False
        else:
            self.hide_file_preview()

    def hide_file_preview(self):
        self.preview_btn.config(state='disabled')
        self.audio_loaded = False

    def open_big_preview(self, mode=None):
        if not self.file_path:
            return
        ext = os.path.splitext(self.file_path)[1].lower()
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
                img = Image.open(self.file_path)
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
            play_btn = tk.Button(btn_frame, text='Play', command=self.play_selected_file)
            pause_btn = tk.Button(btn_frame, text='Pause', command=self.pause_audio)
            stop_btn = tk.Button(btn_frame, text='Stop', command=self.stop_audio)
            play_btn.pack(side='left', padx=10)
            pause_btn.pack(side='left', padx=10)
            stop_btn.pack(side='left', padx=10)
        elif mode == 'video':
            try:
                if platform.system() == 'Windows':
                    os.startfile(self.file_path)
                elif platform.system() == 'Darwin':
                    subprocess.call(['open', self.file_path])
                else:
                    subprocess.call(['xdg-open', self.file_path])
            except Exception as e:
                messagebox.showerror('Error', f'Could not play video: {e}')

    def play_selected_file(self):
        if not self.file_path:
            return
        ext = os.path.splitext(self.file_path)[1].lower()
        audio_exts = ['.wav', '.mp3']
        video_exts = ['.mp4', '.avi', '.mov', '.mkv']
        if ext in audio_exts:
            try:
                if not self.audio_loaded:
                    pygame.mixer.init()
                    pygame.mixer.music.load(self.file_path)
                    self.audio_loaded = True
                pygame.mixer.music.play()
            except Exception as e:
                messagebox.showerror('Error', f'Could not play audio: {e}')
        elif ext in video_exts:
            try:
                if platform.system() == 'Windows':
                    os.startfile(self.file_path)
                elif platform.system() == 'Darwin':
                    subprocess.call(['open', self.file_path])
                else:
                    subprocess.call(['xdg-open', self.file_path])
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

    def log(self, msg):
        self.log_area.config(state='normal')
        self.log_area.insert('end', msg + '\n')
        self.log_area.see('end')
        self.log_area.config(state='disabled')

    def clear_logs(self):
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', 'end')
        self.log_area.config(state='disabled')

    def start_transmission(self):
        if not self.connected:
            messagebox.showerror('Error', 'Please connect to the server first.')
            return
        if self.transmitting:
            messagebox.showinfo('Info', 'Transmission already in progress.')
            return
        ip = self.server_ip.get().strip()
        try:
            error_prob = float(self.error_prob.get())
            if not (0 <= error_prob <= 1):
                raise ValueError
        except ValueError:
            messagebox.showerror('Error', 'Error probability must be a number between 0 and 1.')
            return
        # Ensure only one of text or file is selected
        if self.file_path and self.input_text.get():
            messagebox.showerror('Error', 'Please provide either text or a file, not both.')
            return
        if self.send_choice.get() == 'file':
            input_data = self.file_path
            is_binary_file = True
            info_msg = f"Preparing to send file: {os.path.basename(self.file_path)}"
            # If mp3, send extension as metadata before file data
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext == '.mp3' and self.s:
                try:
                    ext_bytes = ext.encode().ljust(8, b' ')
                    self.s.sendall(ext_bytes)
                except Exception:
                    pass
        else:
            input_data = self.input_text.get()
            is_binary_file = False
            if not input_data:
                messagebox.showerror('Error', 'Please enter text to send.')
                return
            info_msg = "Preparing to send text message."
        # Clear all log files before each new transmission
        open(LOG_FILE, 'w').close()
        open(CRC_LOG_FILE, 'w').close()
        open(METRICS_LOG_FILE, 'w').close()
        self.clear_logs()  # Clear GUI log area before each transmission
        self.log(info_msg)
        with open(LOG_FILE, 'a') as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {info_msg}\n")
        threading.Thread(target=self.transmit, args=(ip, input_data, is_binary_file, error_prob), daemon=True).start()

    def transmit(self, server_ip, input_data, is_binary_file, error_prob):
        self.transmitting = True
        # Use the persistent socket self.s for all transmissions
        if not self.s:
            self.log('No connection to server. Please connect first.')
            self.transmitting = False
            return
        def log_event(msg):
            self.log(msg)
            with open(LOG_FILE, 'a') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")
        def log_crc(chunk_num, crc):
            with open(CRC_LOG_FILE, 'a') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Chunk {chunk_num}: CRC sent: {crc:08X}\n")
        def log_metrics(metrics_lines):
            with open(METRICS_LOG_FILE, 'a') as f:
                for line in metrics_lines:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")
        def get_chunks(input_data, is_binary_file):
            if is_binary_file:
                return list(file_chunker(input_data, CHUNK_SIZE))
            else:
                data = input_data.encode()
                return [data[i:i+CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]
        chunks = get_chunks(input_data, is_binary_file)
        total_chunks = len(chunks)
        self.log(f"Total chunks to send: {total_chunks}")
        log_event(f"Transmission started: {input_data} | Chunks: {total_chunks} | Error prob: {error_prob}")
        chunk_num = 0
        total_bytes_acked = 0
        total_chunks_sent = 0
        unique_chunks_acked = set()
        start_time = time.time()
        chunk_rtts = []
        # SNR counters
        total_bits_sent = 0
        error_bits = 0
        transfer_success = True
        while chunk_num < total_chunks:
            chunk = chunks[chunk_num]
            retries = 0
            while retries < MAX_RETRIES:
                crc = crc32(chunk)
                log_crc(chunk_num, crc)
                send_chunk = chunk
                bit_error_introduced = False
                if error_prob > 0 and random.random() < error_prob:
                    send_chunk = self.flip_random_bit(send_chunk)
                    log_event(f"Chunk {chunk_num}: Bit error introduced.")
                    bit_error_introduced = True
                send_time = time.time()
                try:
                    self.s.sendall(send_chunk + crc.to_bytes(4, 'big'))
                except Exception as e:
                    log_event(f"Send error: {e}")
                    self.transmitting = False
                    return
                log_event(f"Chunk {chunk_num}: Sent (retry {retries+1})")
                total_chunks_sent += 1
                total_bits_sent += len(send_chunk) * 8
                if bit_error_introduced:
                    error_bits += 8  # 1 bit flipped per chunk
                try:
                    resp = self.s.recv(1024)
                    ack_time = time.time()
                    resp_decoded = resp.decode()
                    log_event(f"Chunk {chunk_num}: Server response: {resp_decoded}")
                    if resp_decoded.startswith('ACK'):
                        chunk_num += 1
                        total_bytes_acked += len(chunk)
                        unique_chunks_acked.add(chunk_num)
                        chunk_rtts.append(ack_time - send_time)
                        break
                    else:
                        log_event(f"Chunk {chunk_num}: NACK received. Retrying.")
                except socket.timeout:
                    log_event(f"Chunk {chunk_num}: Timeout waiting for ACK/NACK. Retrying.")
                retries += 1
            else:
                self.log(f"Chunk {chunk_num}: Failed after {MAX_RETRIES} attempts. Aborting.")
                log_event(f"Chunk {chunk_num}: Failed after {MAX_RETRIES} attempts. Aborting.")
                transfer_success = False
                # Send abort signal to server
                try:
                    self.s.sendall(ABORT_SIGNAL)
                except Exception:
                    pass
                break
        end_time = time.time()
        try:
            if transfer_success and chunk_num == total_chunks:
                self.s.sendall(EOT_SIGNAL)
        except Exception:
            pass
        # Show transfer status only
        if transfer_success and chunk_num == total_chunks:
            self.show_status_message('Transfer complete.', 'green')
        else:
            self.show_status_message('Transfer failed.', 'red')
        log_event(f"Transmission complete for {input_data}.")
        # Metrics (do not display in main log area)
        duration = end_time - start_time if end_time > start_time else 1
        throughput = total_bytes_acked / duration
        data_integrity_rate = (len(unique_chunks_acked) / total_chunks_sent) if total_chunks_sent else 0
        avg_rtt = sum(chunk_rtts) / len(chunk_rtts) if chunk_rtts else 0
        import math
        if error_bits == 0:
            snr_db = 'Infinity'
        else:
            correct_bits = total_bits_sent - error_bits
            snr = correct_bits / error_bits if error_bits > 0 else 0
            snr_db = f"{10 * math.log10(snr):.2f}" if snr > 0 else '0.00'
        snr_line = f"Simulated SNR: {snr_db} dB (Total bits: {total_bits_sent}, Error bits: {error_bits})"
        metrics_lines = [
            f"Total transmission time: {duration:.4f} seconds",
            f"Throughput: {throughput:.2f} bytes/sec",
            f"Data Integrity Rate: {data_integrity_rate:.4f}",
            f"Average RTT: {avg_rtt:.4f} seconds",
            snr_line
        ]
        log_metrics(metrics_lines)
        self.transmitting = False
        # Reset input fields for next transmission, but stay connected
        self.connected = True
        self.connect_btn.config(state='disabled')
        self.ip_entry.config(state='disabled')
        self.text_radio.config(state='normal')
        self.file_radio.config(state='normal')
        self.error_entry.config(state='disabled')
        self.start_btn.config(state='disabled')
        self.input_text.set('')
        self.file_path = None
        self.is_binary_file = False
        self.file_label.config(text='No file selected')
        self.update_send_choice()

    def flip_random_bit(self, data):
        if not data:
            return data
        idx = random.randint(0, len(data) - 1)
        bit = 1 << random.randint(0, 7)
        flipped = bytearray(data)
        flipped[idx] ^= bit
        return bytes(flipped)

    def end_session(self):
        if self.s:
            try:
                self.s.sendall(END_SIGNAL)
            except Exception:
                pass
            self.s.close()
            self.s = None
        self.log('Session ended by user.')
        self.transmitting = False

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
            ('Transmission Log', LOG_FILE),
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

    def show_status_message(self, message, color):
        self.log_area.config(state='normal')
        self.log_area.insert('end', message + '\n')
        self.log_area.tag_add('status', 'end-2l', 'end-1l')
        self.log_area.tag_config('status', foreground=color, font=('Arial', 12, 'bold'))
        self.log_area.see('end')
        self.log_area.config(state='disabled')

if __name__ == '__main__':
    root = tk.Tk()
    app = ClientGUI(root)
    root.mainloop() 