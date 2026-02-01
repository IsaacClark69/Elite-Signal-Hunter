# Elite Signal Hunter - Field Manual

Welcome, Commander. This document outlines the features and usage of the Elite Signal Hunter analysis suite.

## Overview

Elite Signal Hunter is a high-performance desktop application designed to analyze live audio from Elite Dangerous. Its purpose is to help you find, identify, and catalog anomalous signals, from the whispers of unknown probes to the hum of a distant star.

---

## Main Interface

The application is divided into two main sections: the **Analysis Panel** on the left and the **Control Panel** on the right.

### Analysis Panel (Left)

This is where you will spend most of your time viewing signal data. It is organized into tabs:

*   **Spectrogram Tab:** The primary view. This is a "waterfall" display showing signal **Frequency** (horizontal axis) vs. **Time** (vertical axis). The newest signals appear at the top and scroll down. The color of a signal indicates its amplitude (loudness), from black (silent) to bright yellow (loud).
*   **Oscilloscope Tab:** A classic time-domain view that shows the raw audio waveform. This is useful for seeing the actual shape of a sound wave, identifying clicks, pops, or other transient events.
*   **Settings Tab:** Allows you to configure the audio capture device.

### Control Panel (Right)

This is where you control the application's behavior and manage your findings.

*   **CMDR STATUS:** Shows your current in-game location and ship, updated in real-time by monitoring the Elite Dangerous journal files.
*   **MASTER CONTROLS:** Adjusts how the signal is processed and displayed.
*   **SIGNAL IDENTIFICATION:** Manage your library of saved signal profiles.

---

## Controls Explained

### Master Controls

*   **SIGNAL GAIN:** Adjusts the visual "contrast" of the signal. Higher values make weaker signals brighter.
*   **NOISE CUTOFF:** Adjusts the "black level." Increase this to filter out low-level background noise and make the spectrogram cleaner.
*   **FREQ ZOOM:** Zooms the horizontal (frequency) axis. Use this to focus on a specific frequency range without losing resolution.
*   **VERTICAL STRETCH:** Magnifies the vertical (time) axis. Higher values make signals appear "taller" and easier to see. **Defaults to 8x.**
*   **SOURCE:** Selects which audio channel to analyze. "Stereo Mix" is recommended.
*   **Mode: LOG/LINEAR:** Toggles the amplitude scale. **LOG** (decibel) is best for general listening as it mimics human hearing. **LINEAR** shows raw signal energy, which can be useful for data analysis.
*   **Auto-Profiling:** When enabled, the application listens for the quietest sounds over a few seconds and automatically creates a noise profile to subtract from the live signal. This is a powerful, automatic noise-canceling feature.
*   **DETECT THRESHOLD:** Sets the sensitivity for the "SIGNAL DETECTED" alert. Lower this to detect weaker signals, but you may get more false positives.
*   **CAPTURE DURATION:** Sets the length of the rolling audio buffer (5-60 seconds).
*   **Save Snapshot:** The primary data integrity tool. See "The Snapshot System" below.

### Signal Identification

*   **Define from Selection:** Toggles the 2D selection box (the "ROI") on the spectrogram.
*   **Save Profile:** Saves the current signal as a profile. Its behavior changes based on the "Define from Selection" button (see workflow below).
*   **Delete Selected Profile:** Deletes the profile currently highlighted in the list.
*   **Review Selected Profile:** Opens a new, independent window showing the data for the selected profile. You can open multiple windows to compare profiles.

---

## Analysis Workflow

### The "Return to Live" Button

The spectrogram is always recording audio history. You can use the scrollbar at any time to look back at recent events. If you get lost in the history, simply click the **Return to Live** button at the top to instantly snap your view back to the most recent data.

### How to Save and Identify a New Signal

This is the core workflow of the application.

1.  **Find a Signal:** Watch the spectrogram for anything that stands out from the background noise.
2.  **Isolate the Signal (Optional, but Recommended):**
    *   Click the **Define from Selection** button. A red box will appear on the spectrogram.
    *   The "Save..." button will now read **"Save Selection as Profile"**.
    *   Drag and resize the red box to tightly frame the signal you are interested in. This is crucial for creating a high-quality, low-noise profile.
3.  **Name and Save:**
    *   Type a descriptive name for the signal in the "NEW PROFILE NAME" box (e.g., "Thargoid Probe Scan").
    *   Click **"Save Selection as Profile"**.
4.  **Live Identification:** The application will now automatically compare the live audio against your new profile. When a match is found, the "CURRENT ID" label will update with the profile name and a confidence score.

### The Snapshot System

For maximum scientific rigor, the **Save Snapshot** button creates a complete, verifiable data package in a new folder (e.g., `snapshot_2023-10-28_16-45-00/`). This folder contains:
*   `capture.wav`: The raw audio from the capture buffer.
*   `metadata.json`: A complete record of every application setting at the moment of capture.
*   `context.json`: Your in-game location and ship status.
*   `capture.sha256`: A cryptographic signature to prove the `capture.wav` has not been altered.

This ensures that any discovery you make can be independently verified by others. Happy hunting, Commander.
o7