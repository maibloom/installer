import sys
import subprocess
import json
import os
import traceback
import time
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
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
# Use a dedicated mount point for the installation target
MOUNT_POINT = Path("/mnt/maibloom_install") 

def check_root():
    """Checks if the script is running as root."""
    return os.geteuid() == 0

# --- Installer Engine Thread (Direct Command Orchestration) ---
class InstallerEngineThread(QThread):
    """
    This thread orchestrates the Arch Linux installation by directly calling
    standard Linux commands (lsblk, sgdisk, mkfs, mount, pacstrap, arch-chroot, etc.),
    following the general steps of the official Arch Linux Installation Guide.
    This is generally more stable than wrapping the archinstall CLI/TUI.
    """
    installation_finished = pyqtSignal(bool, str) # bool: success, str: message
    installation_log = pyqtSignal(str)            # str: log message
    disk_scan_complete = pyqtSignal(dict)         # dict: {dev_path: {info}}

    def __init__(self, installation_settings):
        super().__init__()
        self.settings = installation_settings
        self._running = True # Flag to allow stopping the thread gracefully

    def log(self, message, level="INFO"):
        """Sends a log message to the GUI."""
        # Optional: print to console as well for debugging outside GUI
        # print(f"LOG [{level}]: {message}") 
        self.installation_log.emit(f"[{level}] {message}")
        # Give the GUI event loop a chance to process the message
        QApplication.processEvents() 

    def stop(self):
        """Requests the installation process to stop."""
        self.log("Stop request received. Attempting to halt...", "WARN")
        self._running = False

    def run_command(self, command_list, check=True, capture_output=False, text=True, shell=False, input_data=None, cwd=None):
        """
        Helper function to run subprocess commands, log them, and handle errors.
        Raises subprocess.CalledProcessError if check=True and command fails.
        Raises FileNotFoundError if the command isn't found.
        """
        # Check if a stop has been requested before starting a new critical command
        if not self._running and check: 
            self.log(f"Skipping command due to stop request: {' '.join(command_list)}", "WARN")
            # Raise a specific error or return a status to indicate stoppage
            raise InterruptedError("Installation stopped by user request.") 

        command_str = ' '.join(command_list) if isinstance(command_list, list) else command_list
        self.log(f"Executing: {command_str}", "CMD")
        
        try:
            process = subprocess.run(
                command_list,
                check=check, 
                capture_output=capture_output,
                text=text,
                shell=shell,
                input=input_data if input_data else None,
                cwd=cwd,
                encoding='utf-8' # Be explicit about encoding
            )
            # Log output even on success if captured
            if capture_output:
                # Limit logged output length if necessary
                stdout_log = process.stdout.strip()
                stderr_log = process.stderr.strip()
                if stdout_log: self.log(f"STDOUT:\n{stdout_log}", "CMD_OUT")
                # Log stderr even on success as some tools print info there
                if stderr_log: self.log(f"STDERR:\n{stderr_log}", "CMD_ERR") 
            return process
        except subprocess.CalledProcessError as e:
            self.log(f"Command failed with code {e.returncode}: {command_str}", "ERROR")
            # Log captured output from the failed command
            if e.stdout: self.log(f"Failed STDOUT:\n{e.stdout.strip()}", "ERROR")
            if e.stderr: self.log(f"Failed STDERR:\n{e.stderr.strip()}", "ERROR")
            raise # Re-raise the exception to be caught by the main run() method
        except FileNotFoundError as e:
            self.log(f"Command not found: {command_list[0]} - {e}", "ERROR")
            raise
        except Exception as e: # Catch other potential subprocess errors
            self.log(f"Unexpected error running command {command_str}: {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")
            raise

    def arch_chroot_command(self, command_list_in_chroot, input_data=None):
        """Helper to run commands within the arch-chroot environment."""
        # Ensure MOUNT_POINT exists and is a directory before chrooting
        if not MOUNT_POINT.is_dir():
             raise FileNotFoundError(f"Chroot target mount point {MOUNT_POINT} does not exist or is not a directory.")
             
        base_cmd = ["arch-chroot", str(MOUNT_POINT)]
        full_cmd = base_cmd + command_list_in_chroot
        return self.run_command(full_cmd, input_data=input_data)

    def run_disk_scan(self): # Called by GUI helper instance
        """Scans for suitable disks using lsblk."""
        self.log("Starting disk scan using lsblk...")
        processed_disks = {}
        try:
            # Get device info in JSON format, request specific columns
            cmd = ['lsblk', '-J', '-b', '-p', '-o', 'NAME,SIZE,TYPE,MODEL,RO,RM,PKNAME,PATH,TRAN']
            # Run directly using subprocess, not self.run_command, as it's a query not part of install sequence
            self.log(f"Executing: {' '.join(cmd)}", "CMD")
            process = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
            data = json.loads(process.stdout)
            
            self.log(f"Found {len(data.get('blockdevices', []))} block devices. Filtering...", "DEBUG")

            for device in data.get('blockdevices', []):
                dev_path_str = device.get('path', device.get('name'))
                
                # Safely get type and tran, handling None before lower()
                type_val = device.get('type')
                dev_type = str(type_val).lower() if type_val is not None else 'unknown'
                tran_val = device.get('tran')
                dev_tran = str(tran_val).lower() if tran_val is not None else 'unknown'
                
                dev_ro = device.get('ro', True)
                dev_pkname = device.get('pkname', None) # Is it a partition?
                dev_model = device.get('model', 'Unknown Model')
                dev_size_bytes = int(device.get('size', 0))

                log_line = (f"  Checking: {dev_path_str}, Type: {dev_type}, RO: {dev_ro}, PKNAME: {dev_pkname}, "
                            f"Size: {dev_size_bytes}, Model: {dev_model}, Tran: {dev_tran}")

                # --- Filtering Logic ---
                is_suitable = True
                if dev_type != 'disk': 
                    log_line += " -> Skipping (Not a disk)"
                    is_suitable = False
                elif dev_ro:
                    log_line += " -> Skipping (Read-only)"
                    is_suitable = False
                elif dev_pkname:
                    log_line += " -> Skipping (Is a partition)"
                    is_suitable = False
                elif dev_size_bytes < 20 * (1024**3): # Min 20GB for KDE Plasma
                    log_line += f" -> Skipping (Too small: {dev_size_bytes / (1024**3):.2f} GB)"
                    is_suitable = False
                else:
                    # Basic check to avoid listing the device the live OS is potentially running from
                    try:
                        df_process = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', '--target', '/'], capture_output=True, text=True, check=True, encoding='utf-8')
                        current_root_source = df_process.stdout.strip()
                        # Resolve symlinks for comparison (e.g. /dev/mapper/xxx -> /dev/sdXY)
                        real_root_source = os.path.realpath(current_root_source)
                        real_dev_path = os.path.realpath(dev_path_str)
                        # Check if the device path is the start of the resolved root source path 
                        # (e.g., /dev/sda is the start of /dev/sda1)
                        if real_root_source.startswith(real_dev_path):
                            log_line += f" -> Skipping (Possibly related to current root FS: {real_root_source})"
                            is_suitable = False
                    except Exception as e:
                        self.log(f"Could not accurately determine current root device to exclude: {e}", "DEBUG")
                        # Proceed cautiously if root check fails

                # Add to list if suitable after all checks
                if is_suitable:
                    processed_disks[dev_path_str] = {
                        "model": dev_model,
                        "size": f"{dev_size_bytes / (1024**3):.2f} GB",
                        "path": dev_path_str
                    }
                    self.log(log_line + " -> Suitable disk found.", "DEBUG")
                else:
                    self.log(log_line, "DEBUG") # Log skipped devices
            
            if not processed_disks: self.log("No suitable disks found after filtering.", "WARN")
            self.disk_scan_complete.emit(processed_disks)

        except subprocess.CalledProcessError as e:
            self.log(f"Error running lsblk: {e.stderr or e.stdout or e}", "ERROR")
            self.disk_scan_complete.emit({}) # Emit empty dict on error
        except json.JSONDecodeError as e:
            self.log(f"Error parsing lsblk JSON output: {e}", "ERROR")
            self.disk_scan_complete.emit({})
        except Exception as e: 
            self.log(f"Error during disk scan: {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")
            self.disk_scan_complete.emit({})

    def run(self): # This runs in the QThread - Main Installation Logic
        self.log(f"Installation started for {DEFAULT_DESKTOP_ENVIRONMENT_NAME}.")
        # --- Get settings passed from GUI ---
        disk_path = Path(self.settings.get("target_disk_path"))
        wipe_disk = self.settings.get("wipe_disk")
        hostname = self.settings.get("hostname")
        username = self.settings.get("username")
        user_password = self.settings.get("password") 
        locale_full = self.settings.get("locale", "en_US.UTF-8")
        locale_lang = locale_full.split('.')[0] 
        kb_layout = self.settings.get("kb_layout", "us")
        timezone = self.settings.get("timezone", "UTC")
        is_efi = self.settings.get("is_efi", True) # Assume EFI
        swap_size_gb = self.settings.get("swap_size_gb", 4) # Default 4GB swap
        additional_packages_from_gui = self.settings.get("additional_packages", [])

        # --- Define expected partition paths (adjust if partitioning changes) ---
        # Assumes GPT partitioning using sgdisk -n 1, -n 2, -n 3 sequentially
        partition_suffix = "p" if ("nvme" in disk_path.name or "mmcblk" in disk_path.name) else ""
        esp_partition = Path(f"{disk_path}{partition_suffix}1")
        swap_partition = Path(f"{disk_path}{partition_suffix}2")
        root_partition = Path(f"{disk_path}{partition_suffix}3")

        esp_mount_path = MOUNT_POINT / "boot" / "efi" # Standard mount point for ESP when using GRUB

        try:
            # === Preparation ===
            self.log("Preparing for installation...")
            self.run_command(["swapoff", "-a"], check=False) # Ensure target swap is off
            # Force unmount previous attempts if they exist
            self.run_command(["umount", "-R", str(MOUNT_POINT)], check=False, capture_output=True) 
            os.makedirs(MOUNT_POINT, exist_ok=True) # Ensure base mount point exists

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 1. Disk Partitioning (Standard UEFI/GPT layout) ===
            if wipe_disk:
                self.log(f"Wiping and partitioning disk: {disk_path}")
                swap_size_mb = swap_size_gb * 1024
                
                self.run_command(["sgdisk", "-Z", str(disk_path)]) # Zap all partitions
                self.run_command(["sgdisk", "-n", f"1:0:+550M", "-t", "1:ef00", "-c", "1:EFI System Partition", str(disk_path)])
                self.run_command(["sgdisk", "-n", f"2:0:+{swap_size_mb}M", "-t", "2:8200", "-c", "2:Linux swap", str(disk_path)])
                self.run_command(["sgdisk", "-n", "3:0:0", "-t", "3:8300", "-c", "3:Linux root", str(disk_path)]) # Use remaining space
                self.run_command(["partprobe", str(disk_path)]) # Inform kernel
                time.sleep(3) # Give kernel time to recognize new partitions
                self.log("Disk partitioning complete.")
            else:
                self.log("Skipping disk wipe and partitioning (user choice).", "WARN")
                # If not wiping, we assume esp_partition, swap_partition, root_partition already exist
                # and the user knows what they are doing. Validation could be added here.

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 2. Formatting Partitions ===
            self.log("Formatting partitions...")
            # Format ESP as FAT32
            self.run_command(["mkfs.fat", "-F32", str(esp_partition)])
            # Format swap
            self.run_command(["mkswap", str(swap_partition)])
            # Format root as Ext4 (use -F to force even if it contains data - expected after wipe)
            self.run_command(["mkfs.ext4", "-F", str(root_partition)]) 
            self.log("Formatting complete.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 3. Mounting Filesystems ===
            self.log("Mounting filesystems...")
            self.run_command(["mount", str(root_partition), str(MOUNT_POINT)])
            # Create ESP mount point and mount ESP
            self.run_command(["mkdir", "-p", str(esp_mount_path)])
            self.run_command(["mount", str(esp_partition), str(esp_mount_path)])
            # Activate swap
            self.run_command(["swapon", str(swap_partition)])
            self.log(f"Filesystems mounted at {MOUNT_POINT}.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 4. Pacstrap (Install Base, KDE, Bootloader, Additional Packages) ===
            self.log("Running pacstrap. This will take a significant amount of time...")
            # Core system packages
            base_packages = ["base", "linux", "linux-firmware", "base-devel", "networkmanager", "sudo", "nano"]
            # KDE Plasma packages (adjust as needed for desired components)
            kde_packages = ["plasma-meta", "sddm", "konsole", "dolphin", "ark", "packagekit-qt5"] # Includes essentials
            # Bootloader packages (GRUB UEFI assumed)
            bootloader_packages = ["grub", "efibootmgr"] # os-prober is optional
            
            # Combine all package lists, ensuring uniqueness
            all_packages = list(set(base_packages + kde_packages + bootloader_packages + additional_packages_from_gui))
            
            self.log(f"Pacstrapping with {len(all_packages)} total unique packages...")
            # Use -K to init keyring, essential for first pacstrap on new mount
            self.run_command(["pacstrap", "-K", str(MOUNT_POINT)] + all_packages) 
            self.log("Pacstrap complete.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 5. Generate fstab ===
            self.log("Generating fstab...")
            # Append fstab entries to the file inside the new root
            with open(MOUNT_POINT / "etc" / "fstab", "ab") as fstab_file: # Open in append binary mode
                process = self.run_command(["genfstab", "-U", str(MOUNT_POINT)], capture_output=True, text=False) # Capture bytes
                fstab_file.write(process.stdout) # Write captured bytes
            self.log("fstab generated.")

            if not self._running: raise InterruptedError("Installation stopped.")

            # === 6. Chroot and System Configuration ===
            self.log("Configuring the installed system (inside chroot)...")
            
            # Timezone
            self.arch_chroot_command(["ln", "-sf", f"/usr/share/zoneinfo/{timezone}", "/etc/localtime"])
            self.arch_chroot_command(["hwclock", "--systohc"])
            self.log(f"Timezone set: {timezone}")

            # Locale
            # Use sed within chroot to uncomment the locale
            self.arch_chroot_command(["sed", "-i", f"s/^#\\({locale_full}.*\\)/\\1/", "/etc/locale.gen"])
            self.arch_chroot_command(["locale-gen"])
            # Create locale.conf
            self.run_command(["bash", "-c", f"echo 'LANG={locale_full}' > {MOUNT_POINT}/etc/locale.conf"])
            self.log(f"Locale set: {locale_full}")

            # Keyboard layout
            self.run_command(["bash", "-c", f"echo 'KEYMAP={kb_layout}' > {MOUNT_POINT}/etc/vconsole.conf"])
            self.log(f"Keyboard layout set: {kb_layout}")

            # Hostname
            self.run_command(["bash", "-c", f"echo '{hostname}' > {MOUNT_POINT}/etc/hostname"])
            # Configure /etc/hosts
            hosts_content = f"127.0.0.1 localhost\n::1       localhost\n127.0.1.1 {hostname}.localdomain {hostname}\n"
            self.run_command(["bash", "-c", f"echo -e '{hosts_content}' > {MOUNT_POINT}/etc/hosts"]) # Use echo -e for newlines
            self.log(f"Hostname set: {hostname}")

            # Passwords (using chpasswd)
            self.log("Setting root and user passwords...")
            self.arch_chroot_command(["chpasswd"], input_data=f"root:{user_password}\n")
            self.log("Root password set.")
            # Create user (ensure group 'wheel' exists via base-devel or add user utils package if needed)
            self.arch_chroot_command(["useradd", "-m", "-G", "wheel", "-s", "/bin/bash", username]) 
            self.arch_chroot_command(["chpasswd"], input_data=f"{username}:{user_password}\n")
            self.log(f"User '{username}' created, added to 'wheel', password set.")

            # Sudoers (uncomment %wheel group using sed in chroot)
            self.arch_chroot_command(["sed", "-i", "s/^# %wheel ALL=(ALL:ALL) ALL/%wheel ALL=(ALL:ALL) ALL/", "/etc/sudoers"])
            self.log("Sudoers configured.")

            # Bootloader (GRUB for UEFI example)
            if is_efi:
                self.log("Installing GRUB for UEFI...")
                # Ensure mount point /boot/efi exists inside chroot before installing
                self.arch_chroot_command(["mkdir", "-p", "/boot/efi"])
                # Ensure ESP is mounted at /boot/efi via fstab before mkconfig (genfstab should have done this)
                # Install GRUB to ESP
                self.arch_chroot_command([
                    "grub-install", 
                    "--target=x86_64-efi", 
                    f"--efi-directory={esp_mount_path.relative_to(MOUNT_POINT)}", # Path relative to chroot root, e.g., /boot/efi
                    "--bootloader-id=MaiBloomOS", 
                    "--recheck" # Force update of firmware entries
                ])
                # Generate grub config
                self.arch_chroot_command(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
                self.log("GRUB installed and configured for UEFI.")
            else:
                self.log("BIOS system detected. Installing GRUB for BIOS/MBR...", "WARN")
                # Install GRUB to MBR
                self.arch_chroot_command(["grub-install", "--target=i386-pc", str(disk_path)]) 
                self.arch_chroot_command(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
                self.log("GRUB for BIOS installed.", "WARN")

            # Enable Services (NetworkManager and SDDM for KDE)
            self.log("Enabling essential services (NetworkManager, SDDM)...")
            self.arch_chroot_command(["systemctl", "enable", "NetworkManager.service"])
            self.arch_chroot_command(["systemctl", "enable", "sddm.service"]) 
            self.log("NetworkManager and SDDM enabled.")
            
            if not self._running: raise InterruptedError("Installation stopped.")

            self.log("System configuration inside chroot complete.")
            # === End of Chroot operations ===

            # === 7. Unmount and Finish ===
            self.log("Finalizing installation...")
            # Unmounting is crucial but done outside the thread for safety,
            # Here we just log completion.
            
            self.log(f"Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME}) installation process finished!")
            self.installation_finished.emit(True, f"Installation successful! You can now reboot into Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME}).")

        except subprocess.CalledProcessError as e:
            self.log(f"A command failed with error code {e.returncode}: {' '.join(e.cmd)}", "CRITICAL_ERROR")
            self.log(f"Error Output: {e.stderr or e.stdout or '<no output>'}", "CRITICAL_ERROR")
            self.installation_finished.emit(False, f"Installation failed at command: {' '.join(e.cmd)}\nCheck log for details.")
        except InterruptedError as e:
            self.log(f"Installation process was interrupted: {e}", "WARN")
            self.installation_finished.emit(False, f"Installation interrupted: {e}")
        except FileNotFoundError as e:
             self.log(f"A required command was not found: {e}", "CRITICAL_ERROR")
             self.installation_finished.emit(False, f"Missing command: {e}. Ensure core utils and arch-install-scripts are installed.")
        except Exception as e:
            self.log(f"An unexpected critical error occurred: {e}", "CRITICAL_ERROR")
            self.log(traceback.format_exc(), "CRITICAL_ERROR")
            self.installation_finished.emit(False, f"A critical error occurred: {e}")
        finally:
            # Unmounting should ideally happen *after* the thread finishes and signals completion/failure.
            # Attempting it here can be problematic if chroot operations failed mid-way.
            # It's better handled externally or with extreme care.
            self.log("InstallerEngineThread finished execution. Manual unmount recommended if errors occurred.", "INFO")
            # Example (risky here): self.run_command(["umount", "-R", str(MOUNT_POINT)], check=False)


# --- Main Application Window ---
class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.installation_settings = {}
        self.installer_thread = None
        # Helper instance for calling run_disk_scan from GUI thread
        self._engine_helper = InstallerEngineThread({}) 
        self._engine_helper.disk_scan_complete.connect(self.on_disk_scan_complete)
        self._engine_helper.installation_log.connect(self.update_log_output) # Log scan messages too
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f'Mai Bloom OS Installer ({DEFAULT_DESKTOP_ENVIRONMENT_NAME})')
        self.setGeometry(100, 100, 850, 700)
        overall_layout = QVBoxLayout(self)

        title_label = QLabel(f"<b>Welcome to Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME}) Installation!</b>")
        title_label.setAlignment(Qt.AlignCenter)
        overall_layout.addWidget(title_label)
        overall_layout.addWidget(QLabel("<small>This installer uses standard Arch Linux commands to install Mai Bloom OS with KDE Plasma.</small>"))
        
        splitter = QSplitter(Qt.Horizontal)
        overall_layout.addWidget(splitter)

        # --- Left Pane: Controls ---
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)

        # Disk Setup
        disk_group = QGroupBox("1. Disk Setup")
        disk_layout_vbox = QVBoxLayout()
        self.scan_disks_button = QPushButton("Scan for Available Disks")
        self.scan_disks_button.clicked.connect(self.trigger_disk_scan)
        disk_layout_vbox.addWidget(self.scan_disks_button)
        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Select the target disk. Data will be erased if 'Wipe Disk' is checked.")
        disk_layout_vbox.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk & create standard UEFI layout")
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("Erases the ENTIRE disk and creates EFI, Swap, and Root partitions.\nUNCHECK ONLY IF YOU HAVE MANUALLY PREPARED COMPATIBLE PARTITIONS (ADVANCED).")
        disk_layout_vbox.addWidget(self.wipe_disk_checkbox)
        disk_group.setLayout(disk_layout_vbox)
        controls_layout.addWidget(disk_group)

        # System & User Configuration
        system_group = QGroupBox("2. System & User Configuration")
        system_layout_grid = QGridLayout()
        self.hostname_input = QLineEdit("maibloom-os"); system_layout_grid.addWidget(QLabel("Hostname:"), 0, 0); system_layout_grid.addWidget(self.hostname_input, 0, 1)
        self.username_input = QLineEdit("maiuser"); system_layout_grid.addWidget(QLabel("Username:"), 1, 0); system_layout_grid.addWidget(self.username_input, 1, 1)
        self.password_input = QLineEdit(); self.password_input.setPlaceholderText("User & Root Password"); self.password_input.setEchoMode(QLineEdit.Password)
        system_layout_grid.addWidget(QLabel("Password (User+Root):"), 2, 0); system_layout_grid.addWidget(self.password_input, 2, 1)
        self.locale_input = QLineEdit("en_US.UTF-8"); system_layout_grid.addWidget(QLabel("Locale:"), 3,0); system_layout_grid.addWidget(self.locale_input, 3,1)
        self.kb_layout_input = QLineEdit("us"); system_layout_grid.addWidget(QLabel("Keyboard Layout:"), 4,0); system_layout_grid.addWidget(self.kb_layout_input, 4,1)
        self.timezone_input = QLineEdit("UTC"); system_layout_grid.addWidget(QLabel("Timezone:"), 5,0); system_layout_grid.addWidget(self.timezone_input, 5,1)
        system_group.setLayout(system_layout_grid)
        controls_layout.addWidget(system_group)
        
        # Additional Applications
        app_group = QGroupBox(f"3. Additional Applications (on top of {DEFAULT_DESKTOP_ENVIRONMENT_NAME})")
        app_layout_grid = QGridLayout()
        self.app_category_checkboxes = {}
        row, col = 0,0
        for cat_name in APP_CATEGORIES.keys():
            self.app_category_checkboxes[cat_name] = QCheckBox(f"{cat_name} Apps")
            app_layout_grid.addWidget(self.app_category_checkboxes[cat_name], row, col)
            col +=1
            if col > 1: col = 0; row +=1
        app_group.setLayout(app_layout_grid)
        controls_layout.addWidget(app_group)
        
        # Optional Post Install Script (No longer core to setup, just extra for user)
        post_install_group = QGroupBox("4. Custom Script (Optional, runs after core setup)")
        post_install_layout_vbox = QVBoxLayout()
        self.post_install_script_button = QPushButton("Select Bash Script")
        self.post_install_script_button.clicked.connect(self.select_post_install_script)
        self.post_install_script_label = QLabel("No script selected.")
        post_install_layout_vbox.addWidget(self.post_install_script_button)
        post_install_layout_vbox.addWidget(self.post_install_script_label)
        post_install_group.setLayout(post_install_layout_vbox)
        controls_layout.addWidget(post_install_group)

        controls_layout.addStretch(1) # Push controls up
        splitter.addWidget(controls_widget)

        # --- Right Pane: Log Output ---
        log_group_box = QGroupBox("Installation Log")
        log_layout_vbox = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True); self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        self.log_output.setStyleSheet("font-family: monospace;") # Use monospace font for logs
        log_layout_vbox.addWidget(self.log_output)
        log_group_box.setLayout(log_layout_vbox)
        splitter.addWidget(log_group_box)
        
        splitter.setSizes([400, 450]) # Adjust initial size ratio if needed
        overall_layout.addWidget(splitter)

        # --- Bottom: Install Button ---
        self.install_button = QPushButton(f"Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME})")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold;")
        self.install_button.setToolTip("Begin installation using the settings above.")
        self.install_button.clicked.connect(self.start_installation)
        button_layout = QHBoxLayout(); button_layout.addStretch(); button_layout.addWidget(self.install_button); button_layout.addStretch()
        overall_layout.addLayout(button_layout)
        
        self.trigger_disk_scan() # Initial disk scan on startup

    def create_form_row(self, label_text, widget):
        """Helper to create a label + widget row."""
        row_layout = QHBoxLayout(); label = QLabel(label_text); label.setFixedWidth(120) 
        row_layout.addWidget(label); row_layout.addWidget(widget); return row_layout

    def trigger_disk_scan(self):
        """Initiates the disk scan."""
        self.update_log_output("GUI: Triggering disk scan...")
        self.scan_disks_button.setEnabled(False) # Disable button during scan
        self._engine_helper.run_disk_scan() # Calls the method directly (synchronous)

    def on_disk_scan_complete(self, disks_data):
        """Handles the result of the disk scan."""
        self.update_log_output(f"GUI: Disk scan finished. Found {len(disks_data)} suitable disk(s).")
        self.disk_combo.clear()
        if disks_data:
            for path_key, info_dict in sorted(disks_data.items()): # Sort disks by path
                display_text = f"{path_key} - {info_dict.get('model', 'N/A')} ({info_dict.get('size', 'N/A')})"
                self.disk_combo.addItem(display_text, userData=path_key) # Store path in userData
        else:
            self.update_log_output("GUI: No suitable installation disks found.")
            QMessageBox.warning(self, "Disk Scan", "No suitable installation disks detected. Please check your VM settings or hardware.")
        self.scan_disks_button.setEnabled(True) # Re-enable button

    def update_log_output(self, message):
        """Appends a message to the log view."""
        self.log_output.append(message)
        self.log_output.ensureCursorVisible() # Scroll to the bottom
        QApplication.processEvents() # Process events to keep GUI responsive

    def gather_settings(self):
        """Gathers all settings from the GUI controls."""
        settings = {}
        
        # Disk
        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0:
            self.update_log_output("Error: No target disk selected.", "ERROR"); return None
        settings["target_disk_path"] = self.disk_combo.itemData(selected_disk_index)
        if not settings["target_disk_path"]:
            self.update_log_output("Error: Selected disk is invalid.", "ERROR"); return None
        settings["wipe_disk"] = self.wipe_disk_checkbox.isChecked()

        # System & User
        settings["hostname"] = self.hostname_input.text().strip()
        settings["username"] = self.username_input.text().strip()
        settings["password"] = self.password_input.text() 
        settings["locale"] = self.locale_input.text().strip()
        settings["kb_layout"] = self.kb_layout_input.text().strip()
        settings["timezone"] = self.timezone_input.text().strip()
        settings["is_efi"] = os.path.exists("/sys/firmware/efi") 
        settings["swap_size_gb"] = 4 # Make this configurable later if needed

        # Validation
        if not all([settings["hostname"], settings["username"], settings["password"], 
                    settings["locale"], settings["kb_layout"], settings["timezone"]]):
            self.update_log_output("Error: Please fill in all System & User fields.", "ERROR"); return None
        
        # Additional Packages
        additional_packages = []
        for cat_name, checkbox_widget in self.app_category_checkboxes.items():
            if checkbox_widget.isChecked():
                additional_packages.extend(APP_CATEGORIES.get(cat_name, []))
        settings["additional_packages"] = list(set(additional_packages))
        
        # Add essentials just in case (pacstrap handles duplicates)
        settings["additional_packages"] = list(set(settings["additional_packages"] + ["sudo", "nano"]))

        self.update_log_output(f"Settings gathered for {DEFAULT_DESKTOP_ENVIRONMENT_NAME} on {settings['target_disk_path']}")
        return settings

    def start_installation(self):
        """Starts the installation process in the background thread."""
        current_settings = self.gather_settings()
        if not current_settings:
            QMessageBox.warning(self, "Configuration Incomplete", 
                                "Please fill all required fields (including password) and select a target disk.")
            return

        wipe_warning = "YES (ENTIRE DISK WILL BE ERASED!)" if current_settings.get('wipe_disk') else "NO (Advanced - Ensure disk is pre-partitioned compatibly!)"
        confirm_msg = (f"Ready to install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_NAME}) with the following settings:\n\n"
                       f"  - Target Disk: {current_settings.get('target_disk_path','N/A')}\n"
                       f"  - Wipe Disk & Auto-Partition (UEFI): {wipe_warning}\n"
                       f"  - Hostname: {current_settings.get('hostname')}\n"
                       f"  - Username: {current_settings.get('username')}\n"
                       f"  - Locale: {current_settings.get('locale')}\n\n"
                       "This process cannot be undone. Proceed?")
        
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.update_log_output("Installation cancelled by user.")
            return

        self.install_button.setEnabled(False); self.scan_disks_button.setEnabled(False)
        self.log_output.clear(); self.update_log_output("Starting installation. This will take time...")

        # Create and start the thread
        self.installer_thread = InstallerEngineThread(current_settings)
        self.installer_thread.installation_log.connect(self.update_log_output)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start() # Calls run() in a new thread

    def on_installation_finished(self, success, message):
        """Handles the signal emitted when the installer thread finishes."""
        self.update_log_output(f"GUI: Installation finished. Success: {success}")
        if success:
            QMessageBox.information(self, "Installation Complete", message)
        else:
            # Include more details in the message box for critical failures
            log_content = self.log_output.toPlainText()
            last_log_lines = "\n".join(log_content.splitlines()[-15:]) # Get last 15 lines
            detailed_message = f"{message}\n\nLast log entries:\n---\n{last_log_lines}\n---"
            QMessageBox.critical(self, "Installation Failed", detailed_message)
            
        # Cleanup / Reset UI state
        self.install_button.setEnabled(True) 
        self.scan_disks_button.setEnabled(True)
        self.installer_thread = None # Clear thread reference

        # Attempt to unmount target - best effort, might fail if in use or errors occurred
        self.update_log_output("Attempting final unmount...")
        unmount_process = subprocess.run(["umount", "-R", str(MOUNT_POINT)], capture_output=True, text=True)
        if unmount_process.returncode == 0:
             self.update_log_output(f"Successfully unmounted {MOUNT_POINT}.")
        else:
             self.update_log_output(f"Could not unmount {MOUNT_POINT} (may already be unmounted or error): {unmount_process.stderr.strip()}", "WARN")

    def select_post_install_script(self):
        """Allows user to select an optional script (not used by core install)."""
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getOpenFileName(self, "Select Optional Post-Installation Bash Script", "", "Bash Scripts (*.sh);;All Files (*)", options=options)
        if filePath:
            # Store path, but currently not passed to the installer engine
            self.post_install_script_path = filePath 
            self.post_install_script_label.setText(f"Script: {os.path.basename(filePath)}")
            self.update_log_output(f"Optional post-install script selected: {filePath}")
        else:
            self.post_install_script_path = ""; self.post_install_script_label.setText("No script selected.")

    def closeEvent(self, event):
        """Handle window close event, attempt to stop thread if running."""
        if self.installer_thread and self.installer_thread.isRunning():
            reply = QMessageBox.question(self, 'Installation in Progress',
                                         "An installation is currently running. Stopping now may leave the system in an inconsistent state. Are you sure you want to exit?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.installer_thread.stop() # Request thread to stop
                # Optionally wait a short time, but don't block indefinitely
                self.installer_thread.wait(1000) 
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    # Setup basic logging to console for early errors or subprocess details
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    if not check_root():
        logging.error("Application must be run as root.")
        # Initialize minimal QApplication to show error message box
        app_temp = QApplication.instance();
        if not app_temp: app_temp = QApplication(sys.argv)
        QMessageBox.critical(None, "Root Access Required", "This installer must be run with root privileges (e.g., using `sudo python your_script.py`).")
        sys.exit(1)
        
    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())

