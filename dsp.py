import numpy as np

def calculate_characteristics(gated_magnitude, noise_profile, sample_rate, fft_size):
    """
    Calculates key characteristics for a given signal magnitude array.

    Args:
        gated_magnitude (np.ndarray): The signal magnitude after noise subtraction.
        noise_profile (np.ndarray): The calculated noise profile.
        sample_rate (int): The sample rate of the audio.
        fft_size (int): The size of the FFT window.

    Returns:
        dict: A dictionary containing SNR, bandwidth, spectral centroid, and peak frequency.
    """
    freqs = np.fft.rfftfreq(fft_size, 1 / sample_rate)
    
    # Calculate SNR
    signal_power = np.sum(gated_magnitude**2)
    noise_power = np.sum(noise_profile**2)
    snr = 10 * np.log10(signal_power / noise_power) if noise_power > 0 else float('inf')

    # Calculate Bandwidth
    signal_bins = np.where(gated_magnitude > 0)[0]
    if len(signal_bins) > 1:
        bandwidth = freqs[signal_bins[-1]] - freqs[signal_bins[0]]
    else:
        bandwidth = 0

    # Calculate Spectral Centroid
    if np.sum(gated_magnitude) > 0:
        centroid = np.sum(freqs * gated_magnitude) / np.sum(gated_magnitude)
    else:
        centroid = 0
        
    # Find Peak Frequency
    peak_freq = freqs[np.argmax(gated_magnitude)] if gated_magnitude.any() else 0

    return {
        "snr": snr,
        "bandwidth": bandwidth,
        "spectral_centroid": centroid,
        "peak_frequency": peak_freq
    }

class SignalProcessor:
    def __init__(self, fft_size):
        self.num_bins = fft_size // 2 + 1
        self.noise_mean = np.zeros(self.num_bins)
        self.noise_std = np.ones(self.num_bins)
        self.is_calibrated = False
        
        # Tuning Parameters
        self.spectral_floor = 0.1 # Keep 10% of the original signal floor to prevent "musical noise"
        self.oversubtraction = 1.5 # Subtract 1.5x the noise profile to push it down

    def capture_noise_profile(self, magnitude_buffer):
        """
        Analyzes a buffer of magnitude arrays to create a statistical noise profile.
        
        Args:
            magnitude_buffer (list or np.ndarray): A collection of frequency magnitude frames.
                                                   Shape should be (num_frames, num_bins).
        """
        data = np.array(magnitude_buffer)
        if data.ndim != 2 or data.shape[1] != self.num_bins:
            return

        self.noise_mean = np.mean(data, axis=0)
        self.noise_std = np.std(data, axis=0)
        
        # Prevent division by zero and ensure a minimum floor for std dev
        self.noise_std = np.maximum(self.noise_std, 1e-9)
        self.is_calibrated = True

    def apply_spectral_gate(self, magnitude_data):
        """
        Subtracts the calibrated noise profile from the incoming signal using a Soft Knee approach.
        
        Args:
            magnitude_data (np.ndarray): The live frequency magnitude frame.
            
        Returns:
            np.ndarray: The gated magnitude.
        """
        if not self.is_calibrated:
            return magnitude_data
        
        # Soft Spectral Subtraction
        # 1. Calculate the subtraction amount (Oversubtraction)
        subtraction_amount = self.noise_mean * self.oversubtraction
        
        # 2. Perform subtraction
        subtracted = magnitude_data - subtraction_amount
        
        # 3. Apply Spectral Floor (instead of hard clipping to 0)
        # This keeps a tiny bit of the original signal structure, preventing the "black void" effect
        # where faint details get swallowed.
        floor = magnitude_data * self.spectral_floor
        
        return np.maximum(subtracted, floor)

    def detect_anomaly(self, magnitude_data, threshold=3.0):
        """
        Detects if the signal deviates significantly from the noise profile using Z-Score.
        
        Args:
            magnitude_data (np.ndarray): The live frequency magnitude frame.
            threshold (float): The Z-Score threshold for detection (default: 3.0).
            
        Returns:
            bool: True if an anomaly is detected.
        """
        if not self.is_calibrated:
            return False

        # Calculate Z-Score: (X - Mean) / Std
        z_scores = (magnitude_data - self.noise_mean) / self.noise_std
        
        # Check if any frequency bin exceeds the threshold
        max_z = np.max(z_scores)
        
        return max_z > threshold
