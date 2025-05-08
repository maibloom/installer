import sys
import os
import shutil
import tempfile
import tarfile
import requests
import json
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit,
                             QLabel, QMessageBox, QProgressBar)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QProcess, QTimer

# GitHub repository details
GH_REPO_OWNER = "calamares"
GH_REPO_NAME = "calamares"
GH_API_LATEST_RELEASE_URL = f"https://api.github.com/repos/{GH_REPO_OWNER}/{GH_REPO_NAME}/releases/latest"

# Arch Linux Dependencies for Calamares (Qt5 build)
CALAMARES_DEPENDENCIES = [
    "qt5-base", "qt5-svg", "qt5-xmlpatterns",
    "kconfig5", "kcoreaddons5", "ki18n5", "kiconthemes5", "kio5",
    "plasma-framework5", "solid5", "polkit-qt5", "kpmcore",
    "yaml-cpp", "python-yaml", "python-pyqt5", "python-jsonschema",
    "squashfs-tools", "boost", "extra-cmake-modules",
    "cmake", "make", "ninja", "git", "base-devel" # base-devel for general build tools
]

class AutomatorSignals(QObject):
    progress_update = pyqtSignal(str)
    process_finished = pyqtSignal(str) # Emits message on successful stage completion
    process_error = pyqtSignal(str)    # Emits error message for a stage
    all_done = pyqtSignal(str)         # Emits message when all stages are done
    critical_error = pyqtSignal(str)   # Emits message for fatal errors before stages start
    update_progress_bar = pyqtSignal(int) # Emits percentage for progress bar


class CalamaresAutomatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Fully Automated Calamares Installer (Arch Linux)")
        self.setGeometry(100, 100, 900, 700)

        self.calamares_version = "Fetching..."
        self.calamares_download_url = ""
        self.archive_filename = ""
        self.temp_dir_obj = None
        self.temp_dir_path = ""
        self.extracted_calamares_path = ""
        self.build_path = ""

        self.signals = AutomatorSignals()
        self.signals.progress_update.connect(self.log_message)
        self.signals.process_finished.connect(self.log_message) # Also log success message
        self.signals.process_error.connect(self.handle_process_error)
        self.signals.all_done.connect(self.handle_all_done)
        self.signals.critical_error.connect(self.handle_critical_error)
        self.signals.update_progress_bar.connect(self.set_progress_bar_value)

        self.qprocess = None
        self.current_stage_index = 0
        self.automation_stages = []

        self.init_ui()

        if not self._ensure_sudo():
            # _ensure_sudo will schedule app close if not sudo
            return

        # Automatically start the first step (fetching release info)
        # QTimer allows the constructor and UI setup to complete before starting operations
        QTimer.singleShot(100, self.start_step_1_fetch_release_info)

    def _ensure_sudo(self):
        if os.geteuid() != 0:
            self.log_message("CRITICAL: This script must be run with sudo privileges.")
            self.log_message("Example: sudo python your_script_name.py")
            QMessageBox.critical(self, "Sudo Required",
                                 "This script requires sudo privileges for full automation.\n"
                                 "Please run it again using 'sudo python your_script_name.py'.")
            QTimer.singleShot(100, self.close) # Schedule app to close
            return False
        self.log_message("Sudo privileges confirmed.")
        return True

    def init_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel("Status: Initializing and checking permissions...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100) # Represents overall progress
        layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFontFamily("Monospace")
        self.log_output.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.log_output)

        self.setLayout(layout)

    def log_message(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible()
        QApplication.processEvents()

    def set_status_message(self, message):
        self.status_label.setText(f"Status: {message}")
        self.log_message(f"--- STATUS: {message} ---")

    def set_progress_bar_value(self, value):
        self.progress_bar.setValue(value)

    def handle_process_error(self, error_message):
        self.log_message(f"ERROR ENCOUNTERED: {error_message}")
        self.set_status_message(f"Automation Failed: {error_message.splitlines()[0] if error_message else 'Unknown error'}")
        QMessageBox.critical(self, "Automation Error", f"An error occurred during automation:\n{error_message}")
        # Consider if app should close or allow retry (retry is complex for state)

    def handle_critical_error(self, error_message):
        self.log_message(f"CRITICAL FAILURE: {error_message}")
        self.set_status_message(f"Critical Failure: {error_message}")
        QMessageBox.critical(self, "Critical Failure", error_message)
        QTimer.singleShot(100, self.close) # Close app on critical failure

    def handle_all_done(self, message):
        self.log_message(message)
        self.set_status_message(message)
        self.set_progress_bar_value(100)
        QMessageBox.information(self, "Automation Complete", message)
        # Optionally, could offer to run Calamares again or clean up and exit.
        # For now, it just completes.

    def _define_automation_stages(self):
        if not self.calamares_download_url or not self.temp_dir_path:
             self.signals.critical_error.emit("Cannot define automation stages. Release info or temp dir not ready.")
             return False
        self.automation_stages = [
            {"name": "Install Dependencies", "function": self.run_step_2_install_dependencies, "progress_target": 15},
            {"name": "Download Calamares", "function": self.run_step_3_download_calamares, "progress_target": 30},
            {"name": "Extract Calamares", "function": self.run_step_4_extract_calamares, "progress_target": 45},
            {"name": "Configure Calamares (CMake)", "function": self.run_step_5_cmake_calamares, "progress_target": 60},
            {"name": "Compile Calamares (Make)", "function": self.run_step_6_make_calamares, "progress_target": 85},
            {"name": "Run Calamares", "function": self.run_step_7_run_calamares, "progress_target": 100},
        ]
        return True

    def run_next_automation_stage(self):
        if self.current_stage_index < len(self.automation_stages):
            stage = self.automation_stages[self.current_stage_index]
            self.set_status_message(f"Executing: {stage['name']}")
            # Set progress to just before the target, or current if it's the first one
            prev_progress = self.automation_stages[self.current_stage_index-1]['progress_target'] if self.current_stage_index > 0 else 0
            self.set_progress_bar_value(prev_progress + 1) # Show activity

            QTimer.singleShot(50, stage["function"]) # Allow UI to update
        else:
            self.signals.all_done.emit("All automation stages successfully completed.")

    def current_stage_completed(self):
        if self.current_stage_index < len(self.automation_stages):
            stage = self.automation_stages[self.current_stage_index]
            self.set_progress_bar_value(stage['progress_target'])
            self.log_message(f"Stage '{stage['name']}' completed successfully.")
            self.current_stage_index += 1
            self.run_next_automation_stage()
        # If it was the last stage, run_next_automation_stage will trigger all_done.

    # --- Automation Stages ---

    def start_step_1_fetch_release_info(self):
        self.set_status_message("Fetching latest Calamares release information...")
        self.set_progress_bar_value(1)
        try:
            response = requests.get(GH_API_LATEST_RELEASE_URL, timeout=20)
            response.raise_for_status()
            release_data = response.json()
            self.calamares_version = release_data.get("tag_name", "N/A")

            assets = release_data.get("assets", [])
            source_tarball_asset_url = None
            for asset in assets:
                if asset.get("name", "").endswith(".tar.gz") and GH_REPO_NAME in asset.get("name", ""):
                    if self.calamares_version.lstrip('v') in asset.get("name"):
                        source_tarball_asset_url = asset.get("browser_download_url")
                        self.archive_filename = asset.get("name")
                        break
            
            if not source_tarball_asset_url: # Fallback to main tarball_url if specific asset not found
                self.calamares_download_url = release_data.get("tarball_url")
                self.archive_filename = f"{GH_REPO_NAME}-{self.calamares_version}.tar.gz" # Guess filename
            else:
                self.calamares_download_url = source_tarball_asset_url

            if not self.calamares_download_url or self.calamares_version == "N/A":
                raise ValueError("Could not determine download URL or version from GitHub API response.")

            self.setWindowTitle(f"Automated Calamares {self.calamares_version} Installer")
            self.log_message(f"Latest Calamares version: {self.calamares_version}")
            self.log_message(f"Download URL: {self.calamares_download_url}")
            self.log_message(f"Archive will be named: {self.archive_filename}")

            self.temp_dir_obj = tempfile.TemporaryDirectory(prefix="calamares_auto_")
            self.temp_dir_path = self.temp_dir_obj.name
            self.log_message(f"Using temporary directory: {self.temp_dir_path}")
            self.set_progress_bar_value(5)

            if self._define_automation_stages():
                self.set_status_message(f"Calamares {self.calamares_version} info fetched. Starting automation...")
                self.run_next_automation_stage() # Automatically start the sequence
            else:
                # _define_automation_stages would have emitted critical_error
                pass

        except requests.exceptions.Timeout:
            self.signals.critical_error.emit("Fetching release info timed out. Check internet.")
        except requests.exceptions.RequestException as e:
            self.signals.critical_error.emit(f"GitHub API request failed: {e}")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            self.signals.critical_error.emit(f"Failed to parse GitHub API response: {e}")

    def run_step_2_install_dependencies(self):
        self.log_message("Installing dependencies using pacman (--noconfirm --needed)...")
        # The pacman command does not perform a full system update (like -Syu).
        # It installs specified packages if not present or outdated, and their dependencies.
        command = ["pacman", "-S", "--noconfirm", "--needed"] + CALAMARES_DEPENDENCIES
        self.run_qprocess_command(command, "Dependency Installation")

    def run_step_3_download_calamares(self):
        self.log_message(f"Downloading Calamares {self.calamares_version}...")
        # Progress for this download stage is handled within this method
        initial_progress = self.automation_stages[self.current_stage_index-1]['progress_target'] if self.current_stage_index > 0 else 5
        target_progress_span = self.automation_stages[self.current_stage_index]['progress_target'] - initial_progress
        
        download_target_path = os.path.join(self.temp_dir_path, self.archive_filename)

        try:
            response = requests.get(self.calamares_download_url, stream=True, timeout=120) # Increased timeout
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            self.log_message(f"Total download size: {total_size / (1024*1024):.2f} MB")

            with open(download_target_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192 * 8): # 64KB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            # Calculate percentage of this specific download stage
                            download_stage_percent = (downloaded_size / total_size)
                            # Update overall progress bar based on this stage's contribution
                            current_overall_progress = initial_progress + int(download_stage_percent * target_progress_span)
                            self.set_progress_bar_value(current_overall_progress)
            
            self.set_progress_bar_value(initial_progress + target_progress_span) # Ensure it hits target
            self.log_message(f"Download complete: {download_target_path}")
            self.current_stage_completed()

        except requests.exceptions.Timeout:
            self.signals.process_error.emit(f"Download timed out for {self.calamares_download_url}.")
        except requests.exceptions.RequestException as e:
            self.signals.process_error.emit(f"Download failed: {e}")
        except Exception as e:
            self.signals.process_error.emit(f"An unexpected error occurred during download: {e}")


    def run_step_4_extract_calamares(self):
        self.log_message("Extracting Calamares source...")
        archive_path = os.path.join(self.temp_dir_path, self.archive_filename)
        try:
            with tarfile.open(archive_path, "r:*") as tar:
                members = tar.getmembers()
                if not members: raise tarfile.TarError("Archive is empty.")
                
                # Determine top-level directory (GitHub archives usually have one)
                # e.g. calamares-calamares-aabbccdd or calamares-3.3.14
                top_level_dir_name = members[0].name.split('/')[0]
                tar.extractall(path=self.temp_dir_path)
                self.extracted_calamares_path = os.path.join(self.temp_dir_path, top_level_dir_name)

                if not os.path.isdir(self.extracted_calamares_path):
                    # Attempt a more robust find if simple extraction naming was off
                    found_dir = False
                    for item in os.listdir(self.temp_dir_path):
                        # Look for a directory that starts with "calamares-" and seems plausible
                        if item.startswith(GH_REPO_NAME + "-") and \
                           os.path.isdir(os.path.join(self.temp_dir_path, item)):
                            self.extracted_calamares_path = os.path.join(self.temp_dir_path, item)
                            self.log_message(f"Adjusted extracted path to: {self.extracted_calamares_path}")
                            found_dir = True
                            break
                    if not found_dir:
                        raise NotADirectoryError(f"Could not reliably find Calamares source directory in {self.temp_dir_path} after extraction.")

            self.log_message(f"Extracted to: {self.extracted_calamares_path}")
            self.build_path = os.path.join(self.extracted_calamares_path, "build")
            os.makedirs(self.build_path, exist_ok=True)
            self.log_message(f"Build directory: {self.build_path}")
            self.current_stage_completed()
        except (tarfile.TarError, NotADirectoryError, FileNotFoundError, Exception) as e:
            self.signals.process_error.emit(f"Extraction failed: {e}")

    def run_step_5_cmake_calamares(self):
        self.log_message("Configuring Calamares with CMake...")
        if not self.build_path or not os.path.isdir(self.build_path) or not self.extracted_calamares_path:
             self.signals.process_error.emit(f"Build or source path invalid for CMake. Build: '{self.build_path}', Source: '{self.extracted_calamares_path}'")
             return

        command = ["cmake", "-S", self.extracted_calamares_path, "-B", self.build_path,
                   "-DCMAKE_BUILD_TYPE=Release",
                   "-DCMAKE_INSTALL_PREFIX=/usr", # Standard, though not installing globally here
                   # Example to disable a module if problematic, check Calamares CMake options for valid ones
                   # "-DWITH_WEBVIEWMODULE=OFF"
                   # "-Dವೆಬ್ವಿವೀಕ್ಷಣೆ=ನಿಷ್ಕ್ರಿಯಗೊಳಿಸಲಾಗಿದೆ" was illustrative, actual flags are like the above.
                  ]
        self.run_qprocess_command(command, "CMake Configuration")

    def run_step_6_make_calamares(self):
        self.log_message("Compiling Calamares with make...")
        if not self.build_path or not os.path.isdir(self.build_path):
             self.signals.process_error.emit(f"Build path '{self.build_path}' invalid for Make.")
             return
        num_cores = os.cpu_count() or 2
        command = ["make", f"-j{num_cores}"]
        self.run_qprocess_command(command, "Compilation (make)", working_directory=self.build_path)

    def run_step_7_run_calamares(self):
        self.log_message("Attempting to run compiled Calamares...")
        calamares_executable = os.path.join(self.build_path, "bin", "calamares")
        if not os.path.exists(calamares_executable):
            calamares_executable = os.path.join(self.build_path, "calamares") # Some builds might place it directly in build
            if not os.path.exists(calamares_executable):
                self.signals.process_error.emit(f"Calamares executable not found at common locations in '{self.build_path}'.")
                return
        
        self.log_message(f"Executing: {calamares_executable}")
        self.log_message("--- CALAMARES GUI SHOULD APPEAR. CLOSE IT TO FINISH THIS SCRIPT. ---")
        # This script is already running as sudo, so Calamares will inherit sudo.
        self.run_qprocess_command([calamares_executable], "Running Calamares")

    def run_qprocess_command(self, command_list, process_name, working_directory=None):
        if self.qprocess and self.qprocess.state() == QProcess.Running:
            self.signals.process_error.emit(f"Cannot start '{process_name}': Another process is already running.")
            return

        self.qprocess = QProcess(self)
        if working_directory:
            self.qprocess.setWorkingDirectory(working_directory)
        
        # Merge stdout and stderr for simpler logging in some cases if desired
        # self.qprocess.setProcessChannelMode(QProcess.MergedChannels)
        self.qprocess.readyReadStandardOutput.connect(self.handle_stdout)
        self.qprocess.readyReadStandardError.connect(self.handle_stderr)
        self.qprocess.finished.connect(lambda exit_code, exit_status: self.handle_qprocess_finished(exit_code, exit_status, process_name))

        self.log_message(f"Starting process '{process_name}': {' '.join(command_list)}")
        self.qprocess.start(command_list[0], command_list[1:])

        if not self.qprocess.waitForStarted(7000): # 7s timeout to start
            self.signals.process_error.emit(f"Failed to start process '{process_name}': Command {' '.join(command_list)}")
            self.qprocess = None # Ensure it's cleared

    def handle_stdout(self):
        if not self.qprocess: return
        data = self.qprocess.readAllStandardOutput().data().decode(errors='ignore').strip()
        if data: self.log_message(data)

    def handle_stderr(self):
        if not self.qprocess: return
        data = self.qprocess.readAllStandardError().data().decode(errors='ignore').strip()
        if data: self.log_message(f"STDERR: {data}")

    def handle_qprocess_finished(self, exit_code, exit_status, process_name):
        # Ensure all output is read before declaring finished
        QTimer.singleShot(50, self.handle_stdout) # Read any trailing stdout
        QTimer.singleShot(50, self.handle_stderr) # Read any trailing stderr

        def final_processing():
            if not self.qprocess: return # Already handled or race condition

            self.log_message(f"Process '{process_name}' finished with Exit Code: {exit_code}, Exit Status: {exit_status}.")
            
            if exit_code == 0 and exit_status == QProcess.NormalExit:
                # Special handling for "Run Calamares" stage - it "completes" when Calamares GUI is closed.
                if process_name == "Running Calamares":
                    self.signals.all_done.emit("Calamares application was closed. Automation sequence complete.")
                else:
                    self.current_stage_completed()
            else:
                error_output = self.qprocess.readAllStandardError().data().decode(errors='ignore').strip()
                stdout_output = self.qprocess.readAllStandardOutput().data().decode(errors='ignore').strip()
                detailed_error = (f"Process '{process_name}' failed.\n"
                                  f"Exit Code: {exit_code}, Exit Status: {exit_status}\n")
                if stdout_output: detailed_error += f"STDOUT:\n{stdout_output}\n"
                if error_output: detailed_error += f"STDERR:\n{error_output}\n"
                self.signals.process_error.emit(detailed_error)
            
            self.qprocess.deleteLater() # Schedule QProcess object for deletion
            self.qprocess = None
        
        # Delay final processing slightly to ensure all output signals are processed.
        QTimer.singleShot(100, final_processing)


    def closeEvent(self, event):
        self.log_message("Close event received. Cleaning up...")
        if self.qprocess and self.qprocess.state() == QProcess.Running:
            self.log_message("A process is still running. Attempting to terminate...")
            self.qprocess.terminate() # Try to terminate gracefully
            if not self.qprocess.waitForFinished(3000): # Wait 3s
                self.log_message("Process did not terminate gracefully, killing.")
                self.qprocess.kill()
                self.qprocess.waitForFinished(1000) # Wait for kill

        if self.temp_dir_obj:
            try:
                self.log_message(f"Cleaning up temporary directory: {self.temp_dir_path}")
                self.temp_dir_obj.cleanup()
                self.log_message("Temporary directory cleanup successful.")
            except Exception as e:
                self.log_message(f"Warning: Could not cleanup temporary directory {self.temp_dir_path}: {e}")
        super().closeEvent(event)


if __name__ == '__main__':
    # Initial sudo check before even starting QApplication for critical message
    if os.geteuid() != 0:
        print("CRITICAL ERROR: This script MUST be run with sudo privileges for full automation.")
        print("Example: sudo python your_script_name.py")
        # Attempt a simple GUI message if PyQt5 is available, otherwise exit.
        try:
            # Minimal app to show message box without full app init if not sudo
            if 'PyQt5' not in sys.modules:
                # If we haven't imported it, we can't guarantee QMessageBox works
                # This check is mostly for environments where PyQt5 might not be present AT ALL
                # but if the script reaches here, it means python found the PyQt5 import at the top.
                 pass
            temp_app = QApplication.instance() or QApplication(sys.argv)
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("Sudo Required")
            msg_box.setText("This script requires sudo privileges for full automation.\n"
                            "Please run it again using 'sudo python your_script_name.py'.")
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec_()
        except Exception as e:
            print(f"Could not show GUI error message (PyQt5 might not be fully available yet): {e}")
        sys.exit(1)

    app = QApplication(sys.argv)
    ex = CalamaresAutomatorApp()
    ex.show()
    sys.exit(app.exec_())

