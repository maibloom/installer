import sys
import subprocess
import json
import os
import logging # Keep for QtLogHandler if ArchinstallThread needs to emit pre-subprocess logs
import traceback
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout, QSplitter)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# --- Configuration ---
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "vscode", "python", "gcc", "gdb", "base-devel"],
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"],
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}

# --- Helper: Check if running as root ---
def check_root():
    return os.geteuid() == 0

# --- Archinstall Interaction Thread (Reverted to JSON + CLI) ---
class ArchinstallThread(QThread):
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str)

    def __init__(self, config_dict_for_json): # Takes the dict to be serialized
        super().__init__()
        self.config_data = config_dict_for_json
        self.config_file_path = "/tmp/archinstall_config.json"

    def run(self):
        try:
            self.installation_log.emit("Preparing archinstall JSON configuration...")
            with open(self.config_file_path, 'w') as f:
                json.dump(self.config_data, f, indent=2) # indent for readability if user inspects

            self.installation_log.emit(f"Archinstall JSON configuration saved to {self.config_file_path}")
            self.installation_log.emit(f"Full JSON configuration:\n{json.dumps(self.config_data, indent=2)}")
            self.installation_log.emit("Starting Arch Linux installation process via archinstall CLI...")
            self.installation_log.emit("This may take a while. Please be patient.")

            cmd = ["archinstall", "--config", self.config_file_path]
            # --silent is already in the JSON, but adding it to CLI ensures it if JSON key is missed.
            # However, the example JSON has "silent": false. We need "silent": true in our JSON.
            # If "silent": true is in JSON, CLI --silent might be redundant or an override.
            # Let's ensure our JSON has "silent": true.
            # cmd.append("--silent") # Optional: archinstall should respect "silent": true in JSON.

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)

            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    self.installation_log.emit(line.strip())
                process.stdout.close()

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
            self.installation_log.emit(f"An error occurred before or during archinstall CLI execution: {str(e)}\n{traceback.format_exc()}")
            self.installation_finished.emit(False, f"An unexpected error occurred: {str(e)}")
        finally:
            if os.path.exists(self.config_file_path):
                try:
                    os.remove(self.config_file_path)
                except OSError as e:
                    self.installation_log.emit(f"Warning: Could not remove temporary config file {self.config_file_path}: {e}")


class PostInstallThread(QThread):
    post_install_finished = pyqtSignal(bool, str)
    post_install_log = pyqtSignal(str)
    def __init__(self, script_path, target_mount_point="/mnt/archinstall"):
        super().__init__()
        self.script_path = script_path
        self.target_mount_point = target_mount_point
    def run(self):
        if not self.script_path or not os.path.exists(self.script_path):
            self.post_install_log.emit("Post-install script not provided or not found.")
            self.post_install_finished.emit(True, "No post-install script executed.")
            return
        try:
            self.post_install_log.emit(f"Running post-installation script: {self.script_path}")
            subprocess.run(["chmod", "+x", self.script_path], check=True)
            script_basename = os.path.basename(self.script_path)
            target_tmp_dir = os.path.join(self.target_mount_point, "tmp")
            os.makedirs(target_tmp_dir, exist_ok=True)
            target_script_path = os.path.join(target_tmp_dir, script_basename)
            subprocess.run(["cp", self.script_path, target_script_path], check=True)
            self.post_install_log.emit(f"Copied post-install script to {target_script_path}")
            chroot_script_internal_path = os.path.join("/tmp", script_basename)
            cmd = ["arch-chroot", self.target_mount_point, "/bin/bash", chroot_script_internal_path]
            self.post_install_log.emit(f"Executing in chroot: {' '.join(cmd)}")
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True)
            if process.stdout:
                for line in iter(process.stdout.readline, ''): self.post_install_log.emit(line.strip())
                process.stdout.close()
            stderr_output = ""
            if process.stderr:
                stderr_output = process.stderr.read()
                if stderr_output: self.post_install_log.emit(f"Post-install script STDERR:\n{stderr_output}")
                process.stderr.close()
            ret_code = process.wait()
            if ret_code == 0:
                self.post_install_log.emit("Post-installation script executed successfully.")
                self.post_install_finished.emit(True, "Post-installation script finished.")
            else:
                error_msg = f"Post-installation script failed with error code {ret_code}.\n{stderr_output}"
                self.post_install_log.emit(error_msg); self.post_install_finished.emit(False, error_msg)
        except FileNotFoundError as e:
            err_msg = f"Error: `arch-chroot` or script copy failed ({e}). `arch-install-scripts` installed?"
            self.post_install_log.emit(err_msg); self.post_install_finished.emit(False, err_msg)
        except Exception as e:
            self.post_install_log.emit(f"Error running post-install script: {str(e)}\n{traceback.format_exc()}")
            self.post_install_finished.emit(False, f"Error running post-install script: {str(e)}")
        finally:
            if 'target_script_path' in locals() and os.path.exists(target_script_path): # type: ignore
                try: os.remove(target_script_path); self.post_install_log.emit(f"Cleaned up: {target_script_path}") # type: ignore
                except OSError as e: self.post_install_log.emit(f"Warning: Could not remove {target_script_path}: {e}") # type: ignore


