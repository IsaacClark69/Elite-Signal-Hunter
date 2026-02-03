# Elite Signal Hunter - Field Manual

Welcome, Commander. This document outlines the features and usage of the **Elite Signal Hunter** analysis suite.

## Overview
Elite Signal Hunter is a high-performance desktop application designed to analyze live audio from *Elite Dangerous*. Its purpose is to help you find, identify, and catalog anomalous signals, from the whispers of unknown probes to the hum of a distant star.

---

## Main Interface
The application is divided into two main sections: the **Analysis Panel** on the left and the **Control Panel** on the right.

### Analysis Panel (Left)
This is where you will spend most of your time viewing signal data. It is organized into tabs:

*   **Spectrogram Tab**: The primary view. This is a "waterfall" display showing signal **Frequency** (horizontal axis) vs. **Time** (vertical axis). The newest signals appear at the top and scroll down. The color of a signal indicates its amplitude (loudness), from black (silent) to bright yellow (loud).
    *   **Histogram/LUT**: A graph on the right side of the spectrogram allows you to fine-tune the color contrast and noise floor visibility.
*   **Oscilloscope Tab**: A precision time-domain view showing the raw audio waveform.
    *   **Trigger**: Stabilize repetitive waveforms by setting a voltage threshold.
    *   **Zoom (Timebase)**: Inspect the fine details of a wave cycle.
    *   **Gain**: Amplify weak signals for better visibility.
    *   **Freeze**: Pause the display to analyze a transient event.
*   **Spectrum Analyzer Tab**: A real-time frequency domain plot (Frequency vs. Magnitude).
    *   **Live Trace**: Shows the current frequency content.
    *   **Max Hold**: A dotted line that remembers the highest peak for each frequency, useful for catching fleeting signals.
*   **I/Q Constellation Tab**: A specialized plot for analyzing signal phase and modulation. It maps the In-Phase (I) component against the Quadrature (Q) component.
    *   **Live Feed**: Shows the phase relationship of the strongest frequency in the live audio.
    *   **History Inspection**: Hovering over the Spectrogram will update this plot to show the phase data for that specific moment in time.
*   **Snapshot Browser**: Allows you to review, compare, and **play back** previously saved signal snapshots.
*   **Database Tab**: A raw view of all logged sightings and snapshots in the local database.
*   **Batch Processing**: A tool for analyzing entire folders of `.wav` files for potential signals.
*   **Settings Tab**: Allows you to configure the audio capture device, recording paths, and file formats.

### Control Panel (Right)
This is where you control the application's behavior and manage your findings. The controls are context-sensitive and will change based on which tab you are viewing.

*   **CMDR STATUS**: Shows your current in-game location and ship, updated in real-time by monitoring the *Elite Dangerous* journal files.
*   **MASTER CONTROLS**: Adjusts how the signal is processed and displayed (see below).
*   **SIGNAL CHARACTERISTICS**: Displays real-time metrics like SNR (Signal-to-Noise Ratio), Bandwidth, and Spectral Centroid.
*   **SIGNAL IDENTIFICATION**: Manage your library of saved signal profiles.

---

## Controls Explained

### Spectrogram Controls
*   **SIGNAL GAIN**: Adjusts the visual "contrast" of the signal. Higher values make weaker signals brighter.
*   **NOISE CUTOFF**: Adjusts the "black level." Increase this to filter out low-level background noise and make the spectrogram cleaner.
*   **FREQ ZOOM**: Zooms the horizontal (frequency) axis. Use this to focus on a specific frequency range without losing resolution.
*   **VERTICAL STRETCH**: Magnifies the vertical (time) axis. Higher values make signals appear "taller" and easier to see. Defaults to 8x.
*   **SOURCE**: Selects which audio channel to analyze. "Stereo Mix" is recommended.
*   **Mode: LOG/LINEAR**: Toggles the amplitude scale. LOG (decibel) is best for general listening as it mimics human hearing. LINEAR shows raw signal energy, which can be useful for data analysis.
*   **Auto-Profiling**: When enabled, the application listens for the quietest sounds over a few seconds and automatically creates a noise profile to subtract from the live signal. This is a powerful, automatic noise-canceling feature.
*   **DETECT THRESHOLD**: Sets the sensitivity for the "SIGNAL DETECTED" alert. Lower this to detect weaker signals, but you may get more false positives.
*   **CAPTURE DURATION**: Sets the length of the rolling audio buffer (5-60 seconds) for snapshots.
*   **Save Snapshot**: The primary data integrity tool. See "The Snapshot System" below.
*   **Triggered Capture**: Automatically saves a snapshot when your ship receives a text message (e.g., from a scan).
*   **Start Recording**: Begins a long-form recording session. This is separate from snapshots and can record for minutes or hours.

### Oscilloscope Controls
*   **Trigger Checkbox**: Enables/disables the trigger.
*   **Trig Level**: Sets the amplitude level the signal must cross to start drawing.
*   **Zoom**: Expands the horizontal axis (Time).
*   **Gain**: Expands the vertical axis (Amplitude).
*   **Freeze**: Stops the display from updating.

