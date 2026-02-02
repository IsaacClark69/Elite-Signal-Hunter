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
