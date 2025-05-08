import sys
import subprocess
import json
import os
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# --- Configuration ---
# Define application category packages
# You MUST customize these lists!
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "vscode", "python", "gcc", "gdb", "base-devel"], # base-devel is a group
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"], # noto-fonts-cjk for game compatibility
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}

# --- Helper: Check if running as root ---
def check_root():
    return os.geteuid() == 0

# --- Archinstall Interaction Thread (largely unchanged from previous) ---
class ArchinstallThread(QThread):
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        # Using a temporary file for archinstall config is often more reliable
        # than trying to set dozens of global variables in archinstall's library mode.
        self.script_path = "/tmp/archinstall_config.json"

    def run(self):
        try:
            self.installation_log.emit("Preparing archinstall configuration...")

            with open(self.script_path, 'w') as f:
                json.dump(self.config, f, indent=4)

            self.installation_log.emit(f"Archinstall configuration saved to {self.script_path}")
            self.installation_log.emit(f"Full configuration:\n{json.dumps(self.config, indent=2)}")
            self.installation_log.emit("Starting Arch Linux installation process via archinstall CLI...")
            self.installation_log.emit("This may take a while. Please be patient.")

            # Command to run archinstall with the generated configuration
            # Add --dry-run for testing without making changes
            # cmd = ["archinstall", "--config", self.script_path, "--silent", "--dry-run"]
            cmd = ["archinstall", "--config", self.script_path, "--silent"]


            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)

            # Stream stdout
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    self.installation_log.emit(line.strip())
                process.stdout.close()

            # Capture stderr
            stderr_output = ""
            if process.stderr:
                stderr_output = process.stderr.read()
                if stderr_output:
                    self.installation_log.emit(f"Archinstall STDERR:\n{stderr_output}")
                process.stderr.close()

            ret_code = process.wait()

            if ret_code == 0:
                self.installation_log.emit("Archinstall process completed successfully.")
                self.installation_finished.emit(True, "Arch Linux installation successful!")
            else:
                error_msg = f"Archinstall process failed with error code {ret_code}.\n{stderr_output}"
                self.installation_log.emit(error_msg)
                self.installation_finished.emit(False, error_msg)

        except FileNotFoundError:
            err_msg = "Error: `archinstall` command not found. Is it installed and in your PATH?"
            self.installation_log.emit(err_msg)
            self.installation_finished.emit(False, err_msg)
        except Exception as e:
            self.installation_log.emit(f"An error occurred during archinstall execution: {str(e)}")
            self.installation_finished.emit(False, f"An unexpected error occurred: {str(e)}")
        finally:
            if os.path.exists(self.script_path):
                try:
                    os.remove(self.script_path)
                except OSError as e:
                    self.installation_log.emit(f"Warning: Could not remove temporary config file {self.script_path}: {e}")


