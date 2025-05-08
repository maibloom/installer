import sys
import subprocess
import json # Still useful for lsblk output
import os
import traceback
import time # For any necessary small delays or user feedback
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, # QComboBox for disks
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout, QSplitter)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# --- App Configuration ---
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "code", "python", "gcc", "gdb", "base-devel"], # Using 'code' (VSCode OSS)
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"],
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}
DEFAULT_DESKTOP_ENVIRONMENT_NAME = "KDE Plasma"
MOUNT_POINT = Path("/mnt/maibloom_install") # Custom mount point to avoid conflict if /mnt is used by ISO

def check_root():
    return os.geteuid() == 0

# --- Installer Engine Thread (Direct Command Orchestration) ---
class InstallerEngineThread(QThread):
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str)
    disk_scan_complete = pyqtSignal(dict)

    def __init__(self, installation_settings):
        super().__init__()
        self.settings = installation_settings
        self._running = True

    def log(self, message, level="INFO"):
        # print(f"LOG [{level}]: {message}") # Optional: print to console as well
        self.installation_log.emit(f"[{level}] {message}")
        QApplication.processEvents() # Keep UI slightly responsive during log updates

    def stop(self):
        self.log("Stop request received. Attempting to halt ongoing operations (best effort).", "WARN")
        self._running = False

    def run_command(self, command_list, check=True, capture_output=False, text=True, shell=False, input_data=None, cwd=None):
        """Helper to run subprocess commands and log them."""
        if not self._running and check: # Don't start new critical commands if stopping
            self.log(f"Skipping command due to stop request: {' '.join(command_list)}", "WARN")
            raise subprocess.CalledProcessError(returncode=-1, cmd=command_list, output="Installation stopped by user.")

        self.log(f"Executing: {' '.join(command_list)}", "CMD")
        try:
            process = subprocess.run(
                command_list,
                check=check, # Will raise CalledProcessError if non-zero exit and check=True
                capture_output=capture_output,
                text=text,
                shell=shell,
                input=input_data if input_data else None,
                cwd=cwd
            )
            if capture_output:
                if process.stdout: self.log(f"STDOUT: {process.stdout.strip()}", "CMD_OUT")
                if process.stderr: self.log(f"STDERR: {process.stderr.strip()}", "CMD_ERR") # Log even if successful
            return process
        except subprocess.CalledProcessError as e:
            self.log(f"Command failed: {' '.join(e.cmd)}", "ERROR")
            if e.stdout: self.log(f"Failed STDOUT: {e.stdout.strip()}", "ERROR")
            if e.stderr: self.log(f"Failed STDERR: {e.stderr.strip()}", "ERROR")
            raise # Re-raise the exception to be caught by the main run() method's error handler
        except FileNotFoundError as e:
            self.log(f"Command not found: {command_list[0]} - {e}", "ERROR")
            raise

    def arch_chroot_command(self, command_list_in_chroot, input_data=None):
        """Helper to run commands within the arch-chroot environment."""
        base_cmd = ["arch-chroot", str(MOUNT_POINT)]
        full_cmd = base_cmd + command_list_in_chroot
        return self.run_command(full_cmd, input_data=input_data)

    def run_disk_scan(self): # Called by GUI
        self.log("Starting disk scan using lsblk...")
        processed_disks = {}
        try:
            cmd = ['lsblk', '-J', '-b', '-p', '-o', 'NAME,SIZE,TYPE,MODEL,RO,RM,PKNAME,PATH,TRAN']
            result = self.run_command(cmd, capture_output=True)
            data = json.loads(result.stdout)
            
            self.log(f"Found {len(data.get('blockdevices', []))} block devices. Filtering...", "DEBUG")

            for device in data.get('blockdevices', []):
                dev_path_str = device.get('path', device.get('name')) # path is preferred due_to -p
                dev_type = device.get('type', 'unknown').lower()
                dev_ro = device.get('ro', True)
                dev_pkname = device.get('pkname', None)
                dev_model = device.get('model', 'Unknown Model')
                dev_size_bytes = int(device.get('size', 0))
                dev_tran = device.get('tran', 'unknown').lower()

                log_line = (f"  Checking: {dev_path_str}, Type: {dev_type}, RO: {dev_ro}, PKNAME: {dev_pkname}, "
                            f"Size: {dev_size_bytes}, Model: {dev_model}, Tran: {dev_tran}")

                if dev_type == 'disk' and not dev_ro and not dev_pkname:
                    if dev_size_bytes < 20 * (1024**3): # Min 20GB for a DE install
                        self.log(log_line + f" -> Skipping (Too small: {dev_size_bytes / (1024**3):.2f} GB)", "DEBUG")
                        continue
                    
                    is_root_fs_device = False # Heuristic to skip live ISO medium
                    # ... (root fs check logic can be added here if needed, simplified for now) ...

                    processed_disks[dev_path_str] = {
                        "model": dev_model,
                        "size": f"{dev_size_bytes / (1024**3):.2f} GB",
                        "path": dev_path_str
                    }
                    self.log(log_line + " -> Suitable disk found.", "DEBUG")
                else:
                    self.log(log_line + " -> Skipping.", "DEBUG")
            
            if not processed_disks: self.log("No suitable disks found after filtering.", "WARN")
            self.disk_scan_complete.emit(processed_disks)

        except Exception as e: # Catch lsblk errors or JSON parsing errors
            self.log(f"Error during disk scan: {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")
            self.disk_scan_complete.emit({})

    def run(self): # This runs in the QThread
        self.log(f"Installation started for {DEFAULT_DESKTOP_ENVIRONMENT_NAME}.")
        disk_path = Path(self.settings.get("target_disk_path"))
        wipe_disk = self.settings.get("wipe_disk")
        hostname = self.settings.get("hostname")
        username = self.settings.get("username")
        user_password = self.settings.get("password") # Will be used for user and root
        locale_full = self.settings.get("locale", "en_US.UTF-8")
        locale_lang = locale_full.split('.')[0] # e.g., en_US
        kb_layout = self.settings.get("kb_layout", "us")
        timezone = self.settings.get("timezone", "UTC")
        is_efi = self.settings.get("is_efi", True) # Assume EFI by default for modern systems

        # Define partition paths (these will be relative to /dev usually)
        # These are determined *after* sgdisk runs if it uses default numbering.
        # For simplicity, we'll assume /dev/disk_name1, /dev/disk_name2, /dev/disk_name3
        # A more robust way is to use PARTUUIDs or labels after creating them.
        # For now, relying on predictable partition numbering from sgdisk.
        esp_partition = Path(f"{disk_path}1")
        swap_partition = Path(f"{disk_path}2")
        root_partition = Path(f"{disk_path}3")
        # If disk_path is like /dev/nvme0n1, partitions become /dev/nvme0n1p1 etc.
        if "nvme" in disk_path.name or "mmcblk" in disk_path.name:
            esp_partition = Path(f"{disk_path}p1")
            swap_partition = Path(f"{disk_path}p2")
            root_partition = Path(f"{disk_path}p3")

        try:
            # === 0. Pre-checks (Optional) ===
            self.log("Checking internet connection (conceptual)...") # ping -c 1 archlinux.org
            self.log(f"EFI mode detected: {is_efi}") # From GUI

            if not self._running: raise InterruptedError("Installation stopped by user request.")

            # === 1. Disk Partitioning (UEFI/GPT assumed) ===
            if wipe_disk:
                self.log(f"Wiping and partitioning disk: {disk_path}")
                swap_size_mb = self.settings.get("swap_size_gb", 4) * 1024 # Default 4GB swap
                
                self.run_command(["swapoff", "-a"], check=False) # Turn off any existing swap on the target
                self.run_command(["umount", "-R", str(MOUNT_POINT)], check=False) # Ensure mount point is clear

                self.run_command(["sgdisk", "-Z", str(disk_path)]) # Zap all partitions
                self.run_command(["sgdisk", "-n", f"1:0:+550M", "-t", "1:ef00", "-c", "1:EFI System Partition", str(disk_path)])
                self.run_command(["sgdisk", "-n", f"2:0:+{swap_size_mb}M", "-t", "2:8200", "-c", "2:Linux swap", str(disk_path)])
                self.run_command(["sgdisk", "-n", "3:0:0", "-t", "3:8300", "-c", "3:Linux root", str(disk_path)])
                self.run_command(["partprobe", str(disk_path)]) # Inform kernel of partition table changes
                time.sleep(2) # Give kernel a moment
                self.log("Disk partitioning complete.")
            else:
                self.log("Skipping disk wipe and partitioning (user choice). Assuming pre-partitioned.", "WARN")
                # User needs to ensure esp_partition, swap_partition, root_partition variables correctly point to existing ones.
                # This part is advanced and requires user to map their existing parts to roles.
                # For this automated script, focusing on wipe_disk is simpler.

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 2. Formatting Partitions ===
            self.log("Formatting partitions...")
            self.run_command(["mkfs.fat", "-F32", str(esp_partition)])
            self.run_command(["mkswap", str(swap_partition)])
            self.run_command(["mkfs.ext4", "-F", str(root_partition)]) # -F to force if already formatted
            self.log("Formatting complete.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 3. Mounting Filesystems ===
            self.log("Mounting filesystems...")
            self.run_command(["mount", str(root_partition), str(MOUNT_POINT)])
            
            esp_mount_path = MOUNT_POINT / "boot" / "efi" # For GRUB with --efi-directory=/boot/efi
            # Or MOUNT_POINT / "boot" if systemd-boot is directly installing to /boot
            # Let's use /boot/efi as it's common for GRUB.
            self.run_command(["mkdir", "-p", str(esp_mount_path)])
            self.run_command(["mount", str(esp_partition), str(esp_mount_path)])
            
            self.run_command(["swapon", str(swap_partition)])
            self.log("Filesystems mounted.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 4. Pacstrap (Install Base, KDE, and Additional Packages) ===
            self.log("Running pacstrap. This will take a significant amount of time...")
            base_packages = ["base", "linux", "linux-firmware", "base-devel", "networkmanager", "sudo", "nano"]
            kde_packages = ["plasma-meta", "sddm", "konsole", "dolphin", "packagekit-qt5", "ark", "gwenview", "okular"] # A good set for KDE
            bootloader_packages = []
            if is_efi:
                bootloader_packages.extend(["grub", "efibootmgr"]) # os-prober optional
            else: # BIOS (less common for new installs but for completeness)
                bootloader_packages.append("grub") 

            all_packages = list(set(base_packages + kde_packages + bootloader_packages + self.settings.get("additional_packages", [])))
            
            self.log(f"Pacstrapping with packages: {', '.join(all_packages)}")
            self.run_command(["pacstrap", "-K", str(MOUNT_POINT)] + all_packages) # -K initializes keyring
            self.log("Pacstrap complete.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 5. Generate fstab ===
            self.log("Generating fstab...")
            with open(MOUNT_POINT / "etc" / "fstab", "a") as fstab_file:
                process = self.run_command(["genfstab", "-U", str(MOUNT_POINT)], capture_output=True)
                fstab_file.write(process.stdout)
            self.log("fstab generated.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 6. Chroot and System Configuration ===
            self.log("Configuring the installed system (inside chroot)...")
            
            # Timezone
            self.arch_chroot_command(["ln", "-sf", f"/usr/share/zoneinfo/{timezone}", "/etc/localtime"])
            self.arch_chroot_command(["hwclock", "--systohc"])
            self.log(f"Timezone set to {timezone}.")

            # Locale
            self.run_command(["sed", "-i", f"s/^#{locale_full}/{locale_full}/", str(MOUNT_POINT / "etc" / "locale.gen")])
            self.arch_chroot_command(["locale-gen"])
            with open(MOUNT_POINT / "etc" / "locale.conf", "w") as f: f.write(f"LANG={locale_full}\n")
            self.log(f"Locale set to {locale_full}.")

            # Keyboard layout
            with open(MOUNT_POINT / "etc" / "vconsole.conf", "w") as f: f.write(f"KEYMAP={kb_layout}\n")
            self.log(f"Keyboard layout set to {kb_layout}.")

            # Hostname
            with open(MOUNT_POINT / "etc" / "hostname", "w") as f: f.write(f"{hostname}\n")
            with open(MOUNT_POINT / "etc" / "hosts", "w") as f:
                f.write("127.0.0.1 localhost\n")
                f.write("::1       localhost\n")
                f.write(f"127.0.1.1 {hostname}.localdomain {hostname}\n")
            self.log(f"Hostname set to {hostname}.")

            # Passwords (Root and User) - using chpasswd for non-interactivity
            self.log("Setting root and user passwords...")
            self.arch_chroot_command(["chpasswd"], input_data=f"root:{user_password}\n")
            self.log("Root password set.")
            self.arch_chroot_command(["useradd", "-m", "-G", "wheel", "-s", "/bin/bash", username]) # Add user to wheel, set bash
            self.arch_chroot_command(["chpasswd"], input_data=f"{username}:{user_password}\n")
            self.log(f"User '{username}' created and password set.")

            # Sudoers (uncomment %wheel group)
            self.run_command(["sed", "-i", "s/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/", str(MOUNT_POINT / "etc" / "sudoers")])
            self.log("Sudoers configured for wheel group.")

            # Bootloader (GRUB for UEFI example)
            if is_efi:
                self.log("Installing GRUB for UEFI...")
                # ESP was mounted at MOUNT_POINT / "boot" / "efi", so in chroot it's /boot/efi
                self.arch_chroot_command(["grub-install", "--target=x86_64-efi", "--efi-directory=/boot/efi", "--bootloader-id=MaiBloomOS", "--recheck"])
                self.arch_chroot_command(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
                self.log("GRUB installed and configured.")
            else:
                self.log("Installing GRUB for BIOS/MBR...", "WARN") # Simpler MBR example
                self.arch_chroot_command(["grub-install", "--target=i386-pc", str(disk_path)]) # Install to disk MBR
                self.arch_chroot_command(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
                self.log("GRUB for BIOS installed.", "WARN")

            # Enable Services (NetworkManager and SDDM for KDE)
            self.log("Enabling essential services (NetworkManager, SDDM)...")
            self.arch_chroot_command(["systemctl", "enable", "NetworkManager.service"])
            self.arch_chroot_command(["systemctl", "enable", "sddm.service"]) # SDDM for KDE Plasma
            self.log("Services enabled.")
            
            if not self._running: raise InterruptedError("Installation stopped.")

            # === 7. Unmount and Finish ===
            self.log("Finalizing... Unmounting file systems.")
            # Unmounting should be done outside the thread if possible, or very carefully.
            # For simplicity in thread, just log. Real unmounting is critical.
            # self.run_command(["umount", "-R", str(MOUNT_POINT)]) # This can be risky if chroot is still active

            self.log("Mai Bloom OS with KDE Plasma Installation process completed successfully!")
            self.installation_finished.emit(True, f"Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME}) installed successfully!")

        except subprocess.CalledProcessError as e:
            self.log(f"A command failed during installation: {e}", "CRITICAL_ERROR")
            self.installation_finished.emit(False, f"Installation failed at command: {' '.join(e.cmd)}\nError: {e.stderr or e.stdout or e}")
        except InterruptedError as e:
            self.log(f"Installation process was interrupted: {e}", "WARN")
            self.installation_finished.emit(False, f"Installation interrupted: {e}")
        except Exception as e:
            self.log(f"An critical error occurred: {e}", "CRITICAL_ERROR")
            self.log(traceback.format_exc(), "CRITICAL_ERROR")
            self.installation_finished.emit(False, f"A critical error occurred: {e}")
        finally:
            self.log("Attempting to clean up mounts (best effort)...", "INFO")
            # It's safer to unmount from outside the chroot context and after all operations
            # subprocess.run(["umount", "-R", str(MOUNT_POINT)], capture_output=True, text=True) # Best effort
            self.log("InstallerEngineThread finished.", "INFO")


# --- Main Application Window ---
class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.installation_settings = {}
        self.installer_thread = None
        self._engine_helper = InstallerEngineThread({}) 
        self._engine_helper.disk_scan_complete.connect(self.on_disk_scan_complete)
        self._engine_helper.installation_log.connect(self.update_log_output)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f'Mai Bloom OS Installer ({DEFAULT_DESKTOP_ENVIRONMENT_NAME})')
        self.setGeometry(100, 100, 850, 700)
        overall_layout = QVBoxLayout(self)

        title_label = QLabel(f"<b>Welcome to Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME}) Installation!</b>")
        title_label.setAlignment(Qt.AlignCenter)
        overall_layout.addWidget(title_label)
        overall_layout.addWidget(QLabel("<small>This installer will guide you through setting up Mai Bloom OS. It will install KDE Plasma by default.</small>"))
        
        splitter = QSplitter(Qt.Horizontal)
        overall_layout.addWidget(splitter)

        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)

        # Disk Setup
        disk_group = QGroupBox("Disk Setup")
        disk_layout_vbox = QVBoxLayout()
        self.scan_disks_button = QPushButton("Scan for Available Disks")
        self.scan_disks_button.clicked.connect(self.trigger_disk_scan)
        disk_layout_vbox.addWidget(self.scan_disks_button)
        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Select the target disk. <b>ALL DATA ON THIS DISK WILL BE ERASED if 'Wipe Disk' is checked.</b>")
        disk_layout_vbox.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk & create standard UEFI layout")
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("This will erase the entire disk and create: EFI, Swap, and Root partitions.")
        disk_layout_vbox.addWidget(self.wipe_disk_checkbox)
        disk_group.setLayout(disk_layout_vbox)
        controls_layout.addWidget(disk_group)

        # System Configuration
        system_group = QGroupBox("System & User Configuration")
        system_layout_grid = QGridLayout()
        self.hostname_input = QLineEdit("maibloom-os"); system_layout_grid.addWidget(QLabel("Hostname:"), 0, 0); system_layout_grid.addWidget(self.hostname_input, 0, 1)
        self.username_input = QLineEdit("maiuser"); system_layout_grid.addWidget(QLabel("Username:"), 1, 0); system_layout_grid.addWidget(self.username_input, 1, 1)
        self.password_input = QLineEdit(); self.password_input.setPlaceholderText("User & Root Password"); self.password_input.setEchoMode(QLineEdit.Password)
        system_layout_grid.addWidget(QLabel("User/Root Password:"), 2, 0); system_layout_grid.addWidget(self.password_input, 2, 1)
        self.locale_input = QLineEdit("en_US.UTF-8"); system_layout_grid.addWidget(QLabel("Locale (e.g., en_US.UTF-8):"), 3,0); system_layout_grid.addWidget(self.locale_input, 3,1)
        self.kb_layout_input = QLineEdit("us"); system_layout_grid.addWidget(QLabel("Keyboard Layout (e.g., us):"), 4,0); system_layout_grid.addWidget(self.kb_layout_input, 4,1)
        self.timezone_input = QLineEdit("UTC"); system_layout_grid.addWidget(QLabel("Timezone (e.g., Europe/London):"), 5,0); system_layout_grid.addWidget(self.timezone_input, 5,1)
        system_group.setLayout(system_layout_grid)
        controls_layout.addWidget(system_group)
        
        # Additional Applications
        app_group = QGroupBox(f"Additional Applications (on top of {DEFAULT_DESKTOP_ENVIRONMENT_NAME})")
        app_layout_grid = QGridLayout()
        self.app_category_checkboxes = {}
        row, col = 0,0
        for cat_name in APP_CATEGORIES.keys():
            self.app_category_checkboxes[cat_name] = QCheckBox(f"{cat_name} Apps")
            app_layout_grid.addWidget(self.app_category_checkboxes[cat_name], row, col)
            col +=1
            if col > 1: col = 0; row +=1 # 2 checkboxes per row
        app_group.setLayout(app_layout_grid)
        controls_layout.addWidget(app_group)
        
        # Post Install Script (Optional)
        post_install_group = QGroupBox("Custom Post-Installation Script (Optional)")
        post_install_layout_vbox = QVBoxLayout()
        self.post_install_script_button = QPushButton("Select Bash Script")
        self.post_install_script_button.clicked.connect(self.select_post_install_script)
        self.post_install_script_label = QLabel("No script selected.")
        post_install_layout_vbox.addWidget(self.post_install_script_button)
        post_install_layout_vbox.addWidget(self.post_install_script_label)
        post_install_group.setLayout(post_install_layout_vbox)
        controls_layout.addWidget(post_install_group)

        controls_layout.addStretch(1)
        splitter.addWidget(controls_widget)

        log_group_box = QGroupBox("Installation Log")
        log_layout_vbox = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True); self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        log_layout_vbox.addWidget(self.log_output)
        log_group_box.setLayout(log_layout_vbox)
        splitter.addWidget(log_group_box)
        splitter.setSizes([400, 450])
        
        overall_layout.addWidget(splitter)

        self.install_button = QPushButton(f"Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME})")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold;")
        self.install_button.clicked.connect(self.start_installation)
        button_layout = QHBoxLayout(); button_layout.addStretch(); button_layout.addWidget(self.install_button); button_layout.addStretch()
        overall_layout.addLayout(button_layout)
        
        self.trigger_disk_scan() # Initial scan

    def create_form_row(self, label_text, widget):
        row_layout = QHBoxLayout(); label = QLabel(label_text); label.setFixedWidth(120) # Adjusted width
        row_layout.addWidget(label); row_layout.addWidget(widget); return row_layout

    def trigger_disk_scan(self):
        self.update_log_output("GUI: Triggering disk scan...")
        self.scan_disks_button.setEnabled(False)
        self._engine_helper.run_disk_scan() # This is synchronous for now

    def on_disk_scan_complete(self, disks_data):
        self.update_log_output(f"GUI: Disk scan signal received. Found {len(disks_data)} processed disk(s).")
        self.disk_combo.clear()
        if disks_data:
            for path_key, info_dict in disks_data.items():
                display_text = f"{path_key} - {info_dict.get('model', 'N/A')} ({info_dict.get('size', 'N/A')})"
                self.disk_combo.addItem(display_text, userData=path_key)
        else:
            self.update_log_output("GUI: No suitable disks found by scan or scan failed.")
        self.scan_disks_button.setEnabled(True)

    def update_log_output(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible(); QApplication.processEvents()

    def gather_settings(self):
        settings = {}
        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0:
            self.update_log_output("Error: No target disk selected in combobox.", "ERROR")
            return None
        settings["target_disk_path"] = self.disk_combo.itemData(selected_disk_index)
        if not settings["target_disk_path"]:
            self.update_log_output("Error: Selected disk has no valid path data.", "ERROR")
            return None
            
        settings["wipe_disk"] = self.wipe_disk_checkbox.isChecked()
        settings["hostname"] = self.hostname_input.text().strip()
        settings["username"] = self.username_input.text().strip()
        settings["password"] = self.password_input.text() # User & Root password
        
        settings["locale"] = self.locale_input.text().strip()
        settings["kb_layout"] = self.kb_layout_input.text().strip()
        settings["timezone"] = self.timezone_input.text().strip()
        settings["is_efi"] = os.path.exists("/sys/firmware/efi") # Detect EFI mode
        settings["swap_size_gb"] = 4 # Example, make configurable if needed

        additional_packages = []
        for cat_name, checkbox_widget in self.app_category_checkboxes.items():
            if checkbox_widget.isChecked():
                additional_packages.extend(APP_CATEGORIES.get(cat_name, []))
        settings["additional_packages"] = list(set(additional_packages))
        
        if not settings["password"]: # Basic password check
            self.update_log_output("Error: Password cannot be empty.", "ERROR")
            return None
        if not settings["username"] or not settings["hostname"]:
            self.update_log_output("Error: Username and Hostname cannot be empty.", "ERROR")
            return None

        self.update_log_output(f"Installation settings gathered for {DEFAULT_DESKTOP_ENVIRONMENT_NAME} on {settings['target_disk_path']}")
        return settings

    def start_installation(self):
        current_settings = self.gather_settings()
        if not current_settings:
            QMessageBox.warning(self, "Configuration Incomplete", "Please fill all required fields and select a target disk.")
            return

        confirm_msg = (f"This will install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME}) on:\n"
                       f"DISK: {current_settings.get('target_disk_path','N/A')}\n"
                       f"WIPE DISK & AUTO-PARTITION (UEFI): {'YES' if current_settings.get('wipe_disk') else 'NO (Advanced - Not fully supported by this auto-script)'}\n\n"
                       f"Username: {current_settings.get('username')}\n"
                       f"Hostname: {current_settings.get('hostname')}\n"
                       f"Locale: {current_settings.get('locale')}\n\n"
                       "ALL DATA ON THE SELECTED DISK WILL BE ERASED if 'Wipe Disk' is checked.\n"
                       "Proceed with installation?")
        
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.update_log_output("Installation cancelled by user.")
            return

        self.install_button.setEnabled(False); self.scan_disks_button.setEnabled(False)
        self.log_output.clear(); self.update_log_output("Starting installation process...")

        self.installer_thread = InstallerEngineThread(current_settings)
        self.installer_thread.installation_log.connect(self.update_log_output)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message):
        self.update_log_output(f"GUI: Installation finished signal. Success: {success}, Message: {message}")
        if success:
            QMessageBox.information(self, "Installation Complete", message + "\nYou may now reboot your system.")
        else:
            QMessageBox.critical(self, "Installation Failed", message)
        self.install_button.setEnabled(True); self.scan_disks_button.setEnabled(True)
    
    def select_post_install_script(self):
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getOpenFileName(self, "Select Post-Installation Bash Script", "", "Bash Scripts (*.sh);;All Files (*)", options=options)
        if filePath:
            # This setting isn't currently used by InstallerEngineThread as it handles full setup
            # Could be passed to PostInstallThread if that's reinstated for further custom user scripts
            self.post_install_script_path = filePath 
            self.post_install_script_label.setText(f"Script: {os.path.basename(filePath)}")
            self.update_log_output(f"Custom post-install script selected: {filePath} (Note: current installer performs full setup)")
        else:
            self.post_install_script_path = ""; self.post_install_script_label.setText("No script selected.")


if __name__ == '__main__':
    if not check_root():
        app_temp = QApplication.instance();
        if not app_temp: app_temp = QApplication(sys.argv)
        QMessageBox.critical(None, "Root Access Required", "This application must be run as root (or with sudo).")
        sys.exit(1)
    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())
