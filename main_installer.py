import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget, QMessageBox
)
from PyQt5.QtCore import QProcess, Qt, QTimer

# --- Configuration ---
# IMPORTANT: This script MUST be run with sudo privileges for archinstall and many post-install commands.
# Example: sudo python3 this_script_name.py

# Command to run archinstall. Assumes 'archinstall' is in PATH.
# If archinstall is not directly in PATH or needs specific invocation, adjust this.
# For example: ["python", "-m", "archinstall.entrypoint"]
ARCHINSTALL_COMMAND = "archinstall"
ARCHINSTALL_ARGS = [] # Add any default arguments for archinstall if needed

# Define post-installation commands
# Each command is a dictionary:
#   "cmd": command name (e.g., "pacman", "echo", "mkdir")
#   "args": list of arguments (e.g., ["-Syyu", "--noconfirm"])
# These commands are run from the live environment after archinstall successfully completes.
# They will run with the same privileges as this script (i.e., root if script is run with sudo).
POST_INSTALL_COMMANDS = [
    {"cmd": "echo", "args": ["--------------------------------------------------"], "description": "Separator"},
    {"cmd": "echo", "args": ["Archinstall finished. Starting post-installation tasks..."], "description": "Post-install Start"},
    {"cmd": "lsblk", "args": [], "description": "List block devices to see new partitions"},
    {"cmd": "echo", "args": ["--- Updating package database on the live environment (if needed) ---"], "description": "Live Env Update Info"},
    # The following commands would typically be run INSIDE the new system via arch-chroot,
    # or archinstall's own custom command execution.
    # For simplicity, these examples run on the live host or assume /mnt/archinstall is the target.
    # If you want to run commands INSIDE the newly installed system, you'd use:
    # {"cmd": "arch-chroot", "args": ["/mnt/archinstall", "pacman", "-Syyu", "--noconfirm"], "description": "Update new system"},
    # {"cmd": "arch-chroot", "args": ["/mnt/archinstall", "pacman", "-S", "neofetch", "git", "--noconfirm", "--needed"], "description": "Install packages in new system"},
    # For this example, let's assume we are just doing some operations on the host/mount point
    # or that archinstall mounts the new system to /mnt/arch (common default for guided installs)
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

class ArchInstallerTerminal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Archinstall Runner & Post-Install Executor")
        self.setGeometry(100, 100, 800, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.output_area = QPlainTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setStyleSheet("background-color: #2E3440; color: #D8DEE9; font-family: 'Monospace';")
        self.layout.addWidget(self.output_area)

        self.start_button = QPushButton("Start Archinstall")
        self.start_button.setStyleSheet("font-size: 16px; padding: 10px;")
        self.start_button.clicked.connect(self.run_archinstall_flow)
        self.layout.addWidget(self.start_button)

        self.archinstall_process = None
        self.post_install_process = None
        self.current_post_command_index = 0

        self.log_message("Welcome to the Archinstall Runner.")
        self.log_message("IMPORTANT: This script and 'archinstall' require root privileges.")
        self.log_message("Please ensure you have run this Python script using 'sudo'.")
        if os.geteuid() != 0:
            self.log_message("WARNING: Script not run as root. 'archinstall' and privileged operations will likely fail.")
            QMessageBox.critical(self, "Permissions Error", "This script must be run with sudo (as root) to execute archinstall and other system commands.")
            # QApplication.instance().quit() # Exit if not root, or let it try and fail
            self.start_button.setEnabled(False)
            self.start_button.setText("Run script with sudo to enable")


    def log_message(self, message):
        self.output_area.appendPlainText(message)
        self.output_area.verticalScrollBar().setValue(self.output_area.verticalScrollBar().maximum())
        QApplication.processEvents() # Ensure GUI updates

    def handle_process_error(self, process_type="Process"):
        if process_type == "archinstall":
            process = self.archinstall_process
        else:
            process = self.post_install_process

        error_map = {
            QProcess.FailedToStart: "Failed to start.",
            QProcess.Crashed: "Crashed.",
            QProcess.Timedout: "Timed out.",
            QProcess.ReadError: "Read error.",
            QProcess.WriteError: "Write error.",
            QProcess.UnknownError: "Unknown error."
        }
        error_string = error_map.get(process.error(), "An unknown error occurred.")
        self.log_message(f"Error with {process_type}: {error_string} (Native error: {process.errorString()})")
        self.start_button.setEnabled(True)

    def run_archinstall_flow(self):
        self.start_button.setEnabled(False)
        self.output_area.clear()
        self.log_message(f"Attempting to start '{ARCHINSTALL_COMMAND}'...")
        self.log_message("Archinstall is interactive and will use the terminal from which this application was launched.")
        self.log_message("Please follow the prompts in that terminal.")
        self.log_message("This GUI will wait for archinstall to complete before running post-install commands.")
        self.log_message("--------------------------------------------------")

        self.archinstall_process = QProcess()
        self.archinstall_process.setProcessChannelMode(QProcess.ForwardedChannels) # Archinstall uses the launching terminal

        # ForwardedChannels means we can't directly capture stdout/stderr here easily.
        # We rely on the finished signal.
        self.archinstall_process.finished.connect(self.on_archinstall_finished)
        self.archinstall_process.errorOccurred.connect(lambda: self.handle_process_error("archinstall"))

        try:
            self.archinstall_process.start(ARCHINSTALL_COMMAND, ARCHINSTALL_ARGS)
            if self.archinstall_process.state() == QProcess.NotRunning:
                 # Sometimes start() might fail immediately if command not found,
                 # and errorOccurred might not fire if it's an issue caught before process launch.
                 QTimer.singleShot(100, self.check_archinstall_start_failure)

        except Exception as e:
            self.log_message(f"Failed to initiate archinstall process: {e}")
            self.start_button.setEnabled(True)

    def check_archinstall_start_failure(self):
        if self.archinstall_process and self.archinstall_process.state() == QProcess.NotRunning and self.archinstall_process.exitStatus() == QProcess.CrashExit:
             # This is a fallback check if errorOccurred didn't catch a very early startup failure
            if self.archinstall_process.error() == QProcess.FailedToStart:
                 self.log_message(f"Error with archinstall: Failed to start. Command: '{ARCHINSTALL_COMMAND}'. Is it installed and in PATH?")
            else:
                 self.log_message(f"Archinstall process failed to start or exited immediately. State: {self.archinstall_process.state()}, Error: {self.archinstall_process.errorString()}")
            self.start_button.setEnabled(True)


    def on_archinstall_finished(self, exit_code, exit_status):
        self.log_message("--------------------------------------------------")
        if exit_status == QProcess.NormalExit and exit_code == 0:
            self.log_message("Archinstall finished successfully (exit code 0).")
            self.current_post_command_index = 0
            self.run_next_post_install_command()
        else:
            self.log_message(f"Archinstall failed or was cancelled.")
            self.log_message(f"  Exit code: {exit_code}")
            self.log_message(f"  Exit status: {'Normal Exit' if exit_status == QProcess.NormalExit else 'Crash Exit'}")
            if self.archinstall_process.error() != QProcess.UnknownError : # if no specific error was emitted, don't double log
                 self.log_message(f"  Error details: {self.archinstall_process.errorString()}")
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
        self.post_install_process.setProcessChannelMode(QProcess.MergedChannels) # Capture output for GUI

        self.post_install_process.readyReadStandardOutput.connect(self.handle_post_install_output)
        self.post_install_process.finished.connect(self.on_post_install_command_finished)
        self.post_install_process.errorOccurred.connect(lambda: self.handle_process_error("Post-install"))

        try:
            self.post_install_process.start(cmd, args)
            if self.post_install_process.state() == QProcess.NotRunning:
                 QTimer.singleShot(100, self.check_post_install_start_failure)
        except Exception as e:
            self.log_message(f"Failed to initiate post-install command '{cmd}': {e}")
            self.start_button.setEnabled(True) # Stop further execution

    def check_post_install_start_failure(self):
        if self.post_install_process and self.post_install_process.state() == QProcess.NotRunning and self.post_install_process.exitStatus() == QProcess.CrashExit:
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
            # Add a small delay before running the next command to allow GUI to update
            QTimer.singleShot(100, self.run_next_post_install_command)
        else:
            self.log_message(f"Command '{cmd_str}' failed.")
            self.log_message(f"  Exit code: {exit_code}")
            self.log_message(f"  Exit status: {'Normal Exit' if exit_status == QProcess.NormalExit else 'Crash Exit'}")
            if self.post_install_process and self.post_install_process.error() != QProcess.UnknownError:
                 self.log_message(f"  Error details: {self.post_install_process.errorString()}")
            self.log_message("Stopping post-installation tasks due to error.")
            self.start_button.setEnabled(True)

    def closeEvent(self, event):
        # Ensure processes are killed if the window is closed
        if self.archinstall_process and self.archinstall_process.state() == QProcess.Running:
            self.archinstall_process.terminate()
            self.archinstall_process.waitForFinished(1000) # Wait a bit
            if self.archinstall_process.state() == QProcess.Running: # If still running, force kill
                self.archinstall_process.kill()
                self.archinstall_process.waitForFinished(1000)


        if self.post_install_process and self.post_install_process.state() == QProcess.Running:
            self.post_install_process.terminate()
            self.post_install_process.waitForFinished(1000)
            if self.post_install_process.state() == QProcess.Running:
                self.post_install_process.kill()
                self.post_install_process.waitForFinished(1000)
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = ArchInstallerTerminal()
    main_window.show()
    sys.exit(app.exec_())
