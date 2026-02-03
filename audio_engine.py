import numpy as np
import pyaudiowpatch as pyaudio
from PyQt6.QtCore import QThread, pyqtSignal
import collections
import time
import soundfile as sf
from datetime import datetime
import os
import queue
import threading

class ProxyAudioEngine(QThread):
    """
    A "Man-in-the-Middle" audio engine.
    Captures from an Input Device -> Forwards to Output Device (High Priority).
    Offloads Analysis/Spectrogram to a separate thread (Low Priority).
    """
    audio_data_ready = pyqtSignal(np.ndarray) # Signal for the UI/Spectrogram
    error_occurred = pyqtSignal(str)

    def __init__(self, input_device_index=None, output_device_index=None, parent=None):
        super().__init__(parent)
        self.running = True
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index
        
        # Audio State
        self.p = None
        self.input_stream = None
        self.output_stream = None
        
        # Configuration
        self.input_rate = 48000 
        self.output_rate = 48000 
        self.channels = 2
        self.buffer_size = 4096 
        self.low_latency_mode = False
        
        # Black Box (Shadowplay)
        self.black_box_buffer = collections.deque(maxlen=60) 
        self.black_box_seconds = 60
        
        # Resampling State
        self.resample_ratio = 1.0
        
        # Threading / Decoupling
        self.analysis_queue = queue.Queue(maxsize=20) 
        self.analysis_thread = None

    def set_latency_mode(self, low_latency: bool):
        self.low_latency_mode = low_latency
        if low_latency:
            self.buffer_size = 512 # ~10ms
        else:
            self.buffer_size = 4096 # ~85ms
            
        if self.isRunning():
            self.restart()

    def restart(self):
        self.stop()
        self.start()

    def run(self):
        self.running = True
        self.p = pyaudio.PyAudio()
        
        # Start the analysis worker thread
        self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self.analysis_thread.start()
        
        try:
            # 1. Setup Input Device
            if self.input_device_index is None:
                wasapi_info = self.p.get_host_api_info_by_type(pyaudio.paWASAPI)
                default_speakers = self.p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                for loopback in self.p.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        self.input_device_index = loopback["index"]
                        break
            
            input_info = self.p.get_device_info_by_index(self.input_device_index)
            self.input_rate = int(input_info["defaultSampleRate"])
            self.channels = input_info["maxInputChannels"]
            
            # 2. Setup Output Device
            if self.output_device_index is None:
                self.output_device_index = self.p.get_default_output_device_info()["index"]
                
            output_info = self.p.get_device_info_by_index(self.output_device_index)
            self.output_rate = int(output_info["defaultSampleRate"])
            
            self.resample_ratio = self.output_rate / self.input_rate
            
            print(f"Proxy Engine Started:")
            print(f"  Input: {input_info['name']} @ {self.input_rate}Hz")
            print(f"  Output: {output_info['name']} @ {self.output_rate}Hz")
            print(f"  Buffer: {self.buffer_size}")

            # 3. Open Streams (Int16 for stability)
            self.input_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.input_rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.buffer_size
            )
            
            self.output_stream = self.p.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.output_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=int(self.buffer_size * self.resample_ratio)
            )
            
            # 4. Critical Audio Loop
            while self.running:
                try:
                    # A. Read (Blocking)
                    raw_data = self.input_stream.read(self.buffer_size, exception_on_overflow=False)
                    
                    # B. Write (Pass-through) - PRIORITY
                    if self.resample_ratio == 1.0:
                        self.output_stream.write(raw_data, exception_on_underflow=False)
                    else:
                        # FAST LINEAR INTERPOLATION RESAMPLING
                        # Convert bytes to Int16 numpy array
                        audio_chunk_int16 = np.frombuffer(raw_data, dtype=np.int16)
                        
                        # Calculate new length
                        input_len = len(audio_chunk_int16)
                        output_len = int(input_len * self.resample_ratio)
                        
                        # Ensure we align with channels
                        if self.channels > 1:
                            # Reshape to (Samples, Channels)
                            # We must ensure input_len is divisible by channels
                            num_frames = input_len // self.channels
                            input_reshaped = audio_chunk_int16.reshape(num_frames, self.channels)
                            
                            num_output_frames = int(num_frames * self.resample_ratio)
                            
                            # Create time indices
                            x_old = np.linspace(0, num_frames - 1, num_frames)
                            x_new = np.linspace(0, num_frames - 1, num_output_frames)
                            
                            # Interpolate each channel
                            output_reshaped = np.zeros((num_output_frames, self.channels), dtype=np.float32)
                            for ch in range(self.channels):
                                output_reshaped[:, ch] = np.interp(x_new, x_old, input_reshaped[:, ch])
                                
                            # Flatten
                            output_data_float = output_reshaped.flatten()
                        else:
                            # Mono
                            x_old = np.linspace(0, input_len - 1, input_len)
                            x_new = np.linspace(0, input_len - 1, output_len)
                            output_data_float = np.interp(x_new, x_old, audio_chunk_int16)
                            
                        # Clip and Cast
                        # Fast clipping in-place
                        np.clip(output_data_float, -32768, 32767, out=output_data_float)
                        output_data_int16 = output_data_float.astype(np.int16)
                            
                        self.output_stream.write(output_data_int16.tobytes(), exception_on_underflow=False)

                    # C. Offload Analysis (Non-Blocking)
                    if not self.analysis_queue.full():
                        self.analysis_queue.put(raw_data)
                        
                except Exception as e:
                    print(f"Stream Loop Error: {e}")
                    continue

        except Exception as e:
            self.error_occurred.emit(f"Critical Engine Failure: {e}")
        finally:
            self._cleanup()

    def _analysis_loop(self):
        """
        Secondary thread that handles heavy math, UI updates, and recording.
        Does not block the audio stream.
        """
        while self.running:
            try:
                # Get data with timeout to allow checking self.running
                raw_data = self.analysis_queue.get(timeout=0.5)
                
                # Convert to Float32 for Analysis
                audio_chunk_int16 = np.frombuffer(raw_data, dtype=np.int16)
                audio_chunk_float = audio_chunk_int16.astype(np.float32) / 32768.0
                
                # Reshape
                if self.channels > 1:
                    analysis_chunk = audio_chunk_float.reshape(-1, self.channels)
                else:
                    analysis_chunk = audio_chunk_float
                
                # Update UI
                self.audio_data_ready.emit(analysis_chunk)
                
                # Update Black Box
                self.black_box_buffer.append(analysis_chunk)
                
                # Maintain buffer size
                chunks_per_second = self.input_rate / self.buffer_size
                max_chunks = int(self.black_box_seconds * chunks_per_second)
                if len(self.black_box_buffer) > max_chunks:
                    self.black_box_buffer.popleft()
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Analysis Error: {e}")

    def save_black_box(self, save_dir):
        if not self.black_box_buffer:
            return None
            
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f"blackbox_{timestamp}.wav"
        filepath = os.path.join(save_dir, filename)
        
        try:
            # Combine all chunks
            full_audio = np.concatenate(list(self.black_box_buffer))
            sf.write(filepath, full_audio, self.input_rate)
            return filepath
        except Exception as e:
            print(f"Failed to save black box: {e}")
            return None

    def _cleanup(self):
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
        if self.p:
            self.p.terminate()

    def stop(self):
        self.running = False
        self.wait()
        if self.analysis_thread:
            self.analysis_thread.join(timeout=1.0)

    @staticmethod
    def get_devices():
        inputs = []
        outputs = []
        p = pyaudio.PyAudio()
        try:
            for device in p.get_loopback_device_info_generator():
                inputs.append({
                    "name": device['name'],
                    "index": device['index'],
                    "rate": int(device['defaultSampleRate'])
                })
            info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
            num_devices = info.get('deviceCount')
            for i in range(num_devices):
                dev = p.get_device_info_by_host_api_device_index(info['index'], i)
                if dev.get('maxOutputChannels') > 0:
                    outputs.append({
                        "name": dev['name'],
                        "index": dev['index'],
                        "rate": int(dev['defaultSampleRate'])
                    })
        except Exception as e:
            print(f"Device enumeration error: {e}")
        finally:
            p.terminate()
        return inputs, outputs