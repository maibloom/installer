#!/usr/bin/env python3
import sys
import os
import subprocess
import shlex
import time # For demonstration purposes or minor delays

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextEdit, 
                             QGroupBox, QMessageBox, QScrollArea)
from PyQt5.QtCore import pyqtSignal, QObject, QThread, Qt, QMetaObject
from PyQt5.QtGui import QFont

# --- Configuration (Same as your previous CLI script) ---
DEFAULT_TARGET_MOUNT_POINT = "/mnt/archinstall" 
POST_INSTALL_SCRIPTS_DIR = "post_install_scripts"
EXTRA_PACKAGES = [
    "neofetch", "htop", "firefox", "vlc",
]
MAI_BLOOM_SCRIPTS = [
    "01_basic_setup.sh",
    "02_desktop_config.sh",
]

# --- Worker Signals for Threading ---
class WorkerSignals(QObject):
    log_message = pyqtSignal(str, bool)  # message, is_error (True/False)
    finished = pyqtSignal(bool)          # success (True/False)
    archinstall_launched = pyqtSignal(bool, str) # launched_successfully, message

# --- Thread for launching Archinstall ---
class ArchinstallLauncherThread(QThread):
    signals = WorkerSignals()

    def __init__(self):
        super().__init__()

    def run(self):
        self.signals.log_message.emit("Attempting to launch archinstall in a new terminal...", False)
        
        terminal_commands_to_try = [
            ["konsole", "-e", "sudo", "archinstall"],
            ["gnome-terminal", "--", "sudo", "archinstall"],
            ["xfce4-terminal", "--command=sudo archinstall"],
            ["xterm", "-e", "sudo", "archinstall"]
        ]
        
        launched = False
        terminal_used = "None"
        for cmd_parts in terminal_commands_to_try:
            try:
                subprocess.Popen(cmd_parts) # Launch and don't wait
                self.signals.log_message.emit(f"Archinstall launched with '{cmd_parts[0]}'. Please complete installation in that window.", False)
                terminal_used = cmd_parts[0]
                launched = True
                break
            except FileNotFoundError:
                self.signals.log_message.emit(f"Terminal '{cmd_parts[0]}' not found. Trying next...", True)
            except Exception as e:
                self.signals.log_message.emit(f"Error launching with '{cmd_parts[0]}': {e}", True)
        
        self.signals.archinstall_launched.emit(launched, terminal_used if launched else "No suitable terminal found.")

# --- Thread for Post-Installation Tasks ---
class PostInstallThread(QThread):
    signals = WorkerSignals()

    def __init__(self, target_mount_point):
        super().__init__()
        self.target_mount_point = target_mount_point

    def _run_command_in_thread(self, command_list, check=True, capture_output=True):
        """Runs a command and emits log signals."""
        log_msg = f"Executing: {' '.join(command_list)}"
        self.signals.log_message.emit(log_msg, False)
        try:
            process = subprocess.run(command_list, check=check, capture_output=capture_output, text=True)
            if capture_output and process.stdout:
                self.signals.log_message.emit(f"Stdout:\n{process.stdout.strip()}", False)
            if capture_output and process.stderr:
                self.signals.log_message.emit(f"Stderr:\n{process.stderr.strip()}", True) # Assume stderr is an error/warning
            return process.returncode == 0
        except subprocess.CalledProcessError as e:
            self.signals.log_message.emit(f"Error running: {' '.join(e.cmd)}\nStdout: {e.stdout}\nStderr: {e.stderr}", True)
            return False
        except FileNotFoundError:
            self.signals.log_message.emit(f"Error: Command '{command_list[0]}' not found.", True)
            return False
        except Exception as e_gen:
            self.signals.log_message.emit(f"General error with command {' '.join(command_list)}: {e_gen}", True)
            return False


    def _run_in_chroot_thread(self, command_to_run_in_chroot):
        chroot_cmd_list = ["arch-chroot", self.target_mount_point, "/bin/bash", "-c", command_to_run_in_chroot]
        return self._run_command_in_thread(chroot_cmd_list)

    def run(self):
        self.signals.log_message.emit(f"Starting Mai Bloom customizations on target: {self.target_mount_point}", False)

        if not os.path.isdir(self.target_mount_point) or not os.path.exists(os.path.join(self.target_mount_point, 'bin/bash')):
            self.signals.log_message.emit(f"ERROR: Target mount point '{self.target_mount_point}' does not look like a valid Linux root.", True)
            self.signals.finished.emit(False)
            return

        overall_success = True

        # 1. Install extra packages
        if EXTRA_PACKAGES:
            self.signals.log_message.emit("--- Installing extra Mai Bloom packages ---", False)
            package_string = " ".join(shlex.quote(pkg) for pkg in EXTRA_PACKAGES)
            if not self._run_in_chroot_thread(f"pacman -S --noconfirm --needed {package_string}"):
                self.signals.log_message.emit("Failed to install one or more extra packages.", True)
                overall_success = False # Mark as failed but continue with other scripts for now
            else:
                self.signals.log_message.emit("Extra packages installed successfully.", False)
            self.signals.log_message.emit("", False) # Newline

        # 2. Run custom Mai Bloom scripts
        if MAI_BLOOM_SCRIPTS:
            self.signals.log_message.emit("--- Running Mai Bloom post-installation scripts ---", False)
            if not os.path.isdir(POST_INSTALL_SCRIPTS_DIR):
                self.signals.log_message.emit(f"Warning: Scripts directory '{POST_INSTALL_SCRIPTS_DIR}' not found. Skipping scripts.", True)
            else:
                for script_name in MAI_BLOOM_SCRIPTS:
                    host_script_path = os.path.join(POST_INSTALL_SCRIPTS_DIR, script_name)
                    if not os.path.isfile(host_script_path):
                        self.signals.log_message.emit(f"Warning: Script '{host_script_path}' not found. Skipping.", True)
                        continue

                    chroot_tmp_script_path = os.path.join("/tmp", os.path.basename(script_name))
                    cp_target_path_on_host = os.path.join(self.target_mount_point, chroot_tmp_script_path.lstrip('/'))

                    self.signals.log_message.emit(f"Preparing script: {script_name}", False)
                    if not self._run_command_in_thread(["cp", host_script_path, cp_target_path_on_host], capture_output=False): # cp doesn't output much unless error
                        self.signals.log_message.emit(f"Failed to copy script '{script_name}' to target.", True)
                        overall_success = False; continue
                    
                    if not self._run_in_chroot_thread(f"chmod +x {chroot_tmp_script_path}"):
                        self.signals.log_message.emit(f"Failed to make script '{script_name}' executable in chroot.", True)
                        overall_success = False; continue
                        
                    self.signals.log_message.emit(f"Executing '{chroot_tmp_script_path}' inside chroot...", False)
                    if not self._run_in_chroot_thread(chroot_tmp_script_path):
                        self.signals.log_message.emit(f"Script '{script_name}' execution failed or had errors.", True)
                        overall_success = False
                    else:
                        self.signals.log_message.emit(f"Script '{script_name}' executed.", False)

                    self._run_in_chroot_thread(f"rm -f {chroot_tmp_script_path}") # Try to clean up
                    self.signals.log_message.emit("-" * 20, False)
        else:
            self.signals.log_message.emit("No Mai Bloom post-installation scripts defined.", False)
        
        self.signals.finished.emit(overall_success)


