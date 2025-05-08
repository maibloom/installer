import sys
import subprocess
import json
import os # For checking sudo

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox)
from PyQt5.QtCore import QThread, pyqtSignal

# --- Configuration ---
# It's a good idea to check if running as root early on,
# as archinstall will definitely need it.
def check_root():
    return os.geteuid() == 0

# --- Archinstall Interaction Thread ---
# Running archinstall directly in the GUI thread will freeze it.
# So, we use a QThread.

class ArchinstallThread(QThread):
    installation_finished = pyqtSignal(bool, str) # bool: success, str: message/error
    installation_log = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.script_path = "/tmp/archinstall_config.json" # Temporary config file

    def run(self):
        try:
            self.installation_log.emit("Preparing archinstall configuration...")
            # Archinstall typically takes a JSON file for its --conf parameter
            # Or can be scripted by setting global variables within archinstall.Installer()
            # For simplicity and better control, let's simulate preparing a config
            # that archinstall functions would use.

            # --- IMPORTANT ---
            # This is where the core interaction with the archinstall library happens.
            # You'll need to consult the archinstall source code to see how to
            # programmatically set these values and trigger the installation steps.
            #
            # Example (Conceptual - API might differ significantly):
            #
            # from archinstall import Installer, GlobalArchinstallVariables
            #
            # # 1. Set global variables (less direct, more prone to breaking with updates)
            # GlobalArchinstallVariables.BIOS_UEFI_BOOT_MODE = 'uefi' # or 'bios'
            # GlobalArchinstallVariables.DISK_LAYOUTS = {...} # complex
            # GlobalArchinstallVariables.USER_CONFIG = {...}
            # # ... and many others
            #
            # # 2. Or, more likely, you might prepare a dictionary and pass it to
            # # specific functions or an Installer class instance.
            #
            # installer_instance = Installer()
            # # installer_instance.load_config(self.config) # Hypothetical
            # installer_instance.select_disk(self.config.get('block_device'))
            # installer_instance.set_hostname(self.config.get('hostname'))
            # # ... and so on for each step: partitioning, formatting, installing base, user creation etc.
            # installer_instance.install_base_packages()
            # installer_instance.setup_user(...)
            # installer_instance.install_bootloader()
            #
            # This part is HIGHLY dependent on the archinstall library's structure
            # and how it's meant to be used programmatically.
            # The following is a placeholder for calling archinstall as a command-line
            # tool with a generated config, which is often more stable if a programmatic API
            # isn't well-defined or is too complex for this stage.

            self.installation_log.emit(f"Using configuration: {json.dumps(self.config, indent=2)}")

            # --- Alternative: Using archinstall as a command-line tool ---
            # This is generally more robust if the library API is not stable
            # or easy to use directly for all necessary steps.
            with open(self.script_path, 'w') as f:
                json.dump(self.config, f, indent=4)

            self.installation_log.emit(f"Archinstall configuration saved to {self.script_path}")
            self.installation_log.emit("Starting Arch Linux installation process via archinstall CLI...")
            self.installation_log.emit("This may take a while. Please be patient.")

            # Ensure archinstall is in PATH or provide full path
            # The exact command might vary based on how you want to control archinstall
            # --config is a common way to pass settings.
            # --dry-run is extremely useful for testing!
            # You might need to run `archinstall --script guided` and see what kind of JSON
            # it expects or how it structures its settings.
            #
            # For a real programmatic approach, you would replace this subprocess call
            # with direct calls to archinstall's Python functions/classes.

            # Example command (you WILL need to adjust this):
            cmd = ["archinstall", "--config", self.script_path, "--silent"] # Add --dry-run for testing
            # cmd = ["python", "-m", "archinstall", "--config", self.script_path, "--silent"]


            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self.installation_log.emit(output.strip())

            stderr_output = process.stderr.read()
            if stderr_output:
                 self.installation_log.emit(f"Archinstall STDERR:\n{stderr_output}")

            ret_code = process.wait()

            if ret_code == 0:
                self.installation_log.emit("Archinstall process completed successfully.")
                self.installation_finished.emit(True, "Arch Linux installation successful!")
            else:
                error_msg = f"Archinstall process failed with error code {ret_code}.\n{stderr_output}"
                self.installation_log.emit(error_msg)
                self.installation_finished.emit(False, error_msg)

        except Exception as e:
            self.installation_log.emit(f"An error occurred: {str(e)}")
            self.installation_finished.emit(False, f"An unexpected error occurred: {str(e)}")
        finally:
            if os.path.exists(self.script_path):
                os.remove(self.script_path)


