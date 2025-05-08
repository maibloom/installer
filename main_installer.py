import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget, QMessageBox
)
from PyQt5.QtCore import QProcess, Qt, QTimer

# --- Configuration ---
# IMPORTANT: This script MUST be run with sudo privileges.
# Example: sudo python3 this_script_name.py

# The actual command parts to run archinstall.
# If archinstall is a direct command: ["archinstall"]
# If it needs python -m: ["python", "-m", "archinstall.entrypoint"]
ACTUAL_ARCHINSTALL_CMD_PARTS = ["archinstall"]

# Any default arguments you always want to pass to archinstall
# e.g., ["--config", "/path/to/my_archinstall_config.json"]
USER_ARCHINSTALL_ARGS = []


# Define post-installation commands (same as before)
# These commands are run from the live environment after archinstall successfully completes.
# They will run with the same privileges as this script (i.e., root if script is run with sudo).
POST_INSTALL_COMMANDS = [
    {"cmd": "echo", "args": ["--------------------------------------------------"], "description": "Separator"},
    {"cmd": "echo", "args": ["Archinstall (via Konsole) finished. Starting post-installation tasks..."], "description": "Post-install Start"},
    {"cmd": "lsblk", "args": [], "description": "List block devices to see new partitions"},
    {"cmd": "echo", "args": ["--- Example post-install commands (run from live environment) ---"], "description": "Example Commands Info"},
    {"cmd": "pacman", "args": ["-Syu", "--noconfirm", "--needed"], "description": "Update live environment packages"},
    {"cmd": "echo", "args": ["Installing some common packages ON THE LIVE ENVIRONMENT (e.g., neofetch, git)..."], "description": "Install common packages (Live Env)"},
    {"cmd": "pacman", "args": ["-S", "neofetch", "git", "base-devel", "--noconfirm", "--needed"], "description": "Install neofetch, git, base-devel (Live Env)"},
    {"cmd": "echo", "args": ["--- Running neofetch on the live environment ---"], "description": "Neofetch (Live Env)"},
    {"cmd": "neofetch", "args": ["--config", "none"], "description": "Run neofetch (Live Env)"},
    {"cmd": "echo", "args": ["--- Creating a test directory and file (ensure /mnt/arch is your target mount point if applicable) ---"], "description": "Test Dir Info"},
    {"cmd": "mkdir", "args": ["-p", "/mnt/archinstall_post_script_output"], "description": "Create test directory"},
    {"cmd": "touch", "args": ["/mnt/archinstall_post_script_output/script_test_file.txt"], "description": "Create test file"},
    {"cmd": "ls", "args": ["-l", "/mnt/archinstall_post_script_output"], "description": "List test directory"},
    {"cmd": "echo", "args": ["--------------------------------------------------"], "description": "Separator"},
    {"cmd": "echo", "args": ["All post-installation tasks configured in this script are complete."], "description": "Post-install End"},
    {"cmd": "echo", "args": ["You may need to chroot into your new system for further configuration:"], "description": "Chroot Info"},
    {"cmd": "echo", "args": ["e.g., arch-chroot /mnt/arch (or your specific mount point)"], "description": "Chroot Example"},
]