class PostInstallThread(QThread):
    post_install_finished = pyqtSignal(bool, str)
    post_install_log = pyqtSignal(str)

    def __init__(self, script_path, target_mount_point="/mnt/archinstall"):
        super().__init__()
        self.script_path = script_path
        self.target_mount_point = target_mount_point # archinstall's default mount point

    def run(self):
        if not self.script_path or not os.path.exists(self.script_path):
            self.post_install_log.emit("Post-install script not provided or not found.")
            # Not necessarily a failure of this thread's operation if no script was intended
            self.post_install_finished.emit(True, "No post-install script executed.")
            return

        try:
            self.post_install_log.emit(f"Running post-installation script: {self.script_path}")
            self.post_install_log.emit("The script should handle chrooting if necessary, or be designed to run on the new system via arch-chroot.")

            # Make script executable
            subprocess.run(["chmod", "+x", self.script_path], check=True)

            # It's safer for the Python script to explicitly chroot
            # The script is copied to the target system to avoid issues with mount points from host
            # A more robust way is to copy the script into the chroot, then execute it there.
            # For KISS, we'll try direct execution if the script itself is chroot-aware.
            # Or, if archinstall allows running commands post-setup but before unmounting.

            # Let's refine this: copy the script to the target, then arch-chroot
            # This is more reliable.
            script_basename = os.path.basename(self.script_path)
            target_script_path = os.path.join(self.target_mount_point, "tmp", script_basename)

            # Ensure /tmp exists in chroot
            os.makedirs(os.path.join(self.target_mount_point, "tmp"), exist_ok=True)
            subprocess.run(["cp", self.script_path, target_script_path], check=True)
            self.post_install_log.emit(f"Copied post-install script to {target_script_path}")


            # Command to execute the script inside the chroot
            chroot_script_internal_path = os.path.join("/tmp", script_basename) # Path inside the chroot
            cmd = ["arch-chroot", self.target_mount_point, "/bin/bash", chroot_script_internal_path]
            self.post_install_log.emit(f"Executing in chroot: {' '.join(cmd)}")

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)

            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    self.post_install_log.emit(line.strip())
                process.stdout.close()

            stderr_output = ""
            if process.stderr:
                stderr_output = process.stderr.read()
                if stderr_output:
                    self.post_install_log.emit(f"Post-install script STDERR:\n{stderr_output}")
                process.stderr.close()

            ret_code = process.wait()

            if ret_code == 0:
                self.post_install_log.emit("Post-installation script executed successfully.")
                self.post_install_finished.emit(True, "Post-installation script finished.")
            else:
                error_msg = f"Post-installation script failed with error code {ret_code}.\n{stderr_output}"
                self.post_install_log.emit(error_msg)
                self.post_install_finished.emit(False, error_msg)

        except FileNotFoundError:
            err_msg = "Error: `arch-chroot` command not found or script copy failed. Is `arch-install-scripts` installed?"
            self.post_install_log.emit(err_msg)
            self.post_install_finished.emit(False, err_msg)
        except Exception as e:
            self.post_install_log.emit(f"Error running post-install script: {str(e)}")
            self.post_install_finished.emit(False, f"Error running post-install script: {str(e)}")
        finally:
            # Clean up the copied script
            if 'target_script_path' in locals() and os.path.exists(target_script_path):
                try:
                    os.remove(target_script_path)
                    self.post_install_log.emit(f"Cleaned up: {target_script_path}")
                except OSError as e:
                    self.post_install_log.emit(f"Warning: Could not remove temporary script {target_script_path}: {e}")


