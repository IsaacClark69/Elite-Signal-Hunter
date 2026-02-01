import numpy as np
import pyaudiowpatch as pyaudio
from PyQt6.QtCore import QThread, pyqtSignal

class AudioEngine(QThread):
    """
    A more advanced audio engine capable of finding all loopback devices
    and targeting specific applications.
    """
    audio_data_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)

    def __init__(self, device_index=None, parent=None):
        super().__init__(parent)
        self.running = True
        self.chunk_size = 1024
        self.device_index = device_index
        self.stream = None
        self.p = None # Will be initialized in run()

    @staticmethod
    def get_available_devices():
        """
        Static method to get a list of all available WASAPI loopback devices.
        This uses the library's intended features to correctly list all sources.
        """
        devices = []
        with pyaudio.PyAudio() as p:
            try:
                # Find the default output device's name
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                default_speaker_name = default_speakers['name']

                # Find the loopback device corresponding to the default speakers
                default_loopback = None
                for device in p.get_loopback_device_info_generator():
                    if default_speaker_name in device['name']:
                        default_loopback = device
                        break
                
                if default_loopback:
                    devices.append({
                        "name": f"Default: {default_loopback['name']}",
                        "index": None, # Use None to signify the default device
                        "channels": default_loopback['maxInputChannels'],
                        "rate": int(default_loopback['defaultSampleRate'])
                    })

                # Add all other loopback devices, including applications
                for device in p.get_loopback_device_info_generator():
                    # Avoid duplicating the default device if it appears in the list
                    if not default_loopback or device['name'] != default_loopback['name']:
                        devices.append({
                            "name": device['name'],
                            "index": device['index'],
                            "channels": device['maxInputChannels'],
                            "rate": int(device['defaultSampleRate'])
                        })
            except Exception as e:
                print(f"Error getting audio devices: {e}")
                if not devices:
                    devices.append({"name": "No devices found", "index": -1, "channels": 0, "rate": 0})
        return devices

    def run(self):
        """
        The main loop. Opens a stream on the selected device and captures audio.
        """
        self.p = pyaudio.PyAudio()
        try:
            target_device = self._get_target_device()
            if not target_device or target_device.get("index") == -1:
                self.error_occurred.emit("Could not find a valid audio device.")
                self.p.terminate()
                return

            self.stream = self.p.open(
                format=pyaudio.paFloat32,
                channels=target_device["maxInputChannels"],
                rate=int(target_device["defaultSampleRate"]),
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=target_device["index"]
            )

            print(f"Audio engine started on: {target_device['name']}")

            while self.running:
                raw_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                audio_array = np.frombuffer(raw_data, dtype=np.float32)

                if target_device["maxInputChannels"] > 1:
                     audio_array = audio_array.reshape(-1, target_device["maxInputChannels"])

                self.audio_data_ready.emit(audio_array)

        except Exception as e:
            self.error_occurred.emit(f"Audio Engine Error: {e}")
            print(f"Critical Engine Failure: {e}")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
            if self.p:
                self.p.terminate()
            print("Audio engine terminated.")

    def _get_target_device(self):
        """Finds the device info for the requested device index."""
        if self.device_index is None:
            # This is the correct logic to find the default loopback device
            with pyaudio.PyAudio() as p:
                try:
                    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                    for loopback in p.get_loopback_device_info_generator():
                        if default_speakers["name"] in loopback["name"]:
                            return loopback
                    # If not found, return None
                    self.error_occurred.emit("Default loopback device could not be found.")
                    return None
                except OSError as e:
                    self.error_occurred.emit(f"Error finding default device: {e}")
                    return None
        else:
            return self.p.get_device_info_by_index(self.device_index)

    def stop(self):
        self.running = False
        self.wait(2000)