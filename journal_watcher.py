import os
import time
import json
from PyQt6.QtCore import QThread, pyqtSignal

class JournalWatcher(QThread):
    """
    A QThread that monitors the Elite Dangerous journal directory for the latest
    log file and emits signals when relevant new events are found.
    """
    status_update = pyqtSignal(dict)  # Emits a dictionary with status info

    def __init__(self, parent=None):
        super().__init__(parent)
        self.running = True
        self.journal_path = self._find_journal_path()
        self.latest_log_file = None
        self.current_status = {
            "StarSystem": "Unknown",
            "Ship": "Unknown"
        }

    def _find_journal_path(self):
        """Finds the path to the Elite Dangerous journal directory."""
        user_profile = os.path.expanduser("~")
        # Standard path for Elite Dangerous journals
        return os.path.join(user_profile, "Saved Games", "Frontier Developments", "Elite Dangerous")

    def _find_latest_log(self):
        """Finds the most recently modified .log file in the journal directory."""
        if not os.path.isdir(self.journal_path):
            print(f"Journal directory not found at: {self.journal_path}")
            return None

        log_files = [f for f in os.listdir(self.journal_path) if f.startswith("Journal.") and f.endswith(".log")]
        if not log_files:
            return None

        latest_file = max(log_files, key=lambda f: os.path.getmtime(os.path.join(self.journal_path, f)))
        return os.path.join(self.journal_path, latest_file)

    def run(self):
        """
        Main loop for the watcher thread. It checks for new log files and
        tails the latest one for new entries.
        """
        print("Journal Watcher thread started.")
        
        # Initial check to populate status from the latest log
        self.latest_log_file = self._find_latest_log()
        if self.latest_log_file:
            self._parse_existing_log(self.latest_log_file)

        # Main watch loop
        while self.running:
            latest_file = self._find_latest_log()

            if not latest_file:
                time.sleep(10) # Wait a while if no logs are found
                continue

            # If a new log file has been created (e.g., game restarted)
            if self.latest_log_file != latest_file:
                self.latest_log_file = latest_file
                self._parse_existing_log(self.latest_log_file)

            # Tail the latest log file for new entries
            try:
                with open(self.latest_log_file, 'r', encoding='utf-8') as f:
                    f.seek(0, 2) # Go to the end of the file
                    while self.running:
                        line = f.readline()
                        if not line:
                            time.sleep(1) # Wait for new lines
                            # Check if the file has changed, indicating a new game session
                            if self.latest_log_file != self._find_latest_log():
                                break
                            continue
                        
                        self._process_line(line)

            except Exception as e:
                print(f"Error reading journal file: {e}")
                time.sleep(5)

    def _parse_existing_log(self, file_path):
        """Parses an entire log file from the beginning to find the last known status."""
        print(f"Parsing existing log: {os.path.basename(file_path)}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    self._process_line(line, emit_signal=False) # Process without emitting for each line
            # Emit a single update after parsing the whole file
            self.status_update.emit(self.current_status)
        except Exception as e:
            print(f"Error parsing existing log {file_path}: {e}")

    def _process_line(self, line, emit_signal=True):
        """Processes a single JSON line from the log."""
        try:
            log_entry = json.loads(line)
            event = log_entry.get("event")
            
            updated = False
            if event in ["Location", "FSDJump", "LoadGame"]:
                if "StarSystem" in log_entry:
                    self.current_status["StarSystem"] = log_entry["StarSystem"]
                    updated = True
                if "Ship" in log_entry:
                    self.current_status["Ship"] = log_entry["Ship"]
                    updated = True
            
            if updated and emit_signal:
                self.status_update.emit(self.current_status.copy())

        except (json.JSONDecodeError, TypeError):
            pass # Ignore lines that aren't valid JSON

    def stop(self):
        self.running = False
        print("Journal Watcher thread stopping.")
        self.wait(2000)