# --- Main Application Window ---
class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.archinstall_config = {}
        self.post_install_script_path = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Mai Bloom OS Installer')
        self.setGeometry(100, 100, 750, 650) # Adjusted size

        main_layout = QVBoxLayout()

        # --- Title ---
        title_label = QLabel("<b>Welcome to Mai Bloom OS Installation!</b>")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        main_layout.addWidget(QLabel("<small>This installer will guide you through setting up Mai Bloom OS (Arch Linux based). Please read explanations carefully.</small>"))


        # --- Disk Selection ---
        disk_group = QGroupBox("Disk Setup")
        disk_layout = QVBoxLayout()

        scan_button = QPushButton("Scan for Available Disks")
        scan_button.setToolTip("Click to detect hard drives suitable for installation.")
        scan_button.clicked.connect(self.scan_and_populate_disks)
        disk_layout.addWidget(scan_button)

        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Select the target disk for installation. <b>ALL DATA ON THIS DISK WILL BE ERASED by default.</b>")
        disk_layout.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        disk_layout.addWidget(QLabel("<small>Ensure you select the correct disk. This is irreversible if 'Wipe Disk' is checked.</small>"))

        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk (Auto-partition & Format)")
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("If checked, the selected disk will be completely erased and automatically partitioned by archinstall.\nUncheck ONLY if you have pre-existing compatible partitions you want archinstall to use (advanced).")
        disk_layout.addWidget(self.wipe_disk_checkbox)
        disk_group.setLayout(disk_layout)
        main_layout.addWidget(disk_group)


        # --- Basic System Settings ---
        system_group = QGroupBox("System Configuration")
        system_layout = QGridLayout() # Using QGridLayout for better alignment

        self.hostname_input = QLineEdit()
        self.hostname_input.setPlaceholderText("mai-bloom-pc")
        self.hostname_input.setToolTip("Enter the desired name for this computer on the network.")
        system_layout.addWidget(QLabel("Hostname:"), 0, 0)
        system_layout.addWidget(self.hostname_input, 0, 1)

        self.locale_input = QLineEdit("en_US.UTF-8")
        self.locale_input.setToolTip("System language and character encoding (e.g., en_US.UTF-8, fr_FR.UTF-8).")
        system_layout.addWidget(QLabel("Locale:"), 1, 0)
        system_layout.addWidget(self.locale_input, 1, 1)

        self.keyboard_layout_input = QLineEdit("us")
        self.keyboard_layout_input.setToolTip("Your keyboard layout (e.g., us, uk, de).")
        system_layout.addWidget(QLabel("Keyboard Layout:"), 2, 0)
        system_layout.addWidget(self.keyboard_layout_input, 2, 1)

        self.timezone_input = QLineEdit("UTC")
        self.timezone_input.setToolTip("Specify the timezone, e.g., UTC, Europe/London, America/New_York.")
        system_layout.addWidget(QLabel("Timezone:"), 3, 0)
        system_layout.addWidget(self.timezone_input, 3, 1)

        system_group.setLayout(system_layout)
        main_layout.addWidget(system_group)


        # --- User Account ---
        user_group = QGroupBox("User Account Setup")
        user_layout = QGridLayout()

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("bloomuser")
        self.username_input.setToolTip("Enter the username for your main user account.")
        user_layout.addWidget(QLabel("Username:"), 0, 0)
        user_layout.addWidget(self.username_input, 0, 1)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setToolTip("Enter the password for the user account.")
        user_layout.addWidget(QLabel("Password:"), 1, 0)
        user_layout.addWidget(self.password_input, 1, 1)

        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        self.confirm_password_input.setToolTip("Confirm the password.")
        user_layout.addWidget(QLabel("Confirm Password:"), 2, 0)
        user_layout.addWidget(self.confirm_password_input, 2, 1)
        user_group.setLayout(user_layout)
        main_layout.addWidget(user_group)


        # --- Software Selection ---
        software_group = QGroupBox("Software Selection")
        software_layout = QVBoxLayout()

        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip("Select a base system profile or desktop environment.\n'minimal' is a very basic system. Others install a full desktop.")
        # These should ideally be fetched from archinstall or be well-tested known profiles.
        self.profile_combo.addItems(["kde", "gnome", "xfce4", "minimal", "server", "i3"]) # Added i3 as example
        software_layout.addLayout(self.create_form_row("Desktop/Profile:", self.profile_combo))

        software_layout.addWidget(QLabel("<b>Additional Application Categories (Optional):</b>"))
        self.app_category_checkboxes = {}
        app_cat_layout = QGridLayout()
        row, col = 0, 0
        for i, (category, _) in enumerate(APP_CATEGORIES.items()):
            self.app_category_checkboxes[category] = QCheckBox(category)
            self.app_category_checkboxes[category].setToolTip(f"Install a collection of {category.lower()} applications.")
            app_cat_layout.addWidget(self.app_category_checkboxes[category], row, col)
            col += 1
            if col > 1: # Two categories per row
                col = 0
                row += 1
        software_layout.addLayout(app_cat_layout)
        software_group.setLayout(software_layout)
        main_layout.addWidget(software_group)


        # --- Post-install script ---
        post_install_group = QGroupBox("Custom Post-Installation")
        post_install_layout = QVBoxLayout()
        self.post_install_script_button = QPushButton("Select Post-Install Bash Script (Optional)")
        self.post_install_script_button.setToolTip("Select a custom bash script to run after the main installation for further tweaks.")
        self.post_install_script_button.clicked.connect(self.select_post_install_script)
        self.post_install_script_label = QLabel("No script selected.")
        post_install_layout.addWidget(self.post_install_script_button)
        post_install_layout.addWidget(self.post_install_script_label)
        post_install_group.setLayout(post_install_layout)
        main_layout.addWidget(post_install_group)


        # --- Installation Log ---
        log_group = QGroupBox("Installation Log")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.NoWrap) # For better readability of logs
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group) # Add to main_layout, not system_layout


        # --- Install Button ---
        self.install_button = QPushButton("Start Installation")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold;")
        self.install_button.setToolTip("Begin the Mai Bloom OS installation with the selected settings.")
        self.install_button.clicked.connect(self.start_installation_process)
        main_layout.addWidget(self.install_button)

        self.setLayout(main_layout)
        self.scan_and_populate_disks() # Initial scan

    def create_form_row(self, label_text, widget):
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        label.setFixedWidth(120) # Adjust for consistent alignment
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        return row_layout

    def scan_and_populate_disks(self):
        self.log_output.append("Scanning for disks...")
        QApplication.processEvents()
        self.disk_combo.clear()
        try:
            # Use lsblk for disk info. -b for bytes, -J for JSON.
            # NAME,SIZE,TYPE,MODEL,PATH,TRAN (transport type, e.g. sata, nvme)
            result = subprocess.run(['lsblk', '-J', '-b', '-o', 'NAME,SIZE,TYPE,MODEL,PATH,TRAN'],
                                    capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            disks_found = 0
            for device in data.get('blockdevices', []):
                # Filter for disks, exclude loop devices, cd/dvd roms
                if device.get('type') == 'disk' and device.get('tran') not in ['usb'] : # Basic filter, can be enhanced
                    name = f"/dev/{device.get('name', 'N/A')}"
                    model = device.get('model', 'Unknown Model')
                    size_bytes = int(device.get('size', 0))
                    size_gb = size_bytes / (1024**3)
                    display_text = f"{name} - {model} ({size_gb:.2f} GB)"
                    self.disk_combo.addItem(display_text, userData=name)
                    self.log_output.append(f"Found disk: {display_text}")
                    disks_found += 1
            if disks_found == 0:
                self.log_output.append("No suitable disks found or lsblk error. Check permissions or connect a disk.")
                QMessageBox.warning(self, "Disk Scan", "No suitable disks found. Please ensure drives are connected and you have permissions. External USB drives are currently filtered out by default for safety.")
            else:
                self.log_output.append(f"Disk scan complete. Found {disks_found} disk(s). Please select one.")

        except FileNotFoundError:
            self.log_output.append("Error: `lsblk` command not found. Is it installed?")
            QMessageBox.critical(self, "Error", "`lsblk` command not found. Please install `util-linux`.")
        except subprocess.CalledProcessError as e:
            self.log_output.append(f"Error scanning disks: {e.stderr}")
            QMessageBox.warning(self, "Disk Scan Error", f"Could not scan disks: {e.stderr}")
        except json.JSONDecodeError:
            self.log_output.append("Error parsing disk information.")
            QMessageBox.warning(self, "Disk Scan Error", "Failed to parse disk information from lsblk.")


    def select_post_install_script(self):
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getOpenFileName(self, "Select Post-Installation Bash Script", "",
                                                  "Bash Scripts (*.sh);;All Files (*)", options=options)
        if filePath:
            self.post_install_script_path = filePath
            self.post_install_script_label.setText(f"Script: {os.path.basename(filePath)}")
            self.log_output.append(f"Post-install script selected: {filePath}")
        else:
            self.post_install_script_path = ""
            self.post_install_script_label.setText("No script selected.")


    def update_log(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible() # Scroll to the bottom
        QApplication.processEvents() # Keep UI responsive

    def start_installation_process(self):
        # --- Basic Validation ---
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        locale = self.locale_input.text().strip()
        kb_layout = self.keyboard_layout_input.text().strip()
        timezone = self.timezone_input.text().strip()

        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: # No disk selected
            QMessageBox.warning(self, "Input Error", "Please select a target disk after scanning.")
            return
        disk = self.disk_combo.itemData(selected_disk_index) # Get the /dev/path from userData

        profile = self.profile_combo.currentText()
        wipe_disk = self.wipe_disk_checkbox.isChecked()

        if not all([hostname, username, password, locale, kb_layout, disk, timezone]):
            QMessageBox.warning(self, "Input Error", "Please fill in all required system and user fields.")
            return

        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match.")
            return

        # --- Confirmation ---
        confirm_msg = (f"This will install Mai Bloom OS on <b>{disk}</b> with hostname <b>{hostname}</b>.\n"
                       f"Profile: <b>{profile}</b>.\n")
        if wipe_disk:
            confirm_msg += f"<b>ALL DATA ON {disk} WILL BE ERASED and the disk will be auto-partitioned!</b>\n"
        else:
            confirm_msg += f"<b>The disk {disk} will NOT be wiped. You must have compatible pre-existing partitions. This is an ADVANCED option.</b>\n"
        confirm_msg += "Are you sure you want to proceed?"

        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg,
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            self.log_output.append("Installation cancelled by user.")
            return

        self.install_button.setEnabled(False)
        self.log_output.clear()
        self.log_output.append("Starting installation preparation...")

        # --- Prepare archinstall configuration ---
        # This structure MUST align with archinstall's --config JSON format.
        # Check archinstall documentation or a generated config for the exact fields.
        self.archinstall_config = {
            # "__hostname__": hostname, # Some archinstall versions prefix with __
            "hostname": hostname,
            "locale_config": {
                "kb_layout": kb_layout,
                "sys_enc": "UTF-8",
                "sys_lang": locale
            },
            "timezone": timezone,
            "bootloader": "systemd-boot", # Default, make configurable if UEFI/BIOS detection is added
            "efi": True, # Assume UEFI for simplicity. Needs detection (e.g., check /sys/firmware/efi)
            "swap": True, # Let archinstall manage swap, or make configurable
            "profile_config": {
                "profile": {"main": profile} # Structure depends on archinstall version
            },
            "users": [
                {
                    "username": username,
                    "password": password, # archinstall will hash it
                    "sudo": True
                }
            ],
            "kernels": ["linux"], # Default Arch kernel. Could add "linux-lts".
            "network_config": {
                "type": "nm", # Use NetworkManager
            },
            "packages": [], # For additional packages from categories
            "silent": True, # To avoid archinstall's interactive prompts
            # Disk configuration is crucial and complex.
            # This relies on archinstall's auto-partitioning or guided partitioning features
            # if "disk_layouts" is used as shown.
            "disk_config": {
                # This part needs to be carefully structured based on archinstall's expectations
                "disk_layouts": {
                    disk: { # The actual device path, e.g., /dev/sda
                        "wipe": wipe_disk,
                        # "layout_type": "auto" # Tells archinstall to auto-partition if wiping
                                             # Or you define partitions here if not wiping or for custom.
                        # If wipe_disk is true, archinstall should auto-partition.
                        # If wipe_disk is false, archinstall expects partitions to be defined or existing.
                        # For KISS, if wipe_disk is true, we rely on archinstall's default full disk wipe and auto-partition.
                        # If wipe_disk is false, the user is on their own to provide a disk that archinstall can use
                        # or the JSON config would need to describe the partitions.
                    }
                }
            },
            # "harddrives": [disk] # Simpler alternative for some archinstall versions if just targeting a disk to auto-setup
        }
        if wipe_disk:
             self.archinstall_config["disk_config"]["disk_layouts"][disk]["layout_type"] = "auto"


        # Add packages from selected categories
        selected_packages = []
        for category, checkbox in self.app_category_checkboxes.items():
            if checkbox.isChecked():
                selected_packages.extend(APP_CATEGORIES[category])
        if selected_packages:
            self.archinstall_config["packages"] = list(set(selected_packages)) # Ensure unique packages

        # EFI/BIOS detection (simple example)
        if os.path.exists("/sys/firmware/efi"):
            self.archinstall_config["efi"] = True
            self.archinstall_config["bootloader"] = "systemd-boot" # Good default for UEFI
            self.log_output.append("UEFI system detected. Using systemd-boot.")
        else:
            self.archinstall_config["efi"] = False
            self.archinstall_config["bootloader"] = "grub" # GRUB is more common for BIOS
            self.log_output.append("BIOS system detected (or UEFI not found). Using GRUB.")
            # GRUB might need specific disk config for bios_boot partition if disk is GPT
            # This can get complex. Archinstall usually handles it if 'efi' is set correctly.


        self.log_output.append("Configuration prepared (verify against archinstall docs):")
        self.log_output.append(json.dumps(self.archinstall_config, indent=2))

        # --- Start Archinstall in a separate thread ---
        self.installer_thread = ArchinstallThread(self.archinstall_config)
        self.installer_thread.installation_log.connect(self.update_log)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message):
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Installation Complete", "Arch Linux base installation finished successfully!")
            if self.post_install_script_path:
                self.log_output.append("\n--- Installation successful. Proceeding to post-installation script. ---")
                self.run_post_install_script()
            else:
                self.install_button.setEnabled(True)
                self.log_output.append("No post-installation script to run. System setup complete.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Arch Linux installation failed.\nSee log for details.\n{message}")
            self.install_button.setEnabled(True)

    def run_post_install_script(self):
        self.log_output.append("\n--- Starting Post-Installation Script ---")
        # Default mount point for archinstall is /mnt/archinstall
        # If your archinstall version uses something else, adjust here.
        target_mount = self.archinstall_config.get("mount_point", "/mnt/archinstall")

        self.post_installer_thread = PostInstallThread(self.post_install_script_path, target_mount_point=target_mount)
        self.post_installer_thread.post_install_log.connect(self.update_log)
        self.post_installer_thread.post_install_finished.connect(self.on_post_install_finished)
        self.post_installer_thread.start()

    def on_post_install_finished(self, success, message):
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Post-Install Complete", "Post-installation script finished successfully.")
        else:
            QMessageBox.warning(self, "Post-Install Issue", f"Post-installation script reported issues or failed.\n{message}")
        self.install_button.setEnabled(True)
        self.log_output.append("Mai Bloom OS setup process finished.")


if __name__ == '__main__':
    if not check_root():
        print("Error: This application must be run as root (or with sudo) to perform installation tasks.")
        # Attempt to show a simple Qt message box even if full app doesn't init
        # This is tricky as QApplication might not be running yet.
        # For simplicity, console print and exit is more reliable here.
        app_temp = QApplication.instance() # Check if an instance already exists
        if not app_temp:
            app_temp = QApplication(sys.argv)
        QMessageBox.critical(None, "Root Access Required", "This installer must be run with root privileges (e.g., using sudo).\nPlease restart the application as root.")
        sys.exit(1)

    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())
