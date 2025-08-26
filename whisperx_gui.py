"""
whisperx_gui.py
A PyQt5 GUI wrapper to run whisperx transcription (CPU by default).
Features:
 - File selection (audio/video)
 - Model selection
 - Output format selection (txt, srt, json)
 - Diarization toggle (uses HF token if enabled)
 - HF token input (masked)
 - Run in background thread with live log
 - Option to open output folder after finish
"""

import sys
import os
import shlex
import subprocess
import time
from pathlib import Path

from PyQt5 import QtWidgets, QtGui, QtCore

# ====== CONFIG - update to point to python interpreter that has whisperx installed ======
# You can set this to your venv python exe, or just "python" if running in same env
DEFAULT_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "Scripts", "python.exe")
if not os.path.exists(DEFAULT_PYTHON):
    DEFAULT_PYTHON = "python.exe"  # fallback to system python
# ======================================================================================

# Update the venv detection and script paths
DEFAULT_PYTHON = "python.exe"  # default fallback
ACTIVATE_SCRIPT = None
venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")

if os.path.exists(venv_dir):
    DEFAULT_PYTHON = os.path.join(venv_dir, "Scripts", "python.exe")
    ACTIVATE_SCRIPT = os.path.join(venv_dir, "Scripts", "activate.bat")
    os.environ['VIRTUAL_ENV'] = venv_dir
    os.environ['PATH'] = os.path.join(venv_dir, 'Scripts') + os.pathsep + os.environ['PATH']

class WorkerSignals(QtCore.QObject):
    progress = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(int)       # exit code
    error = QtCore.pyqtSignal(str)

class TranscribeWorker(QtCore.QRunnable):
    def __init__(self, cmd_list, cwd=None):
        super().__init__()
        self.cmd_list = [str(x) for x in cmd_list]  # Convert all arguments to strings
        self.cwd = cwd
        self.signals = WorkerSignals()

    @QtCore.pyqtSlot()
    def run(self):
        try:
            env = os.environ.copy()
            
            # Build the command with venv activation if available
            if ACTIVATE_SCRIPT and os.path.exists(ACTIVATE_SCRIPT):
                # Create a batch script that activates venv and runs the command
                temp_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_whisperx.bat")
                with open(temp_script, "w", encoding='utf-8') as f:
                    f.write('@echo off\n')
                    f.write(f'call "{ACTIVATE_SCRIPT}"\n')
                    # Set HF_TOKEN environment variable if present
                    if '--hf_token' in self.cmd_list:
                        token_index = self.cmd_list.index('--hf_token') + 1
                        if token_index < len(self.cmd_list):
                            f.write(f'set HF_TOKEN={self.cmd_list[token_index]}\n')
                    
                    # Build the whisperx command
                    cmd = f'python -m whisperx "{self.cmd_list[3]}" '  # Input file
                    cmd += f'--model {self.cmd_list[5]} '
                    cmd += f'--output_dir "{self.cmd_list[7]}" '
                    cmd += f'--output_format {self.cmd_list[9]} '
                    cmd += f'--compute_type {self.cmd_list[11]} '
                    cmd += f'--device {self.cmd_list[13]}'
                    
                    # Add diarization if enabled
                    if '--diarize' in self.cmd_list:
                        cmd += ' --diarize'
                    
                    f.write(cmd + '\n')

                # Run the batch script
                proc = subprocess.Popen(
                    temp_script,
                    cwd=self.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    shell=True,
                    env=env
                )
            else:
                # Fallback if no venv activation script exists
                proc = subprocess.Popen(
                    self.cmd_list,
                    cwd=self.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    env=env
                )

            # Process output
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    self.signals.progress.emit(line.strip())
            
            # Clean up temporary batch script
            if os.path.exists(ACTIVATE_SCRIPT) and os.path.exists("run_whisperx.bat"):
                try:
                    os.remove("run_whisperx.bat")
                except:
                    pass

            # Emit completion signal with return code
            self.signals.finished.emit(proc.returncode)

        except Exception as e:
            self.signals.error.emit(str(e))
            self.signals.finished.emit(-1)


class WhisperXApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhisperX Transcriber GUI - by kentosama10")
        self.resize(780, 520)
        
        # Set application icon if available
        try:
            icon_path = "whisperx.ico"
            if os.path.exists(icon_path):
                self.setWindowIcon(QtGui.QIcon(icon_path))
            else:
                # Try PNG as fallback
                icon_path = "whisperx_icon.png"
                if os.path.exists(icon_path):
                    self.setWindowIcon(QtGui.QIcon(icon_path))
        except Exception as e:
            # Icon setting failed, continue without icon
            pass
        
        self.threadpool = QtCore.QThreadPool()

        layout = QtWidgets.QVBoxLayout(self)

        # File selection
        file_layout = QtWidgets.QHBoxLayout()
        self.file_input = QtWidgets.QLineEdit()
        self.file_input.setPlaceholderText("Select audio/video file ...")
        file_btn = QtWidgets.QPushButton("Browse")
        file_btn.clicked.connect(self.browse_file)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(file_btn)

        # Model / options
        options_layout = QtWidgets.QGridLayout()
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(["tiny","base","small","medium","large-v2","large-v3"])
        self.model_combo.setCurrentText("medium")

        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.addItems(["txt","srt","json","txt,srt,json"])
        self.format_combo.setCurrentText("txt")

        self.compute_combo = QtWidgets.QComboBox()
        self.compute_combo.addItems(["float32","int8"])  # float32 recommended for CPU precision
        self.compute_combo.setCurrentText("float32")

        self.device_combo = QtWidgets.QComboBox()
        self.device_combo.addItems(["cpu","cuda"])
        self.device_combo.setCurrentText("cpu")

        self.diarize_checkbox = QtWidgets.QCheckBox("Enable diarization (pyannote)")
        self.diarize_checkbox.setChecked(False)

        self.hf_token = QtWidgets.QLineEdit()
        self.hf_token.setPlaceholderText("Hugging Face Token (required for gated diarize)")
        self.hf_token.setEchoMode(QtWidgets.QLineEdit.Password)

        self.timestamped_txt_checkbox = QtWidgets.QCheckBox("Include timestamps in TXT")
        self.timestamped_txt_checkbox.setChecked(False)
        options_layout.addWidget(self.timestamped_txt_checkbox, 3, 0, 1, 2)

        options_layout.addWidget(QtWidgets.QLabel("Model:"),0,0)
        options_layout.addWidget(self.model_combo,0,1)
        options_layout.addWidget(QtWidgets.QLabel("Output format:"),0,2)
        options_layout.addWidget(self.format_combo,0,3)
        options_layout.addWidget(QtWidgets.QLabel("Compute type:"),1,0)
        options_layout.addWidget(self.compute_combo,1,1)
        options_layout.addWidget(QtWidgets.QLabel("Device:"),1,2)
        options_layout.addWidget(self.device_combo,1,3)
        options_layout.addWidget(self.diarize_checkbox,2,0,1,2)
        options_layout.addWidget(QtWidgets.QLabel("HF Token:"),2,2)
        options_layout.addWidget(self.hf_token,2,3)

        # Advanced options
        adv_layout = QtWidgets.QHBoxLayout()
        self.output_dir_input = QtWidgets.QLineEdit()
        self.output_dir_input.setPlaceholderText("Output directory (defaults to ./output)")
        adv_browse = QtWidgets.QPushButton("Output folder")
        adv_browse.clicked.connect(self.browse_output)
        adv_layout.addWidget(self.output_dir_input)
        adv_layout.addWidget(adv_browse)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.run_btn = QtWidgets.QPushButton("Transcribe")
        self.run_btn.clicked.connect(self.run_transcription)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel) 
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(self.cancel_btn)

        # Log area
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)

        layout.addLayout(file_layout)
        layout.addLayout(options_layout)
        layout.addLayout(adv_layout)
        layout.addLayout(btn_layout)
        layout.addWidget(QtWidgets.QLabel("Activity log:"))
        layout.addWidget(self.log)

        # status
        self.status_bar = QtWidgets.QLabel("")
        layout.addWidget(self.status_bar)

        self.current_proc = None

    def browse_file(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select audio or video file",
                                                      str(Path.home()), "Media Files (*.wav *.mp3 *.m4a *.mp4 *.mkv *.flac);;All Files (*)")
        if fn:
            self.file_input.setText(fn)
            # set default output dir near file
            out = str(Path(fn).parent / "transcripts")
            self.output_dir_input.setText(out)

    def browse_output(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output folder", str(Path.home()))
        if d:
            self.output_dir_input.setText(d)

    def append_log(self, text):
        ts = time.strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] {text}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

        

    def run_transcription(self):
        infile = self.file_input.text().strip()
        if not infile or not Path(infile).exists():
            QtWidgets.QMessageBox.warning(self, "No file", "Please choose a valid file to transcribe.")
            return

        outdir = self.output_dir_input.text().strip() or "output"
        os.makedirs(outdir, exist_ok=True)

        model = self.model_combo.currentText()
        outformat = self.format_combo.currentText()
        compute = self.compute_combo.currentText()
        device = self.device_combo.currentText()
        diarize = self.diarize_checkbox.isChecked()
        hf_token = self.hf_token.text().strip()
        timestamped_txt = self.timestamped_txt_checkbox.isChecked()

        # Build command
        cmd = [DEFAULT_PYTHON, "-m", "whisperx", infile,
               "--model", model,
               "--output_dir", outdir,
               "--output_format", outformat,
               "--compute_type", compute,
               "--device", device]
        
        # Ensure JSON output is included if timestamped TXT is requested
        if timestamped_txt and outformat != "all":
            # Change output format to "all" to ensure JSON is generated
            cmd[cmd.index("--output_format") + 1] = "all"
            self.append_log(f"Changed output format to 'all' for timestamped TXT (includes JSON)")

        if diarize:
            if not hf_token:
                QtWidgets.QMessageBox.warning(self, "HF token required", "Diarization requires a Hugging Face token (gated model).")
                return
            cmd += ["--diarize", "--hf_token", hf_token]

        # Show command in log (sanitized)
        cmd_display = " ".join(shlex.quote(x) if x != hf_token else "<HF_TOKEN>" for x in cmd)
        self.append_log("Launching: " + cmd_display)

        # Disable UI while running
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_bar.setText("Running...")

        worker = TranscribeWorker(cmd, cwd=None)
        worker.signals.progress.connect(self.append_log)
        worker.signals.error.connect(lambda e: self.append_log("[ERROR] " + e))
        worker.signals.finished.connect(self._on_finished)
        self.threadpool.start(worker)
        self.current_worker = worker

    def _on_finished(self, exit_code):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if exit_code == 0:
            self.append_log("Process finished successfully.")
            self.status_bar.setText("Finished ✅")
            # If timestamped TXT requested, process JSON output
            if self.timestamped_txt_checkbox.isChecked():
                try:
                    self._create_timestamped_txt()
                except Exception as e:
                    self.append_log(f"[ERROR] Failed to create timestamped TXT: {e}")
            QtWidgets.QMessageBox.information(self, "Done", "Transcription completed. Check the output folder.")
        else:
            self.append_log(f"Process exited with code {exit_code}")
            self.status_bar.setText("Exited with error ❌")
            QtWidgets.QMessageBox.warning(self, "Error", f"Transcription ended with code {exit_code}.\nSee log for details.")

    def cancel(self):
        # we used subprocess in worker; we cannot kill it directly here unless we maintain process handle
        # Option: ask user to kill command window or we can implement a better process handle sharing.
        QtWidgets.QMessageBox.information(self, "Cancel", "Cancel is best-effort. If process is running, close the terminal/kill python process to force stop.")
        self.append_log("Cancel requested (best effort).")

    def _create_timestamped_txt(self):
        """
        Parse the JSON output from WhisperX and create a sentence/segment-level timestamped TXT file.
        Each line: [HH:MM:SS] text
        """
        import json
        from datetime import timedelta
        import glob
        
        infile = self.file_input.text().strip()
        outdir = self.output_dir_input.text().strip() or "output"
        base = os.path.splitext(os.path.basename(infile))[0]
        
        # Try to find the JSON file - WhisperX might create it with different naming
        json_path = os.path.join(outdir, base + ".json")
        if not os.path.exists(json_path):
            # Try alternative naming patterns
            json_patterns = [
                os.path.join(outdir, base + "*.json"),
                os.path.join(outdir, "*.json")
            ]
            json_found = False
            for pattern in json_patterns:
                json_files = glob.glob(pattern)
                if json_files:
                    # Use the first JSON file found
                    json_path = json_files[0]
                    json_found = True
                    self.append_log(f"Found JSON file: {json_path}")
                    break
            
            if not json_found:
                # List all files in output directory for debugging
                all_files = os.listdir(outdir)
                self.append_log(f"Files in output directory: {all_files}")
                raise FileNotFoundError(f"JSON output not found. Expected: {os.path.join(outdir, base + '.json')}")
        
        txt_path = os.path.join(outdir, base + ".timestamped.txt")
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON file {json_path}: {e}")
        
        # WhisperX JSON: expect 'segments' key with list of dicts with 'start', 'end', 'text'
        segments = data.get("segments")
        if not isinstance(segments, list):
            raise ValueError("Invalid JSON: 'segments' key missing or not a list.")
        
        lines = []
        for seg in segments:
            start = seg.get("start")
            text = seg.get("text")
            if start is None or text is None:
                continue  # skip malformed segments
            
            # Format start time as [HH:MM:SS]
            try:
                start_td = timedelta(seconds=float(start))
                start_str = str(start_td)
                if "." in start_str:
                    start_str = start_str.split(".")[0]
                if len(start_str.split(":")) == 2:
                    start_str = "0:" + start_str  # pad hours if needed
                line = f"[{start_str}] {text.strip()}"
                lines.append(line)
            except Exception as e:
                self.append_log(f"Warning: Skipping segment with invalid timestamp: {e}")
                continue  # skip segment if error
        
        if not lines:
            raise ValueError("No valid segments found in JSON.")
        
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        
        self.append_log(f"Timestamped TXT created: {txt_path}")
        self.append_log(f"Processed {len(lines)} segments from JSON")

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = WhisperXApp()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