class ArchInstallerKonsoleRunner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Archinstall (via Konsole) & Post-Install Executor")
        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.output_area = QPlainTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setStyleSheet("background-color: #2E3440; color: #D8DEE9; font-family: 'Monospace';")
        self.layout.addWidget(self.output_area)

        self.start_button = QPushButton("Start Archinstall in Konsole")
        self.start_button.setStyleSheet("font-size: 16px; padding: 10px;")
        self.start_button.clicked.connect(self.run_archinstall_in_konsole)
        self.layout.addWidget(self.start_button)

        self.konsole_process = None # For the konsole process itself
        self.post_install_process = None # For post-install commands
        self.current_post_command_index = 0

        self.log_message("Welcome to the Archinstall (via Konsole) Runner.")
        self.log_message("IMPORTANT: This script requires root privileges to launch Konsole (running archinstall as root) and for post-install commands.")
        self.log_message("Please ensure you have run this Python script using 'sudo'.")

        if os.geteuid() != 0:
            self.log_message("WARNING: Script not run as root. Operations will likely fail.")
            QMessageBox.critical(self, "Permissions Error", "This script must be run with sudo (as root).")
            self.start_button.setEnabled(False)
            self.start_button.setText("Run script with sudo to enable")
        else:
            # Check if konsole is available
            konsole_check_process = QProcess()
            konsole_check_process.start("which", ["konsole"])
            konsole_check_process.waitForFinished(1000)
            if konsole_check_process.exitCode() != 0:
                self.log_message("WARNING: 'konsole' command not found. Please install Konsole (KDE's terminal emulator).")
                QMessageBox.warning(self, "Konsole Not Found", "'konsole' could not be found. This script requires Konsole to run archinstall.")
                self.start_button.setEnabled(False)
                self.start_button.setText("Konsole not found")


    def log_message(self, message):
        self.output_area.appendPlainText(message)
        self.output_area.verticalScrollBar().setValue(self.output_area.verticalScrollBar().maximum())
        QApplication.processEvents()

    def handle_process_error(self, process_type="Process"):
        process = self.konsole_process if process_type == "Konsole (archinstall)" else self.post_install_process
        if not process: return

        error_map = {
            QProcess.FailedToStart: "Failed to start.", QProcess.Crashed: "Crashed.",
            QProcess.Timedout: "Timed out.", QProcess.ReadError: "Read error.",
            QProcess.WriteError: "Write error.", QProcess.UnknownError: "Unknown error."
        }
        error_string = error_map.get(process.error(), "An unknown error occurred.")
        self.log_message(f"Error with {process_type}: {error_string} (Native error: {process.errorString()})")
        self.start_button.setEnabled(True)

    def run_archinstall_in_konsole(self):
        self.start_button.setEnabled(False)
        self.output_area.clear()

        konsole_executable = "konsole"
        # Construct the command that konsole's -e option will execute
        command_to_run_in_konsole = ACTUAL_ARCHINSTALL_CMD_PARTS + USER_ARCHINSTALL_ARGS
        args_for_konsole_process = ["-e"] + command_to_run_in_konsole

        self.log_message(f"Attempting to start '{' '.join(command_to_run_in_konsole)}' inside a new Konsole window...")
        self.log_message("Please interact with archinstall in the new Konsole window that appears.")
        self.log_message("This GUI will wait for Konsole to close before proceeding with post-install commands.")
        self.log_message("--------------------------------------------------")

        self.konsole_process = QProcess()
        # We don't need to forward channels; Konsole handles its own TTY.
        # We can optionally capture Konsole's own stdout/stderr if needed, but it's usually minimal.
        self.konsole_process.readyReadStandardOutput.connect(self.handle_konsole_own_output)
        self.konsole_process.readyReadStandardError.connect(self.handle_konsole_own_output)

        self.konsole_process.finished.connect(self.on_konsole_finished)
        self.konsole_process.errorOccurred.connect(lambda: self.handle_process_error("Konsole (archinstall)"))

        try:
            self.konsole_process.start(konsole_executable, args_for_konsole_process)
            if self.konsole_process.state() == QProcess.NotRunning:
                 QTimer.singleShot(100, self.check_konsole_start_failure)
        except Exception as e:
            self.log_message(f"Failed to initiate Konsole process: {e}")
            self.start_button.setEnabled(True)

    def check_konsole_start_failure(self):
        if self.konsole_process and self.konsole_process.state() == QProcess.NotRunning:
            # This condition might indicate 'konsole -e' failed before even running the command,
            # or the command inside konsole was not found and konsole exited immediately.
            if self.konsole_process.error() == QProcess.FailedToStart:
                 self.log_message(f"Error: Failed to start Konsole. Is 'konsole' installed and in your PATH?")
            else:
                 command_str = ' '.join(ACTUAL_ARCHINSTALL_CMD_PARTS + USER_ARCHINSTALL_ARGS)
                 self.log_message(f"Konsole process failed to start properly or exited immediately. "
                                  f"Command given to Konsole: '{command_str}'. "
                                  f"Konsole error: {self.konsole_process.errorString()}")
            self.start_button.setEnabled(True)


    def handle_konsole_own_output(self):
        # This handles any output from the konsole process itself, not archinstall's main output.
        if self.konsole_process:
            out_data = self.konsole_process.readAllStandardOutput().data().decode(errors='ignore').strip()
            err_data = self.konsole_process.readAllStandardError().data().decode(errors='ignore').strip()
            if out_data:
                self.log_message(f"[Konsole STDOUT]: {out_data}")
            if err_data:
                self.log_message(f"[Konsole STDERR]: {err_data}")


    def on_konsole_finished(self, exit_code, exit_status):
        self.log_message("--------------------------------------------------")
        command_str = ' '.join(ACTUAL_ARCHINSTALL_CMD_PARTS + USER_ARCHINSTALL_ARGS)
        if exit_status == QProcess.NormalExit and exit_code == 0:
            self.log_message(f"Konsole (running '{command_str}') finished successfully (exit code 0).")
            self.log_message("Assuming archinstall completed successfully.")
            self.current_post_command_index = 0
            self.run_next_post_install_command()
        else:
            self.log_message(f"Konsole (running '{command_str}') exited with an error or was cancelled.")
            self.log_message(f"  Konsole Exit code: {exit_code}")
            self.log_message(f"  Konsole Exit status: {'Normal Exit' if exit_status == QProcess.NormalExit else 'Crash Exit'}")
            if self.konsole_process and self.konsole_process.errorString():
                 self.log_message(f"  Konsole Process Error: {self.konsole_process.errorString()}")
            self.log_message("This likely indicates archinstall failed or the Konsole window was closed prematurely.")
            self.log_message("Post-install commands will NOT be executed.")
            self.start_button.setEnabled(True)

    def run_next_post_install_command(self):
        if self.current_post_command_index >= len(POST_INSTALL_COMMANDS):
            self.log_message("--------------------------------------------------")
            self.log_message("All post-install commands executed.")
            self.start_button.setEnabled(True)
            return

        command_dict = POST_INSTALL_COMMANDS[self.current_post_command_index]
        cmd = command_dict["cmd"]
        args = command_dict["args"]
        description = command_dict.get("description", cmd)

        self.log_message(f"\nRunning post-install command ({description}): {cmd} {' '.join(args)}")

        self.post_install_process = QProcess()
        self.post_install_process.setProcessChannelMode(QProcess.MergedChannels)
        self.post_install_process.readyReadStandardOutput.connect(self.handle_post_install_output)
        self.post_install_process.finished.connect(self.on_post_install_command_finished)
        self.post_install_process.errorOccurred.connect(lambda: self.handle_process_error("Post-install"))

        try:
            self.post_install_process.start(cmd, args)
            if self.post_install_process.state() == QProcess.NotRunning: # Fallback check
                 QTimer.singleShot(100, self.check_post_install_start_failure)
        except Exception as e:
            self.log_message(f"Failed to initiate post-install command '{cmd}': {e}")
            self.start_button.setEnabled(True)

    def check_post_install_start_failure(self):
        if self.post_install_process and self.post_install_process.state() == QProcess.NotRunning:
            if self.post_install_process.error() == QProcess.FailedToStart:
                command_dict = POST_INSTALL_COMMANDS[self.current_post_command_index]
                cmd = command_dict["cmd"]
                self.log_message(f"Error with post-install command: '{cmd}' - Failed to start. Is it installed and in PATH?")
            else:
                self.log_message(f"Post-install command failed to start or exited immediately. State: {self.post_install_process.state()}, Error: {self.post_install_process.errorString()}")
            self.start_button.setEnabled(True)


    def handle_post_install_output(self):
        if self.post_install_process:
            data = self.post_install_process.readAllStandardOutput().data().decode(errors='ignore').strip()
            if data:
                self.output_area.appendPlainText(data)
                self.output_area.verticalScrollBar().setValue(self.output_area.verticalScrollBar().maximum())

    def on_post_install_command_finished(self, exit_code, exit_status):
        command_dict = POST_INSTALL_COMMANDS[self.current_post_command_index]
        cmd_str = f"{command_dict['cmd']} {' '.join(command_dict['args'])}"

        if exit_status == QProcess.NormalExit and exit_code == 0:
            self.log_message(f"Command '{cmd_str}' finished successfully.")
            self.current_post_command_index += 1
            QTimer.singleShot(100, self.run_next_post_install_command)
        else:
            self.log_message(f"Command '{cmd_str}' failed.")
            self.log_message(f"  Exit code: {exit_code}")
            self.log_message(f"  Exit status: {'Normal Exit' if exit_status == QProcess.NormalExit else 'Crash Exit'}")
            if self.post_install_process and self.post_install_process.errorString():
                 self.log_message(f"  Error details: {self.post_install_process.errorString()}")
            self.log_message("Stopping post-installation tasks due to error.")
            self.start_button.setEnabled(True)

    def closeEvent(self, event):
        # Ensure processes are killed if the window is closed
        if self.konsole_process and self.konsole_process.state() == QProcess.Running:
            self.log_message("Attempting to terminate Konsole process...")
            self.konsole_process.terminate() # Ask Konsole to close
            if not self.konsole_process.waitForFinished(2000): # Wait up to 2 seconds
                self.log_message("Konsole did not terminate gracefully, killing...")
                self.konsole_process.kill()
                self.konsole_process.waitForFinished(1000)

        if self.post_install_process and self.post_install_process.state() == QProcess.Running:
            self.log_message("Attempting to terminate post-install process...")
            self.post_install_process.terminate()
            if not self.post_install_process.waitForFinished(1000):
                self.post_install_process.kill()
                self.post_install_process.waitForFinished(1000)
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = ArchInstallerKonsoleRunner()
    main_window.show()
    sys.exit(app.exec_())
