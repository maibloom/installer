import sys
import subprocess
import json
import os
import logging # Not used, but was imported
import traceback
from pathlib import Path # Not used, but was imported

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

# --- Archinstall Interaction Thread (JSON + CLI) ---
class ArchinstallThread(QThread):
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str)

    def __init__(self, config_dict_for_json):
        super().__init__()
        self.config_data = config_dict_for_json
        self.config_file_path = "/tmp/archinstall_config.json"

    def run(self):
        try:
            self.installation_log.emit("Preparing archinstall JSON configuration...")
            # self.config_data should already contain 'silent': True and 'script': 'default_installer'
            # from MaiBloomInstallerApp.start_installation_process
            with open(self.config_file_path, 'w') as f:
                json.dump(self.config_data, f, indent=2)

            self.installation_log.emit(f"Archinstall JSON configuration saved to {self.config_file_path}")
            self.installation_log.emit("Starting Arch Linux installation process via archinstall CLI...")
            self.installation_log.emit("This may take a while. Please be patient.")

            # --- MODIFICATION: Added --silent to the command line ---
            cmd = ["archinstall", "--config", self.config_file_path, "--silent"]

            proc_env = os.environ.copy()
            proc_env["TERM"] = "dumb"
            if 'LC_ALL' not in proc_env:
                proc_env['LC_ALL'] = 'C.UTF-8'
            if 'LANG' not in proc_env:
                proc_env['LANG'] = 'C.UTF-8'
            
            self.installation_log.emit(f"Launching subprocess: {' '.join(cmd)}")
            self.installation_log.emit(f"  with ENV: TERM={proc_env['TERM']}, LC_ALL={proc_env.get('LC_ALL', 'Not Set')}, LANG={proc_env.get('LANG', 'Not Set')}")

            process = subprocess.Popen(cmd,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       stdin=subprocess.DEVNULL,
                                       text=True,
                                       bufsize=1,
                                       universal_newlines=True,
                                       env=proc_env)

            stdout_lines = []
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    line_strip = line.strip()
                    self.installation_log.emit(line_strip)
                    stdout_lines.append(line_strip)

            ret_code = process.wait()

            stderr_output = ""
            if process.stderr:
                stderr_output = process.stderr.read()
                if stderr_output:
                    stderr_log_snippet = stderr_output.strip().split('\n')
                    if len(stderr_log_snippet) > 20:
                        self.installation_log.emit(f"Archinstall STDERR (snippet):\n" + "\n".join(stderr_log_snippet[:10]) + "\n...\n" + "\n".join(stderr_log_snippet[-10:]))
                    else:
                        self.installation_log.emit(f"Archinstall STDERR:\n{stderr_output.strip()}")
            
            if ret_code == 0:
                self.installation_log.emit("Archinstall process completed successfully.")
                self.installation_finished.emit(True, "Arch Linux installation successful!")
            else:
                error_msg_detail = f"Archinstall process failed with error code {ret_code}."
                if stderr_output.strip():
                     error_msg_detail += f"\n\nError Output (from archinstall STDERR):\n---\n{stderr_output.strip()}\n---"
                elif stdout_lines:
                     error_msg_detail += f"\n\nLast Output Lines (from archinstall STDOUT):\n---\n"
                     error_msg_detail += "\n".join(stdout_lines[-15:])
                     error_msg_detail += "\n---"
                
                self.installation_log.emit(f"Archinstall failure. Full details:\n{error_msg_detail}")
                popup_error_msg = f"Archinstall process failed (code {ret_code}).\nSee installation log for detailed error output."
                self.installation_finished.emit(False, popup_error_msg)

        except FileNotFoundError:
            err_msg = "Error: `archinstall` command not found. Is it installed and in your PATH?"
            self.installation_log.emit(err_msg); self.installation_finished.emit(False, err_msg)
        except Exception as e:
            self.installation_log.emit(f"An error occurred in ArchinstallThread: {str(e)}\n{traceback.format_exc()}")
            self.installation_finished.emit(False, f"An unexpected error occurred in ArchinstallThread: {str(e)}")
        finally:
            if os.path.exists(self.config_file_path):
                try: os.remove(self.config_file_path)
                except OSError as e: self.installation_log.emit(f"Warning: Could not remove temp config file {self.config_file_path}: {e}")


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
        
        target_script_path_in_chroot_tmp = None 

        try:
            self.post_install_log.emit(f"Preparing post-installation script: {self.script_path}")
            subprocess.run(["chmod", "+x", self.script_path], check=True)
            script_basename = os.path.basename(self.script_path)
            
            chroot_tmp_dir_on_host = os.path.join(self.target_mount_point, "tmp")
            os.makedirs(chroot_tmp_dir_on_host, exist_ok=True)
            target_script_path_in_chroot_tmp = os.path.join(chroot_tmp_dir_on_host, script_basename)
            
            subprocess.run(["cp", self.script_path, target_script_path_in_chroot_tmp], check=True)
            self.post_install_log.emit(f"Copied post-install script to {target_script_path_in_chroot_tmp} (for chroot)")
            
            script_path_inside_chroot = os.path.join("/tmp", script_basename) 
            
            cmd = ["arch-chroot", self.target_mount_point, "/bin/bash", script_path_inside_chroot]
            self.post_install_log.emit(f"Executing in chroot: {' '.join(cmd)}")

            proc_env_chroot = os.environ.copy()
            proc_env_chroot["TERM"] = "dumb"
            if 'LC_ALL' not in proc_env_chroot:
                proc_env_chroot['LC_ALL'] = 'C.UTF-8'
            if 'LANG' not in proc_env_chroot:
                proc_env_chroot['LANG'] = 'C.UTF-8'

            process = subprocess.Popen(cmd,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       stdin=subprocess.DEVNULL,
                                       text=True,
                                       bufsize=1,
                                       universal_newlines=True,
                                       env=proc_env_chroot)
            
            if process.stdout:
                for line in iter(process.stdout.readline, ''): self.post_install_log.emit(line.strip())

            ret_code = process.wait()

            stderr_output = ""
            if process.stderr:
                stderr_output = process.stderr.read()
                if stderr_output: self.post_install_log.emit(f"Post-install script STDERR:\n{stderr_output.strip()}")

            if ret_code == 0:
                self.post_install_log.emit("Post-installation script executed successfully.")
                self.post_install_finished.emit(True, "Post-installation script finished.")
            else:
                error_msg = f"Post-installation script failed with error code {ret_code}.\n{stderr_output.strip()}"
                self.post_install_log.emit(error_msg); self.post_install_finished.emit(False, error_msg)
        except FileNotFoundError as e:
            err_msg = f"Error: `arch-chroot` or script copy target missing ({e}). Is `arch-install-scripts` package installed and target system mounted?"
            self.post_install_log.emit(err_msg); self.post_install_finished.emit(False, err_msg)
        except subprocess.CalledProcessError as e:
            err_msg = f"Subprocess error during post-install prep: {e}"
            self.post_install_log.emit(err_msg); self.post_install_finished.emit(False, err_msg)
        except Exception as e:
            self.post_install_log.emit(f"Error running post-install script: {str(e)}\n{traceback.format_exc()}")
            self.post_install_finished.emit(False, f"Error running post-install script: {str(e)}")
        finally:
            if target_script_path_in_chroot_tmp and os.path.exists(target_script_path_in_chroot_tmp):
                try:
                    os.remove(target_script_path_in_chroot_tmp)
                    self.post_install_log.emit(f"Cleaned up temporary script: {target_script_path_in_chroot_tmp}")
                except OSError as e:
                    self.post_install_log.emit(f"Warning: Could not remove temporary script {target_script_path_in_chroot_tmp}: {e}")


