import sys
import subprocess
import json
import os
import logging
import traceback
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout, QSplitter) # Added QSplitter
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

# --- Custom Log Handler for PyQt ---
class QtLogHandler(logging.Handler):
    def __init__(self, log_signal):
        super().__init__()
        self.log_signal = log_signal

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)

# --- Archinstall Interaction Thread (Modified for Granular Library Mode) ---
class ArchinstallThread(QThread):
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str)

    def __init__(self, gui_config_dict):
        super().__init__()
        self.gui_config = gui_config_dict

    def run(self):
        try:
            self.installation_log.emit("Initializing archinstall library (granular mode)...")

            from archinstall.lib.disk.device_handler import device_handler
            from archinstall.lib.disk.filesystem import FilesystemHandler
            from archinstall.lib.installer import Installer
            from archinstall.lib.models.device_model import (
                DeviceModification, DiskEncryption, DiskLayoutConfiguration,
                DiskLayoutType, EncryptionType, FilesystemType, ModificationStatus,
                PartitionFlag, PartitionModification, PartitionType, Size, Unit
            )
            from archinstall.lib.models.profile_model import ProfileConfiguration
            from archinstall.lib.models.users import User # Password class handled by User constructor
            # MODIFICATION: Corrected import path for LocaleConfiguration
            from archinstall.lib.models.locale_configuration import LocaleConfiguration
            from archinstall.lib.profile.profiles_handler import profile_handler
            from archinstall.lib.services import NetworkManager # Assuming this is the correct service class

            archinstall_logger = logging.getLogger('archinstall')
            for handler in list(archinstall_logger.handlers):
                archinstall_logger.removeHandler(handler)
            qt_handler = QtLogHandler(self.installation_log)
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            qt_handler.setFormatter(formatter)
            archinstall_logger.addHandler(qt_handler)
            archinstall_logger.setLevel(logging.INFO)
            self.installation_log.emit("Archinstall logging redirected to GUI.")

            target_disk_path_str = self.gui_config.get("disk_config", {}).get("device_path")
            if not target_disk_path_str:
                raise ValueError("Target disk path not provided in GUI configuration.")
            
            wipe_disk = self.gui_config.get("disk_config", {}).get("wipe", False)
            if not wipe_disk:
                self.installation_log.emit("Error: This installation mode currently only supports wiping the disk.")
                self.installation_finished.emit(False, "Granular library mode requires disk wipe. Manual partitioning not supported yet.")
                return

            hostname = self.gui_config.get("hostname", "archlinux")
            kernels = self.gui_config.get("kernels", ["linux"])
            additional_packages = self.gui_config.get("packages", [])
            users_data = self.gui_config.get("users", [])
            profile_name_str = self.gui_config.get("profile_config", {}).get("profile", {}).get("main")
            is_efi_system = self.gui_config.get("efi", os.path.exists("/sys/firmware/efi"))
            lc_details_gui = self.gui_config.get("locale_config", {})
            timezone_gui = self.gui_config.get("timezone", "UTC")

            self.installation_log.emit(f"Getting device information for {target_disk_path_str}...")
            device = device_handler.get_device(Path(target_disk_path_str))
            if not device:
                raise ValueError(f"Device {target_disk_path_str} not found by archinstall.")

            device_modification = DeviceModification(device, wipe=True)
            current_offset_mib = Size(1, Unit.MiB, device.device_info.sector_size)

            if is_efi_system:
                boot_partition_size_mib = Size(512, Unit.MiB, device.device_info.sector_size)
                boot_partition_mod = PartitionModification(
                    status=ModificationStatus.Create, type=PartitionType.Primary,
                    start=current_offset_mib, length=boot_partition_size_mib,
                    mountpoint=Path('/boot'), fs_type=FilesystemType.Fat32,
                    flags=[PartitionFlag.BOOT, PartitionFlag.ESP]
                )
                device_modification.add_partition(boot_partition_mod)
                current_offset_mib += boot_partition_size_mib
                self.installation_log.emit("Defined EFI boot partition: 512MiB at /boot")
            elif device.device_info.disk_type == 'gpt': # BIOS system on GPT disk
                bios_boot_part_size_mib = Size(1, Unit.MiB, device.device_info.sector_size)
                bios_boot_partition_mod = PartitionModification(
                    status=ModificationStatus.Create, type=PartitionType.Primary,
                    start=current_offset_mib, length=bios_boot_part_size_mib,
                    fs_type=None, # Unformatted
                    flags=[PartitionFlag.BiosGrub]
                )
                device_modification.add_partition(bios_boot_partition_mod)
                current_offset_mib += bios_boot_part_size_mib
                self.installation_log.emit("Defined BIOS Boot partition (1MiB for GPT/BIOS with GRUB).")
            else: # BIOS system on MBR disk
                 self.installation_log.emit("BIOS system on MBR disk. No special boot partition defined here (boot flag will be on root or /boot if separate).")


            available_for_root_home_mib = device.device_info.total_size - current_offset_mib
            min_total_fs_space_mib = Size(20 * 1024, Unit.MiB, device.device_info.sector_size)
            if available_for_root_home_mib < min_total_fs_space_mib :
                 raise ValueError(f"Not enough space for Root/Home. Need at least {min_total_fs_space_mib.format()}. Available: {available_for_root_home_mib.format()}")

            root_size_percentage = 0.60
            max_root_mib = Size(100 * 1024, Unit.MiB, device.device_info.sector_size)
            min_root_mib = Size(15 * 1024, Unit.MiB, device.device_info.sector_size)
            root_partition_size_mib = available_for_root_home_mib * root_size_percentage
            if root_partition_size_mib > max_root_mib: root_partition_size_mib = max_root_mib
            if root_partition_size_mib < min_root_mib: root_partition_size_mib = min_root_mib
            if root_partition_size_mib > available_for_root_home_mib: root_partition_size_mib = available_for_root_home_mib
            home_partition_size_mib = available_for_root_home_mib - root_partition_size_mib

            root_fs_type = FilesystemType('ext4')
            root_partition_mod = PartitionModification(
                status=ModificationStatus.Create, type=PartitionType.Primary,
                start=current_offset_mib, length=root_partition_size_mib,
                mountpoint=Path('/'), fs_type=root_fs_type, mount_options=[]
            )
            # If BIOS MBR, root partition needs boot flag
            if not is_efi_system and device.device_info.disk_type == 'mbr':
                root_partition_mod.flags.append(PartitionFlag.BOOT)
                self.installation_log.emit("Adding BOOT flag to root partition for BIOS/MBR setup.")

            device_modification.add_partition(root_partition_mod)
            current_offset_mib += root_partition_size_mib
            self.installation_log.emit(f"Defined root partition: {root_partition_size_mib.format()} at / (ext4)")

            if home_partition_size_mib.value > 1024 : # Min 1GiB for home
                home_partition_mod = PartitionModification(
                    status=ModificationStatus.Create, type=PartitionType.Primary,
                    start=current_offset_mib, length=home_partition_size_mib,
                    mountpoint=Path('/home'), fs_type=root_fs_type, mount_options=[]
                )
                device_modification.add_partition(home_partition_mod)
                self.installation_log.emit(f"Defined home partition: {home_partition_size_mib.format()} at /home (ext4)")

            disk_layout_config = DiskLayoutConfiguration(
                config_type=DiskLayoutType.Manual, device_modifications=[device_modification]
            )
            disk_encryption_config = None

            fs_handler = FilesystemHandler(disk_layout_config, disk_encryption_config)
            self.installation_log.emit("Applying disk modifications (formatting...). This may take a while.")
            fs_handler.perform_filesystem_operations(show_countdown=False)

            install_target_mountpoint = Path(self.gui_config.get("target_mountpoint", "/mnt/archinstall"))
            os.makedirs(install_target_mountpoint, exist_ok=True)
            self.installation_log.emit(f"Preparing installer for target mountpoint: {install_target_mountpoint}")

            installer_locale_config = LocaleConfiguration(
                kb_layout=lc_details_gui.get("kb_layout", "us"),
                sys_lang=lc_details_gui.get("sys_lang", "en_US.UTF-8"),
                sys_enc=lc_details_gui.get("sys_enc", "UTF-8")
            )

            with Installer(
                mountpoint=install_target_mountpoint,
                disk_config=disk_layout_config,
                disk_encryption=disk_encryption_config,
                kernels=kernels,
                locale_config=installer_locale_config,
                timezone=timezone_gui
            ) as installation:
                self.installation_log.emit("Mounting configured layout...")
                installation.mount_ordered_layout()

                self.installation_log.emit(f"Performing minimal system installation with hostname: {hostname}...")
                installation.minimal_installation(hostname=hostname)
                
                if additional_packages:
                    self.installation_log.emit(f"Adding additional packages: {additional_packages}")
                    installation.add_additional_packages(additional_packages)
                
                # Explicitly set locale and timezone post-chroot setup by minimal_installation
                self.installation_log.emit(f"Applying system locale: {installer_locale_config.sys_lang}, Kbd: {installer_locale_config.kb_layout}")
                installation.set_locale_configuration(installer_locale_config)
                
                self.installation_log.emit(f"Applying timezone: {timezone_gui}")
                installation.set_timezone(timezone_gui)

                if profile_name_str:
                    self.installation_log.emit(f"Preparing to install profile: {profile_name_str}")
                    profile_to_install_class = None
                    profile_name_lower = profile_name_str.lower()
                    if profile_name_lower == 'kde': from archinstall.default_profiles.kde import KdeProfile; profile_to_install_class = KdeProfile
                    elif profile_name_lower == 'gnome': from archinstall.default_profiles.gnome import GnomeProfile; profile_to_install_class = GnomeProfile
                    elif profile_name_lower == 'xfce4': from archinstall.default_profiles.xfce import XfceProfile; profile_to_install_class = XfceProfile
                    elif profile_name_lower == 'minimal': from archinstall.default_profiles.minimal import MinimalProfile; profile_to_install_class = MinimalProfile
                    
                    if profile_to_install_class:
                        profile_instance = profile_to_install_class(installation.target)
                        current_profile_config = ProfileConfiguration(profile_instance)
                        self.installation_log.emit(f"Installing profile: {profile_name_str}...")
                        lang_for_profile = installer_locale_config.sys_lang
                        profile_handler.install_profile_config(installation, current_profile_config, lang_for_profile)
                    else: self.installation_log.emit(f"Warning: Profile '{profile_name_str}' not mapped. Skipping.")
                
                users_to_create_objs = [User(ud["username"], ud["password"], ud.get("sudo", True)) for ud in users_data]
                if users_to_create_objs:
                    self.installation_log.emit(f"Creating users: {[u.username for u in users_to_create_objs]}")
                    installation.create_users(*users_to_create_objs)

                self.installation_log.emit("Enabling NetworkManager service...")
                installation.enable_service('NetworkManager.service')

                self.installation_log.emit("Ensuring bootloader is installed (handled by installer/profile)...")
                # Bootloader installation should be handled by Installer.minimal_installation() or the profile based on EFI status
                # Forcing a specific bootloader if needed:
                # if is_efi_system: installation.add_bootloader("systemd-boot") else: installation.add_bootloader("grub")
                # installation.install_bootloader() # This might be a more explicit call if needed

                self.installation_log.emit("System configuration steps applied within chroot.")

            self.installation_log.emit("Installation process completed successfully via granular library mode.")
            self.installation_finished.emit(True, "Arch Linux installation successful (granular library mode)!")

        except ImportError as e:
            err_msg = f"ImportError during archinstall library setup: {str(e)}.\n"
            err_msg += "This can be due to an internal archinstall issue or a problem with your archinstall environment/version."
            err_msg += f"\nTraceback:\n{traceback.format_exc()}"
            self.installation_log.emit(err_msg)
            self.installation_finished.emit(False, err_msg)
        except Exception as e:
            err_msg = f"An critical error occurred during archinstall library execution: {str(e)}"
            err_msg += f"\nTraceback:\n{traceback.format_exc()}"
            self.installation_log.emit(err_msg)
            self.installation_finished.emit(False, err_msg)
        finally:
            if 'qt_handler' in locals() and 'archinstall_logger' in locals(): # type: ignore
                archinstall_logger.removeHandler(qt_handler) # type: ignore


