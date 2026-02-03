import sys
import os
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout,
                             QWidget, QLabel, QSlider, QHBoxLayout, QGridLayout, QComboBox, QPushButton, QLineEdit, QListWidget, QTabWidget, QTextEdit, QFileDialog, QListWidgetItem, QCheckBox, QDial, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QSplitter, QDockWidget)
from PyQt6.QtCore import Qt, QTimer
from collections import deque
import soundfile as sf
from datetime import datetime, timezone
import json
import hashlib
import webbrowser
import subprocess
import winsound

from audio_engine import ProxyAudioEngine
from journal_watcher import JournalWatcher
from api_client import submit_signal
import database as db
from dsp import SignalProcessor, calculate_characteristics

# ... [ProfileReviewWindow and SnapshotLabWindow classes remain unchanged] ...
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
        spec_view.setImage(np.ascontiguousarray(display_data.T), autoLevels=True)

class SnapshotLabWindow(QWidget):
    def __init__(self, snapshot_path, parent=None):
        super().__init__()
        self.snapshot_path = snapshot_path
        self.parent_station = parent
        self.setWindowTitle(f"Signal Lab: {os.path.basename(snapshot_path)}")
        self.resize(1000, 600)
        self.setStyleSheet("background-color: #050505; color: #FFA500;")
        
        self.layout = QVBoxLayout(self)
        
        # Header
        self.header_label = QLabel(">> SIGNAL ANALYSIS LAB <<")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header_label.setStyleSheet("font-family: Consolas; font-size: 14pt; font-weight: bold; color: #00FF00;")
        self.layout.addWidget(self.header_label)
        
        # Spectrogram View
        self.spec_view = pg.ImageView()
        self.spec_view.ui.histogram.hide()
        self.spec_view.ui.menuBtn.hide()
        self.spec_view.getView().setAspectLocked(False)
        self.spec_view.getView().invertY(False) # Time on X, Freq on Y usually for static
        
        # Custom Color Map
        pos = np.array([0.0, 0.15, 0.4, 0.7, 1.0])
        color = np.array([[0, 0, 0, 255], [5, 15, 30, 255], [160, 50, 0, 255], [255, 140, 0, 255], [255, 255, 220, 255]], dtype=np.ubyte)
        self.spec_view.setColorMap(pg.ColorMap(pos, color))
        
        self.layout.addWidget(self.spec_view)
        
        # ROI Tool
        self.roi = pg.RectROI(pos=[0, 0], size=[100, 100], pen=pg.mkPen('r', width=2), movable=True, resizable=True, rotatable=False)
        self.spec_view.addItem(self.roi)
        
        # Controls
        controls_layout = QHBoxLayout()
        self.profile_name_input = QLineEdit()
        self.profile_name_input.setPlaceholderText("Enter Profile Name...")
        self.btn_save_selection = QPushButton("Save Selection as Profile")
        self.btn_save_selection.clicked.connect(self.save_selection_as_profile)
        
        controls_layout.addWidget(QLabel("Profile Name:"))
        controls_layout.addWidget(self.profile_name_input)
        controls_layout.addWidget(self.btn_save_selection)
        self.layout.addLayout(controls_layout)
        
        self.load_data()

    def load_data(self):
        # Check if it's a directory (snapshot) or a file (recording)
        if os.path.isdir(self.snapshot_path):
            wav_path = os.path.join(self.snapshot_path, "capture.wav")
        else:
            wav_path = self.snapshot_path

        if not os.path.exists(wav_path):
            self.header_label.setText("ERROR: Audio file not found.")
            return
            
        try:
            data, samplerate = sf.read(wav_path)
            if data.ndim > 1:
                data = np.mean(data, axis=1)
                
            # Generate Spectrogram
            # Using matplotlib.mlab.specgram logic simplified or scipy
            # For simplicity/speed without extra deps, we'll do a basic STFT here
            n_fft = 4096
            hop_length = 1024
            window = np.hanning(n_fft)
            
            # Pad to ensure we don't lose data
            pad_width = n_fft // 2
            padded_data = np.pad(data, (pad_width, pad_width), mode='reflect')
            
            n_frames = (len(padded_data) - n_fft) // hop_length + 1
            spectrogram = np.zeros((n_frames, n_fft // 2 + 1))
            
            for i in range(n_frames):
                start = i * hop_length
                end = start + n_fft
                chunk = padded_data[start:end] * window
                fft_res = np.fft.rfft(chunk)
                spectrogram[i, :] = np.abs(fft_res)
                
            # Log scale
            spectrogram = 20 * np.log10(spectrogram + 1e-9)
            spectrogram = np.clip(spectrogram, 0, None)
            
            # Display
            # ImageItem expects (x, y). We want Time on X, Freq on Y.
            # Our spectrogram is (Time, Freq). So we pass it directly.
            self.spec_view.setImage(spectrogram, autoLevels=True)
            self.full_spectrogram_data = spectrogram # Store for extraction
            
            # Set ROI bounds
            self.roi.maxBounds = pg.QtCore.QRectF(0, 0, spectrogram.shape[0], spectrogram.shape[1])
            self.roi.setSize([spectrogram.shape[0] / 4, spectrogram.shape[1] / 2])
            self.roi.setPos([spectrogram.shape[0] / 4, spectrogram.shape[1] / 4])
            
        except Exception as e:
            self.header_label.setText(f"ERROR: {e}")

    def save_selection_as_profile(self):
        name = self.profile_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a profile name.")
            return
            
        # Get ROI data
        # getArrayRegion returns the data within the ROI
        # The image data is (Time, Freq)
        selected_data = self.roi.getArrayRegion(self.full_spectrogram_data, self.spec_view.getImageItem())
        
        if selected_data is None or selected_data.size == 0:
             QMessageBox.warning(self, "Error", "Invalid selection.")
             return

        # Save to DB
        # We save it as a 2D profile. 
        # Note: The live system expects (Time, Freq) or (Freq, Time) depending on orientation.
        # The live system's `full_spectrogram_data` is (History/Time, Freq).
        # Our `selected_data` is also (Time, Freq).
        # However, the live matching logic might need to be robust to size differences.
        # For now, we save it as is.
        
        try:
            db.save_profile_to_db(name, "2D", selected_data)
            QMessageBox.information(self, "Success", f"Profile '{name}' saved to database.")
            if self.parent_station:
                self.parent_station.load_profiles() # Refresh main window list
            self.close()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save profile: {e}")


class ComparisonWindow(QWidget):
    def __init__(self, snapshot_paths):
        super().__init__()
        self.setWindowTitle("Snapshot Comparison")
        self.resize(1200, 800)
        self.setStyleSheet("background-color: #050505; color: #FFA500;")
        self.main_layout = QHBoxLayout(self)
        
        for path in snapshot_paths:
            container = QWidget()
            layout = QVBoxLayout(container)
            
            # Label for the snapshot directory
            label = QLabel(os.path.basename(path))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            
            # Spectrogram view
            spec_view = pg.ImageView()
            spec_view.ui.histogram.hide(); spec_view.ui.roiBtn.hide(); spec_view.ui.menuBtn.hide()
            spec_view.getView().setAspectLocked(False); spec_view.getView().invertY(False)
            pos = np.array([0.0, 0.15, 0.4, 0.7, 1.0]); color = np.array([[0, 0, 0, 255], [5, 15, 30, 255], [160, 50, 0, 255], [255, 140, 0, 255], [255, 255, 220, 255]], dtype=np.ubyte)
            spec_view.setColorMap(pg.ColorMap(pos, color))
            
            # Load and display the spectrogram
            wav_path = os.path.join(path, "capture.wav")
            if os.path.exists(wav_path):
                data, samplerate = sf.read(wav_path)
                # This is a simplified spectrogram generation for display
                # A real implementation would use the saved app_settings
                # For now, we'll just show the waveform
                plot_widget = pg.PlotWidget()
                plot_widget.plot(data)
                layout.addWidget(plot_widget)

            self.main_layout.addWidget(container)

class SettingsDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("System Configuration", parent)
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        
        self.tabs = QTabWidget()
        self.setWidget(self.tabs)
        
        # Tab A: Routing
        self.routing_tab = QWidget()
        routing_layout = QVBoxLayout(self.routing_tab) # Changed to QVBoxLayout for addStretch
        
        self.combo_input = QComboBox()
        self.combo_output = QComboBox()
        self.btn_refresh = QPushButton("Refresh Devices")
        
        routing_layout.addWidget(QLabel("Input Source (Virtual Cable):"))
        routing_layout.addWidget(self.combo_input)
        routing_layout.addWidget(QLabel("Output Monitor (Headset):"))
        routing_layout.addWidget(self.combo_output)
        routing_layout.addWidget(self.btn_refresh)
        routing_layout.addStretch()
        
        self.tabs.addTab(self.routing_tab, "Routing")
        
        # Tab B: Performance
        self.perf_tab = QWidget()
        perf_layout = QVBoxLayout(self.perf_tab)
        
        self.chk_low_latency = QCheckBox("Combat Mode (Low Latency)")
        self.btn_save_blackbox = QPushButton("Save Black Box (Last 60s)")
        self.btn_save_blackbox.setStyleSheet("background-color: #440000; color: white; font-weight: bold;")
        
        perf_layout.addWidget(self.chk_low_latency)
        perf_layout.addWidget(self.btn_save_blackbox)
        perf_layout.addStretch()
        
        self.tabs.addTab(self.perf_tab, "Performance")

class ScienceStation(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Elite Signal Hunter: MK XXVIII (Proxy Engine)")
        self.resize(1600, 900)
        self.setStyleSheet("background-color: #050505; color: #FFA500;")

        # Initialize all member variables first
        self.FFT_SIZE = 4096 # Reset to standard for stability with new engine
        self.INPUT_CHUNK = 1024
        self.SAMPLE_RATE = 48000 # Will be updated by engine
        self.MAX_BINS = self.FFT_SIZE // 2 + 1
        self.history_length = 1200
        self.first_render = True
        
        self.full_spectrogram_data = np.zeros((self.history_length, self.MAX_BINS))
        self.full_spectrogram_data_complex = np.zeros((self.history_length, self.MAX_BINS), dtype=np.complex64)
        self.rolling_audio_buffer = np.zeros(self.FFT_SIZE)
        self.use_log_scale = True
        self.latest_magnitude = np.zeros(self.MAX_BINS)
        self.latest_fft_complex = np.zeros(self.MAX_BINS, dtype=np.complex64)
        self.spectrogram_is_vertical = True
        self.auto_profiling_enabled = False
        self.profiling_buffer = deque(maxlen=100)
        self.detection_threshold = 10.0
        self.signal_detected_cooldown = 0
        self.identification_threshold = 0.85
        self.anomaly_highlight_line = None
        self.capture_buffer = None
        self.profiles = {}
        self.review_windows = []
        self.current_cmdr_status = {}
        self.audio_devices = []
        self.engine = None
        self.comparison_windows = []
        self.lab_windows = []
        self.batch_folder_path = None
        self.is_recording = False
        self.recording_start_time = None
        self.recording_buffer = []
        self.recording_save_path = os.getcwd()
        self.recording_format = "WAV"
        self.recording_subtype = "PCM_24"
        self.is_hovering_spectrogram = False
        self.iq_trail_buffer = deque(maxlen=50)
        self.iq_zoom_level = 1.0
        self.iq_point_size = 5
        self.iq_rotation = 0.0
        self.iq_grid_visible = False
        self.iq_grid_items = []
        
        # Oscilloscope variables
        self.scope_trigger_level = 0.0
        self.scope_trigger_enabled = False
        self.scope_timebase = 1.0
        self.scope_gain = 1.0
        self.scope_freeze = False
        
        # Spectrum variables
        self.spectrum_hold_max = np.zeros(self.MAX_BINS)
        self.spectrum_hold_decay = 0.95
        
        # Signal Processor
        self.signal_processor = SignalProcessor(self.FFT_SIZE)

        # Setup UI layouts
        self.main_layout = QHBoxLayout()
        self.central_widget = QWidget()
        self.central_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.central_widget)
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        self.main_layout.addWidget(self.left_panel, 7)
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.main_layout.addWidget(self.right_panel, 3)

        # Setup UI elements
        header_layout = QHBoxLayout()
        self.label = QLabel(">> INITIALIZING... <<")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("font-family: Consolas; font-size: 14pt; font-weight: bold; color: #FF8800;")
        self.crosshair_label = QLabel("FREQ: --- Hz | AMP: --- dB")
        self.crosshair_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.crosshair_label.setStyleSheet("font-family: Consolas; font-size: 10pt; color: #CCCCCC;")
        self.btn_return_to_live = QPushButton("Return to Live")
        header_layout.addWidget(self.btn_return_to_live)
        header_layout.addWidget(self.label)
        header_layout.addWidget(self.crosshair_label)
        self.left_layout.addLayout(header_layout)

        self.tabs = QTabWidget()
        self.left_layout.addWidget(self.tabs)
        
        self.spec_tab = QWidget()
        self.spec_layout = QVBoxLayout(self.spec_tab)
        self.spec_plot = pg.PlotWidget(enableMenu=False, background=None, border=None)
        self.spec_image = pg.ImageItem()
        self.spec_plot.addItem(self.spec_image)
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('gray', style=Qt.PenStyle.DashLine))
        self.roi = pg.RectROI(pos=[100, 100], size=[100, 100], pen=pg.mkPen('r', width=2), movable=True, resizable=True, rotatable=False)
        
        self.scope_tab = QWidget()
        self.scope_layout = QVBoxLayout(self.scope_tab)
        self.scope_plot = pg.PlotWidget()
        self.scope_curve = self.scope_plot.plot(pen=pg.mkPen('#FFA500', width=2))
        
        self.spectrum_tab = QWidget()
        self.spectrum_layout = QVBoxLayout(self.spectrum_tab)
        self.spectrum_plot = pg.PlotWidget()
        self.spectrum_curve = self.spectrum_plot.plot(pen=pg.mkPen('#00FF00', width=1))
        self.spectrum_max_curve = self.spectrum_plot.plot(pen=pg.mkPen('#008800', width=1, style=Qt.PenStyle.DotLine))

        self.iq_tab = QWidget()
        self.iq_layout = QVBoxLayout(self.iq_tab)
        self.iq_plot = pg.PlotWidget()
        self.iq_scatter = pg.ScatterPlotItem(size=5, pen=pg.mkPen(None), brush=pg.mkBrush(255, 165, 0, 150))
        
        self.browser_tab = QWidget()
        self.browser_layout = QVBoxLayout(self.browser_tab)
        self.snapshot_list_widget = QListWidget()
        self.btn_compare_snapshots = QPushButton("Compare Selected Snapshots")
        self.btn_play_snapshot = QPushButton("Play Selected Snapshot")
        self.btn_open_lab = QPushButton("Analyze in Lab (Define Profile)")
        self.btn_analyze_file = QPushButton("Analyze External File")
        self.lbl_browser_metadata = QLabel("Select a snapshot to view details.")
        self.lbl_browser_metadata.setWordWrap(True)
        self.lbl_browser_metadata.setStyleSheet("color: #AAAAAA; font-family: Consolas;")
        
        self.db_tab = QWidget()
        self.db_layout = QVBoxLayout(self.db_tab)
        self.db_table = QTableWidget()
        self.btn_refresh_db = QPushButton("Refresh Database View")
        
        self.batch_tab = QWidget()
        self.batch_layout = QGridLayout(self.batch_tab)
        self.btn_select_batch_folder = QPushButton("Select Folder")
        self.lbl_batch_folder = QLabel("No folder selected.")
        self.btn_run_batch = QPushButton("Run Batch Analysis")
        self.batch_results_text = QTextEdit()
        
        self.settings_tab = QWidget()
        self.settings_layout = QGridLayout(self.settings_tab)
        self.audio_source_combo = QComboBox()
        self.btn_refresh_audio = QPushButton("Refresh Devices")
        self.btn_show_readme = QPushButton("View Field Manual (README)")
        self.btn_select_rec_path = QPushButton("Select Recording Folder")
        self.lbl_rec_path = QLabel(self.recording_save_path)
        self.combo_rec_format = QComboBox()
        self.combo_rec_format.addItems(["WAV", "FLAC", "OGG"])
        self.combo_rec_subtype = QComboBox()
        self.combo_rec_subtype.addItems(["PCM_16", "PCM_24", "PCM_32", "FLOAT"])
        
        self.lbl_cmdr_system = QLabel("SYSTEM: Unknown")
        self.lbl_cmdr_ship = QLabel("SHIP: Unknown")
        self.lbl_gain = QLabel("SIGNAL GAIN: 3.0x")
        self.slider_gain = QSlider(Qt.Orientation.Horizontal)
        self.lbl_floor = QLabel("NOISE CUTOFF: 60")
        self.slider_floor = QSlider(Qt.Orientation.Horizontal)
        self.lbl_zoom = QLabel("FREQ ZOOM: 24.0 kHz")
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.lbl_stretch = QLabel("VERTICAL STRETCH: 8x")
        self.slider_stretch = QSlider(Qt.Orientation.Horizontal)
        self.combo_channel = QComboBox()
        self.btn_scale = QPushButton("Mode: LOG SCALE")
        self.btn_orientation = QPushButton("Orientation: Vertical")
        self.btn_auto_profile = QPushButton("Auto-Profiling: OFF")
        self.lbl_threshold = QLabel("DETECT THRESHOLD: 10.0")
        self.slider_threshold = QSlider(Qt.Orientation.Horizontal)
        self.btn_save_snapshot = QPushButton("Save Snapshot")
        self.btn_triggered_capture = QPushButton("Triggered Capture: OFF")
        self.btn_submit_signal = QPushButton("Submit to Database")
        self.lbl_capture_duration = QLabel("CAPTURE DURATION: 15s")
        self.slider_capture_duration = QSlider(Qt.Orientation.Horizontal)
        self.lbl_identity = QLabel("CURRENT ID: ---")
        self.lbl_snr = QLabel("SNR: ---")
        self.lbl_bandwidth = QLabel("BANDWIDTH: --- Hz")
        self.lbl_centroid = QLabel("CENTROID: --- Hz")
        self.profile_list_widget = QListWidget()
        self.profile_name_input = QLineEdit()
        self.btn_save_profile = QPushButton("Save Full Signal as Profile")
        self.btn_delete_profile = QPushButton("Delete Selected Profile")
        self.btn_review_profile = QPushButton("Review Selected Profile")
        self.btn_record_audio = QPushButton("Start Recording")
        self.lbl_recording_status = QLabel("REC: STOPPED")

        # Initialize Settings Dock
        self.settings_dock = SettingsDock(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.settings_dock)

        # Call setup methods
        db.init_db()
        self.setup_spec_tab()
        self.setup_scope_tab()
        self.setup_spectrum_tab()
        self.setup_iq_tab()
        self.setup_browser_tab()
        self.setup_database_tab()
        self.setup_batch_tab()
        self.setup_settings_tab()
        self.setup_control_panel()

        # Setup timers
        self.render_timer = QTimer(self)
        self.identification_timer = QTimer(self)
        
        # Connect signals
        self.btn_return_to_live.clicked.connect(self.return_to_live)
        self.render_timer.timeout.connect(self.render_view)
        self.identification_timer.timeout.connect(self.run_identification)
        
        # Settings Dock Connections
        self.settings_dock.btn_refresh.clicked.connect(self.refresh_audio_devices)
        self.settings_dock.combo_input.currentIndexChanged.connect(self.restart_audio_engine)
        self.settings_dock.combo_output.currentIndexChanged.connect(self.restart_audio_engine)
        self.settings_dock.chk_low_latency.stateChanged.connect(self.toggle_latency_mode)
        self.settings_dock.btn_save_blackbox.clicked.connect(self.save_black_box)
        
        self.btn_show_readme.clicked.connect(self.show_readme)
        self.slider_gain.valueChanged.connect(self.update_labels)
        self.slider_floor.valueChanged.connect(self.update_labels)
        self.slider_zoom.valueChanged.connect(self.update_labels)
        self.slider_stretch.valueChanged.connect(self.update_labels)
        self.btn_scale.clicked.connect(self.toggle_scale)
        self.btn_orientation.clicked.connect(self.toggle_orientation)
        self.btn_auto_profile.clicked.connect(self.toggle_auto_profiling)
        self.slider_threshold.valueChanged.connect(self.update_labels)
        self.btn_save_snapshot.clicked.connect(self.save_snapshot)
        self.btn_triggered_capture.clicked.connect(self.toggle_triggered_capture)
        self.btn_submit_signal.clicked.connect(self.submit_current_signal)
        self.slider_capture_duration.valueChanged.connect(self.update_capture_buffer)
        self.btn_save_profile.clicked.connect(self.save_current_profile)
        self.btn_delete_profile.clicked.connect(self.delete_selected_profile)
        self.btn_review_profile.clicked.connect(self.review_selected_profile)
        self.btn_compare_snapshots.clicked.connect(self.launch_comparison_window)
        self.btn_play_snapshot.clicked.connect(self.play_selected_snapshot)
        self.btn_open_lab.clicked.connect(self.launch_lab_window)
        self.btn_analyze_file.clicked.connect(self.analyze_external_file)
        self.btn_refresh_db.clicked.connect(self.refresh_database_view)
        self.btn_select_batch_folder.clicked.connect(self.select_batch_folder)
        self.btn_run_batch.clicked.connect(self.run_batch_analysis)
        self.btn_record_audio.clicked.connect(self.toggle_recording)
        self.btn_select_rec_path.clicked.connect(self.select_recording_path)
        self.combo_rec_format.currentTextChanged.connect(self.update_recording_settings)
        self.combo_rec_subtype.currentTextChanged.connect(self.update_recording_settings)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.snapshot_list_widget.itemSelectionChanged.connect(self.on_snapshot_selected)

        # Final initialization steps
        self.update_capture_buffer()
        self.load_profiles()
        self.refresh_snapshot_browser()
        self.refresh_audio_devices()

        self.journal_watcher = JournalWatcher()
        self.journal_watcher.status_update.connect(self.update_cmdr_status)
        self.journal_watcher.start()

        self.check_first_launch()
        self.return_to_live()

    # ... [Previous methods remain unchanged] ...
    
    def setup_settings_tab(self):
        # Simplified settings tab since we moved routing to the Dock
        self.settings_layout.addWidget(QLabel("RECORDING FOLDER:"), 0, 0)
        self.settings_layout.addWidget(self.lbl_rec_path, 0, 1)
        self.settings_layout.addWidget(self.btn_select_rec_path, 0, 2)
        
        self.settings_layout.addWidget(QLabel("RECORDING FORMAT:"), 1, 0)
        self.settings_layout.addWidget(self.combo_rec_format, 1, 1)
        self.settings_layout.addWidget(self.combo_rec_subtype, 1, 2)
        
        self.settings_layout.addWidget(self.btn_show_readme, 2, 0, 1, 3)
        self.settings_layout.setColumnStretch(1, 1)
        self.settings_layout.setRowStretch(3, 1)
        self.tabs.addTab(self.settings_tab, "Settings")
        self.settings_tab.setLayout(self.settings_layout)

    def refresh_audio_devices(self):
        self.label.setText(">> SCANNING AUDIO DEVICES... <<")
        inputs, outputs = ProxyAudioEngine.get_devices()
        
        self.settings_dock.combo_input.blockSignals(True)
        self.settings_dock.combo_output.blockSignals(True)
        self.settings_dock.combo_input.clear()
        self.settings_dock.combo_output.clear()
        
        if not inputs:
            self.settings_dock.combo_input.addItem("No inputs found")
            self.settings_dock.combo_input.setEnabled(False)
        else:
            self.settings_dock.combo_input.setEnabled(True)
            for dev in inputs:
                self.settings_dock.combo_input.addItem(dev['name'], userData=dev['index'])
                
        if not outputs:
            self.settings_dock.combo_output.addItem("No outputs found")
            self.settings_dock.combo_output.setEnabled(False)
        else:
            self.settings_dock.combo_output.setEnabled(True)
            for dev in outputs:
                self.settings_dock.combo_output.addItem(dev['name'], userData=dev['index'])
                
        self.settings_dock.combo_input.blockSignals(False)
        self.settings_dock.combo_output.blockSignals(False)
        
        if self.engine is None:
            self.restart_audio_engine()
            
        self.label.setText(">> STANDING BY <<")

    def restart_audio_engine(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
            
        input_idx = self.settings_dock.combo_input.currentData()
        output_idx = self.settings_dock.combo_output.currentData()
        
        if input_idx is None:
            return

        self.label.setText(f">> STARTING PROXY ENGINE <<")
        self.first_render = True
        
        self.engine = ProxyAudioEngine(input_device_index=input_idx, output_device_index=output_idx)
        self.engine.audio_data_ready.connect(self.update_data_stream)
        self.engine.error_occurred.connect(lambda msg: self.label.setText(f">> ERROR: {msg} <<"))
        
        # Apply current latency setting
        is_low_latency = self.settings_dock.chk_low_latency.isChecked()
        self.engine.set_latency_mode(is_low_latency)
        
        self.engine.start()
        
        if not self.render_timer.isActive():
            self.render_timer.start(16)
        if not self.identification_timer.isActive():
            self.identification_timer.start(100)

    def toggle_latency_mode(self):
        if self.engine:
            is_low_latency = self.settings_dock.chk_low_latency.isChecked()
            self.engine.set_latency_mode(is_low_latency)
            mode_text = "COMBAT (LOW LATENCY)" if is_low_latency else "ANALYSIS (HIGH QUALITY)"
            self.label.setText(f">> MODE SWITCHED: {mode_text} <<")

    def save_black_box(self):
        if self.engine:
            path = self.engine.save_black_box(self.recording_save_path)
            if path:
                self.label.setText(f">> BLACK BOX SAVED: {os.path.basename(path)} <<")
                # Optionally open in lab immediately
                # self.launch_lab_window(path) 
            else:
                self.label.setText(">> ERROR SAVING BLACK BOX <<")

    # ... [Rest of methods remain unchanged: setup_spec_tab, mouse_moved_on_spectrogram, return_to_live, render_view, update_iq_plot, check_first_launch, show_readme, setup_scope_tab, setup_spectrum_tab, setup_iq_tab, setup_browser_tab, on_snapshot_selected, launch_lab_window, analyze_external_file, setup_database_tab, setup_batch_tab, setup_control_panel, clear_iq_trail, update_iq_trail_length, update_iq_zoom, update_iq_size, update_iq_rotation, toggle_iq_grid, draw_reticle, on_tab_changed, update_cmdr_status, save_snapshot, toggle_recording, select_recording_path, update_recording_settings, save_long_recording, submit_current_signal, toggle_roi_definition, save_current_profile, load_profiles, delete_selected_profile, closeEvent, review_selected_profile, launch_comparison_window, play_selected_snapshot, refresh_snapshot_browser, refresh_database_view, select_batch_folder, run_batch_analysis, update_data_stream, update_signal_characteristics, run_identification, update_capture_buffer, toggle_auto_profiling, toggle_scale, toggle_orientation, toggle_triggered_capture, update_labels, change_audio_device, toggle_scope_trigger, update_scope_trigger_level, update_scope_timebase, update_scope_gain, toggle_scope_freeze] ...
    
    # Re-implementing missing methods from previous overwrite to ensure completeness
    def setup_spec_tab(self):
        # Rebuild Spectrogram Tab
        while self.spec_layout.count():
            item = self.spec_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        self.spec_widget = pg.GraphicsLayoutWidget()
        self.spec_layout.addWidget(self.spec_widget)

        self.spec_plot = self.spec_widget.addPlot(row=0, col=0)
        self.spec_plot.setLabel('left', 'Time / History')
        self.spec_plot.setLabel('bottom', 'Frequency', units='Hz')
        self.spec_plot.showGrid(x=True, y=True, alpha=0.3)
        self.spec_plot.setMenuEnabled(False)
        self.spec_plot.setMouseEnabled(x=False, y=False)

        self.spec_image = pg.ImageItem()
        self.spec_plot.addItem(self.spec_image)

        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.spec_image)
        self.spec_widget.addItem(self.hist, row=0, col=1)

        pos = np.array([0.0, 0.15, 0.4, 0.7, 1.0])
        color = np.array([[0, 0, 0, 255], [5, 15, 30, 255], [160, 50, 0, 255], [255, 140, 0, 255], [255, 255, 220, 255]], dtype=np.ubyte)
        cmap = pg.ColorMap(pos, color)
        self.hist.gradient.setColorMap(cmap)

        self.spec_plot.addItem(self.v_line)
        self.spec_plot.addItem(self.h_line)
        
        self.anomaly_highlight_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('r', width=2, style=Qt.PenStyle.DashLine))
        self.anomaly_highlight_line.hide()
        self.spec_plot.addItem(self.anomaly_highlight_line)

        self.spec_widget.scene().sigMouseMoved.connect(self.mouse_moved_on_spectrogram)
        self.tabs.addTab(self.spec_tab, "Spectrogram")

    def mouse_moved_on_spectrogram(self, pos):
        if self.spec_plot.sceneBoundingRect().contains(pos):
            self.is_hovering_spectrogram = True
            mouse_point = self.spec_plot.getViewBox().mapSceneToView(pos)
            
            if self.spectrogram_is_vertical:
                freq_bin, time_idx = mouse_point.x(), int(mouse_point.y())
            else: # Horizontal
                time_idx, freq_bin = int(mouse_point.x()), mouse_point.y()

            zoom_percent = self.slider_zoom.value() / 100.0
            cutoff_index = max(50, int(self.MAX_BINS * zoom_percent))
            
            max_freq_bin = cutoff_index - 1
            freq_bin = np.clip(freq_bin, 0, max_freq_bin)
            
            freq_hz = (float(freq_bin) / self.MAX_BINS) * (self.SAMPLE_RATE / 2)

            if 0 <= time_idx < self.history_length and 0 <= int(freq_bin) < self.MAX_BINS:
                # Correct for np.roll in data access
                rolled_time_idx = (time_idx - (self.history_length - self.slider_stretch.value()) % self.history_length + self.history_length) % self.history_length
                amp_val = self.full_spectrogram_data[rolled_time_idx, int(freq_bin)]
                self.crosshair_label.setText(f"FREQ: {freq_hz:,.0f} Hz | AMP: {amp_val:.2f} dB")

                # Update I/Q plot based on the hovered cell
                iq_data = self.full_spectrogram_data_complex[rolled_time_idx, int(freq_bin)]
                self.update_iq_plot(iq_data)

            self.v_line.setPos(mouse_point.x())
            self.h_line.setPos(mouse_point.y())
        else:
            self.is_hovering_spectrogram = False

    def return_to_live(self):
        viewbox = self.spec_plot.getViewBox()
        if self.spectrogram_is_vertical:
            viewbox.setYRange(0, self.history_length)
        else: # Horizontal
            viewbox.setXRange(0, self.history_length)
        self.label.setText(">> VIEW SNAPPED TO LIVE FEED <<")

    def render_view(self):
        # 1. Process Spectrogram Data
        # Use SignalProcessor for gating
        gated_magnitude = self.signal_processor.apply_spectral_gate(self.latest_magnitude)
        
        if self.use_log_scale: processed_data = 20 * np.log10(gated_magnitude + 1e-9) + 100
        else: processed_data = gated_magnitude * 5000
        processed_data = np.clip(processed_data, 0, None)
        
        stretch_factor = self.slider_stretch.value()
        self.full_spectrogram_data = np.roll(self.full_spectrogram_data, stretch_factor, axis=0)
        self.full_spectrogram_data[:stretch_factor] = processed_data
        
        self.full_spectrogram_data_complex = np.roll(self.full_spectrogram_data_complex, stretch_factor, axis=0)
        self.full_spectrogram_data_complex[:stretch_factor] = self.latest_fft_complex
        
        zoom_percent = self.slider_zoom.value() / 100.0
        cutoff_index = max(50, int(self.MAX_BINS * zoom_percent))
        viewbox = self.spec_plot.getViewBox()
        
        view_data = self.full_spectrogram_data[:, :cutoff_index]
        
        auto_levels = False
        if self.first_render:
            auto_levels = True
            self.first_render = False

        if self.spectrogram_is_vertical:
            viewbox.invertY(True)
            self.spec_image.setImage(np.ascontiguousarray(view_data.T), autoLevels=auto_levels)
            if not auto_levels:
                min_level = self.slider_floor.value()
                gain_factor = self.slider_gain.value() / 10.0
                max_level = min_level + (100 / gain_factor)
                self.spec_image.setLevels([min_level, max_level])
            self.spec_image.setRect(pg.QtCore.QRectF(0, 0, cutoff_index, self.history_length))
            self.spec_plot.setXRange(0, cutoff_index)
            self.spec_plot.setYRange(0, self.history_length)
            if self.anomaly_highlight_line: self.anomaly_highlight_line.setAngle(90)
        else: # Horizontal
            viewbox.invertY(False)
            self.spec_image.setImage(np.ascontiguousarray(view_data), autoLevels=auto_levels)
            if not auto_levels:
                min_level = self.slider_floor.value()
                gain_factor = self.slider_gain.value() / 10.0
                max_level = min_level + (100 / gain_factor)
                self.spec_image.setLevels([min_level, max_level])
            self.spec_image.setRect(pg.QtCore.QRectF(0, 0, self.history_length, cutoff_index))
            self.spec_plot.setXRange(0, self.history_length)
            self.spec_plot.setYRange(0, cutoff_index)
            if self.anomaly_highlight_line: self.anomaly_highlight_line.setAngle(0)
        
        if self.first_render:
            self.return_to_live()

        # 2. Update Oscilloscope
        if not self.scope_freeze:
            scope_data = self.rolling_audio_buffer * self.scope_gain
            
            # Triggering Logic
            start_idx = 0
            if self.scope_trigger_enabled:
                # Find first crossing of trigger level with positive slope
                # Simple implementation
                crossings = np.where((scope_data[:-1] < self.scope_trigger_level) & (scope_data[1:] >= self.scope_trigger_level))[0]
                if len(crossings) > 0:
                    start_idx = crossings[0]
            
            # Apply Timebase (Zoom)
            window_size = int(len(scope_data) * self.scope_timebase)
            end_idx = min(start_idx + window_size, len(scope_data))
            display_data = scope_data[start_idx:end_idx]
            
            self.scope_curve.setData(display_data)

        # 3. Update Spectrum Analyzer
        freqs = np.fft.rfftfreq(self.FFT_SIZE, 1/self.SAMPLE_RATE)
        mag_db = 20 * np.log10(self.latest_magnitude + 1e-9)
        
        # Update Max Hold
        self.spectrum_hold_max = np.maximum(self.spectrum_hold_max * self.spectrum_hold_decay, mag_db)
        
        self.spectrum_curve.setData(freqs[:cutoff_index], mag_db[:cutoff_index])
        self.spectrum_max_curve.setData(freqs[:cutoff_index], self.spectrum_hold_max[:cutoff_index])

        if self.is_recording:
            elapsed = (datetime.now() - self.recording_start_time).total_seconds()
            self.lbl_recording_status.setText(f"REC: {elapsed:.1f}s")
            
        if not self.is_hovering_spectrogram:
            peak_bin = np.argmax(self.latest_magnitude)
            iq_data = self.latest_fft_complex[peak_bin]
            self.update_iq_plot(iq_data)

    def update_iq_plot(self, iq_data):
        # Apply rotation
        if self.iq_rotation != 0:
            angle_rad = np.radians(self.iq_rotation)
            iq_data = iq_data * np.exp(1j * angle_rad)

        self.iq_trail_buffer.append(iq_data)
        
        # Create arrays for scatter plot
        x_data = [p.real for p in self.iq_trail_buffer]
        y_data = [p.imag for p in self.iq_trail_buffer]
        
        # Create a brush array for fading effect
        n_points = len(self.iq_trail_buffer)
        brushes = [pg.mkBrush(255, 165, 0, int(255 * (i / n_points))) for i in range(n_points)]
        
        self.iq_scatter.setData(x=x_data, y=y_data, brush=brushes, size=self.iq_point_size)
        
        # Update zoom
        range_val = 1000 / self.iq_zoom_level
        self.iq_plot.setRange(xRange=[-range_val, range_val], yRange=[-range_val, range_val])

    def check_first_launch(self):
        flag_file = ".first_launch_seen"
        if not os.path.exists(flag_file):
            self.show_readme()
            with open(flag_file, 'w') as f: f.write("This file prevents the README from showing on every launch.")
    @staticmethod
    def show_readme():
        readme_path = "README.md"
        if os.path.exists(readme_path):
            try:
                if sys.platform == "win32": subprocess.run(['notepad.exe', os.path.realpath(readme_path)])
                else: webbrowser.open(os.path.realpath(readme_path))
            except Exception as e: print(f"Could not open README.md: {e}")
            
    def setup_scope_tab(self):
        # Enhanced Oscilloscope Setup
        self.scope_plot.setYRange(-1.0, 1.0)
        self.scope_plot.showGrid(x=True, y=True, alpha=0.5)
        self.scope_plot.setLabel('left', 'Amplitude')
        self.scope_plot.setLabel('bottom', 'Samples')
        
        # Controls Layout
        controls_layout = QHBoxLayout()
        
        # Trigger Controls
        self.chk_scope_trigger = QCheckBox("Trigger")
        self.chk_scope_trigger.stateChanged.connect(self.toggle_scope_trigger)
        self.slider_scope_trigger = QSlider(Qt.Orientation.Horizontal)
        self.slider_scope_trigger.setRange(-100, 100)
        self.slider_scope_trigger.setValue(0)
        self.slider_scope_trigger.valueChanged.connect(self.update_scope_trigger_level)
        self.lbl_scope_trigger = QLabel("Trig: 0.00")
        
        # Timebase Control
        self.slider_scope_timebase = QSlider(Qt.Orientation.Horizontal)
        self.slider_scope_timebase.setRange(1, 100)
        self.slider_scope_timebase.setValue(100)
        self.slider_scope_timebase.valueChanged.connect(self.update_scope_timebase)
        self.lbl_scope_timebase = QLabel("Zoom: 1.0x")
        
        # Gain Control
        self.slider_scope_gain = QSlider(Qt.Orientation.Horizontal)
        self.slider_scope_gain.setRange(1, 50)
        self.slider_scope_gain.setValue(10)
        self.slider_scope_gain.valueChanged.connect(self.update_scope_gain)
        self.lbl_scope_gain = QLabel("Gain: 1.0x")
        
        # Freeze
        self.btn_scope_freeze = QPushButton("Freeze")
        self.btn_scope_freeze.setCheckable(True)
        self.btn_scope_freeze.clicked.connect(self.toggle_scope_freeze)
        
        controls_layout.addWidget(self.chk_scope_trigger)
        controls_layout.addWidget(self.lbl_scope_trigger)
        controls_layout.addWidget(self.slider_scope_trigger)
        controls_layout.addWidget(self.lbl_scope_timebase)
        controls_layout.addWidget(self.slider_scope_timebase)
        controls_layout.addWidget(self.lbl_scope_gain)
        controls_layout.addWidget(self.slider_scope_gain)
        controls_layout.addWidget(self.btn_scope_freeze)
        
        self.scope_layout.addLayout(controls_layout)
        self.scope_layout.addWidget(self.scope_plot)
        self.tabs.addTab(self.scope_tab, "Oscilloscope")

    def setup_spectrum_tab(self):
        self.spectrum_plot.setLabel('left', 'Magnitude (dB)')
        self.spectrum_plot.setLabel('bottom', 'Frequency (Hz)')
        self.spectrum_plot.showGrid(x=True, y=True, alpha=0.5)
        self.spectrum_plot.setYRange(0, 150)
        
        self.spectrum_layout.addWidget(self.spectrum_plot)
        self.tabs.addTab(self.spectrum_tab, "Spectrum Analyzer")

    def setup_iq_tab(self):
        self.iq_plot.setLabel('left', 'Quadrature')
        self.iq_plot.setLabel('bottom', 'In-Phase')
        self.iq_plot.showGrid(x=True, y=True, alpha=0.3)
        self.iq_plot.setAspectLocked(True)
        self.iq_plot.addItem(self.iq_scatter)
        
        self.iq_layout.addWidget(self.iq_plot)
        self.tabs.addTab(self.iq_tab, "I/Q Constellation")
        self.iq_tab.setLayout(self.iq_layout)

    def setup_browser_tab(self):
        # Splitter for Archive (Left) and Data Card (Right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left Container (Inventory)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("SAVED SNAPSHOTS:"))
        left_layout.addWidget(self.snapshot_list_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_play_snapshot)
        btn_layout.addWidget(self.btn_compare_snapshots)
        btn_layout.addWidget(self.btn_open_lab)
        btn_layout.addWidget(self.btn_analyze_file) # Add new button
        left_layout.addLayout(btn_layout)
        
        # Right Container (Data Card)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("METADATA CARD:"))
        right_layout.addWidget(self.lbl_browser_metadata)
        right_layout.addStretch()
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([400, 200])
        
        self.browser_layout.addWidget(splitter)
        
        self.snapshot_list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.tabs.addTab(self.browser_tab, "Snapshot Browser")

    def on_snapshot_selected(self):
        selected_items = self.snapshot_list_widget.selectedItems()
        if not selected_items:
            self.lbl_browser_metadata.setText("Select a snapshot to view details.")
            return
            
        # Get metadata from DB or file
        # We stored directory in UserRole
        path = selected_items[0].data(Qt.ItemDataRole.UserRole)
        meta_path = os.path.join(path, "metadata.json")
        
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                    
                context = meta.get("cmdr_context", {})
                settings = meta.get("app_settings", {})
                timestamp = meta.get("timestamp_utc", "Unknown")
                
                info = f"""
                <b>TIMESTAMP:</b> {timestamp}<br>
                <b>SYSTEM:</b> {context.get('StarSystem', 'Unknown')}<br>
                <b>SHIP:</b> {context.get('Ship', 'Unknown')}<br>
                <hr>
                <b>SAMPLE RATE:</b> {settings.get('sample_rate', '---')} Hz<br>
                <b>FFT SIZE:</b> {settings.get('fft_size', '---')}<br>
                <b>SOURCE:</b> {settings.get('audio_source', '---')}
                """
                self.lbl_browser_metadata.setText(info)
            except Exception as e:
                self.lbl_browser_metadata.setText(f"Error reading metadata: {e}")
        else:
            self.lbl_browser_metadata.setText("Metadata file missing.")

    def launch_lab_window(self):
        selected_items = self.snapshot_list_widget.selectedItems()
        if not selected_items:
            self.label.setText(">> Select a snapshot to analyze. <<")
            return
        
        path = selected_items[0].data(Qt.ItemDataRole.UserRole)
        lab_win = SnapshotLabWindow(path, parent=self)
        self.lab_windows.append(lab_win)
        lab_win.show()
        
    def analyze_external_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Audio File", "", "Audio Files (*.wav)")
        if file_path:
            lab_win = SnapshotLabWindow(file_path, parent=self)
            self.lab_windows.append(lab_win)
            lab_win.show()

    # ... [Rest of the class remains unchanged] ...
    def setup_database_tab(self):
        self.db_layout.addWidget(self.btn_refresh_db)
        self.db_layout.addWidget(self.db_table)
        self.db_table.setColumnCount(4)
        self.db_table.setHorizontalHeaderLabels(["ID", "Timestamp", "Directory", "Metadata"])
        self.db_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabs.addTab(self.db_tab, "Database")

    def setup_batch_tab(self):
        self.batch_layout.addWidget(self.btn_select_batch_folder, 0, 0)
        self.batch_layout.addWidget(self.lbl_batch_folder, 0, 1)
        self.batch_layout.addWidget(self.btn_run_batch, 1, 0, 1, 2)
        self.batch_layout.addWidget(self.batch_results_text, 2, 0, 1, 2)
        self.batch_results_text.setReadOnly(True)
        self.tabs.addTab(self.batch_tab, "Batch Processing")

    def setup_settings_tab(self):
        self.settings_layout.addWidget(QLabel("AUDIO SOURCE:"), 0, 0)
        self.settings_layout.addWidget(self.audio_source_combo, 0, 1)
        self.settings_layout.addWidget(self.btn_refresh_audio, 0, 2)
        
        self.settings_layout.addWidget(QLabel("RECORDING FOLDER:"), 1, 0)
        self.settings_layout.addWidget(self.lbl_rec_path, 1, 1)
        self.settings_layout.addWidget(self.btn_select_rec_path, 1, 2)
        
        self.settings_layout.addWidget(QLabel("RECORDING FORMAT:"), 2, 0)
        self.settings_layout.addWidget(self.combo_rec_format, 2, 1)
        self.settings_layout.addWidget(self.combo_rec_subtype, 2, 2)
        
        self.settings_layout.addWidget(self.btn_show_readme, 3, 0, 1, 3)
        self.settings_layout.setColumnStretch(1, 1)
        self.settings_layout.setRowStretch(4, 1)
        self.tabs.addTab(self.settings_tab, "Settings")
        self.settings_tab.setLayout(self.settings_layout)

    def setup_control_panel(self):
        # Create separate widgets for different control sets
        self.spec_controls = QWidget()
        spec_ctrl_layout = QGridLayout(self.spec_controls)
        
        # Spectrogram Controls
        self.slider_gain.setRange(1, 100)
        self.slider_gain.setValue(30)
        self.slider_floor.setRange(0, 200)
        self.slider_floor.setValue(60)
        self.slider_zoom.setRange(5, 100)
        self.slider_zoom.setValue(100)
        self.slider_stretch.setRange(1, 20)
        self.slider_stretch.setValue(8)
        self.combo_channel.addItems(["Stereo Mix", "Left Channel Only", "Right Channel Only"])
        self.btn_scale.setCheckable(True)
        self.btn_auto_profile.setCheckable(True)
        self.slider_threshold.setRange(1, 200)
        self.slider_threshold.setValue(20)
        self.slider_capture_duration.setRange(5, 60)
        self.slider_capture_duration.setValue(15)
        self.btn_record_audio.setCheckable(True)

        spec_ctrl_layout.addWidget(self.lbl_gain, 0, 0)
        spec_ctrl_layout.addWidget(self.slider_gain, 0, 1)
        spec_ctrl_layout.addWidget(self.lbl_floor, 1, 0)
        spec_ctrl_layout.addWidget(self.slider_floor, 1, 1)
        spec_ctrl_layout.addWidget(self.lbl_zoom, 2, 0)
        spec_ctrl_layout.addWidget(self.slider_zoom, 2, 1)
        spec_ctrl_layout.addWidget(self.lbl_stretch, 3, 0)
        spec_ctrl_layout.addWidget(self.slider_stretch, 3, 1)
        spec_ctrl_layout.addWidget(QLabel("SOURCE:"), 4, 0)
        spec_ctrl_layout.addWidget(self.combo_channel, 4, 1)
        spec_ctrl_layout.addWidget(self.btn_scale, 5, 0, 1, 1)
        spec_ctrl_layout.addWidget(self.btn_orientation, 5, 1, 1, 1)
        spec_ctrl_layout.addWidget(QLabel("--- AUTO-DETECTION ---"), 6, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        spec_ctrl_layout.addWidget(self.btn_auto_profile, 7, 0, 1, 2)
        spec_ctrl_layout.addWidget(self.lbl_threshold, 8, 0)
        spec_ctrl_layout.addWidget(self.slider_threshold, 8, 1)
        spec_ctrl_layout.addWidget(QLabel("--- CAPTURE ---"), 9, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        spec_ctrl_layout.addWidget(self.lbl_capture_duration, 10, 0)
        spec_ctrl_layout.addWidget(self.slider_capture_duration, 10, 1)
        spec_ctrl_layout.addWidget(self.btn_save_snapshot, 11, 0, 1, 1)
        spec_ctrl_layout.addWidget(self.btn_triggered_capture, 11, 1, 1, 1)
        spec_ctrl_layout.addWidget(QLabel("--- LONG RECORDING ---"), 12, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        spec_ctrl_layout.addWidget(self.lbl_recording_status, 13, 0)
        spec_ctrl_layout.addWidget(self.btn_record_audio, 13, 1)

        # I/Q Controls
        self.iq_controls = QWidget()
        iq_ctrl_layout = QGridLayout(self.iq_controls)
        
        self.btn_iq_clear = QPushButton("Clear Trail")
        self.slider_iq_trail = QSlider(Qt.Orientation.Horizontal)
        self.slider_iq_trail.setRange(10, 200)
        self.slider_iq_trail.setValue(50)
        self.lbl_iq_trail = QLabel("Trail Length: 50")
        
        self.slider_iq_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_iq_zoom.setRange(1, 50)
        self.slider_iq_zoom.setValue(10)
        self.lbl_iq_zoom = QLabel("Zoom: 1.0x")
        
        self.slider_iq_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_iq_size.setRange(1, 20)
        self.slider_iq_size.setValue(5)
        self.lbl_iq_size = QLabel("Point Size: 5")
        
        self.dial_iq_rotation = QDial()
        self.dial_iq_rotation.setRange(0, 360)
        self.dial_iq_rotation.setNotchesVisible(True)
        self.lbl_iq_rotation = QLabel("Rotation: 0°")
        
        self.chk_iq_grid = QCheckBox("Show Polar Grid")
        
        iq_ctrl_layout.addWidget(self.btn_iq_clear, 0, 0, 1, 2)
        iq_ctrl_layout.addWidget(QLabel("Trail Length:"), 1, 0)
        iq_ctrl_layout.addWidget(self.slider_iq_trail, 1, 1)
        iq_ctrl_layout.addWidget(self.lbl_iq_trail, 1, 2)
        
        iq_ctrl_layout.addWidget(QLabel("Zoom:"), 2, 0)
        iq_ctrl_layout.addWidget(self.slider_iq_zoom, 2, 1)
        iq_ctrl_layout.addWidget(self.lbl_iq_zoom, 2, 2)
        
        iq_ctrl_layout.addWidget(QLabel("Point Size:"), 3, 0)
        iq_ctrl_layout.addWidget(self.slider_iq_size, 3, 1)
        iq_ctrl_layout.addWidget(self.lbl_iq_size, 3, 2)
        
        iq_ctrl_layout.addWidget(QLabel("Rotation:"), 4, 0)
        iq_ctrl_layout.addWidget(self.dial_iq_rotation, 4, 1)
        iq_ctrl_layout.addWidget(self.lbl_iq_rotation, 4, 2)
        
        iq_ctrl_layout.addWidget(self.chk_iq_grid, 5, 0, 1, 2)
        
        # Connect I/Q controls
        self.btn_iq_clear.clicked.connect(self.clear_iq_trail)
        self.slider_iq_trail.valueChanged.connect(self.update_iq_trail_length)
        self.slider_iq_zoom.valueChanged.connect(self.update_iq_zoom)
        self.slider_iq_size.valueChanged.connect(self.update_iq_size)
        self.dial_iq_rotation.valueChanged.connect(self.update_iq_rotation)
        self.chk_iq_grid.stateChanged.connect(self.toggle_iq_grid)

        # CMDR Status
        status_container = QWidget()
        status_layout = QGridLayout(status_container)
        self.lbl_cmdr_system.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.lbl_cmdr_system, 0, 0)
        status_layout.addWidget(self.lbl_cmdr_ship, 1, 0)

        # Profile Controls
        profile_container = QWidget()
        profile_layout = QGridLayout(profile_container)
        self.lbl_identity.setStyleSheet("font-size: 12pt; font-weight: bold;")
        self.profile_name_input.setPlaceholderText("e.g., Thargoid Probe")
        # self.btn_define_roi.setCheckable(True) # Removed from live control
        profile_layout.addWidget(self.lbl_identity, 0, 0, 1, 2)
        profile_layout.addWidget(QLabel("SAVED PROFILES:"), 1, 0, 1, 2)
        profile_layout.addWidget(self.profile_list_widget, 2, 0, 1, 2)
        profile_layout.addWidget(self.btn_review_profile, 3, 0, 1, 1)
        profile_layout.addWidget(self.btn_delete_profile, 3, 1, 1, 1)
        profile_layout.addWidget(QLabel("NEW PROFILE NAME:"), 4, 0, 1, 2)
        profile_layout.addWidget(self.profile_name_input, 5, 0, 1, 2)
        # profile_layout.addWidget(self.btn_define_roi, 6, 0, 1, 2) # Removed from live control
        profile_layout.addWidget(self.btn_save_profile, 7, 0, 1, 2)
        
        # Signal Characteristics
        characteristics_container = QWidget()
        characteristics_layout = QGridLayout(characteristics_container)
        characteristics_layout.addWidget(self.lbl_snr, 0, 0)
        characteristics_layout.addWidget(self.lbl_bandwidth, 1, 0)
        characteristics_layout.addWidget(self.lbl_centroid, 2, 0)

        # Add to Right Panel
        self.right_layout.addWidget(QLabel("--- CMDR STATUS ---"))
        self.right_layout.addWidget(status_container)
        
        # Stacked Widget for Context-Sensitive Controls
        self.controls_stack = QTabWidget() # Using TabWidget as a simple stack for now, or could use QStackedWidget
        self.controls_stack.setTabBarAutoHide(True) # Hide tabs if we want to control it programmatically
        self.controls_stack.addTab(self.spec_controls, "Spectrogram Controls")
        self.controls_stack.addTab(self.iq_controls, "I/Q Controls") # Added I/Q controls to stack
        
        self.right_layout.addWidget(QLabel("--- MASTER CONTROLS ---"))
        self.right_layout.addWidget(self.controls_stack)
        
        self.right_layout.addWidget(QLabel("--- SIGNAL CHARACTERISTICS ---"))
        self.right_layout.addWidget(characteristics_container)
        self.right_layout.addWidget(QLabel("--- SIGNAL IDENTIFICATION ---"))
        self.right_layout.addWidget(profile_container)
        self.right_layout.addWidget(self.btn_submit_signal)
        self.right_layout.addStretch()

    def clear_iq_trail(self):
        self.iq_trail_buffer.clear()
        
    def update_iq_trail_length(self):
        length = self.slider_iq_trail.value()
        self.lbl_iq_trail.setText(f"Trail Length: {length}")
        new_buffer = deque(list(self.iq_trail_buffer)[-length:], maxlen=length)
        self.iq_trail_buffer = new_buffer

    def update_iq_zoom(self):
        self.iq_zoom_level = self.slider_iq_zoom.value() / 10.0
        self.lbl_iq_zoom.setText(f"Zoom: {self.iq_zoom_level:.1f}x")
        
    def update_iq_size(self):
        self.iq_point_size = self.slider_iq_size.value()
        self.lbl_iq_size.setText(f"Point Size: {self.iq_point_size}")
        
    def update_iq_rotation(self):
        self.iq_rotation = self.dial_iq_rotation.value()
        self.lbl_iq_rotation.setText(f"Rotation: {self.iq_rotation}°")
        
    def toggle_iq_grid(self):
        self.iq_grid_visible = self.chk_iq_grid.isChecked()
        if self.iq_grid_visible:
            self.draw_reticle()
        else:
            for item in self.iq_grid_items:
                self.iq_plot.removeItem(item)
            self.iq_grid_items.clear()

    def draw_reticle(self):
        # Clear existing grid
        for item in self.iq_grid_items:
            self.iq_plot.removeItem(item)
        self.iq_grid_items.clear()
        
        # Draw circles
        for r in [250, 500, 750]:
            circle = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r*2, r*2)
            circle.setPen(pg.mkPen(color=(100, 100, 100), width=1, style=Qt.PenStyle.DashLine))
            self.iq_plot.addItem(circle)
            self.iq_grid_items.append(circle)
            
        # Draw crosshairs
        line_h = pg.InfiniteLine(angle=0, pen=pg.mkPen(color=(100, 100, 100), width=1))
        line_v = pg.InfiniteLine(angle=90, pen=pg.mkPen(color=(100, 100, 100), width=1))
        self.iq_plot.addItem(line_h)
        self.iq_plot.addItem(line_v)
        self.iq_grid_items.extend([line_h, line_v])

    def on_tab_changed(self, index):
        # Logic to switch controls based on tab
        tab_text = self.tabs.tabText(index)
        if tab_text == "Spectrogram":
            self.controls_stack.setCurrentIndex(0) # Show Spectrogram Controls
        elif tab_text == "I/Q Constellation":
            self.controls_stack.setCurrentIndex(1) # Show I/Q Controls
        else:
            # Default to Spectrogram controls for other tabs or keep previous
            self.controls_stack.setCurrentIndex(0)

    def update_cmdr_status(self, status):
        self.current_cmdr_status = status
        self.lbl_cmdr_system.setText(f"SYSTEM: {status.get('StarSystem', 'Unknown')}")
        self.lbl_cmdr_ship.setText(f"SHIP: {status.get('Ship', 'Unknown')}")
        if self.btn_triggered_capture.isChecked() and status.get('event') == 'ReceiveText':
            self.save_snapshot()

    def save_snapshot(self, is_submission=False):
        if not self.capture_buffer:
            self.label.setText(">> Buffer empty. Nothing to save. <<")
            return None, None
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        snapshot_dir = f"snapshot_{timestamp}"
        os.makedirs(snapshot_dir, exist_ok=True)
        wav_path = os.path.join(snapshot_dir, "capture.wav")
        recording_data = np.concatenate(list(self.capture_buffer))
        sf.write(wav_path, recording_data, self.SAMPLE_RATE)
        
        with open(wav_path, 'rb') as f_wav:
            wav_bytes = f_wav.read()
            sha256_hash = hashlib.sha256(wav_bytes).hexdigest()
            
        metadata = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "app_settings": {
                "fft_size": self.FFT_SIZE, "input_chunk": self.INPUT_CHUNK,
                "sample_rate": self.SAMPLE_RATE, "gain_slider": self.slider_gain.value(), "floor_slider": self.slider_floor.value(),
                "zoom_slider": self.slider_zoom.value(), "stretch_slider": self.slider_stretch.value(),
                "audio_source": self.audio_source_combo.currentText(), "channel_mode": self.combo_channel.currentText(),
                "scale_mode": "Log" if self.use_log_scale else "Linear"
            },
            "cmdr_context": self.current_cmdr_status,
            "raw_data_hash": sha256_hash
        }
        
        with open(os.path.join(snapshot_dir, "metadata.json"), 'w') as f: json.dump(metadata, f, indent=4)
        
        with open(os.path.join(snapshot_dir, "capture.sha256"), 'w') as f_hash: f_hash.write(sha256_hash)
        
        # Log to DB
        db.log_snapshot_to_db(f"snap_{timestamp}", metadata["timestamp_utc"], snapshot_dir, metadata)
        
        if not is_submission:
            self.label.setText(f">> Snapshot saved to {snapshot_dir} <<")
            self.refresh_snapshot_browser()
            
        return metadata, sha256_hash
    
    def toggle_recording(self):
        if self.btn_record_audio.isChecked():
            self.is_recording = True
            self.recording_start_time = datetime.now()
            self.recording_buffer = []
            self.btn_record_audio.setText("Stop Recording")
            self.lbl_recording_status.setStyleSheet("color: #FF0000; font-weight: bold;")
            self.label.setText(">> RECORDING STARTED <<")
        else:
            self.is_recording = False
            self.btn_record_audio.setText("Start Recording")
            self.lbl_recording_status.setText("REC: STOPPED")
            self.lbl_recording_status.setStyleSheet("color: #FFA500;")
            self.save_long_recording()

    def select_recording_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Recording Folder")
        if folder:
            self.recording_save_path = folder
            self.lbl_rec_path.setText(folder)

    def update_recording_settings(self):
        self.recording_format = self.combo_rec_format.currentText()
        self.recording_subtype = self.combo_rec_subtype.currentText()

    def save_long_recording(self):
        if not self.recording_buffer:
            self.label.setText(">> Recording empty. Nothing saved. <<")
            return

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        ext = self.recording_format.lower()
        filename = f"recording_{timestamp}.{ext}"
        full_path = os.path.join(self.recording_save_path, filename)
        
        try:
            recording_data = np.concatenate(self.recording_buffer)
            sf.write(full_path, recording_data, self.SAMPLE_RATE, 
                     format=self.recording_format, subtype=self.recording_subtype)
            self.label.setText(f">> Recording saved: {filename} <<")
        except Exception as e:
            self.label.setText(f">> ERROR saving recording: {e} <<")
        
        self.recording_buffer = []

    def submit_current_signal(self):
        self.label.setText(">> Preparing submission... <<")
        
        # 1. Save a snapshot to get the metadata and hash
        metadata, raw_data_hash = self.save_snapshot(is_submission=True)
        if metadata is None:
            self.label.setText(">> SUBMISSION FAILED: Could not create snapshot. <<")
            return
            
        # 2. Extract signal characteristics
        gated_magnitude = self.signal_processor.apply_spectral_gate(self.latest_magnitude)
        characteristics = calculate_characteristics(gated_magnitude, self.signal_processor.noise_mean, self.SAMPLE_RATE, self.FFT_SIZE)

        # 3. Call the API client
        success, sighting_id = submit_signal(
            cmdr_context=metadata["cmdr_context"],
            signal_characteristics=characteristics,
            raw_data_hash=raw_data_hash,
            notes="Manual submission from Elite Signal Hunter."
        )

        if success:
            self.label.setText(f">> SUBMITTED Sighting ID: {sighting_id} <<")
        else:
            self.label.setText(">> SUBMISSION FAILED: See console for details. <<")

    def toggle_roi_definition(self):
        if self.btn_define_roi.isChecked():
            self.roi.show()
            self.btn_save_profile.setText("Save Selection as Profile")
        else:
            self.roi.hide()
            self.btn_save_profile.setText("Save Full Signal as Profile")

    def save_current_profile(self):
        profile_name = self.profile_name_input.text().strip()
        if not profile_name:
            self.label.setText(">> Please enter a profile name. <<")
            return
            
        # Removed ROI logic from live save
        profile_to_save = self.signal_processor.apply_spectral_gate(self.latest_magnitude)
        save_type = "1D"
            
        try:
            db.save_profile_to_db(profile_name, save_type, profile_to_save)
            self.label.setText(f">> Profile '{profile_name}' ({save_type}) saved. <<")
            self.profile_name_input.clear()
            self.load_profiles()
        except Exception as e:
            self.label.setText(">> FAILED to save profile! <<")
            print(f"Error saving profile to DB: {e}")

    def load_profiles(self):
        self.profiles = db.load_profiles_from_db()
        self.profile_list_widget.clear()
        self.profile_list_widget.addItems(self.profiles.keys())
        self.label.setText(f">> {len(self.profiles)} profiles loaded from DB. <<")

    def delete_selected_profile(self):
        selected_items = self.profile_list_widget.selectedItems()
        if not selected_items:
            self.label.setText(">> Select a profile to delete. <<")
            return
        profile_name = selected_items[0].text()
        try:
            db.delete_profile_from_db(profile_name)
            self.label.setText(f">> Profile '{profile_name}' deleted. <<")
            self.load_profiles()
        except Exception as e:
            self.label.setText(f">> FAILED to delete profile! <<")
            print(f"Error deleting profile from DB: {e}")

    def closeEvent(self, event):
        self.journal_watcher.stop()
        if self.engine: self.engine.stop()
        for win in self.review_windows: win.close()
        for win in self.comparison_windows: win.close()
        event.accept()
        
    def review_selected_profile(self):
        selected_items = self.profile_list_widget.selectedItems()
        if not selected_items:
            self.label.setText(">> Select a profile to review. <<")
            return
        profile_name = selected_items[0].text()
        profile_data = self.profiles.get(profile_name)
        if profile_data is not None:
            review_win = ProfileReviewWindow(profile_name, profile_data)
            self.review_windows.append(review_win)
            review_win.show()
        else:
            self.label.setText(">> Could not find profile data to review. <<")
        
    def launch_comparison_window(self):
        selected_items = self.snapshot_list_widget.selectedItems()
        if not selected_items:
            self.label.setText(">> Select at least one snapshot to compare. <<")
            return
        
        paths = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        comp_win = ComparisonWindow(paths)
        self.comparison_windows.append(comp_win)
        comp_win.show()

    def play_selected_snapshot(self):
        selected_items = self.snapshot_list_widget.selectedItems()
        if not selected_items:
            self.label.setText(">> Select a snapshot to play. <<")
            return
        
        path = selected_items[0].data(Qt.ItemDataRole.UserRole)
        wav_path = os.path.join(path, "capture.wav")
        if os.path.exists(wav_path):
            try:
                winsound.PlaySound(wav_path, winsound.SND_ASYNC)
                self.label.setText(f">> Playing: {os.path.basename(path)} <<")
            except Exception as e:
                self.label.setText(f">> Error playing sound: {e} <<")
        else:
            self.label.setText(">> Audio file not found. <<")

    def refresh_snapshot_browser(self):
        self.snapshot_list_widget.clear()
        snapshots = db.get_all_snapshots()
        for snapshot in snapshots:
            item = QListWidgetItem(f"{snapshot['timestamp']} - {snapshot['id']}")
            item.setData(Qt.ItemDataRole.UserRole, snapshot['directory'])
            self.snapshot_list_widget.addItem(item)
            
    def refresh_database_view(self):
        snapshots = db.get_all_snapshots()
        self.db_table.setRowCount(len(snapshots))
        for i, snap in enumerate(snapshots):
            self.db_table.setItem(i, 0, QTableWidgetItem(snap['id']))
            self.db_table.setItem(i, 1, QTableWidgetItem(snap['timestamp']))
            self.db_table.setItem(i, 2, QTableWidgetItem(snap['directory']))
            self.db_table.setItem(i, 3, QTableWidgetItem(str(snap['metadata'])))

    def select_batch_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.batch_folder_path = folder
            self.lbl_batch_folder.setText(folder)

    def run_batch_analysis(self):
        if not self.batch_folder_path:
            self.batch_results_text.setText("Please select a folder first.")
            return

        self.batch_results_text.clear()
        self.batch_results_text.append("Starting batch analysis...")
        QApplication.processEvents() 

        wav_files = [f for f in os.listdir(self.batch_folder_path) if f.lower().endswith('.wav')]

        for wav_file in wav_files:
            self.batch_results_text.append(f"\n--- Analyzing: {wav_file} ---")
            QApplication.processEvents()
            
            file_path = os.path.join(self.batch_folder_path, wav_file)
            try:
                data, samplerate = sf.read(file_path)
                if samplerate != self.SAMPLE_RATE:
                    self.batch_results_text.append(f"  Skipping (unsupported sample rate: {samplerate})")
                    continue
                
                if data.ndim > 1:
                    data = np.mean(data, axis=1)

                num_chunks = len(data) // self.INPUT_CHUNK
                found_signal = False
                for i in range(num_chunks):
                    start = i * self.INPUT_CHUNK
                    end = start + self.FFT_SIZE
                    if end > len(data):
                        break
                    
                    chunk = data[start:end]
                    
                    latest_fft_complex = np.fft.rfft(chunk * np.hanning(self.FFT_SIZE))
                    latest_magnitude = np.abs(latest_fft_complex)
                    
                    # Use SignalProcessor for anomaly detection
                    if self.signal_processor.detect_anomaly(latest_magnitude, threshold=self.detection_threshold):
                        found_signal = True
                        time_in_file = start / samplerate
                        
                        # Calculate frequency of anomaly
                        gated_magnitude = self.signal_processor.apply_spectral_gate(latest_magnitude)
                        anomaly_bin = np.argmax(gated_magnitude)
                        anomaly_freq = (anomaly_bin / self.MAX_BINS) * (self.SAMPLE_RATE / 2)
                        
                        self.batch_results_text.append(f"  - Signal detected at {time_in_file:.2f}s, Freq: {anomaly_freq:,.0f} Hz")
                        QApplication.processEvents()

                if not found_signal:
                    self.batch_results_text.append("  No significant signals detected.")

            except Exception as e:
                self.batch_results_text.append(f"  ERROR processing file: {e}")

        self.batch_results_text.append("\n--- Batch analysis complete. ---")

    def update_data_stream(self, new_audio_chunk):
        if new_audio_chunk.ndim == 1:
            self.capture_buffer.append(np.column_stack([new_audio_chunk, new_audio_chunk]))
        else:
            self.capture_buffer.append(new_audio_chunk)
        
        if self.is_recording:
            if new_audio_chunk.ndim == 1:
                self.recording_buffer.append(np.column_stack([new_audio_chunk, new_audio_chunk]))
            else:
                self.recording_buffer.append(new_audio_chunk)
        
        if self.combo_channel.currentText() == "Left Channel Only" and new_audio_chunk.ndim > 1:
            new_audio = new_audio_chunk[:, 0]
        elif self.combo_channel.currentText() == "Right Channel Only" and new_audio_chunk.ndim > 1:
            new_audio = new_audio_chunk[:, 1]
        else:
            new_audio = np.mean(new_audio_chunk, axis=1) if new_audio_chunk.ndim > 1 else new_audio_chunk
            
        self.rolling_audio_buffer = np.roll(self.rolling_audio_buffer, -len(new_audio))
        self.rolling_audio_buffer[-len(new_audio):] = new_audio
        
        # Perform FFT and store both complex data and magnitude
        self.latest_fft_complex = np.fft.rfft(self.rolling_audio_buffer * np.hanning(self.FFT_SIZE))
        self.latest_magnitude = np.abs(self.latest_fft_complex)
        
        if self.auto_profiling_enabled:
            self.profiling_buffer.append(self.latest_magnitude)
            if len(self.profiling_buffer) == self.profiling_buffer.maxlen:
                # Update the SignalProcessor with the new noise profile
                self.signal_processor.capture_noise_profile(list(self.profiling_buffer))
                self.noise_profile = self.signal_processor.noise_mean # Keep for legacy compatibility if needed

    def update_signal_characteristics(self, gated_magnitude):
        characteristics = calculate_characteristics(gated_magnitude, self.signal_processor.noise_mean, self.SAMPLE_RATE, self.FFT_SIZE)
        
        snr = characteristics["snr"]
        self.lbl_snr.setText(f"SNR: {snr:.2f} dB")

        bandwidth = characteristics["bandwidth"]
        if bandwidth > 0:
            self.lbl_bandwidth.setText(f"BANDWIDTH: {bandwidth:,.0f} Hz")
        else:
            self.lbl_bandwidth.setText("BANDWIDTH: --- Hz")

        centroid = characteristics["spectral_centroid"]
        if centroid > 0:
            self.lbl_centroid.setText(f"CENTROID: {centroid:,.0f} Hz")
        else:
            self.lbl_centroid.setText("CENTROID: --- Hz")

    def run_identification(self):
        if self.anomaly_highlight_line is None: return
        
        # Use SignalProcessor for anomaly detection
        is_anomaly = self.signal_processor.detect_anomaly(self.latest_magnitude, threshold=self.detection_threshold)
        
        gated_magnitude = self.signal_processor.apply_spectral_gate(self.latest_magnitude)
        best_match = "---"
        highest_score = 0
        
        if is_anomaly:
            self.update_signal_characteristics(gated_magnitude)
            if self.signal_detected_cooldown <= 0:
                anomaly_bin = np.argmax(gated_magnitude)
                anomaly_freq = (anomaly_bin / self.MAX_BINS) * (self.SAMPLE_RATE / 2)
                self.label.setText(f">>!! SIGNAL DETECTED at {anomaly_freq:,.0f} Hz !!<<")
                self.label.setStyleSheet("font-family: Consolas; font-size: 14pt; font-weight: bold; color: #FF0000;")
                
                # Play alert sound
                try:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except:
                    pass
                
                pos_val = anomaly_bin
                if self.spectrogram_is_vertical:
                    self.anomaly_highlight_line.setPos(pos_val)
                else:
                    self.anomaly_highlight_line.setPos(pos_val)

                self.anomaly_highlight_line.show()
                self.signal_detected_cooldown = 10
            
            if len(self.profiles) > 0:
                zoom_percent = self.slider_zoom.value() / 100.0
                cutoff_index = max(50, int(self.MAX_BINS * zoom_percent))
                
                for name, profile_data in self.profiles.items():
                    if profile_data.ndim == 1:
                        live_norm_val = np.linalg.norm(gated_magnitude)
                        if live_norm_val > 1e-9:
                            live_signal_norm = gated_magnitude / live_norm_val
                            score = np.dot(live_signal_norm, profile_data)
                            if score > highest_score:
                                highest_score = score
                                best_match = name
                    elif profile_data.ndim == 2:
                        prof_h, prof_w = profile_data.shape
                        if prof_w != cutoff_index: continue

                        live_slice = self.full_spectrogram_data[:prof_h, :prof_w]
                        if live_slice.shape != profile_data.shape: continue

                        live_norm = np.linalg.norm(live_slice)
                        if live_norm > 1e-9:
                            score = np.sum(live_slice * profile_data) / (live_norm * np.linalg.norm(profile_data))
                            if score > highest_score:
                                highest_score = score
                                best_match = name
            
            if highest_score > self.identification_threshold:
                self.lbl_identity.setText(f"ID: {best_match} ({highest_score:.0%})")
            else:
                self.lbl_identity.setText("ID: UNKNOWN SIGNAL")
        else:
            self.lbl_identity.setText("ID: ---")
            self.lbl_snr.setText("SNR: ---")
            self.lbl_bandwidth.setText("BANDWIDTH: --- Hz")
            self.lbl_centroid.setText("CENTROID: --- Hz")
            self.anomaly_highlight_line.hide()
            if self.signal_detected_cooldown > 0:
                self.signal_detected_cooldown -= 1
            else:
                if self.auto_profiling_enabled and len(self.profiling_buffer) < self.profiling_buffer.maxlen:
                    self.label.setText(">> AUTO-PROFILING... <<")
                else:
                    self.label.setText(">> STANDING BY <<")
                self.label.setStyleSheet("font-family: Consolas; font-size: 14pt; font-weight: bold; color: #FF8800;")

    def update_capture_buffer(self):
        duration_seconds = self.slider_capture_duration.value()
        self.lbl_capture_duration.setText(f"CAPTURE DURATION: {duration_seconds}s")
        buffer_size = int(duration_seconds * (self.SAMPLE_RATE / self.INPUT_CHUNK))
        old_contents = list(self.capture_buffer) if self.capture_buffer else []
        self.capture_buffer = deque(old_contents, maxlen=buffer_size)
        
    def toggle_auto_profiling(self):
        self.auto_profiling_enabled = self.btn_auto_profile.isChecked()
        status = "ON" if self.auto_profiling_enabled else "OFF"
        self.btn_auto_profile.setText(f"Auto-Profiling: {status}")
        if not self.auto_profiling_enabled:
            self.noise_profile = np.full(self.MAX_BINS, 1e-9)
            # Reset signal processor calibration if needed, or just stop updating it
        self.label.setText(f">> AUTO-PROFILING {status} <<")
        
    def toggle_scale(self):
        self.use_log_scale = not self.use_log_scale
        self.btn_scale.setText("Mode: LOG SCALE" if self.use_log_scale else "Mode: LINEAR SCALE")
        
    def toggle_orientation(self):
        self.spectrogram_is_vertical = not self.spectrogram_is_vertical
        self.btn_orientation.setText(f"Orientation: {'Vertical' if self.spectrogram_is_vertical else 'Horizontal'}")
        self.first_render = True
        self.render_view()
        self.return_to_live()

    def toggle_triggered_capture(self):
        is_checked = self.btn_triggered_capture.isChecked()
        self.btn_triggered_capture.setText(f"Triggered Capture: {'ON' if is_checked else 'OFF'}")
        self.label.setText(f">> TRIGGERED CAPTURE {'ARMED' if is_checked else 'DISARMED'} <<")

    def update_labels(self):
        self.lbl_gain.setText(f"SIGNAL GAIN: {self.slider_gain.value() / 10:.1f}x")
        self.lbl_floor.setText(f"NOISE CUTOFF: {self.slider_floor.value()}")
        max_khz = 24 * (self.slider_zoom.value() / 100.0)
        self.lbl_zoom.setText(f"FREQ ZOOM: 0 - {max_khz:.1f} kHz")
        self.lbl_stretch.setText(f"VERTICAL STRETCH: {self.slider_stretch.value()}x")
        self.detection_threshold = self.slider_threshold.value() / 2.0
        self.lbl_threshold.setText(f"DETECT THRESHOLD: {self.detection_threshold:.1f}")
        
    def refresh_audio_devices(self):
        self.label.setText(">> SCANNING AUDIO DEVICES... <<")
        # Use ProxyAudioEngine static method
        inputs, outputs = ProxyAudioEngine.get_devices()
        
        self.settings_dock.combo_input.blockSignals(True)
        self.settings_dock.combo_output.blockSignals(True)
        self.settings_dock.combo_input.clear()
        self.settings_dock.combo_output.clear()
        
        if not inputs:
            self.settings_dock.combo_input.addItem("No inputs found")
            self.settings_dock.combo_input.setEnabled(False)
        else:
            self.settings_dock.combo_input.setEnabled(True)
            for dev in inputs:
                self.settings_dock.combo_input.addItem(dev['name'], userData=dev['index'])
                
        if not outputs:
            self.settings_dock.combo_output.addItem("No outputs found")
            self.settings_dock.combo_output.setEnabled(False)
        else:
            self.settings_dock.combo_output.setEnabled(True)
            for dev in outputs:
                self.settings_dock.combo_output.addItem(dev['name'], userData=dev['index'])
                
        self.settings_dock.combo_input.blockSignals(False)
        self.settings_dock.combo_output.blockSignals(False)
        
        if self.engine is None:
            self.restart_audio_engine()
            
        self.label.setText(">> STANDING BY <<")

    def restart_audio_engine(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
            
        input_idx = self.settings_dock.combo_input.currentData()
        output_idx = self.settings_dock.combo_output.currentData()
        
        if input_idx is None:
            return

        self.label.setText(f">> STARTING PROXY ENGINE <<")
        self.first_render = True
        
        self.engine = ProxyAudioEngine(input_device_index=input_idx, output_device_index=output_idx)
        self.engine.audio_data_ready.connect(self.update_data_stream)
        self.engine.error_occurred.connect(lambda msg: self.label.setText(f">> ERROR: {msg} <<"))
        
        # Apply current latency setting
        is_low_latency = self.settings_dock.chk_low_latency.isChecked()
        self.engine.set_latency_mode(is_low_latency)
        
        self.engine.start()
        
        if not self.render_timer.isActive():
            self.render_timer.start(16)
        if not self.identification_timer.isActive():
            self.identification_timer.start(100)

    # Oscilloscope Helper Methods
    def toggle_scope_trigger(self):
        self.scope_trigger_enabled = self.chk_scope_trigger.isChecked()
        
    def update_scope_trigger_level(self):
        self.scope_trigger_level = self.slider_scope_trigger.value() / 100.0
        self.lbl_scope_trigger.setText(f"Trig: {self.scope_trigger_level:.2f}")
        
    def update_scope_timebase(self):
        self.scope_timebase = self.slider_scope_timebase.value() / 100.0
        self.lbl_scope_timebase.setText(f"Zoom: {self.scope_timebase:.2f}x")
        
    def update_scope_gain(self):
        self.scope_gain = self.slider_scope_gain.value() / 10.0
        self.lbl_scope_gain.setText(f"Gain: {self.scope_gain:.1f}x")
        
    def toggle_scope_freeze(self):
        self.scope_freeze = self.btn_scope_freeze.isChecked()
        self.btn_scope_freeze.setText("Resume" if self.scope_freeze else "Freeze")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScienceStation()
    window.show()
    sys.exit(app.exec())