### I/Q Constellation Controls
*   **Clear Trail**: Clears the fading history trail on the plot.
*   **Trail Length**: Adjusts how many past data points are shown (persistence).
*   **Zoom**: Zooms in/out on the center of the plot to see weaker or stronger signals.
*   **Point Size**: Adjusts the size of the scatter dots for better visibility.
*   **Rotation**: Rotates the entire constellation to align phase patterns.
*   **Show Polar Grid**: Toggles a reference grid with rings and crosshairs.

### Signal Identification
*   **Define from Selection**: Toggles the 2D selection box (the "ROI") on the spectrogram.
*   **Save Profile**: Saves the current signal as a profile. Its behavior changes based on the "Define from Selection" button (see workflow below).
*   **Delete Selected Profile**: Deletes the profile currently highlighted in the list.
*   **Review Selected Profile**: Opens a new, independent window showing the data for the selected profile. You can open multiple windows to compare profiles.

---

## Analysis Workflow

### The "Return to Live" Button
The spectrogram is always recording audio history. You can use the scrollbar at any time to look back at recent events. If you get lost in the history, simply click the **Return to Live** button at the top to instantly snap your view back to the most recent data.

### How to Save and Identify a New Signal
This is the core workflow of the application.

1.  **Find a Signal**: Watch the spectrogram for anything that stands out from the background noise.
2.  **Isolate the Signal (Optional, but Recommended)**:
    *   Click the **Define from Selection** button. A red box will appear on the spectrogram.
    *   The "Save..." button will now read "Save Selection as Profile".
    *   Drag and resize the red box to tightly frame the signal you are interested in. This is crucial for creating a high-quality, low-noise profile.
3.  **Name and Save**:
    *   Type a descriptive name for the signal in the "NEW PROFILE NAME" box (e.g., "Thargoid Probe Scan").
    *   Click "Save Selection as Profile".
4.  **Live Identification**: The application will now automatically compare the live audio against your new profile. When a match is found, the "CURRENT ID" label will update with the profile name and a confidence score.

### The Snapshot System
For maximum scientific rigor, the **Save Snapshot** button creates a complete, verifiable data package in a new folder (e.g., `snapshot_2023-10-28_16-45-00/`). This folder contains:

*   `capture.wav`: The raw audio from the capture buffer.
*   `metadata.json`: A complete record of every application setting at the moment of capture.
*   `context.json`: Your in-game location and ship status.
*   `capture.sha256`: A cryptographic signature to prove the `capture.wav` has not been altered.

This ensures that any discovery you make can be independently verified by others.

### Long Recording
For extended sessions, use the **Start Recording** button.
1.  Go to the **Settings Tab** to choose your save folder, format (WAV/FLAC/OGG), and quality (16/24/32-bit).
2.  Click **Start Recording** in the Master Controls panel.
3.  The button will turn red and show a timer.
4.  Click **Stop Recording** to save the file.

### Batch Processing
The **Batch Analyzer** is a powerful offline processing tool designed to save you hours of manual listening. Instead of sitting in front of the screen watching the live spectrogram, you can record hours of audio (using the "Start Recording" feature) and then let the Batch Analyzer scan those files for you while you're away.

**How to use it:**

1.  **Select a Folder**:
    *   Go to the **Batch Processing** tab.
    *   Click **Select Folder**.
    *   Choose the directory where you saved your `.wav` recordings (e.g., your `EliteSignalHunter` root folder or a specific recording folder).

2.  **Configure Sensitivity**:
    *   **Crucial Step**: The analyzer uses the **DETECT THRESHOLD** slider from the Control Panel (right side).
    *   Before running the batch, go to the Spectrogram tab and adjust the threshold. If you set it too low, the batch analyzer will flag every pop and crackle. If too high, it might miss faint signals.

3.  **Run Analysis**:
    *   Click **Run Batch Analysis**.
    *   The text box will update in real-time as it processes each file.

4.  **Review Results**:
    *   The output will list timestamps where "interesting" things happened.
    *   You can then open that specific file in an external player (or the app's snapshot player if you convert it) and jump straight to those timestamps to investigate.

**Technical Note:** The analyzer currently only supports **48kHz .wav files** (the default format of the application). If you have files in other formats or sample rates, they will be skipped to ensure accuracy.

### Automated Anomaly Detection
The application now features an active "Watchdog" system that monitors the audio stream for you.

**How to use it:**

1.  **Calibration (Crucial)**:
    *   When you first launch the app (or change ships/supercruise state), click the **Auto-Profiling** button.
    *   Let it run for a few seconds to build a statistical model of your background noise.
    *   Turn it off. The app is now "calibrated" to your current environment.

2.  **Set Threshold**:
    *   Adjust the **DETECT THRESHOLD** slider.
    *   **3.0 - 5.0**: High sensitivity. Good for quiet environments.
    *   **10.0+**: Low sensitivity. Only triggers on very loud, distinct events (like a Discovery Scanner honk).

3.  **Alerts**:
    *   When an anomaly is detected, a **red dashed line** will appear on the spectrogram at the frequency of the event.
    *   A system sound will play to alert you if you are tabbed out.
    *   The "SIGNAL DETECTED" warning will flash in the top header.

Happy hunting, Commander. o7