class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.archinstall_json_config_data = {} # Stores the dictionary to be serialized to JSON
        self.post_install_script_path = ""
        self.init_ui()

    def init_ui(self): # UI layout remains the same with log on the right
        self.setWindowTitle('Mai Bloom OS Installer')
        self.setGeometry(100, 100, 850, 700)
        overall_layout = QVBoxLayout(self)
        title_label = QLabel("<b>Welcome to Mai Bloom OS Installation!</b>")
        title_label.setAlignment(Qt.AlignCenter)
        overall_layout.addWidget(title_label)
        overall_layout.addWidget(QLabel("<small>This installer generates a JSON config for archinstall. Please read explanations carefully.</small>"))
        splitter = QSplitter(Qt.Horizontal)
        overall_layout.addWidget(splitter)
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        disk_group = QGroupBox("Disk Setup")
        disk_layout_vbox = QVBoxLayout()
        scan_button = QPushButton("Scan for Available Disks")
        scan_button.clicked.connect(self.scan_and_populate_disks)
        disk_layout_vbox.addWidget(scan_button)
        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Select the target disk. <b>ALL DATA WILL BE ERASED if 'Wipe Disk' is checked.</b>")
        disk_layout_vbox.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        disk_layout_vbox.addWidget(QLabel("<small>Ensure correct disk selection. This is irreversible if 'Wipe Disk' is checked.</small>"))
        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk (Auto-partition & Format)")
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("Wipes disk and creates Boot, Root, (+ Home) partitions.\nUncheck to use pre-existing partitions (advanced, requires manual setup).")
        disk_layout_vbox.addWidget(self.wipe_disk_checkbox)
        disk_group.setLayout(disk_layout_vbox)
        controls_layout.addWidget(disk_group)
        system_group = QGroupBox("System Configuration")
        system_layout_grid = QGridLayout()
        self.hostname_input = QLineEdit("mai-bloom-pc")
        system_layout_grid.addWidget(QLabel("Hostname:"), 0, 0); system_layout_grid.addWidget(self.hostname_input, 0, 1)
        self.locale_input = QLineEdit("en_US.UTF-8")
        system_layout_grid.addWidget(QLabel("Locale:"), 1, 0); system_layout_grid.addWidget(self.locale_input, 1, 1)
        self.keyboard_layout_input = QLineEdit("us")
        system_layout_grid.addWidget(QLabel("Keyboard Layout:"), 2, 0); system_layout_grid.addWidget(self.keyboard_layout_input, 2, 1)
        self.timezone_input = QLineEdit("UTC")
        system_layout_grid.addWidget(QLabel("Timezone:"), 3, 0); system_layout_grid.addWidget(self.timezone_input, 3, 1)
        system_group.setLayout(system_layout_grid)
        controls_layout.addWidget(system_group)
        user_group = QGroupBox("User Account Setup")
        user_layout_grid = QGridLayout()
        self.username_input = QLineEdit("bloomuser")
        user_layout_grid.addWidget(QLabel("Username:"), 0, 0); user_layout_grid.addWidget(self.username_input, 0, 1)
        self.password_input = QLineEdit(); self.password_input.setEchoMode(QLineEdit.Password)
        user_layout_grid.addWidget(QLabel("Password:"), 1, 0); user_layout_grid.addWidget(self.password_input, 1, 1)
        self.confirm_password_input = QLineEdit(); self.confirm_password_input.setEchoMode(QLineEdit.Password)
        user_layout_grid.addWidget(QLabel("Confirm Password:"), 2, 0); user_layout_grid.addWidget(self.confirm_password_input, 2, 1)
        user_group.setLayout(user_layout_grid)
        controls_layout.addWidget(user_group)
        software_group = QGroupBox("Software Selection")
        software_layout_vbox = QVBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["kde", "gnome", "xfce4", "minimal"])
        software_layout_vbox.addLayout(self.create_form_row("Desktop/Profile:", self.profile_combo))
        software_layout_vbox.addWidget(QLabel("<b>Additional Application Categories (Optional):</b>"))
        self.app_category_checkboxes = {}
        app_cat_layout_grid = QGridLayout()
        row, col = 0, 0
        for i, (category, _) in enumerate(APP_CATEGORIES.items()):
            self.app_category_checkboxes[category] = QCheckBox(category)
            app_cat_layout_grid.addWidget(self.app_category_checkboxes[category], row, col); col += 1
            if col > 1: col = 0; row += 1
        software_layout_vbox.addLayout(app_cat_layout_grid)
        software_group.setLayout(software_layout_vbox)
        controls_layout.addWidget(software_group)
        post_install_group = QGroupBox("Custom Post-Installation")
        post_install_layout_vbox = QVBoxLayout()
        self.post_install_script_button = QPushButton("Select Post-Install Bash Script (Optional)")
        self.post_install_script_button.clicked.connect(self.select_post_install_script)
        self.post_install_script_label = QLabel("No script selected.")
        post_install_layout_vbox.addWidget(self.post_install_script_button)
        post_install_layout_vbox.addWidget(self.post_install_script_label)
        post_install_group.setLayout(post_install_layout_vbox)
        controls_layout.addWidget(post_install_group)
        controls_layout.addStretch(1)
        splitter.addWidget(controls_widget)
        log_group = QGroupBox("Installation Log")
        log_layout_vbox = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True); self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        log_layout_vbox.addWidget(self.log_output)
        log_group.setLayout(log_layout_vbox)
        splitter.addWidget(log_group)
        splitter.setSizes([400, 450])
        self.install_button = QPushButton("Start Installation")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold;")
        self.install_button.clicked.connect(self.start_installation_process)
        button_layout = QHBoxLayout(); button_layout.addStretch(); button_layout.addWidget(self.install_button); button_layout.addStretch()
        overall_layout.addLayout(button_layout)
        self.scan_and_populate_disks()

    def create_form_row(self, label_text, widget): # Same
        row_layout = QHBoxLayout(); label = QLabel(label_text); label.setFixedWidth(120) 
        row_layout.addWidget(label); row_layout.addWidget(widget); return row_layout

    def scan_and_populate_disks(self): # Same
        self.log_output.append("Scanning for disks...")
        QApplication.processEvents()
        self.disk_combo.clear()
        try:
            result = subprocess.run(['lsblk', '-J', '-b', '-o', 'NAME,SIZE,TYPE,MODEL,PATH,TRAN,PKNAME,FSTYPE,MOUNTPOINT'],
                                    capture_output=True, text=True, check=True) # Added FSTYPE, MOUNTPOINT for future use if needed
            data = json.loads(result.stdout)
            disks_found = 0
            for device in data.get('blockdevices', []):
                if device.get('type') == 'disk' and not device.get('pkname') and device.get('tran') not in ['usb']:
                    name = f"/dev/{device.get('name', 'N/A')}"
                    model = device.get('model', 'Unknown Model')
                    size_bytes = int(device.get('size', 0))
                    size_gb = size_bytes / (1024**3)
                    display_text = f"{name} - {model} ({size_gb:.2f} GB)"
                    self.disk_combo.addItem(display_text, userData={"path": name, "size_bytes": size_bytes}) # Store more data
                    self.log_output.append(f"Found disk: {display_text}")
                    disks_found += 1
            if disks_found == 0:
                self.log_output.append("No suitable disks found or lsblk error.")
                QMessageBox.warning(self, "Disk Scan", "No suitable disks found.")
            else:
                self.log_output.append(f"Disk scan complete. Found {disks_found} disk(s).")
        except FileNotFoundError:
            self.log_output.append("Error: `lsblk` command not found."); QMessageBox.critical(self, "Error", "`lsblk` not found.")
        except subprocess.CalledProcessError as e:
            self.log_output.append(f"Error scanning disks: {e.stderr}"); QMessageBox.warning(self, "Disk Scan Error", f"Could not scan disks: {e.stderr}")
        except json.JSONDecodeError:
            self.log_output.append("Error parsing disk information."); QMessageBox.warning(self, "Disk Scan Error", "Failed to parse disk info.")

    def select_post_install_script(self): # Same
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getOpenFileName(self, "Select Post-Installation Bash Script", "", "Bash Scripts (*.sh);;All Files (*)", options=options)
        if filePath:
            self.post_install_script_path = filePath
            self.post_install_script_label.setText(f"Script: {os.path.basename(filePath)}")
            self.log_output.append(f"Post-install script selected: {filePath}")
        else:
            self.post_install_script_path = ""; self.post_install_script_label.setText("No script selected.")

    def update_log(self, message): # Same
        self.log_output.append(message)
        self.log_output.ensureCursorVisible(); QApplication.processEvents() 

    def start_installation_process(self):
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        locale_str = self.locale_input.text().strip() # e.g. "en_US.UTF-8"
        kb_layout = self.keyboard_layout_input.text().strip()
        timezone = self.timezone_input.text().strip()

        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: 
            QMessageBox.warning(self, "Input Error", "Please select a target disk."); return
        
        disk_data = self.disk_combo.itemData(selected_disk_index)
        disk_path_str = disk_data["path"]
        disk_size_bytes = disk_data["size_bytes"]


        profile_name = self.profile_combo.currentText()
        wipe_disk_checked = self.wipe_disk_checkbox.isChecked()

        if not all([hostname, username, password, locale_str, kb_layout, disk_path_str, timezone]):
            QMessageBox.warning(self, "Input Error", "Please fill in all required fields."); return
        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match."); return

        confirm_msg_detail = f"<b>TARGET DISK: {disk_path_str}</b> ({disk_size_bytes / (1024**3):.2f} GB)\n"
        confirm_msg_detail += f"Hostname: {hostname}, Profile: {profile_name}\n"
        if wipe_disk_checked:
            confirm_msg_detail += f"<b>ALL DATA ON {disk_path_str} WILL BE ERASED and auto-partitioned!</b>\n"
        else:
            confirm_msg_detail += f"<b>The disk {disk_path_str} will NOT be wiped. You MUST have compatible pre-existing partitions. This is an ADVANCED option.</b>\n"
        confirm_msg_detail += "Are you absolutely sure you want to proceed?"
        
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg_detail, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.log_output.append("Installation cancelled by user."); return

        self.install_button.setEnabled(False); self.log_output.clear()
        self.log_output.append("Preparing JSON configuration for archinstall...")

        # --- Build the JSON config dictionary ---
        self.archinstall_json_config_data = {
            "hostname": hostname,
            "kernels": ["linux"],
            "locale_config": {
                "sys_lang": locale_str.split('.')[0] if '.' in locale_str else locale_str, # e.g., en_US
                "sys_enc": locale_str.split('.')[-1] if '.' in locale_str else "UTF-8",    # e.g., UTF-8
                "kb_layout": kb_layout
            },
            "timezone": timezone,
            "ntp": True, # Enable NTP by default
            "swap": True, # Let archinstall handle swap (likely a swap file if we don't define a partition)
            "users": [{"username": username, "password": password, "sudo": True}],
            "packages": [], # Populated below
            "silent": True, # For automated install
            "audio_config": {"audio": "pipewire"}, # Default to pipewire
            # Omitting mirror_config for now, let archinstall handle it
        }

        is_efi = os.path.exists("/sys/firmware/efi")
        self.archinstall_json_config_data["bootloader"] = "Systemd-boot" if is_efi else "Grub"

        # NetworkManager is generally preferred for desktops
        self.archinstall_json_config_data["network_config"] = {
            "type": "networkmanager" # Tells archinstall to setup NetworkManager
        }
        # Ensure networkmanager is in packages if using this type
        default_packages_for_nm = ["networkmanager"]


        if wipe_disk_checked:
            partitions = []
            current_offset_mib = 1 # Start after 1MiB MBR gap

            # 1. Boot Partition
            if is_efi:
                esp_size_mib = 512
                partitions.append({
                    "status": "create", "type": "primary", "fs_type": "fat32",
                    "start": {"unit": "MiB", "value": current_offset_mib},
                    "size": {"unit": "MiB", "value": esp_size_mib},
                    "mountpoint": "/boot", "flags": ["boot", "esp"]
                })
                current_offset_mib += esp_size_mib
            elif (disk_size_bytes / (1024**2)) > 2000: # Crude check if disk is likely GPT for BIOS boot
                # This check isn't perfect, ideally we'd know the disk's partition table type (MBR/GPT)
                # For BIOS on GPT, a bios_grub partition is needed.
                bios_boot_size_mib = 1
                partitions.append({
                    "status": "create", "type": "primary", "fs_type": None, # Unformatted
                    "start": {"unit": "MiB", "value": current_offset_mib},
                    "size": {"unit": "MiB", "value": bios_boot_size_mib},
                    "flags": ["bios_grub"]
                })
                current_offset_mib += bios_boot_size_mib
            
            # Root and Home Partition Sizing Logic (simplified for JSON)
            # Ensure enough space is available
            min_disk_for_layout_mib = current_offset_mib + (20 * 1024) # Boot + min 20GiB root
            if (disk_size_bytes / (1024**2)) < min_disk_for_layout_mib:
                QMessageBox.critical(self, "Disk Too Small", f"The selected disk is too small for the default partition layout (needs > {min_disk_for_layout_mib / 1024:.1f} GiB).")
                self.install_button.setEnabled(True); return

            # Root: 50GiB fixed, if disk is large enough, else smaller. Min 20GiB.
            root_size_gib = 50
            if (disk_size_bytes / (1024**3)) < (root_size_gib + (current_offset_mib / 1024) + 10) : # If disk < root + boot + min 10G home
                root_size_gib = 20 # Fallback to smaller root
            
            partitions.append({
                "status": "create", "type": "primary", "fs_type": "ext4",
                "start": {"unit": "MiB", "value": current_offset_mib},
                "size": {"unit": "GiB", "value": root_size_gib},
                "mountpoint": "/", "flags": [] if is_efi else ["boot"] # Boot flag on root for BIOS/MBR if no separate /boot
            })
            # The example JSON had "start" for home as an absolute offset.
            # For "size": {"unit": "Percent", "value": 100} to work for home, its start must be correctly after root.
            # The official example's home start was: "start": {"unit": "GiB", "value": 20} (assuming boot was 512M, root was 20G)
            # This means home starts after 20.5GiB from the *beginning* of the disk.
            # So, home_start_mib = previous_partitions_total_size_mib
            home_start_mib = current_offset_mib + (root_size_gib * 1024)

            partitions.append({
                "status": "create", "type": "primary", "fs_type": "ext4",
                "start": {"unit": "MiB", "value": home_start_mib}, # Start after root
                "size": {"unit": "Percent", "value": 100}, # Takes rest of the space
                "mountpoint": "/home", "flags": []
            })

            self.archinstall_json_config_data["disk_config"] = {
                "config_type": "default_layout", # As per example, even with detailed partitions
                "device_modifications": [{
                    "device": disk_path_str,
                    "wipe": True,
                    "partitions": partitions
                }]
            }
        else: # Not wiping disk
            self.archinstall_json_config_data["disk_config"] = {
                "config_type": "manual_partitioning" # User is responsible for pre-partitioning
            }
            self.log_output.append("Disk wipe not selected. User is responsible for pre-partitioned disk. Archinstall will attempt to use existing layout.")

        if profile_name:
            # Using the simpler profile config structure first
            self.archinstall_json_config_data["profile_config"] = {"profile": {"main": profile_name.lower()}}
            # If specific greeter/gfx needed for profiles like KDE, can add here:
            if profile_name.lower() == "kde":
                 self.archinstall_json_config_data["profile_config"]["greeter"] = "sddm"
                 self.archinstall_json_config_data["profile_config"]["gfx_driver"] = "All open-source (default)"
            elif profile_name.lower() == "gnome":
                 self.archinstall_json_config_data["profile_config"]["greeter"] = "gdm"
                 self.archinstall_json_config_data["profile_config"]["gfx_driver"] = "All open-source (default)"


        # Add packages from categories + ensure NetworkManager if its type is selected
        final_packages = default_packages_for_nm[:] # Start with NM
        for category, checkbox in self.app_category_checkboxes.items():
            if checkbox.isChecked():
                final_packages.extend(APP_CATEGORIES[category])
        self.archinstall_json_config_data["packages"] = list(set(final_packages))
        
        self.log_output.append("JSON Configuration prepared for Archinstall:")
        # self.log_output.append(json.dumps(self.archinstall_json_config_data, indent=2)) # Logged by thread

        self.installer_thread = ArchinstallThread(self.archinstall_json_config_data)
        self.installer_thread.installation_log.connect(self.update_log)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message): # Same
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Installation Complete", "Arch Linux installation finished successfully!")
            if self.post_install_script_path:
                self.log_output.append("\n--- Proceeding to post-installation script. ---")
                # archinstall default mount is /mnt/archinstall, post_install_script uses this.
                self.run_post_install_script("/mnt/archinstall") 
            else:
                self.install_button.setEnabled(True); self.log_output.append("No post-install script.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Installation failed.\n{message}")
            self.install_button.setEnabled(True)

    def run_post_install_script(self, target_mount_point): # Same
        self.log_output.append(f"\n--- Starting Post-Installation Script (Target: {target_mount_point}) ---")
        self.post_installer_thread = PostInstallThread(self.post_install_script_path, target_mount_point=target_mount_point)
        self.post_installer_thread.post_install_log.connect(self.update_log)
        self.post_installer_thread.post_install_finished.connect(self.on_post_install_finished)
        self.post_installer_thread.start()

    def on_post_install_finished(self, success, message): # Same
        self.update_log(message)
        if success: QMessageBox.information(self, "Post-Install Complete", "Post-installation script finished.")
        else: QMessageBox.warning(self, "Post-Install Issue", f"Post-install script issues.\n{message}")
        self.install_button.setEnabled(True)
        self.log_output.append("Mai Bloom OS setup process finished.")


if __name__ == '__main__':
    if not check_root():
        print("Error: This application must be run as root (or with sudo).")
        sys.exit(1)

    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())