class PostInstallThread(QThread):
    post_install_finished = pyqtSignal(bool, str)
    post_install_log = pyqtSignal(str)

    def __init__(self, script_path, target_mount_point="/mnt/archinstall"): # Adjust mount point as needed
        super().__init__()
        self.script_path = script_path
        self.target_mount_point = target_mount_point

    def run(self):
        if not self.script_path or not os.path.exists(self.script_path):
            self.post_install_log.emit("Post-install script not provided or not found.")
            self.post_install_finished.emit(True, "No post-install script executed.") # Not a failure of this thread
            return

        try:
            self.post_install_log.emit(f"Running post-installation script: {self.script_path}")
            # To run a script *inside* the new system, you'd typically use arch-chroot.
            # The script needs to be copied into the target system first, or accessed from it.

            # Simplistic approach: directly execute if not chrooting (e.g. script handles chroot)
            # More robust: copy script to target, then arch-chroot
            # For now, let's assume the script can be run from the installer environment
            # and knows how to target the installed system (e.g., by taking target_mount_point as an arg)

            # Example: Run script with bash, pass target mount point
            # The script itself needs to be aware it's running on the installed system or use chroot
            # This is a simplified call; a real chroot execution is more involved:
            # cmd = ["arch-chroot", self.target_mount_point, "/bin/bash", "-c", f"/path/to/script/in/chroot_env/your_script.sh"]
            # For now, let's just execute it. The script needs to be designed to work this way or
            # your Python code needs to handle the chrooting.

            # Make sure the script is executable
            subprocess.run(["chmod", "+x", self.script_path], check=True)

            # Run the script. It's often better to make the script itself handle chrooting
            # or expect its paths to be relative to the installed system if run via arch-chroot.
            # If running directly, it needs to know the mount point.
            self.post_install_log.emit(f"Executing: bash {self.script_path} {self.target_mount_point}")
            process = subprocess.Popen(["bash", self.script_path, self.target_mount_point],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self.post_install_log.emit(output.strip())

            stderr_output = process.stderr.read()
            if stderr_output:
                 self.post_install_log.emit(f"Post-install script STDERR:\n{stderr_output}")

            ret_code = process.wait()

            if ret_code == 0:
                self.post_install_log.emit("Post-installation script executed successfully.")
                self.post_install_finished.emit(True, "Post-installation script finished.")
            else:
                error_msg = f"Post-installation script failed with error code {ret_code}.\n{stderr_output}"
                self.post_install_log.emit(error_msg)
                self.post_install_finished.emit(False, error_msg)

        except Exception as e:
            self.post_install_log.emit(f"Error running post-install script: {str(e)}")
            self.post_install_finished.emit(False, f"Error running post-install script: {str(e)}")


# --- Main Application Window ---
class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.archinstall_config = {}
        self.post_install_script_path = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Mai Bloom OS Installer')
        self.setGeometry(100, 100, 700, 500) # Increased height for log

        layout = QVBoxLayout()

        # --- Basic Settings ---
        layout.addWidget(QLabel("<b>Welcome to Mai Bloom OS Installation!</b>"))

        # Hostname
        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("my-arch-pc")
        layout.addLayout(self.create_form_row("Hostname:", self.hostname_input))

        # Username
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("bloomuser")
        layout.addLayout(self.create_form_row("Username:", self.username_input))

        # Password
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addLayout(self.create_form_row("Password:", self.password_input))

        # Confirm Password
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        layout.addLayout(self.create_form_row("Confirm Password:", self.confirm_password_input))

        # Locale (Simplified)
        self.locale_input = QLineEdit("en_US.UTF-8")
        layout.addLayout(self.create_form_row("Locale:", self.locale_input))

        # Keyboard Layout (Simplified)
        self.keyboard_layout_input = QLineEdit("us")
        layout.addLayout(self.create_form_row("Keyboard Layout:", self.keyboard_layout_input))

        # Disk (Highly Simplified - In reality, this is complex!)
        # A real implementation needs to list available disks (e.g. lsblk)
        # and allow partitioning choices. For KISS, we'll just ask for the device.
        self.disk_input = QLineEdit()
        self.disk_input.setPlaceholderText("/dev/sda or /dev/nvme0n1")
        layout.addLayout(self.create_form_row("Target Disk:", self.disk_input))
        layout.addWidget(QLabel("<small><b>Warning:</b> All data on the selected disk will be erased. "
                                "This is a simplified example. Ensure you select the correct disk.</small>"))

        # Wipe disk checkbox
        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk (Format)")
        self.wipe_disk_checkbox.setChecked(True) # Default to wipe for simplicity
        layout.addWidget(self.wipe_disk_checkbox)


        # Desktop Environment/Profile
        self.profile_combo = QComboBox()
        # These profiles need to match what archinstall supports
        # You can get these using `archinstall --show-profiles` or similar introspection
        # Or by checking archinstall.Installer().profiles
        # Example profiles:
        self.profile_combo.addItems(["kde", "gnome", "xfce4", "minimal", "server"])
        layout.addLayout(self.create_form_row("Desktop/Profile:", self.profile_combo))

        # Post-install script
        self.post_install_script_button = QPushButton("Select Post-Install Script (Optional)")
        self.post_install_script_button.clicked.connect(self.select_post_install_script)
        self.post_install_script_label = QLabel("No script selected.")
        script_layout = QHBoxLayout()
        script_layout.addWidget(self.post_install_script_button)
        script_layout.addWidget(self.post_install_script_label)
        layout.addLayout(script_layout)

        # --- Installation Log ---
        layout.addWidget(QLabel("<b>Installation Log:</b>"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)


        # Install Button
        self.install_button = QPushButton("Start Installation")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px;")
        self.install_button.clicked.connect(self.start_installation_process)
        layout.addWidget(self.install_button)

        self.setLayout(layout)

    def create_form_row(self, label_text, widget):
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        label.setFixedWidth(150) # Adjust for consistent alignment
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        return row_layout

    def select_post_install_script(self):
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getOpenFileName(self, "Select Post-Installation Bash Script", "",
                                                  "Bash Scripts (*.sh);;All Files (*)", options=options)
        if filePath:
            self.post_install_script_path = filePath
            self.post_install_script_label.setText(os.path.basename(filePath))
            self.log_output.append(f"Post-install script selected: {filePath}")

    def update_log(self, message):
        self.log_output.append(message)
        QApplication.processEvents() # Keep UI responsive

    def start_installation_process(self):
        if not check_root():
            QMessageBox.critical(self, "Error", "This application must be run as root (or with sudo).")
            return

        # --- Basic Validation ---
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        locale = self.locale_input.text().strip()
        kb_layout = self.keyboard_layout_input.text().strip()
        disk = self.disk_input.text().strip()
        profile = self.profile_combo.currentText()
        wipe_disk = self.wipe_disk_checkbox.isChecked()

        if not all([hostname, username, password, locale, kb_layout, disk]):
            QMessageBox.warning(self, "Input Error", "Please fill in all required fields.")
            return

        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match.")
            return

        if not disk.startswith("/dev/"):
             QMessageBox.warning(self, "Input Error", "Disk path should be like /dev/sda, /dev/nvme0n1, etc.")
             return

        # --- Confirmation ---
        reply = QMessageBox.question(self, 'Confirm Installation',
                                     f"This will install Arch Linux on <b>{disk}</b> with hostname <b>{hostname}</b>.\n"
                                     f"<b>ALL DATA ON {disk} WILL BE ERASED if 'Wipe selected disk' is checked!</b>\n"
                                     "Are you sure you want to proceed?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            self.log_output.append("Installation cancelled by user.")
            return

        self.install_button.setEnabled(False)
        self.log_output.clear()
        self.log_output.append("Starting installation...")


        # --- Prepare archinstall configuration ---
        # This structure needs to align with what archinstall's --config option expects
        # or how its Python API functions. This is a *guess* and will need adjustment.
        # You should generate a config using `archinstall --script guided` and then
        # inspect the generated JSON to understand the structure.
        self.archinstall_config = {
            "hostname": hostname,
            "locale_config": {
                "kb_layout": kb_layout,
                "sys_enc": "UTF-8", # Common default
                "sys_lang": locale
            },
            "disk_config": {
                # This is highly simplified. Real disk config is complex.
                # It involves partitioning, file systems, mount options, etc.
                # Archinstall's guided setup usually creates a more detailed structure.
                "block_devices": [disk], # This assumes a single disk, simple layout
                # A more realistic config would specify partitions, filesystems, etc.
                # For example:
                # "disk_layouts": {
                #     disk: {
                #         "wipe": wipe_disk,
                #         "layout_type": "auto" # or specific partition details
                #     }
                # }
                # The 'auto' layout might be the simplest to invoke if archinstall supports it this way.
                # Or you might need to define partitions explicitly.
                # Let's assume a simplified structure that `archinstall` might accept
                # or that your Python library calls will translate.
            },
            "bootloader": "systemd-boot", # Or "grub-install" - depends on BIOS/UEFI
            "swap": True, # Let archinstall decide size or make it configurable
            "profile_config": { # This part is very dependent on archinstall version
                "profile": {"main": profile} # Check archinstall source for exact structure
            },
            "users": [
                {
                    "username": username,
                    "password": password,
                    "sudo": True
                }
            ],
            "kernels": ["linux"], # Default kernel
            "network_config": { # Basic DHCP configuration
                "type": "nm", # NetworkManager
            },
            # Potentially other settings: audio, timezone, etc.
            "timezone": "UTC", # Make this configurable
            "silent": False, # If True, archinstall might not show its own TUI prompts
            # "!users": [{"username": username, "password": password, "sudo": True}], # Common way to structure in older JSONs
            # "!hostname": hostname,
            # "locale": locale,
            # "keyboard-layout": kb_layout,
            # "disk": disk, # This might be a simplified top-level key in some contexts
            # "profile": profile,
            # "harddrives": [disk], # Another way it might be specified
        }

        # Add partitioning related details if wipe is selected
        # This part is CRITICAL and needs to match `archinstall`'s expectations.
        # The `archinstall` command typically handles partitioning interactively or via
        # a detailed configuration in the JSON. Simulating "auto-partition and format"
        # might look something like this, but this is a MAJOR GUESS.
        if wipe_disk:
            self.archinstall_config['disk_config']['disk_layouts'] = {
                disk: {
                    "wipe": True,
                    "layout_type": "auto" # Ask archinstall to auto-partition
                }
            }
        else:
            # If not wiping, the user must have pre-partitioned.
            # The config would need to describe the existing partitions to use.
            # This is too complex for a KISS example.
            self.log_output.append("WARN: Not wiping disk. Manual partitioning is assumed and NOT handled by this GUI.")
            # Potentially, you'd remove `disk_layouts` or set `wipe: False` and specify partitions.

        # Forcing UEFI or BIOS - this is important
        # You'd need a way to detect this or ask the user.
        # self.archinstall_config["efi"] = True # or False

        self.log_output.append("Configuration prepared (simplified for this example):")
        self.log_output.append(json.dumps(self.archinstall_config, indent=2))

        # --- Start Archinstall in a separate thread ---
        self.installer_thread = ArchinstallThread(self.archinstall_config)
        self.installer_thread.installation_log.connect(self.update_log)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message):
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Installation Complete", "Arch Linux installation finished successfully!")
            if self.post_install_script_path:
                self.run_post_install_script()
            else:
                self.install_button.setEnabled(True)
                self.log_output.append("No post-installation script to run.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Arch Linux installation failed.\n{message}")
            self.install_button.setEnabled(True)

    def run_post_install_script(self):
        self.log_output.append("\n--- Starting Post-Installation Script ---")
        self.post_installer_thread = PostInstallThread(self.post_install_script_path)
        self.post_installer_thread.post_install_log.connect(self.update_log)
        self.post_installer_thread.post_install_finished.connect(self.on_post_install_finished)
        self.post_installer_thread.start()

    def on_post_install_finished(self, success, message):
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Post-Install Complete", "Post-installation script finished.")
        else:
            QMessageBox.warning(self, "Post-Install Issue", f"Post-installation script reported issues or failed.\n{message}")
        self.install_button.setEnabled(True)
        self.log_output.append("Mai Bloom OS setup process finished.")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())