class PostInstallThread(QThread): # No changes needed here for now
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
        self.archinstall_gui_config = {} 
        self.post_install_script_path = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Mai Bloom OS Installer')
        self.setGeometry(100, 100, 850, 700) # Increased size for side panel

        overall_layout = QVBoxLayout(self) # Main layout for the window

        # --- Title ---
        title_label = QLabel("<b>Welcome to Mai Bloom OS Installation!</b>")
        title_label.setAlignment(Qt.AlignCenter)
        overall_layout.addWidget(title_label)
        overall_layout.addWidget(QLabel("<small>This installer uses archinstall's library components directly. Please read explanations carefully.</small>"))

        # --- Splitter for Controls (Left) and Log (Right) ---
        splitter = QSplitter(Qt.Horizontal)
        overall_layout.addWidget(splitter)

        # --- Left Panel for Controls ---
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget) # Layout for all control groups

        # --- Disk Selection GroupBox ---
        disk_group = QGroupBox("Disk Setup")
        disk_layout_vbox = QVBoxLayout() # Changed from disk_layout to avoid name clash
        scan_button = QPushButton("Scan for Available Disks")
        scan_button.clicked.connect(self.scan_and_populate_disks)
        disk_layout_vbox.addWidget(scan_button)
        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Select the target disk. <b>ALL DATA WILL BE ERASED if 'Wipe Disk' is checked.</b>")
        disk_layout_vbox.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        disk_layout_vbox.addWidget(QLabel("<small>Ensure correct disk selection. This is irreversible if 'Wipe Disk' is checked.</small>"))
        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk (Auto-partition & Format)")
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("Wipes disk and creates Boot, Root, Home partitions.\nUsing existing partitions is not supported in this mode.")
        disk_layout_vbox.addWidget(self.wipe_disk_checkbox)
        disk_group.setLayout(disk_layout_vbox)
        controls_layout.addWidget(disk_group)

        # --- System Configuration GroupBox ---
        system_group = QGroupBox("System Configuration")
        system_layout_grid = QGridLayout() # Changed name
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

        # --- User Account GroupBox ---
        user_group = QGroupBox("User Account Setup")
        user_layout_grid = QGridLayout() # Changed name
        self.username_input = QLineEdit("bloomuser")
        user_layout_grid.addWidget(QLabel("Username:"), 0, 0); user_layout_grid.addWidget(self.username_input, 0, 1)
        self.password_input = QLineEdit(); self.password_input.setEchoMode(QLineEdit.Password)
        user_layout_grid.addWidget(QLabel("Password:"), 1, 0); user_layout_grid.addWidget(self.password_input, 1, 1)
        self.confirm_password_input = QLineEdit(); self.confirm_password_input.setEchoMode(QLineEdit.Password)
        user_layout_grid.addWidget(QLabel("Confirm Password:"), 2, 0); user_layout_grid.addWidget(self.confirm_password_input, 2, 1)
        user_group.setLayout(user_layout_grid)
        controls_layout.addWidget(user_group)
        
        # --- Software Selection GroupBox ---
        software_group = QGroupBox("Software Selection")
        software_layout_vbox = QVBoxLayout() # Changed name
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(["kde", "gnome", "xfce4", "minimal"])
        software_layout_vbox.addLayout(self.create_form_row("Desktop/Profile:", self.profile_combo))
        software_layout_vbox.addWidget(QLabel("<b>Additional Application Categories (Optional):</b>"))
        self.app_category_checkboxes = {}
        app_cat_layout_grid = QGridLayout() # Changed name
        row, col = 0, 0
        for i, (category, _) in enumerate(APP_CATEGORIES.items()):
            self.app_category_checkboxes[category] = QCheckBox(category)
            app_cat_layout_grid.addWidget(self.app_category_checkboxes[category], row, col); col += 1
            if col > 1: col = 0; row += 1
        software_layout_vbox.addLayout(app_cat_layout_grid)
        software_group.setLayout(software_layout_vbox)
        controls_layout.addWidget(software_group)

        # --- Post-install script GroupBox ---
        post_install_group = QGroupBox("Custom Post-Installation")
        post_install_layout_vbox = QVBoxLayout() # Changed name
        self.post_install_script_button = QPushButton("Select Post-Install Bash Script (Optional)")
        self.post_install_script_button.clicked.connect(self.select_post_install_script)
        self.post_install_script_label = QLabel("No script selected.")
        post_install_layout_vbox.addWidget(self.post_install_script_button)
        post_install_layout_vbox.addWidget(self.post_install_script_label)
        post_install_group.setLayout(post_install_layout_vbox)
        controls_layout.addWidget(post_install_group)
        
        controls_layout.addStretch(1) # Add stretch to push content up if space available
        splitter.addWidget(controls_widget) # Add controls panel to splitter

        # --- Right Panel for Log ---
        log_group = QGroupBox("Installation Log")
        log_layout_vbox = QVBoxLayout() # Changed name
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        log_layout_vbox.addWidget(self.log_output)
        log_group.setLayout(log_layout_vbox)
        splitter.addWidget(log_group) # Add log panel to splitter

        splitter.setSizes([400, 450]) # Initial sizes for left and right panes

        # --- Install Button (below splitter) ---
        self.install_button = QPushButton("Start Installation")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold;")
        self.install_button.clicked.connect(self.start_installation_process)
        
        button_layout = QHBoxLayout() # To center the button or control its size
        button_layout.addStretch()
        button_layout.addWidget(self.install_button)
        button_layout.addStretch()
        overall_layout.addLayout(button_layout) # Add button layout to the main vertical layout

        self.scan_and_populate_disks()

    def create_form_row(self, label_text, widget):
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        label.setFixedWidth(120) 
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        return row_layout

    def scan_and_populate_disks(self): # No changes here
        self.log_output.append("Scanning for disks...")
        QApplication.processEvents()
        self.disk_combo.clear()
        try:
            result = subprocess.run(['lsblk', '-J', '-b', '-o', 'NAME,SIZE,TYPE,MODEL,PATH,TRAN,PKNAME'],
                                    capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            disks_found = 0
            for device in data.get('blockdevices', []):
                if device.get('type') == 'disk' and not device.get('pkname') and device.get('tran') not in ['usb']:
                    name = f"/dev/{device.get('name', 'N/A')}"
                    model = device.get('model', 'Unknown Model')
                    size_bytes = int(device.get('size', 0))
                    size_gb = size_bytes / (1024**3)
                    display_text = f"{name} - {model} ({size_gb:.2f} GB)"
                    self.disk_combo.addItem(display_text, userData=name)
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

    def select_post_install_script(self): # No changes here
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getOpenFileName(self, "Select Post-Installation Bash Script", "", "Bash Scripts (*.sh);;All Files (*)", options=options)
        if filePath:
            self.post_install_script_path = filePath
            self.post_install_script_label.setText(f"Script: {os.path.basename(filePath)}")
            self.log_output.append(f"Post-install script selected: {filePath}")
        else:
            self.post_install_script_path = ""; self.post_install_script_label.setText("No script selected.")

    def update_log(self, message): # No changes here
        self.log_output.append(message)
        self.log_output.ensureCursorVisible() 
        QApplication.processEvents() 

    def start_installation_process(self): # Logic adjusted for new ArchinstallThread requirements
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        locale = self.locale_input.text().strip()
        kb_layout = self.keyboard_layout_input.text().strip()
        timezone = self.timezone_input.text().strip()

        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: 
            QMessageBox.warning(self, "Input Error", "Please select a target disk."); return
        disk_path_str = self.disk_combo.itemData(selected_disk_index) 

        profile_name = self.profile_combo.currentText()
        wipe_disk_checked = self.wipe_disk_checkbox.isChecked()

        if not all([hostname, username, password, locale, kb_layout, disk_path_str, timezone]):
            QMessageBox.warning(self, "Input Error", "Please fill in all required fields."); return
        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match."); return

        if not wipe_disk_checked:
            QMessageBox.warning(self, "Unsupported Operation", 
                                "This installation mode currently only supports wiping the disk and auto-partitioning. "
                                "Please check 'Wipe selected disk' to proceed.")
            return # Do not proceed if not wiping

        confirm_msg = (f"<b>TARGET DISK: {disk_path_str}</b>\n"
                       f"Hostname: {hostname}, Profile: {profile_name}\n"
                       f"<b>ALL DATA ON {disk_path_str} WILL BE ERASED and auto-partitioned!</b>\n"
                       "Are you absolutely sure you want to proceed?")
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.log_output.append("Installation cancelled by user."); return

        self.install_button.setEnabled(False)
        self.log_output.clear()
        self.log_output.append("Starting installation preparation (granular library mode)...")

        self.archinstall_gui_config = {
            "hostname": hostname,
            "locale_config": {"kb_layout": kb_layout, "sys_lang": locale, "sys_enc": "UTF-8"},
            "timezone": timezone,
            "users": [{"username": username, "password": password, "sudo": True}],
            "kernels": ["linux"],
            "packages": [],
            "disk_config": {"device_path": disk_path_str, "wipe": True}, # Wipe is always true if we reach here
            "profile_config": {"profile": {"main": profile_name}} if profile_name else {},
            "efi": os.path.exists("/sys/firmware/efi"),
            "target_mountpoint": "/mnt/archinstall" 
        }
        
        selected_pkgs = [APP_CATEGORIES[cat][-1] for cat, cb in self.app_category_checkboxes.items() if cb.isChecked() for pkg in APP_CATEGORIES[cat]] # Corrected package selection
        # Flatten and unique packages
        flat_selected_pkgs = []
        for category, checkbox in self.app_category_checkboxes.items():
            if checkbox.isChecked():
                flat_selected_pkgs.extend(APP_CATEGORIES[category])
        self.archinstall_gui_config["packages"] = list(set(flat_selected_pkgs))
        
        self.log_output.append("GUI Configuration dictionary prepared for thread:")
        self.log_output.append(json.dumps(self.archinstall_gui_config, indent=2))

        self.installer_thread = ArchinstallThread(self.archinstall_gui_config)
        self.installer_thread.installation_log.connect(self.update_log)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message): # No changes here
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Installation Complete", "Arch Linux installation finished successfully!")
            if self.post_install_script_path:
                self.log_output.append("\n--- Proceeding to post-installation script. ---")
                mount_point = self.archinstall_gui_config.get("target_mountpoint", "/mnt/archinstall")
                self.run_post_install_script(mount_point)
            else:
                self.install_button.setEnabled(True); self.log_output.append("No post-install script.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Installation failed.\n{message}")
            self.install_button.setEnabled(True)

    def run_post_install_script(self, target_mount_point): # No changes here
        self.log_output.append(f"\n--- Starting Post-Installation Script (Target: {target_mount_point}) ---")
        self.post_installer_thread = PostInstallThread(self.post_install_script_path, target_mount_point=target_mount_point)
        self.post_installer_thread.post_install_log.connect(self.update_log)
        self.post_installer_thread.post_install_finished.connect(self.on_post_install_finished)
        self.post_installer_thread.start()

    def on_post_install_finished(self, success, message): # No changes here
        self.update_log(message)
        if success: QMessageBox.information(self, "Post-Install Complete", "Post-installation script finished.")
        else: QMessageBox.warning(self, "Post-Install Issue", f"Post-install script issues.\n{message}")
        self.install_button.setEnabled(True)
        self.log_output.append("Mai Bloom OS setup process finished.")


if __name__ == '__main__':
    if not check_root():
        print("Error: This application must be run as root (or with sudo).")
        # Simplified exit for non-GUI context if check_root is early
        # app_temp = QApplication.instance();
        # if not app_temp: app_temp = QApplication(sys.argv)
        # QMessageBox.critical(None, "Root Access Required", "Run with sudo.")
        sys.exit(1)

    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())