# --- Main Application Window ---
class MaiBloomInstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.target_mount_point_var_internal = DEFAULT_TARGET_MOUNT_POINT # Internal storage
        self.initUI()
        self.prepare_example_scripts_if_needed()

    def initUI(self):
        self.setWindowTitle("Mai Bloom OS Installer")
        self.setGeometry(200, 200, 700, 550) # x, y, width, height

        self.main_layout = QVBoxLayout(self)

        # Welcome Label
        welcome_label = QLabel("Welcome to the Mai Bloom OS Installer!", self)
        font = QFont()
        font.setPointSize(16)
        welcome_label.setFont(font)
        welcome_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(welcome_label)

        # Step 1: Archinstall Group
        step1_group = QGroupBox("Step 1: Base Arch Linux Installation", self)
        step1_layout = QVBoxLayout()
        
        archinstall_label1 = QLabel(
            "Click below to launch 'archinstall' in a new terminal window.\n"
            "Follow its instructions to install the base Arch Linux system.", self)
        archinstall_label1.setWordWrap(True)
        step1_layout.addWidget(archinstall_label1)

        self.launch_archinstall_button = QPushButton("Launch Archinstall", self)
        self.launch_archinstall_button.clicked.connect(self.start_archinstall_process)
        step1_layout.addWidget(self.launch_archinstall_button, alignment=Qt.AlignCenter)
        
        archinstall_label2 = QLabel(
            "IMPORTANT: Note the root (/) mount point archinstall uses for the new system.", self)
        archinstall_label2.setWordWrap(True)
        step1_layout.addWidget(archinstall_label2)

        mount_point_layout = QHBoxLayout()
        mount_point_layout.addWidget(QLabel("Target Mount Point:", self))
        self.mount_point_entry = QLineEdit(DEFAULT_TARGET_MOUNT_POINT, self)
        mount_point_layout.addWidget(self.mount_point_entry)
        step1_layout.addLayout(mount_point_layout)

        step1_group.setLayout(step1_layout)
        self.main_layout.addWidget(step1_group)

        # Step 2: Mai Bloom Customizations Group
        step2_group = QGroupBox("Step 2: Apply Mai Bloom Customizations", self)
        step2_layout = QVBoxLayout()

        postinstall_label = QLabel(
            "After 'archinstall' is completely finished and you have exited its terminal,\n"
            "verify the Target Mount Point above, then click below to apply customizations.", self)
        postinstall_label.setWordWrap(True)
        step2_layout.addWidget(postinstall_label)

        self.run_postinstall_button = QPushButton("Run Mai Bloom Post-Install", self)
        self.run_postinstall_button.clicked.connect(self.start_postinstall_process)
        self.run_postinstall_button.setEnabled(False) # Initially disabled
        step2_layout.addWidget(self.run_postinstall_button, alignment=Qt.AlignCenter)

        step2_group.setLayout(step2_layout)
        self.main_layout.addWidget(step2_group)

        # Log Area
        log_group = QGroupBox("Installer Log", self)
        log_layout = QVBoxLayout()
        self.log_area = QTextEdit(self)
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Monospace", 9))
        log_layout.addWidget(self.log_area)
        log_group.setLayout(log_layout)
        self.main_layout.addWidget(log_group)
        
        self.setLayout(self.main_layout)
        self.show()

    def add_log_message_slot(self, message, is_error=False):
        if is_error:
            self.log_area.append(f"<font color='red'>[ERROR] {message}</font>")
        else:
            self.log_area.append(f"[INFO] {message}")
        self.log_area.ensureCursorVisible() # Auto-scroll

    def prepare_example_scripts_if_needed(self):
        self.add_log_message_slot(f"Post-install scripts will be looked for in: ./{POST_INSTALL_SCRIPTS_DIR}/")
        if not os.path.isdir(POST_INSTALL_SCRIPTS_DIR):
            self.add_log_message_slot(f"Creating directory: '{POST_INSTALL_SCRIPTS_DIR}'")
            os.makedirs(POST_INSTALL_SCRIPTS_DIR, exist_ok=True)

        for script_name in MAI_BLOOM_SCRIPTS: # Use MAI_BLOOM_SCRIPTS constant
            example_script_path = os.path.join(POST_INSTALL_SCRIPTS_DIR, script_name)
            if not os.path.exists(example_script_path) :
                self.add_log_message_slot(f"Creating example script: '{example_script_path}'")
                try:
                    with open(example_script_path, "w") as f:
                        f.write("#!/bin/bash\n\n")
                        f.write(f"echo '--- Running Mai Bloom Script: {script_name} ---'\n")
                        f.write("# Add your custom commands here.\n")
                        f.write(f"echo '--- {script_name} Finished ---'\n")
                    os.chmod(example_script_path, 0o755)
                except Exception as e:
                    self.add_log_message_slot(f"Could not create example script {example_script_path}: {e}", True)
        self.add_log_message_slot("Mai Bloom Installer Ready.")


    def start_archinstall_process(self):
        self.launch_archinstall_button.setEnabled(False)
        self.add_log_message_slot("Archinstall launch initiated...")

        self.archinstall_thread = ArchinstallLauncherThread()
        self.archinstall_thread.signals.log_message.connect(self.add_log_message_slot)
        self.archinstall_thread.signals.archinstall_launched.connect(self.on_archinstall_launched)
        self.archinstall_thread.start()

    def on_archinstall_launched(self, launched_successfully, message):
        if launched_successfully:
            self.add_log_message_slot(f"Archinstall reported as launched with terminal: {message}")
            self.add_log_message_slot("Please complete the installation in the archinstall terminal.")
            self.add_log_message_slot("Once done, close that terminal and click 'Run Mai Bloom Post-Install'.")
            self.run_postinstall_button.setEnabled(True)
        else:
            self.add_log_message_slot(f"Archinstall launch failed: {message}", True)
            QMessageBox.critical(self, "Archinstall Error", f"Failed to launch archinstall: {message}")
        self.launch_archinstall_button.setEnabled(True) # Re-enable button always

    def start_postinstall_process(self):
        self.target_mount_point_var_internal = self.mount_point_entry.text().strip()
        if not self.target_mount_point_var_internal:
            QMessageBox.warning(self, "Input Error", "Please specify the target mount point used by archinstall.")
            return

        self.run_postinstall_button.setEnabled(False)
        self.add_log_message_slot(f"Starting post-installation tasks for target: {self.target_mount_point_var_internal}")

        self.postinstall_thread = PostInstallThread(self.target_mount_point_var_internal)
        self.postinstall_thread.signals.log_message.connect(self.add_log_message_slot)
        self.postinstall_thread.signals.finished.connect(self.on_postinstall_finished)
        self.postinstall_thread.start()

    def on_postinstall_finished(self, success):
        if success:
            self.add_log_message_slot("Mai Bloom customizations completed successfully!")
            QMessageBox.information(self, "Success", "Mai Bloom OS installation and customizations are complete! You can now reboot.")
        else:
            self.add_log_message_slot("Mai Bloom customizations encountered errors. Please check the log for details.", True)
            QMessageBox.critical(self, "Post-Install Error", "Mai Bloom post-installation customizations failed. Please check the log for details.")
        self.run_postinstall_button.setEnabled(True)

# --- Main Execution ---
def main():
    if os.geteuid() != 0:
        # We need a QApplication instance to show QMessageBox even for early exit
        app_err = QApplication(sys.argv)
        QMessageBox.critical(None, "Permission Error", "This script must be run with root privileges (e.g., using `sudo python script_name.py`).")
        sys.exit(1)
        
    app = QApplication(sys.argv)
    installer_window = MaiBloomInstallerWindow()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
