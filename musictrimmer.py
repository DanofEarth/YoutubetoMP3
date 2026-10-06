import os
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from pydub import AudioSegment
import pygame


class MP3TrimmerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Trimmer & Player")
        self.root.geometry("850x780")

        # Initialize Pygame Mixer for playback
        pygame.mixer.init()

        # Audio data attributes
        self.audio = None
        self.file_path = None
        self.duration_sec = 0.0
        self.temp_playback_file = None

        # State guard to prevent Tkinter slider callback recursion
        self._updating_sliders = False
        self.is_playing = False
        self.playback_offset = 0.0  # Base timestamp in seconds where playback started

        # Matplotlib element references
        self.fig, self.ax = plt.subplots(figsize=(8, 2.5), dpi=100)
        self.canvas = None
        self.start_line = None
        self.end_line = None
        self.play_head_line = None

        # Value trackers
        self.start_val = 0.0
        self.end_val = 0.0
        self.current_play_pos = 0.0

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start timer loop for updating playback position
        self._poll_playback_position()

    def _build_ui(self):
        # Top Frame - File Operations
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        self.btn_load = ttk.Button(top_frame, text="Load Audio File", command=self.load_file)
        self.btn_load.pack(side=tk.LEFT, padx=5)

        self.lbl_file = ttk.Label(top_frame, text="No file loaded", font=("Arial", 10, "italic"))
        self.lbl_file.pack(side=tk.LEFT, padx=10)

        # Waveform Plot Frame
        self.plot_frame = ttk.Frame(self.root, padding=10)
        self.plot_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Playback Controls Frame
        pb_frame = ttk.LabelFrame(self.root, text="Playback Controls", padding=10)
        pb_frame.pack(fill=tk.X, padx=10, pady=5)

        self.btn_play_full = ttk.Button(pb_frame, text="▶ Play Full", command=self.play_full)
        self.btn_play_full.pack(side=tk.LEFT, padx=5)

        self.btn_play_selection = ttk.Button(pb_frame, text="► Play Selection", command=self.play_selection)
        self.btn_play_selection.pack(side=tk.LEFT, padx=5)

        self.btn_pause = ttk.Button(pb_frame, text="⏸ Pause", command=self.pause_audio)
        self.btn_pause.pack(side=tk.LEFT, padx=5)

        self.btn_stop = ttk.Button(pb_frame, text="⏹ Stop", command=self.stop_audio)
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.lbl_status = ttk.Label(pb_frame, text="Status: Stopped", font=("Arial", 9, "bold"))
        self.lbl_status.pack(side=tk.RIGHT, padx=10)

        # Playback Scrubbing Frame
        scrub_frame = ttk.LabelFrame(self.root, text="Playback Scrub Bar", padding=10)
        scrub_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(scrub_frame, text="Playhead Position:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.slider_playhead = ttk.Scale(
            scrub_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            command=self._on_playhead_move
        )
        self.slider_playhead.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.lbl_playhead_time = ttk.Label(scrub_frame, text="0.00 s")
        self.lbl_playhead_time.grid(row=0, column=2, padx=5, pady=5)

        scrub_frame.columnconfigure(1, weight=1)

        # Trim Controls Frame
        ctrl_frame = ttk.LabelFrame(self.root, text="Trim Controls", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)

        # Start Slider
        ttk.Label(ctrl_frame, text="Start Position (s):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.slider_start = ttk.Scale(
            ctrl_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            command=self._on_slider_start_move
        )
        self.slider_start.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        self.lbl_start_time = ttk.Label(ctrl_frame, text="0.00 s")
        self.lbl_start_time.grid(row=0, column=2, padx=5, pady=5)

        # End Slider
        ttk.Label(ctrl_frame, text="End Position (s):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.slider_end = ttk.Scale(
            ctrl_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            command=self._on_slider_end_move
        )
        self.slider_end.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        self.lbl_end_time = ttk.Label(ctrl_frame, text="0.00 s")
        self.lbl_end_time.grid(row=1, column=2, padx=5, pady=5)

        ctrl_frame.columnconfigure(1, weight=1)

        # Export Button
        self.btn_export = ttk.Button(self.root, text="Export Trimmed Audio", command=self.export_audio)
        self.btn_export.pack(pady=10)

    def load_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("Audio Files", "*.mp3 *.wav *.ogg *.flac *.m4a")]
        )
        if not file_path:
            return

        try:
            self.stop_audio()
            self.file_path = file_path
            self.audio = AudioSegment.from_file(file_path)
            self.duration_sec = len(self.audio) / 1000.0

            self.lbl_file.config(text=os.path.basename(file_path), font=("Arial", 10, "normal"))

            # Configure sliders safely
            self._updating_sliders = True
            try:
                self.slider_start.config(from_=0, to=self.duration_sec)
                self.slider_start.set(0)
                self.slider_end.config(from_=0, to=self.duration_sec)
                self.slider_end.set(self.duration_sec)
                self.slider_playhead.config(from_=0, to=self.duration_sec)
                self.slider_playhead.set(0)
            finally:
                self._updating_sliders = False

            self.start_val = 0.0
            self.end_val = self.duration_sec
            self.current_play_pos = 0.0
            self._update_time_labels()

            self._draw_waveform()

        except Exception as e:
            messagebox.showerror("Error Loading File", f"Could not load audio file:\n{e}")

    def _draw_waveform(self):
        self.ax.clear()

        # Downsample audio data for fast plotting
        samples = np.array(self.audio.get_array_of_samples())
        if self.audio.channels == 2:
            samples = samples[::2]  # Take left channel

        step = max(1, len(samples) // 1000)
        downsampled = samples[::step]
        time_axis = np.linspace(0, self.duration_sec, len(downsampled))

        self.ax.plot(time_axis, downsampled, color="gray", alpha=0.6)
        self.ax.set_yticks([])
        self.ax.set_xlim(0, self.duration_sec)

        # Plot selection lines and interactive playhead line
        self.start_line = self.ax.axvline(x=self.start_val, color="green", linewidth=2, label="Start")
        self.end_line = self.ax.axvline(x=self.end_val, color="red", linewidth=2, label="End")
        self.play_head_line = self.ax.axvline(x=self.current_play_pos, color="blue", linewidth=1.5, linestyle="--", label="Playhead")

        self.ax.legend(loc="upper right")
        self.fig.tight_layout()
        self.canvas.draw()

    # --- Playback Logic ---

    def play_from_pos(self, start_pos_sec):
        if not self.audio:
            return

        self.stop_audio()

        # Export starting from target position to temp file
        start_ms = int(start_pos_sec * 1000)
        segment = self.audio[start_ms:]

        self.temp_playback_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        segment.export(self.temp_playback_file.name, format="wav")
        self.temp_playback_file.close()

        try:
            pygame.mixer.music.load(self.temp_playback_file.name)
            pygame.mixer.music.play()
            self.playback_offset = start_pos_sec
            self.is_playing = True
            self.lbl_status.config(text=f"Status: Playing from {start_pos_sec:.2f}s", foreground="green")
        except Exception as e:
            messagebox.showerror("Playback Error", f"Could not play audio:\n{e}")

    def play_full(self):
        if not self.file_path:
            messagebox.showwarning("Warning", "Please load an audio file first.")
            return
        self.play_from_pos(0.0)

    def play_selection(self):
        if not self.audio:
            messagebox.showwarning("Warning", "Please load an audio file first.")
            return

        self.stop_audio()

        start_ms = int(self.start_val * 1000)
        end_ms = int(self.end_val * 1000)
        segment = self.audio[start_ms:end_ms]

        self.temp_playback_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        segment.export(self.temp_playback_file.name, format="wav")
        self.temp_playback_file.close()

        try:
            pygame.mixer.music.load(self.temp_playback_file.name)
            pygame.mixer.music.play()
            self.playback_offset = self.start_val
            self.is_playing = True
            self.lbl_status.config(text="Status: Playing Selection", foreground="green")
        except Exception as e:
            messagebox.showerror("Playback Error", f"Could not play selection:\n{e}")

    def pause_audio(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.lbl_status.config(text="Status: Paused", foreground="orange")
        elif not pygame.mixer.music.get_busy() and self.file_path:
            pygame.mixer.music.unpause()
            self.is_playing = True
            self.lbl_status.config(text="Status: Playing", foreground="green")

    def stop_audio(self):
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
        self.is_playing = False
        self.lbl_status.config(text="Status: Stopped", foreground="black")

        if self.temp_playback_file and os.path.exists(self.temp_playback_file.name):
            try:
                os.remove(self.temp_playback_file.name)
            except OSError:
                pass
            self.temp_playback_file = None

    def _poll_playback_position(self):
        if self.is_playing and pygame.mixer.music.get_busy():
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms >= 0:
                current_time = self.playback_offset + (pos_ms / 1000.0)
                if current_time <= self.duration_sec:
                    self.current_play_pos = current_time
                    self._updating_sliders = True
                    try:
                        self.slider_playhead.set(current_time)
                        self.lbl_playhead_time.config(text=f"{current_time:.2f} s")
                        self._sync_playhead_line(current_time)
                    finally:
                        self._updating_sliders = False
        elif self.is_playing and not pygame.mixer.music.get_busy():
            # Playback naturally reached the end
            self.stop_audio()

        self.root.after(100, self._poll_playback_position)

    # --- Slider Handlers ---

    def _on_playhead_move(self, value):
        if self._updating_sliders or not self.audio:
            return

        val = float(value)
        self.current_play_pos = val
        self.lbl_playhead_time.config(text=f"{val:.2f} s")
        self._sync_playhead_line(val)

        # If currently playing, restart playback instantly from scrub position
        if self.is_playing:
            self.play_from_pos(val)

    def _on_slider_start_move(self, value):
        if self._updating_sliders:
            return

        self._updating_sliders = True
        try:
            start = float(value)
            if start >= self.end_val:
                start = max(0.0, self.end_val - 0.1)
                self.slider_start.set(start)

            self.start_val = start
            self._update_time_labels()
            self._sync_trim_selection(self.start_val, self.end_val)
        finally:
            self._updating_sliders = False

    def _on_slider_end_move(self, value):
        if self._updating_sliders:
            return

        self._updating_sliders = True
        try:
            end = float(value)
            if end <= self.start_val:
                end = min(self.duration_sec, self.start_val + 0.1)
                self.slider_end.set(end)

            self.end_val = end
            self._update_time_labels()
            self._sync_trim_selection(self.start_val, self.end_val)
        finally:
            self._updating_sliders = False

    def _sync_playhead_line(self, pos):
        if hasattr(self, "play_head_line") and self.play_head_line is not None:
            self.play_head_line.set_xdata([pos, pos])
        if hasattr(self, "canvas") and self.canvas is not None:
            self.canvas.draw_idle()

    def _sync_trim_selection(self, start, end):
        if hasattr(self, "start_line") and self.start_line is not None:
            self.start_line.set_xdata([start, start])

        if hasattr(self, "end_line") and self.end_line is not None:
            self.end_line.set_xdata([end, end])

        if hasattr(self, "canvas") and self.canvas is not None:
            self.canvas.draw_idle()

    def _update_time_labels(self):
        self.lbl_start_time.config(text=f"{self.start_val:.2f} s")
        self.lbl_end_time.config(text=f"{self.end_val:.2f} s")

    # --- Export & Clean Up ---

    def export_audio(self):
        if not self.audio:
            messagebox.showwarning("Warning", "Please load an audio file first.")
            return

        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=[("MP3 File", "*.mp3"), ("WAV File", "*.wav")],
        )
        if not save_path:
            return

        try:
            start_ms = int(self.start_val * 1000)
            end_ms = int(self.end_val * 1000)
            trimmed = self.audio[start_ms:end_ms]

            fmt = os.path.splitext(save_path)[1].replace(".", "")
            trimmed.export(save_path, format=fmt)
            messagebox.showinfo("Success", f"File exported successfully to:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not export audio:\n{e}")

    def _on_close(self):
        self.stop_audio()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MP3TrimmerApp(root)
    root.mainloop()
