import sys
import os
import shutil
import tempfile
import tarfile
import requests
import json
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QTextEdit, QLabel, QMessageBox, QProgressBar)
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
    "yaml-cpp", "python-yaml", "python-pyqt5", "python-jsonschema", # python-pyqt5 is also for calamares modules
    "squashfs-tools", "boost", "extra-cmake-modules",
    "cmake", "make", "ninja", "git", "base-devel" # base-devel for build tools
]

class AutomatorSignals(QObject):
    progress_update = pyqtSignal(str)
    process_finished = pyqtSignal(str)
    process_error = pyqtSignal(str)
    all_done = pyqtSignal(str)
    critical_error = pyqtSignal(str)
    update_progress_bar = pyqtSignal(int)


class CalamaresAutomatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Fully Automated Calamares Installer (Arch Linux)")
        self.setGeometry(100, 100, 900, 700)

        self.calamares_version = "Fetching..."
        self.calamares_download_url = ""
        self.calamares_src_dir_pattern = ""
        self.archive_filename = ""
        self.temp_dir_obj = None # For TemporaryDirectory object
        self.temp_dir_path = ""
        self.extracted_calamares_path = ""
        self.build_path = ""

        self.signals = AutomatorSignals()
        self.signals.progress_update.connect(self.log_message)
        self.signals.process_finished.connect(self.log_message)
        self.signals.process_error.connect(self.handle_process_error)
        self.signals.all_done.connect(self.handle_all_done)
        self.signals.critical_error.connect(self.handle_critical_error)
        self.signals.update_progress_bar.connect(self.set_progress_bar)


        self.qprocess = None
        self.current_stage_index = 0
        self.stages = [] # Will be populated after fetching release info

        self.init_ui()
        self._ensure_sudo() # Check if running with sudo

        # Start fetching release info automatically
        QTimer.singleShot(100, self.start_step_1_fetch_release_info)


    def _ensure_sudo(self):
        if os.geteuid() != 0:
            self.log_message("CRITICAL: This script must be run with sudo privileges.")
            self.log_message("Example: sudo python your_script_name.py")
            QMessageBox.critical(self, "Sudo Required",
                                 "This script requires sudo privileges to automate package installation and run Calamares.\n"
                                 "Please run it again using 'sudo python your_script_name.py'.")
            QTimer.singleShot(100, self.close) # Close app after message
            return False
        return True

    def init_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel("Status: Initializing...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100) # Will represent stages or download %
        layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFontFamily("Monospace")
        self.log_output.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.log_output)

        self.btn_start_automation = QPushButton("Start Full Automation (NOT RECOMMENDED - READ WARNINGS)")
        self.btn_start_automation.setStyleSheet("background-color: #ffc107; color: black;") # Warning color
        self.btn_start_automation.setEnabled(False) # Will be enabled after release info
        self.btn_start_automation.clicked.connect(self.confirm_and_start_automation_stages)
        layout.addWidget(self.btn_start_automation)

        self.setLayout(layout)

    def log_message(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible() # Scroll to bottom
        QApplication.processEvents() # Keep UI responsive

    def set_status(self, message):
        self.status_label.setText(f"Status: {message}")
        self.log_message(f"--- STATUS: {message} ---")

    def set_progress_bar(self, value):
        self.progress_bar.setValue(value)

    def handle_process_error(self, error_message):
        self.log_message(f"ERROR: {error_message}")
        self.set_status(f"Error occurred: {error_message.splitlines()[0] if error_message else 'Unknown'}")
        self.btn_start_automation.setEnabled(True) # Allow retry perhaps, or just indicate failure
        self.btn_start_automation.setText("Automation Failed. Retry?")
        self.btn_start_automation.setStyleSheet("background-color: #dc3545; color: white;") # Error color
        QMessageBox.critical(self, "Automation Error", f"An error occurred:\n{error_message}")

    def handle_critical_error(self, error_message):
        self.log_message(f"CRITICAL ERROR: {error_message}")
        self.set_status(f"Critical Error: {error_message}")
        QMessageBox.critical(self, "Critical Error", error_message)
        self.btn_start_automation.setEnabled(False)
        self.btn_start_automation.setStyleSheet("background-color: #dc3545; color: white;")

    def handle_all_done(self, message):
        self.log_message(message)
        self.set_status(message)
        self.progress_bar.setValue(100)
        self.btn_start_automation.setText("Automation Complete. Run Calamares Again?")
        self.btn_start_automation.setStyleSheet("background-color: #28a745; color: white;") # Success color
        # For "Run Calamares Again", we'd need to ensure it points to the last stage (run calamares)
        # and that paths are still valid. Simpler for now is just to indicate completion.
        self.btn_start_automation.setEnabled(True) # Or False if truly one-shot.
        QMessageBox.information(self, "Automation Complete", message)


    def confirm_and_start_automation_stages(self):
        reply = QMessageBox.warning(self, "Confirm Full Automation",
                                    "This will automatically:\n"
                                    "1. Download Calamares.\n"
                                    "2. Install system dependencies using 'sudo pacman' (NON-INTERACTIVE!).\n"
                                    "3. Compile Calamares.\n"
                                    "4. Run Calamares with 'sudo'.\n\n"
                                    "This process is risky and can affect your system. "
                                    "Ensure you understand the implications and have backed up important data.\n\n"
                                    "Do you want to proceed?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.log_message("User confirmed automation. Starting...")
            self.btn_start_automation.setEnabled(False)
            self.btn_start_automation.setText("Automation in Progress...")
            self.btn_start_automation.setStyleSheet("") # Reset color
            self.progress_bar.setValue(0)
            self.current_stage_index = 0 # Start from the first real stage (dependency install)
            # Assuming step 1 (fetch) is done, stages would start from dependency installation.
            # Let's repopulate stages here just to be sure it uses the latest fetched info.
            self.stages = self._get_automation_stages()
            if self.stages:
                self.run_next_stage()
            else:
                self.handle_critical_error("Failed to define automation stages. Release info might be missing.")
        else:
            self.log_message("Automation cancelled by user.")

    def _get_automation_stages(self):
        if not self.calamares_download_url or not self.temp_dir_path:
             self.log_message("ERROR: Cannot define automation stages. Release info or temp dir not ready.")
             return []
        return [
            {"name": "Install Dependencies", "function": self.run_step_2_install_dependencies, "progress": 15},
            {"name": "Download Calamares", "function": self.run_step_3_download_calamares, "progress": 30},
            {"name": "Extract Calamares", "function": self.run_step_4_extract_calamares, "progress": 45},
            {"name": "Configure Calamares (CMake)", "function": self.run_step_5_cmake_calamares, "progress": 60},
            {"name": "Compile Calamares (Make)", "function": self.run_step_6_make_calamares, "progress": 85},
            {"name": "Run Calamares", "function": self.run_step_7_run_calamares, "progress": 100},
        ]

    def run_next_stage(self):
        if self.current_stage_index < len(self.stages):
            stage = self.stages[self.current_stage_index]
            self.set_status(f"Executing: {stage['name']}")
            self.set_progress_bar(stage['progress'] - 5 if stage['progress'] > 5 else 0) # Show progress before stage
            # Use QTimer to allow UI to update before starting potentially blocking task
            QTimer.singleShot(50, stage["function"])
        else:
            self.signals.all_done.emit("All automation stages completed successfully.")

    def stage_completed_successfully(self):
        stage = self.stages[self.current_stage_index]
        self.set_progress_bar(stage['progress'])
        self.current_stage_index += 1
        self.run_next_stage()


    # --- Automation Stages ---

    def start_step_1_fetch_release_info(self):
        self.set_status("Fetching latest Calamares release information...")
        try:
            response = requests.get(GH_API_LATEST_RELEASE_URL, timeout=15)
            response.raise_for_status()
            release_data = response.json()
            self.calamares_version = release_data.get("tag_name", "N/A")
            assets = release_data.get("assets", [])
            
            # Prefer official tar.gz from assets for cleaner extracted dir name
            source_tarball_asset_url = None
            for asset in assets:
                if asset.get("name", "").endswith(".tar.gz") and GH_REPO_NAME in asset.get("name", ""):
                    if self.calamares_version.lstrip('v') in asset.get("name"):
                        source_tarball_asset_url = asset.get("browser_download_url")
                        self.archive_filename = asset.get("name")
                        # Expected dir name from asset like 'calamares-3.3.14.tar.gz' -> 'calamares-3.3.14'
                        self.calamares_src_dir_pattern = self.archive_filename.replace(".tar.gz", "")
                        break
            
            if not source_tarball_asset_url: # Fallback to main tarball_url
                self.calamares_download_url = release_data.get("tarball_url")
                self.archive_filename = f"{GH_REPO_NAME}-{self.calamares_version}.tar.gz"
                # Dir name from GitHub's general tarball_url is less predictable, often owner-repo-hash
                # We'll determine it after extraction. For now, use a placeholder.
                self.calamares_src_dir_pattern = f"{GH_REPO_NAME}-{self.calamares_version.lstrip('v')}-extracted"
            else:
                self.calamares_download_url = source_tarball_asset_url

            if not self.calamares_download_url:
                raise ValueError("Could not determine download URL from GitHub API response.")

            self.setWindowTitle(f"Automated Calamares {self.calamares_version} Installer")
            self.log_message(f"Latest Calamares version: {self.calamares_version}")
            self.log_message(f"Download URL: {self.calamares_download_url}")
            self.log_message(f"Archive will be named: {self.archive_filename}")

            # Create temporary directory
            self.temp_dir_obj = tempfile.TemporaryDirectory(prefix="calamares_auto_")
            self.temp_dir_path = self.temp_dir_obj.name
            self.log_message(f"Using temporary directory: {self.temp_dir_path}")

            self.set_status(f"Ready to download Calamares {self.calamares_version}. Click 'Start Automation'.")
            self.btn_start_automation.setEnabled(True)
            self.set_progress_bar(5) # Small progress for fetching info

        except requests.exceptions.Timeout:
            self.signals.critical_error.emit("Fetching latest release timed out. Check internet and GitHub API status.")
        except requests.exceptions.RequestException as e:
            self.signals.critical_error.emit(f"GitHub API request failed: {e}")
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            self.signals.critical_error.emit(f"Failed to parse GitHub API response or data missing: {e}")


    def run_step_2_install_dependencies(self):
        self.log_message("Attempting to install dependencies using pacman...")
        self.log_message("This requires sudo and will use --noconfirm.")
        command = ["pacman", "-S", "--noconfirm", "--needed"] + CALAMARES_DEPENDENCIES
        self.run_qprocess_command(command, "Dependency installation")

    def run_step_3_download_calamares(self):
        self.log_message(f"Downloading Calamares {self.calamares_version}...")
        self.set_progress_bar(self.stages[self.current_stage_index]['progress'] - 15) # Intermediate progress

        download_target_path = os.path.join(self.temp_dir_path, self.archive_filename)

        try:
            response = requests.get(self.calamares_download_url, stream=True, timeout=60)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(download_target_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192 * 4): # Larger chunk
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress = int((downloaded_size / total_size) * 15) # Scale to 15% for this stage part
                            self.set_progress_bar(self.stages[self.current_stage_index]['progress'] - 15 + progress)
            
            self.log_message(f"Download complete: {download_target_path}")
            self.stage_completed_successfully()

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
                # Determine the top-level directory after extraction
                members = tar.getmembers()
                if not members:
                    raise tarfile.TarError("Archive is empty.")
                
                # Common pattern: single top-level directory
                # e.g., calamares-3.3.14/ or calamares-calamares-gitcommitsha/
                first_member_parts = members[0].name.split('/', 1)
                extracted_folder_name = first_member_parts[0]
                
                tar.extractall(path=self.temp_dir_path)
                self.extracted_calamares_path = os.path.join(self.temp_dir_path, extracted_folder_name)

                if not os.path.isdir(self.extracted_calamares_path):
                    # Fallback if pattern was complex, try to find a dir starting with "calamares-"
                    found_dir = False
                    for item in os.listdir(self.temp_dir_path):
                        if item.startswith(GH_REPO_NAME + "-") and \
                           os.path.isdir(os.path.join(self.temp_dir_path, item)):
                            self.extracted_calamares_path = os.path.join(self.temp_dir_path, item)
                            extracted_folder_name = item
                            found_dir = True
                            break
                    if not found_dir:
                        raise NotADirectoryError(f"Could not reliably find Calamares source directory after extraction in {self.temp_dir_path}")

            self.log_message(f"Successfully extracted to: {self.extracted_calamares_path}")
            self.build_path = os.path.join(self.extracted_calamares_path, "build")
            os.makedirs(self.build_path, exist_ok=True)
            self.log_message(f"Build directory created: {self.build_path}")
            self.stage_completed_successfully()
        except (tarfile.TarError, NotADirectoryError, FileNotFoundError, Exception) as e:
            self.signals.process_error.emit(f"Extraction failed: {e}")


    def run_step_5_cmake_calamares(self):
        self.log_message("Configuring Calamares with CMake...")
        if not self.build_path or not os.path.isdir(self.build_path):
             self.signals.process_error.emit(f"Build path '{self.build_path}' is not valid for CMake.")
             return
        # Calamares might pick Qt6 if KF6/Qt6 dev files are present.
        # To encourage Qt5, ensure KF5/Qt5 dev packages are primary.
        # Forcing with CMAKE_PREFIX_PATH can be an option if needed, but good deps should suffice.
        # Adding -DQT_VERSION_MAJOR=5 if such an option exists in Calamares CMake could also work.
        # Generally, Calamares tries to be smart or one can use options like -DBUILD_WITH_QT6=OFF
        command = ["cmake", "-S", self.extracted_calamares_path, "-B", self.build_path,
                   "-DCMAKE_BUILD_TYPE=Release",
                   "-DCMAKE_INSTALL_PREFIX=/usr", # Standard prefix, though we run from build dir
                   "-Dವೆಬ್ವಿವೀಕ್ಷಣೆ=ನಿಷ್ಕ್ರಿಯಗೊಳಿಸಲಾಗಿದೆ"] # An example, check Calamares for actual -DWITH_WEBVIEWMODULE=OFF etc.
                   # Or better: -DWITH_PYTHONQT=ON (if Calamares uses this for PyQt modules)
        self.run_qprocess_command(command, "CMake configuration")

    def run_step_6_make_calamares(self):
        self.log_message("Compiling Calamares with make...")
        if not self.build_path or not os.path.isdir(self.build_path):
             self.signals.process_error.emit(f"Build path '{self.build_path}' is not valid for Make.")
             return
        num_cores = os.cpu_count() or 2 # Default to 2 if cpu_count fails
        command = ["make", f"-j{num_cores}"]
        self.run_qprocess_command(command, "Compilation (make)", working_directory=self.build_path)

    def run_step_7_run_calamares(self):
        self.log_message("Attempting to run Calamares...")
        calamares_executable = os.path.join(self.build_path, "bin", "calamares")
        if not os.path.exists(calamares_executable):
            self.signals.process_error.emit(f"Calamares executable not found at {calamares_executable}")
            return
        
        self.log_message(f"Executing: {calamares_executable} (requires sudo, script already has it)")
        self.log_message("--- CALAMARES OUTPUT WILL APPEAR BELOW ---")
        self.log_message("--- CLOSING CALAMARES WILL PROCEED/END SCRIPT ---")
        # Running Calamares directly, it will take over the terminal if it needs one,
        # or open its GUI.
        self.run_qprocess_command([calamares_executable], "Running Calamares")


    def run_qprocess_command(self, command_list, process_name, working_directory=None):
        if self.qprocess and self.qprocess.state() == QProcess.Running:
            self.signals.process_error.emit(f"Another process ({process_name}) is already running.")
            return

        self.qprocess = QProcess(self)
        if working_directory:
            self.qprocess.setWorkingDirectory(working_directory)

        self.qprocess.readyReadStandardOutput.connect(self.handle_stdout)
        self.qprocess.readyReadStandardError.connect(self.handle_stderr)
        # Using finished signal that provides exitCode and exitStatus
        self.qprocess.finished.connect(lambda exit_code, exit_status: self.handle_qprocess_finished(exit_code, exit_status, process_name))

        self.log_message(f"Executing {'in '+working_directory if working_directory else ''}: {' '.join(command_list)}")
        self.qprocess.start(command_list[0], command_list[1:])

        if not self.qprocess.waitForStarted(5000): # Wait 5s for process to start
            self.signals.process_error.emit(f"Failed to start process: {process_name} - {' '.join(command_list)}")


    def handle_stdout(self):
        data = self.qprocess.readAllStandardOutput().data().decode().strip()
        if data: self.log_message(data)

    def handle_stderr(self):
        data = self.qprocess.readAllStandardError().data().decode().strip()
        if data: self.log_message(f"STDERR: {data}")


    def handle_qprocess_finished(self, exit_code, exit_status, process_name):
        self.log_message(f"Process '{process_name}' finished.")
        self.log_message(f"Exit Code: {exit_code}, Exit Status: {exit_status}")

        if exit_code == 0 and exit_status == QProcess.NormalExit:
            self.signals.process_finished.emit(f"{process_name} completed successfully.")
            self.stage_completed_successfully()
        else:
            error_output = self.qprocess.readAllStandardError().data().decode().strip()
            stdout_output = self.qprocess.readAllStandardOutput().data().decode().strip()
            detailed_error = f"{process_name} failed.\nExit Code: {exit_code}\nExit Status: {exit_status}"
            if stdout_output: detailed_error += f"\nSTDOUT:\n{stdout_output}"
            if error_output: detailed_error += f"\nSTDERR:\n{error_output}"
            self.signals.process_error.emit(detailed_error)
        self.qprocess = None # Clear the process

    def closeEvent(self, event):
        # Clean up the temporary directory when the application closes
        if self.temp_dir_obj:
            try:
                self.log_message(f"Cleaning up temporary directory: {self.temp_dir_path}")
                self.temp_dir_obj.cleanup()
                self.log_message("Temporary directory cleaned up.")
            except Exception as e:
                self.log_message(f"Warning: Could not cleanup temporary directory {self.temp_dir_path}: {e}")
        super().closeEvent(event)


if __name__ == '__main__':
    if os.geteuid() != 0:
        print("CRITICAL: This script must be run with sudo privileges for full automation.")
        print("Example: sudo python your_script_name.py")
        # Simple QMessageBox if PyQt5 is available, otherwise just exit.
        try:
            dummy_app_for_msgbox = QApplication.instance() # Check if already exists
            if not dummy_app_for_msgbox:
                dummy_app_for_msgbox = QApplication(sys.argv)
            QMessageBox.critical(None, "Sudo Required",
                                 "This script requires sudo privileges to automate package installation and run Calamares.\n"
                                 "Please run it again using 'sudo python your_script_name.py'.")
        except Exception: # In case PyQt5 is not even installed yet
            pass
        sys.exit(1)

    app = QApplication(sys.argv)
    ex = CalamaresAutomatorApp()
    ex.show()
    sys.exit(app.exec_())
