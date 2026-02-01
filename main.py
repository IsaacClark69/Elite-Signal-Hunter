import sys
import os
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout,
                             QWidget, QLabel, QSlider, QHBoxLayout, QGridLayout, QComboBox, QPushButton, QLineEdit, QListWidget, QTabWidget, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QPoint
from collections import deque
import soundfile as sf
from datetime import datetime
from scipy.spatial.distance import cosine
import json
import hashlib
import webbrowser
import subprocess

from audio_engine import AudioEngine
from journal_watcher import JournalWatcher

class ProfileReviewWindow(QWidget):
    def __init__(self, profile_name, profile_data):
        super().__init__()
        self.setWindowTitle(f"Reviewing: {profile_name}")
        self.resize(600, 400)
        self.setStyleSheet("background-color: #050505; color: #FFA500;")
        layout = QVBoxLayout(self)
        spec_view = pg.ImageView()
        spec_view.ui.histogram.hide(); spec_view.ui.roiBtn.hide(); spec_view.ui.menuBtn.hide()
        spec_view.getView().setAspectLocked(False); spec_view.getView().invertY(False)
        pos = np.array([0.0, 0.15, 0.4, 0.7, 1.0]); color = np.array([[0, 0, 0, 255], [5, 15, 30, 255], [160, 50, 0, 255], [255, 140, 0, 255], [255, 255, 220, 255]], dtype=np.ubyte)
        spec_view.setColorMap(pg.ColorMap(pos, color))
        layout.addWidget(spec_view)
        if profile_data.ndim == 1:
            display_data = np.tile(profile_data, (200, 1))
        else:
            display_data = profile_data
        spec_view.setImage(display_data.T, autoLevels=True)