class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.archinstall_json_config_data = {}
        self.post_install_script_path = ""
        self.init_ui()

    def init_ui(self):
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
        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk (Uses archinstall's default auto-partitioning)")
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("Wipes disk and lets archinstall create its default layout.\nUncheck to use pre-existing partitions (advanced, requires manual setup).")
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

    def create_form_row(self, label_text, widget):
        row_layout = QHBoxLayout(); label = QLabel(label_text); label.setFixedWidth(120)
        row_layout.addWidget(label); row_layout.addWidget(widget); return row_layout

    def scan_and_populate_disks(self):
        self.log_output.append("Scanning for disks...")
        QApplication.processEvents()
        self.disk_combo.clear()
        try:
            cmd = ['lsblk', '-J', '-b', '-p', '-o', 'NAME,SIZE,TYPE,MODEL,PATH,TRAN,PKNAME,RO,RM']
            self.log_output.append(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
            
            data = json.loads(result.stdout)
            disks_found = 0
            self.log_output.append("Filtering block devices for installation targets:")

            for device in data.get('blockdevices', []):
                name = device.get('name', 'N/A')
                dtype = device.get('type', 'N/A')
                ro = device.get('ro', True) 
                rm = device.get('rm', True) 
                pkname = device.get('pkname', None)
                tran = device.get('tran', 'N/A')

                log_line = (f"  Checking: {name}, Type: {dtype}, RO: {ro}, RM: {rm}, "
                            f"PKNAME: {pkname}, Size: {device.get('size', 0)}, "
                            f"Model: {device.get('model', 'N/A')}, Tran: {tran}")
                
                if dtype == 'disk' and not ro and not pkname:
                    model = device.get('model', 'Unknown Model')
                    size_bytes = int(device.get('size', 0))

                    if size_bytes < 10 * (1024**3):
                        self.log_output.append(log_line + f" -> Skipping (Too small: {size_bytes / (1024**3):.2f} GB)")
                        continue
                    
                    is_root_device = False
                    if device.get('children'):
                        for child in device.get('children', []):
                            if child.get('mountpoint') == '/' or \
                               (child.get('mountpoints') and '/' in child.get('mountpoints')):
                                is_root_device = True; break
                    if device.get('mountpoint') == '/' or \
                       (device.get('mountpoints') and '/' in device.get('mountpoints')):
                        is_root_device = True
                    
                    if is_root_device:
                        self.log_output.append(log_line + " -> Skipping (Appears to be current root FS)")
                        continue

                    display_text = f"{name} - {model} ({size_bytes / (1024**3):.2f} GB)"
                    self.disk_combo.addItem(display_text, userData={"path": name, "size_bytes": size_bytes})
                    self.log_output.append(log_line + f" -> Added to dropdown: {display_text}")
                    disks_found += 1
                else:
                    self.log_output.append(log_line + " -> Skipping (Does not meet criteria)")
            
            if disks_found == 0:
                msg = "No suitable installation disks found after filtering. Ensure a non-read-only, non-partition, sufficiently large disk is available and not the current OS disk."
                self.log_output.append(msg); QMessageBox.warning(self, "Disk Scan", msg)
            else:
                self.log_output.append(f"Disk scan complete. Found {disks_found} suitable disk(s).")

        except FileNotFoundError:
            self.log_output.append("Error: `lsblk` command not found."); QMessageBox.critical(self, "Error", "`lsblk` not found.")
        except subprocess.CalledProcessError as e:
            self.log_output.append(f"Error scanning disks with lsblk: {e.stderr}"); QMessageBox.warning(self, "Disk Scan Error", f"Could not scan disks: {e.stderr}")
        except json.JSONDecodeError as e:
            self.log_output.append(f"Error parsing lsblk JSON output: {e}"); QMessageBox.warning(self, "Disk Scan Error", "Failed to parse disk info.")
        except Exception as e:
            self.log_output.append(f"Unexpected error during disk scan: {str(e)}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Disk Scan Error", f"An unexpected error occurred: {str(e)}")


    def select_post_install_script(self):
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getOpenFileName(self, "Select Post-Installation Bash Script", "", "Bash Scripts (*.sh);;All Files (*)", options=options)
        if filePath:
            self.post_install_script_path = filePath
            self.post_install_script_label.setText(f"Script: {os.path.basename(filePath)}")
            self.log_output.append(f"Post-install script selected: {filePath}")
        else:
            self.post_install_script_path = ""; self.post_install_script_label.setText("No script selected.")

    def update_log(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible(); QApplication.processEvents()

    def start_installation_process(self):
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        locale_str = self.locale_input.text().strip()
        kb_layout = self.keyboard_layout_input.text().strip()
        timezone = self.timezone_input.text().strip()
        selected_disk_index = self.disk_combo.currentIndex()
        profile_name = self.profile_combo.currentText() 
        wipe_disk_checked = self.wipe_disk_checkbox.isChecked()

        if selected_disk_index < 0:
            QMessageBox.warning(self, "Input Error", "Please select a target disk."); return
        disk_data = self.disk_combo.itemData(selected_disk_index)
        if not disk_data or "path" not in disk_data or "size_bytes" not in disk_data:
            QMessageBox.critical(self, "Disk Error", "Selected disk data is invalid. Please re-scan disks."); return
        disk_path_str = disk_data["path"]
        disk_size_bytes = disk_data["size_bytes"]

        if not all([hostname, username, password, locale_str, kb_layout, disk_path_str, timezone]):
            QMessageBox.warning(self, "Input Error", "Please fill in all required fields."); return
        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match."); return

        confirm_msg_detail = f"<b>TARGET DISK: {disk_path_str}</b> ({disk_size_bytes / (1024**3):.2f} GB)\n"
        confirm_msg_detail += f"Hostname: {hostname}\n"
        confirm_msg_detail += f"Username: {username}\n"
        confirm_msg_detail += f"<b>!!! IMPORTANT WORKAROUND NOTED IN CODE !!!</b>\n"
        confirm_msg_detail += f"The selected profile ('{profile_name}') "
        confirm_msg_detail += f"<b>WILL NOT BE INSTALLED</b> by this configuration.\n"
        confirm_msg_detail += f"Only a minimal command-line system will be set up.\n"
        confirm_msg_detail += f"You must install the desktop environment manually after first boot.\n\n"

        if wipe_disk_checked:
            confirm_msg_detail += f"<b>ALL DATA ON {disk_path_str} WILL BE ERASED. Archinstall will use its default partitioning scheme.</b>\n"
        else:
            confirm_msg_detail += f"<b>The disk {disk_path_str} will NOT be wiped. Using existing partitions (ADVANCED - ensure correct setup).</b>\n"
        confirm_msg_detail += "Proceed with this MINIMAL (no desktop) installation?"

        reply = QMessageBox.question(self, 'Confirm MINIMAL Installation', confirm_msg_detail, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.log_output.append("Installation cancelled by user."); return

        self.install_button.setEnabled(False); self.log_output.clear()
        self.log_output.append("Preparing MINIMAL JSON configuration (NO PROFILE) for archinstall...")

        is_efi = os.path.exists("/sys/firmware/efi")
        self.log_output.append(f"EFI System Detected: {is_efi}")
        sys_lang_base = locale_str.split('.')[0] if '.' in locale_str else locale_str

        minimal_config_data = {
            # --- MODIFICATION: Added "script" key ---
            "script": "default_installer", 
            "silent": True, 

            "hostname": hostname,
            "locale_config": {
                "sys_lang": sys_lang_base,
                "kb_layout": kb_layout
            },
            "timezone": timezone,
            "bootloader": "systemd-boot" if is_efi else "grub",
            "users": [{"username": username, "password": password, "sudo": True}],
            "packages": [], 
            "ntp": True,
            "swap": True,
        }
        if is_efi:
             minimal_config_data['efi'] = True
        
        if wipe_disk_checked:
            minimal_config_data["harddrives"] = [disk_path_str]
            minimal_config_data["disk_encryption"] = None 
            minimal_config_data["disk_layouts"] = {
                 disk_path_str: { "wipe": True, "layout_type": "auto" }
            }
            self.log_output.append(f"Minimal config: Wiping {disk_path_str} and using auto layout.")
        else:
            minimal_config_data["harddrives"] = [disk_path_str]
            minimal_config_data["disk_layouts"] = {
                 disk_path_str: { "wipe": False }
            }
            self.log_output.append(f"Minimal config: Using existing partitions on {disk_path_str} (wipe=False). Ensure setup is correct.")

        final_packages = ["networkmanager", "sudo", "nano", "base", "linux", "linux-firmware"]
        if not is_efi:
            final_packages.append("grub")
        else:
            final_packages.append("efibootmgr")
        for category, checkbox in self.app_category_checkboxes.items():
            if checkbox.isChecked():
                final_packages.extend(APP_CATEGORIES[category])
        minimal_config_data["packages"] = list(set(final_packages))

        self.archinstall_json_config_data = minimal_config_data
        self.log_output.append(f"Minimal JSON Configuration prepared for Archinstall thread:\n{json.dumps(self.archinstall_json_config_data, indent=2)}")

        self.installer_thread = ArchinstallThread(self.archinstall_json_config_data)
        self.installer_thread.installation_log.connect(self.update_log)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message):
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Installation Complete", "Arch Linux MINIMAL base installation finished successfully!\n\nRemember to install a desktop environment and other software manually after booting.")
            if self.post_install_script_path:
                self.log_output.append("\n--- Proceeding to post-installation script. ---")
                archinstall_mount_point = self.archinstall_json_config_data.get("mount_point", "/mnt/archinstall")
                self.run_post_install_script(archinstall_mount_point)
            else:
                self.install_button.setEnabled(True); self.log_output.append("No post-install script selected.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Installation failed.\n{message}")
            self.install_button.setEnabled(True)

    def run_post_install_script(self, target_mount_point):
        self.log_output.append(f"\n--- Starting Post-Installation Script (Target: {target_mount_point}) ---")
        self.post_installer_thread = PostInstallThread(self.post_install_script_path, target_mount_point=target_mount_point)
        self.post_installer_thread.post_install_log.connect(self.update_log)
        self.post_installer_thread.post_install_finished.connect(self.on_post_install_finished)
        self.post_installer_thread.start()

    def on_post_install_finished(self, success, message):
        self.update_log(message)
        if success: QMessageBox.information(self, "Post-Install Complete", "Post-installation script finished.")
        else: QMessageBox.warning(self, "Post-Install Issue", f"Post-install script reported issues.\n{message}")
        self.install_button.setEnabled(True)
        self.log_output.append("Mai Bloom OS setup process finished (minimal system installed).")


if __name__ == '__main__':
    if not check_root():
        temp_app_for_msgbox = QApplication.instance()
        if not temp_app_for_msgbox:
            temp_app_for_msgbox = QApplication(sys.argv)
        
        QMessageBox.critical(None, "Root Access Required", "This application must be run as root (or with sudo).")
        print("Error: This application must be run as root (or with sudo). Exiting.")
        sys.exit(1)
        
    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())