class ScienceStation(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Elite Signal Hunter: MK XXIII (Snapshot)")
        self.resize(1600, 900)
        self.setStyleSheet("background-color: #050505; color: #FFA500;")

        self.main_layout = QHBoxLayout()
        self.central_widget = QWidget(); self.central_widget.setLayout(self.main_layout); self.setCentralWidget(self.central_widget)
        self.left_panel = QWidget(); self.left_layout = QVBoxLayout(self.left_panel); self.main_layout.addWidget(self.left_panel, 7)
        self.right_panel = QWidget(); self.right_layout = QVBoxLayout(self.right_panel); self.main_layout.addWidget(self.right_panel, 3)

        header_layout = QHBoxLayout()
        self.label = QLabel(">> INITIALIZING... <<"); self.label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.label.setStyleSheet("font-family: Consolas; font-size: 14pt; font-weight: bold; color: #FF8800;")
        self.crosshair_label = QLabel("FREQ: --- Hz | AMP: --- dB"); self.crosshair_label.setAlignment(Qt.AlignmentFlag.AlignRight); self.crosshair_label.setStyleSheet("font-family: Consolas; font-size: 10pt; color: #CCCCCC;")
        
        header_layout.addWidget(self.label)
        header_layout.addWidget(self.crosshair_label)
        self.left_layout.addLayout(header_layout)

        self.tabs = QTabWidget(); self.left_layout.addWidget(self.tabs)
        self.setup_spec_tab()
        self.setup_scope_tab()
        self.setup_settings_tab()

        self.setup_control_panel()

        self.FFT_SIZE = 4096; self.INPUT_CHUNK = 1024; self.SAMPLE_RATE = 48000
        self.MAX_BINS = self.FFT_SIZE // 2 + 1; self.history_length = 2000
        
        self.full_spectrogram_data = np.zeros((self.history_length, self.MAX_BINS)); self.rolling_audio_buffer = np.zeros(self.FFT_SIZE)
        self.use_log_scale = True; self.latest_magnitude = np.zeros(self.MAX_BINS)
        self.auto_profiling_enabled = False; self.noise_profile = np.full(self.MAX_BINS, 1e-9); self.profiling_buffer = deque(maxlen=100)
        self.detection_threshold = 10.0; self.signal_detected_cooldown = 0; self.identification_threshold = 0.85
        self.anomaly_highlight_line = None
        self.capture_buffer = None; self.update_capture_buffer()
        self.profiles = {}; self.PROFILES_DIR = "profiles"; self.load_profiles()
        self.review_windows = []
        self.current_cmdr_status = {}

        self.engine = None
        self.render_timer = QTimer(self); self.render_timer.setInterval(33); self.render_timer.timeout.connect(self.render_view)
        self.identification_timer = QTimer(self); self.identification_timer.setInterval(200); self.identification_timer.timeout.connect(self.run_identification)
        
        self.refresh_audio_devices()

        self.journal_watcher = JournalWatcher()
        self.journal_watcher.status_update.connect(self.update_cmdr_status)
        self.journal_watcher.start()

        self.check_first_launch()

    def check_first_launch(self):
        flag_file = ".first_launch_seen"
        if not os.path.exists(flag_file):
            self.show_readme()
            with open(flag_file, 'w') as f:
                f.write("This file prevents the README from showing on every launch.")

    def show_readme(self):
        readme_path = "README.md"
        if os.path.exists(readme_path):
            try:
                if sys.platform == "win32":
                    subprocess.run(['notepad.exe', os.path.realpath(readme_path)])
                else:
                    webbrowser.open(os.path.realpath(readme_path))
            except Exception as e:
                print(f"Could not open README.md: {e}")

    def setup_spec_tab(self):
        self.spec_tab = QWidget(); self.spec_layout = QVBoxLayout(self.spec_tab)
        self.spec_view = pg.ImageView(); self.spec_view.ui.histogram.hide(); self.spec_view.ui.roiBtn.hide(); self.spec_view.ui.menuBtn.hide()
        self.spec_view.getView().setAspectLocked(False); self.spec_view.getView().invertY(False)
        pos = np.array([0.0, 0.15, 0.4, 0.7, 1.0]); color = np.array([[0, 0, 0, 255], [5, 15, 30, 255], [160, 50, 0, 255], [255, 140, 0, 255], [255, 255, 220, 255]], dtype=np.ubyte)
        self.spec_view.setColorMap(pg.ColorMap(pos, color)); self.spec_layout.addWidget(self.spec_view); self.tabs.addTab(self.spec_tab, "Spectrogram")
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine)); self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine))
        self.spec_view.addItem(self.v_line, ignoreBounds=True); self.spec_view.addItem(self.h_line, ignoreBounds=True)
        self.spec_view.scene.sigMouseMoved.connect(self.mouse_moved_on_spectrogram)
        self.anomaly_highlight_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('r', width=2, style=Qt.PenStyle.DashLine)); self.anomaly_highlight_line.hide(); self.spec_view.addItem(self.anomaly_highlight_line, ignoreBounds=True)
        self.roi = pg.RectROI(pos=[100, 100], size=[100, 100], pen=pg.mkPen('r', width=2), movable=True, resizable=True, rotatable=False)
        self.roi.setZValue(1000); self.roi.hide(); self.spec_view.addItem(self.roi)

    def setup_scope_tab(self):
        self.scope_tab = QWidget(); self.scope_layout = QVBoxLayout(self.scope_tab)
        self.scope_plot = pg.PlotWidget(); self.scope_plot.setYRange(-0.5, 0.5); self.scope_plot.showGrid(x=True, y=True, alpha=0.3)
        self.scope_curve = self.scope_plot.plot(pen=pg.mkPen('#FFA500', width=2)); self.scope_layout.addWidget(self.scope_plot); self.tabs.addTab(self.scope_tab, "Oscilloscope")

    def setup_settings_tab(self):
        self.settings_tab = QWidget()
        self.settings_layout = QGridLayout(self.settings_tab)
        self.settings_layout.addWidget(QLabel("AUDIO SOURCE:"), 0, 0)
        self.audio_source_combo = QComboBox()
        self.audio_source_combo.currentIndexChanged.connect(self.change_audio_device)
        self.settings_layout.addWidget(self.audio_source_combo, 0, 1)
        self.btn_refresh_audio = QPushButton("Refresh Devices")
        self.btn_refresh_audio.clicked.connect(self.refresh_audio_devices)
        self.settings_layout.addWidget(self.btn_refresh_audio, 0, 2)
        
        self.btn_show_readme = QPushButton("View Field Manual (README)")
        self.btn_show_readme.clicked.connect(self.show_readme)
        self.settings_layout.addWidget(self.btn_show_readme, 1, 0, 1, 3)

        self.settings_layout.setColumnStretch(1, 1)
        self.settings_layout.setRowStretch(2, 1)
        self.tabs.addTab(self.settings_tab, "Settings")

    def setup_control_panel(self):
        status_container = QWidget(); status_layout = QGridLayout(status_container)
        self.lbl_cmdr_system = QLabel("SYSTEM: Unknown"); self.lbl_cmdr_system.setStyleSheet("font-weight: bold;")
        self.lbl_cmdr_ship = QLabel("SHIP: Unknown")
        status_layout.addWidget(self.lbl_cmdr_system, 0, 0); status_layout.addWidget(self.lbl_cmdr_ship, 1, 0)
        ctrl_container = QWidget(); ctrl_layout = QGridLayout()
        self.lbl_gain = QLabel("SIGNAL GAIN: 3.0x"); self.slider_gain = QSlider(Qt.Orientation.Horizontal); self.slider_gain.setRange(1, 100); self.slider_gain.setValue(30); self.slider_gain.valueChanged.connect(self.update_labels)
        self.lbl_floor = QLabel("NOISE CUTOFF: 60"); self.slider_floor = QSlider(Qt.Orientation.Horizontal); self.slider_floor.setRange(0, 200); self.slider_floor.setValue(60); self.slider_floor.valueChanged.connect(self.update_labels)
        self.lbl_zoom = QLabel("FREQ ZOOM: 24.0 kHz"); self.slider_zoom = QSlider(Qt.Orientation.Horizontal); self.slider_zoom.setRange(5, 100); self.slider_zoom.setValue(100); self.slider_zoom.valueChanged.connect(self.update_labels)
        self.lbl_stretch = QLabel("VERTICAL STRETCH: 8x"); self.slider_stretch = QSlider(Qt.Orientation.Horizontal); self.slider_stretch.setRange(1, 20); self.slider_stretch.setValue(8); self.slider_stretch.valueChanged.connect(self.update_labels)
        self.combo_channel = QComboBox(); self.combo_channel.addItems(["Stereo Mix", "Left Channel Only", "Right Channel Only"])
        self.btn_scale = QPushButton("Mode: LOG SCALE"); self.btn_scale.setCheckable(True); self.btn_scale.clicked.connect(self.toggle_scale)
        self.btn_auto_profile = QPushButton("Auto-Profiling: OFF"); self.btn_auto_profile.setCheckable(True); self.btn_auto_profile.clicked.connect(self.toggle_auto_profiling)
        self.lbl_threshold = QLabel("DETECT THRESHOLD: 10.0"); self.slider_threshold = QSlider(Qt.Orientation.Horizontal); self.slider_threshold.setRange(1, 200); self.slider_threshold.setValue(20); self.slider_threshold.valueChanged.connect(self.update_labels)
        self.btn_save_snapshot = QPushButton("Save Snapshot"); self.btn_save_snapshot.clicked.connect(self.save_snapshot)
        self.lbl_capture_duration = QLabel("CAPTURE DURATION: 15s"); self.slider_capture_duration = QSlider(Qt.Orientation.Horizontal); self.slider_capture_duration.setRange(5, 60); self.slider_capture_duration.setValue(15); self.slider_capture_duration.valueChanged.connect(self.update_capture_buffer)
        ctrl_layout.addWidget(self.lbl_gain, 0, 0); ctrl_layout.addWidget(self.slider_gain, 0, 1); ctrl_layout.addWidget(self.lbl_floor, 1, 0); ctrl_layout.addWidget(self.slider_floor, 1, 1); ctrl_layout.addWidget(self.lbl_zoom, 2, 0); ctrl_layout.addWidget(self.slider_zoom, 2, 1); ctrl_layout.addWidget(self.lbl_stretch, 3, 0); ctrl_layout.addWidget(self.slider_stretch, 3, 1); ctrl_layout.addWidget(QLabel("SOURCE:"), 5, 0); ctrl_layout.addWidget(self.combo_channel, 5, 1); ctrl_layout.addWidget(self.btn_scale, 6, 0, 1, 2); ctrl_layout.addWidget(QLabel("--- AUTO-DETECTION ---"), 7, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter); ctrl_layout.addWidget(self.btn_auto_profile, 8, 0, 1, 2); ctrl_layout.addWidget(self.lbl_threshold, 9, 0); ctrl_layout.addWidget(self.slider_threshold, 9, 1); ctrl_layout.addWidget(QLabel("--- CAPTURE ---"), 10, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter); ctrl_layout.addWidget(self.lbl_capture_duration, 11, 0); ctrl_layout.addWidget(self.slider_capture_duration, 11, 1); ctrl_layout.addWidget(self.btn_save_snapshot, 12, 0, 1, 2)
        ctrl_container.setLayout(ctrl_layout)
        profile_container = QWidget(); profile_layout = QGridLayout()
        self.lbl_identity = QLabel("CURRENT ID: ---"); self.lbl_identity.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.profile_list_widget = QListWidget()
        self.profile_name_input = QLineEdit(); self.profile_name_input.setPlaceholderText("e.g., Thargoid Probe")
        self.btn_define_roi = QPushButton("Define from Selection"); self.btn_define_roi.setCheckable(True); self.btn_define_roi.clicked.connect(self.toggle_roi_definition)
        self.btn_save_profile = QPushButton("Save Full Signal as Profile"); self.btn_save_profile.clicked.connect(self.save_current_profile)
        self.btn_delete_profile = QPushButton("Delete Selected Profile"); self.btn_delete_profile.clicked.connect(self.delete_selected_profile)
        self.btn_review_profile = QPushButton("Review Selected Profile"); self.btn_review_profile.clicked.connect(self.review_selected_profile)
        profile_layout.addWidget(self.lbl_identity, 0, 0, 1, 2); profile_layout.addWidget(QLabel("SAVED PROFILES:"), 1, 0, 1, 2); profile_layout.addWidget(self.profile_list_widget, 2, 0, 1, 2)
        profile_layout.addWidget(self.btn_review_profile, 3, 0, 1, 1); profile_layout.addWidget(self.btn_delete_profile, 3, 1, 1, 1)
        profile_layout.addWidget(QLabel("NEW PROFILE NAME:"), 4, 0, 1, 2); profile_layout.addWidget(self.profile_name_input, 5, 0, 1, 2); profile_layout.addWidget(self.btn_define_roi, 6, 0, 1, 2); profile_layout.addWidget(self.btn_save_profile, 7, 0, 1, 2)
        profile_container.setLayout(profile_layout)
        self.right_layout.addWidget(QLabel("--- CMDR STATUS ---")); self.right_layout.addWidget(status_container)
        self.right_layout.addWidget(QLabel("--- MASTER CONTROLS ---")); self.right_layout.addWidget(ctrl_container)
        self.right_layout.addWidget(QLabel("--- SIGNAL IDENTIFICATION ---")); self.right_layout.addWidget(profile_container); self.right_layout.addStretch()

    def update_cmdr_status(self, status):
        self.current_cmdr_status = status
        self.lbl_cmdr_system.setText(f"SYSTEM: {status.get('StarSystem', 'Unknown')}")
        self.lbl_cmdr_ship.setText(f"SHIP: {status.get('Ship', 'Unknown')}")

    def save_snapshot(self):
        if not self.capture_buffer: self.label.setText(">> Buffer empty. Nothing to save. <<"); return
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        snapshot_dir = f"snapshot_{timestamp}"
        os.makedirs(snapshot_dir, exist_ok=True)
        wav_path = os.path.join(snapshot_dir, "capture.wav")
        recording_data = np.concatenate(list(self.capture_buffer))
        sf.write(wav_path, recording_data, self.SAMPLE_RATE)
        metadata = {
            "timestamp_utc": datetime.utcnow().isoformat(), "fft_size": self.FFT_SIZE, "input_chunk": self.INPUT_CHUNK,
            "sample_rate": self.SAMPLE_RATE, "gain_slider": self.slider_gain.value(), "floor_slider": self.slider_floor.value(),
            "zoom_slider": self.slider_zoom.value(), "stretch_slider": self.slider_stretch.value(),
            "audio_source": self.audio_source_combo.currentText(), "channel_mode": self.combo_channel.currentText(),
            "scale_mode": "Log" if self.use_log_scale else "Linear"
        }
        with open(os.path.join(snapshot_dir, "metadata.json"), 'w') as f: json.dump(metadata, f, indent=4)
        with open(os.path.join(snapshot_dir, "context.json"), 'w') as f: json.dump(self.current_cmdr_status, f, indent=4)
        with open(wav_path, 'rb') as f_wav:
            wav_bytes = f_wav.read()
            sha256_hash = hashlib.sha256(wav_bytes).hexdigest()
        with open(os.path.join(snapshot_dir, "capture.sha256"), 'w') as f_hash: f_hash.write(sha256_hash)
        self.label.setText(f">> Snapshot saved to {snapshot_dir} <<")

    def toggle_roi_definition(self):
        if self.btn_define_roi.isChecked(): self.roi.show(); self.btn_save_profile.setText("Save Selection as Profile")
        else: self.roi.hide(); self.btn_save_profile.setText("Save Full Signal as Profile")

    def save_current_profile(self):
        profile_name = self.profile_name_input.text().strip()
        if not profile_name: self.label.setText(">> Please enter a profile name. <<"); return
        if self.btn_define_roi.isChecked():
            pos = self.roi.pos(); size = self.roi.size()
            min_x, min_y = int(pos.x()), int(pos.y())
            max_x, max_y = int(pos.x() + size.x()), int(pos.y() + size.y())
            min_x = np.clip(min_x, 0, self.MAX_BINS); max_x = np.clip(max_x, 0, self.MAX_BINS)
            min_y = np.clip(min_y, 0, self.history_length); max_y = np.clip(max_y, 0, self.history_length)
            if min_x >= max_x or min_y >= max_y: self.label.setText(">> Invalid selection. <<"); return
            y_start = self.history_length - max_y; y_end = self.history_length - min_y
            profile_to_save = self.full_spectrogram_data[y_start:y_end, min_x:max_x]
            save_type = "2D selection"
        else:
            profile_to_save = np.clip(self.latest_magnitude - self.noise_profile, 0, None)
            save_type = "full signal"
        try:
            np.save(os.path.join(self.PROFILES_DIR, f"{profile_name}.npy"), profile_to_save)
            self.label.setText(f">> Profile '{profile_name}' ({save_type}) saved. <<")
            self.profile_name_input.clear(); self.load_profiles()
        except Exception as e:
            self.label.setText(">> FAILED to save profile! <<"); print(f"Error saving profile: {e}")

    def closeEvent(self, event):
        self.journal_watcher.stop()
        if self.engine: self.engine.stop()
        for win in self.review_windows: win.close()
        event.accept()

    def review_selected_profile(self):
        selected_items = self.profile_list_widget.selectedItems()
        if not selected_items: self.label.setText(">> Select a profile to review. <<"); return
        profile_name = selected_items[0].text()
        raw_profile_data = np.load(os.path.join(self.PROFILES_DIR, f"{profile_name}.npy"))
        review_win = ProfileReviewWindow(profile_name, raw_profile_data)
        self.review_windows.append(review_win); review_win.show()
    def render_view(self):
        gated_magnitude = np.clip(self.latest_magnitude - self.noise_profile, 0, None)
        if self.use_log_scale: processed_data = 20 * np.log10(gated_magnitude + 1e-9) + 100
        else: processed_data = gated_magnitude * 5000
        processed_data = np.clip(processed_data, 0, None)
        stretch_factor = self.slider_stretch.value()
        self.full_spectrogram_data = np.roll(self.full_spectrogram_data, -stretch_factor, axis=0)
        for i in range(stretch_factor): self.full_spectrogram_data[-(i + 1)] = processed_data
        zoom_percent = self.slider_zoom.value() / 100.0; cutoff_index = max(50, int(self.MAX_BINS * zoom_percent))
        view_data = self.full_spectrogram_data[:, :cutoff_index].copy()
        min_level = self.slider_floor.value(); gain_factor = self.slider_gain.value() / 10.0; max_level = min_level + (100 / gain_factor)
        self.spec_view.setImage(view_data.T, autoLevels=False, levels=[min_level, max_level])
        self.scope_curve.setData(self.rolling_audio_buffer)
    def refresh_audio_devices(self):
        self.label.setText(">> SCANNING AUDIO DEVICES... <<")
        self.audio_devices = AudioEngine.get_available_devices()
        self.audio_source_combo.blockSignals(True); self.audio_source_combo.clear()
        if not self.audio_devices or self.audio_devices[0]["index"] == -1:
            self.audio_source_combo.addItem("No devices found"); self.audio_source_combo.setEnabled(False)
            self.label.setText(">> ERROR: NO AUDIO DEVICES FOUND <<"); return
        self.audio_source_combo.setEnabled(True)
        for device in self.audio_devices: self.audio_source_combo.addItem(device["name"], userData=device["index"])
        self.audio_source_combo.blockSignals(False)
        if self.engine is None: self.change_audio_device(0)
        self.label.setText(">> STANDING BY <<")
    def change_audio_device(self, index):
        if self.engine: self.engine.stop(); self.engine = None
        device_index = self.audio_source_combo.itemData(index)
        if device_index is None and index != 0: self.label.setText(f">> ERROR: Invalid device selected. <<"); return
        self.label.setText(f">> STARTING ENGINE: {self.audio_source_combo.currentText()} <<")
        self.engine = AudioEngine(device_index=device_index)
        self.engine.chunk_size = self.INPUT_CHUNK
        self.engine.audio_data_ready.connect(self.update_data_stream)
        self.engine.error_occurred.connect(lambda msg: self.label.setText(f">> ERROR: {msg} <<"))
        self.engine.start()
        if not self.render_timer.isActive(): self.render_timer.start()
        if not self.identification_timer.isActive(): self.identification_timer.start()
    def mouse_moved_on_spectrogram(self, pos):
        if self.spec_view.view.sceneBoundingRect().contains(pos):
            mouse_point = self.spec_view.view.mapSceneToView(pos)
            freq_bin = mouse_point.x(); time_idx = int(mouse_point.y())
            max_freq_bin = self.full_spectrogram_data.shape[1] - 1
            freq_bin = np.clip(freq_bin, 0, max_freq_bin)
            freq_hz = (freq_bin / self.MAX_BINS) * (self.SAMPLE_RATE / 2)
            if 0 <= time_idx < self.history_length:
                amp_val = self.full_spectrogram_data[self.history_length - 1 - time_idx, int(freq_bin)]
                self.crosshair_label.setText(f"FREQ: {freq_hz:,.0f} Hz | AMP: {amp_val:.2f} dB")
            self.v_line.setPos(mouse_point.x()); self.h_line.setPos(mouse_point.y())
    def load_profiles(self):
        if not os.path.exists(self.PROFILES_DIR): os.makedirs(self.PROFILES_DIR)
        self.profiles = {}; self.profile_list_widget.clear()
        for filename in sorted(os.listdir(self.PROFILES_DIR)):
            if filename.endswith(".npy"):
                profile_name = os.path.splitext(filename)[0]
                try:
                    profile_data = np.load(os.path.join(self.PROFILES_DIR, filename))
                    if profile_data.ndim == 1:
                        profile_norm_val = np.linalg.norm(profile_data)
                        if profile_norm_val > 1e-9: self.profiles[profile_name] = profile_data / profile_norm_val
                    else: self.profiles[profile_name] = profile_data
                    self.profile_list_widget.addItem(profile_name)
                except Exception as e: print(f"Error loading profile {filename}: {e}")
    def delete_selected_profile(self):
        selected_items = self.profile_list_widget.selectedItems()
        if not selected_items: self.label.setText(">> Select a profile to delete. <<"); return
        profile_name = selected_items[0].text()
        if QMessageBox.question(self, 'Delete Profile', f"Delete '{profile_name}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try: os.remove(os.path.join(self.PROFILES_DIR, f"{profile_name}.npy")); self.label.setText(f">> Profile '{profile_name}' deleted. <<"); self.load_profiles()
            except Exception as e: self.label.setText(">> FAILED to delete profile! <<"); print(f"Error deleting profile: {e}")
    def update_data_stream(self, new_audio_chunk):
        if new_audio_chunk.ndim == 1: self.capture_buffer.append(np.column_stack([new_audio_chunk, new_audio_chunk]))
        else: self.capture_buffer.append(new_audio_chunk)
        if self.combo_channel.currentText() == "Left Channel Only" and new_audio_chunk.ndim > 1: new_audio = new_audio_chunk[:, 0]
        elif self.combo_channel.currentText() == "Right Channel Only" and new_audio_chunk.ndim > 1: new_audio = new_audio_chunk[:, 1]
        else: new_audio = np.mean(new_audio_chunk, axis=1) if new_audio_chunk.ndim > 1 else new_audio_chunk
        self.rolling_audio_buffer = np.roll(self.rolling_audio_buffer, -len(new_audio)); self.rolling_audio_buffer[-len(new_audio):] = new_audio
        self.latest_magnitude = np.abs(np.fft.rfft(self.rolling_audio_buffer * np.hanning(self.FFT_SIZE)))
        if self.auto_profiling_enabled: self.profiling_buffer.append(self.latest_magnitude);
        if len(self.profiling_buffer) == self.profiling_buffer.maxlen: self.noise_profile = np.min(self.profiling_buffer, axis=0)
    def run_identification(self):
        if self.anomaly_highlight_line is None: return
        gated_magnitude = np.clip(self.latest_magnitude - self.noise_profile, 0, None)
        signal_energy = np.sum(gated_magnitude)
        best_match = "---"; highest_score = 0
        if signal_energy > self.detection_threshold:
            if self.signal_detected_cooldown <= 0:
                anomaly_bin = np.argmax(gated_magnitude); anomaly_freq = (anomaly_bin / self.MAX_BINS) * (self.SAMPLE_RATE / 2)
                self.label.setText(f">>!! SIGNAL DETECTED at {anomaly_freq:,.0f} Hz !!<<"); self.label.setStyleSheet("font-family: Consolas; font-size: 14pt; font-weight: bold; color: #FF0000;")
                self.anomaly_highlight_line.setPos(anomaly_bin); self.anomaly_highlight_line.show(); self.signal_detected_cooldown = 10
            if len(self.profiles) > 0:
                for name, profile_data in self.profiles.items():
                    if profile_data.ndim == 1:
                        live_norm_val = np.linalg.norm(gated_magnitude)
                        if live_norm_val > 1e-9:
                            live_signal_norm = gated_magnitude / live_norm_val
                            score = np.dot(live_signal_norm, profile_data)
                            if score > highest_score: highest_score = score; best_match = name
                    elif profile_data.ndim == 2:
                        prof_h, prof_w = profile_data.shape
                        live_slice = self.full_spectrogram_data[:prof_h, :prof_w]
                        live_norm = np.linalg.norm(live_slice)
                        if live_norm > 1e-9:
                            score = np.sum(live_slice * profile_data) / (live_norm * np.linalg.norm(profile_data))
                            if score > highest_score: highest_score = score; best_match = name
            if highest_score > self.identification_threshold: self.lbl_identity.setText(f"ID: {best_match} ({highest_score:.0%})")
            else: self.lbl_identity.setText("ID: UNKNOWN SIGNAL")
        else:
            self.lbl_identity.setText("ID: ---"); self.anomaly_highlight_line.hide()
            if self.signal_detected_cooldown > 0: self.signal_detected_cooldown -= 1
            else:
                if self.auto_profiling_enabled and len(self.profiling_buffer) < self.profiling_buffer.maxlen: self.label.setText(">> AUTO-PROFILING... <<")
                else: self.label.setText(">> STANDING BY <<")
                self.label.setStyleSheet("font-family: Consolas; font-size: 14pt; font-weight: bold; color: #FF8800;")
    def update_capture_buffer(self):
        duration_seconds = self.slider_capture_duration.value(); self.lbl_capture_duration.setText(f"CAPTURE DURATION: {duration_seconds}s")
        buffer_size = int(duration_seconds * (self.SAMPLE_RATE / self.INPUT_CHUNK))
        old_contents = list(self.capture_buffer) if self.capture_buffer else []
        self.capture_buffer = deque(old_contents, maxlen=buffer_size)
    def toggle_auto_profiling(self):
        self.auto_profiling_enabled = self.btn_auto_profile.isChecked(); status = "ON" if self.auto_profiling_enabled else "OFF"
        self.btn_auto_profile.setText(f"Auto-Profiling: {status}")
        if not self.auto_profiling_enabled: self.noise_profile = np.full(self.MAX_BINS, 1e-9)
        self.label.setText(f">> AUTO-PROFILING {status} <<")
    def toggle_scale(self):
        self.use_log_scale = not self.use_log_scale; self.btn_scale.setText("Mode: LOG SCALE" if self.use_log_scale else "Mode: LINEAR SCALE")
    def update_labels(self):
        self.lbl_gain.setText(f"SIGNAL GAIN: {self.slider_gain.value() / 10:.1f}x"); self.lbl_floor.setText(f"NOISE CUTOFF: {self.slider_floor.value()}")
        max_khz = 24 * (self.slider_zoom.value() / 100.0); self.lbl_zoom.setText(f"FREQ ZOOM: 0 - {max_khz:.1f} kHz")
        self.lbl_stretch.setText(f"VERTICAL STRETCH: {self.slider_stretch.value()}x"); self.detection_threshold = self.slider_threshold.value() / 2.0
        self.lbl_threshold.setText(f"DETECT THRESHOLD: {self.detection_threshold:.1f}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScienceStation()
    window.show()
    sys.exit(app.exec())