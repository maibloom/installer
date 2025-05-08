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
                             QGroupBox, QGridLayout)
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
            # MODIFICATION: Changed import for User, removed Password import from here
            from archinstall.lib.models.users import User
            from archinstall.lib.profile.profiles_handler import profile_handler
            from archinstall.lib.system_conf import LocaleConfiguration
            from archinstall.lib.services import NetworkManager 
            
            # Archinstall logging setup
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
                self.installation_log.emit("Error: This installation mode currently only supports wiping the disk. Manual partitioning via GUI is not yet implemented with this library approach.")
                self.installation_finished.emit(False, "Granular library mode requires disk wipe. Manual partitioning not supported yet.")
                return

            hostname = self.gui_config.get("hostname", "archlinux")
            kernels = self.gui_config.get("kernels", ["linux"])
            additional_packages = self.gui_config.get("packages", [])
            users_data = self.gui_config.get("users", [])
            profile_name_str = self.gui_config.get("profile_config", {}).get("profile", {}).get("main")
            is_efi_system = self.gui_config.get("efi", os.path.exists("/sys/firmware/efi"))

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
            else:
                self.installation_log.emit("BIOS system detected. ESP partition skipped. Ensure bootloader choice is compatible.")
                # Potentially add BIOS boot partition logic here if needed for GRUB on GPT/BIOS
                # For now, keeping it simple. A 1MB unformatted partition with 'bios_grub' flag.
                bios_boot_part_size_mib = Size(1, Unit.MiB, device.device_info.sector_size)
                if device.device_info.disk_type == 'gpt': # Only needed for GPT on BIOS
                    bios_boot_partition_mod = PartitionModification(
                        status=ModificationStatus.Create, type=PartitionType.Primary,
                        start=current_offset_mib, length=bios_boot_part_size_mib,
                        fs_type=None, # Unformatted
                        flags=[PartitionFlag.BiosGrub]
                    )
                    device_modification.add_partition(bios_boot_partition_mod)
                    current_offset_mib += bios_boot_part_size_mib
                    self.installation_log.emit("Defined BIOS Boot partition (for GPT/BIOS with GRUB).")


            available_for_root_home_mib = device.device_info.total_size - current_offset_mib
            min_total_fs_space_mib = Size(20 * 1024, Unit.MiB, device.device_info.sector_size) # 20GiB
            if available_for_root_home_mib < min_total_fs_space_mib :
                 raise ValueError(f"Not enough space for Root and Home partitions. Need at least {min_total_fs_space_mib.format()}. Available: {available_for_root_home_mib.format()}")

            root_size_percentage = 0.60
            max_root_mib = Size(100 * 1024, Unit.MiB, device.device_info.sector_size) # 100GiB
            min_root_mib = Size(15 * 1024, Unit.MiB, device.device_info.sector_size) # 15GiB for root

            root_partition_size_mib = available_for_root_home_mib * root_size_percentage
            if root_partition_size_mib > max_root_mib:
                root_partition_size_mib = max_root_mib
            if root_partition_size_mib < min_root_mib:
                root_partition_size_mib = min_root_mib
            
            # Ensure root doesn't exceed available if calculation is tight
            if root_partition_size_mib > available_for_root_home_mib:
                root_partition_size_mib = available_for_root_home_mib
                
            home_partition_size_mib = available_for_root_home_mib - root_partition_size_mib

            root_fs_type = FilesystemType('ext4')
            root_partition_mod = PartitionModification(
                status=ModificationStatus.Create, type=PartitionType.Primary,
                start=current_offset_mib, length=root_partition_size_mib,
                mountpoint=Path('/'), fs_type=root_fs_type,
                mount_options=[]
            )
            device_modification.add_partition(root_partition_mod)
            current_offset_mib += root_partition_size_mib
            self.installation_log.emit(f"Defined root partition: {root_partition_size_mib.format()} at / (ext4)")

            if home_partition_size_mib.value > 1024 : # Min 1GiB for home
                home_partition_mod = PartitionModification(
                    status=ModificationStatus.Create, type=PartitionType.Primary,
                    start=current_offset_mib, length=home_partition_size_mib,
                    mountpoint=Path('/home'), fs_type=root_fs_type,
                    mount_options=[]
                )
                device_modification.add_partition(home_partition_mod)
                self.installation_log.emit(f"Defined home partition: {home_partition_size_mib.format()} at /home (ext4)")

            disk_layout_config = DiskLayoutConfiguration(
                config_type=DiskLayoutType.Manual,
                device_modifications=[device_modification]
            )
            disk_encryption_config = None

            fs_handler = FilesystemHandler(disk_layout_config, disk_encryption_config)
            self.installation_log.emit("Applying disk modifications (formatting...). This may take a while.")
            fs_handler.perform_filesystem_operations(show_countdown=False)

            install_target_mountpoint = Path(self.gui_config.get("target_mountpoint", "/mnt/archinstall"))
            os.makedirs(install_target_mountpoint, exist_ok=True)
            self.installation_log.emit(f"Preparing installer for target mountpoint: {install_target_mountpoint}")

            # Prepare locale_config object for installer
            lc_details_gui = self.gui_config.get("locale_config", {})
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
                locale_config=installer_locale_config, # Pass locale config here
                timezone=self.gui_config.get("timezone", "UTC") # Pass timezone here
            ) as installation:
                self.installation_log.emit("Mounting configured layout...")
                installation.mount_ordered_layout()

                self.installation_log.emit(f"Performing minimal system installation with hostname: {hostname}...")
                installation.minimal_installation(hostname=hostname) # locale/timezone might be handled by Installer init now
                
                if additional_packages:
                    self.installation_log.emit(f"Adding additional packages: {additional_packages}")
                    installation.add_additional_packages(additional_packages)
                
                # Set Locale and Timezone explicitly if Installer init didn't cover it fully or for confirmation
                # Some Installer versions might require these to be set after chroot is established by minimal_installation
                # self.installation_log.emit(f"Setting system locale: {installer_locale_config.sys_lang}, Kbd: {installer_locale_config.kb_layout}")
                # installation.set_locale_configuration(installer_locale_config) # May be redundant if passed to __init__
                
                # self.installation_log.emit(f"Setting timezone: {self.gui_config.get('timezone', 'UTC')}")
                # installation.set_timezone(self.gui_config.get('timezone', 'UTC')) # May be redundant

                # Profile Installation
                if profile_name_str:
                    self.installation_log.emit(f"Preparing to install profile: {profile_name_str}")
                    profile_to_install_class = None
                    # Ensure profile names are lowercase for comparison
                    profile_name_lower = profile_name_str.lower()
                    if profile_name_lower == 'kde':
                        from archinstall.default_profiles.kde import KdeProfile
                        profile_to_install_class = KdeProfile
                    elif profile_name_lower == 'gnome':
                        from archinstall.default_profiles.gnome import GnomeProfile
                        profile_to_install_class = GnomeProfile
                    elif profile_name_lower == 'xfce4': # common name in GUI
                         from archinstall.default_profiles.xfce import XfceProfile
                         profile_to_install_class = XfceProfile
                    elif profile_name_lower == 'minimal':
                        from archinstall.default_profiles.minimal import MinimalProfile
                        profile_to_install_class = MinimalProfile
                    
                    if profile_to_install_class:
                        # Profiles might need the installation target (chroot path)
                        profile_instance = profile_to_install_class(installation.target if hasattr(installation, 'target') else install_target_mountpoint)
                        current_profile_config = ProfileConfiguration(profile_instance)
                        self.installation_log.emit(f"Installing profile: {profile_name_str}...")
                        lang_for_profile = installer_locale_config.sys_lang
                        profile_handler.install_profile_config(installation, current_profile_config, lang_for_profile)
                    else:
                        self.installation_log.emit(f"Warning: Profile '{profile_name_str}' not mapped. Skipping profile installation.")
                
                # User Creation
                users_to_create_objs = []
                for user_data in users_data:
                    # MODIFICATION: Pass password as string directly to User constructor
                    users_to_create_objs.append(
                        User(user_data["username"], user_data["password"], user_data.get("sudo", True))
                    )
                if users_to_create_objs:
                    self.installation_log.emit(f"Creating users: {[u.username for u in users_to_create_objs]}")
                    installation.create_users(*users_to_create_objs)

                self.installation_log.emit("Enabling NetworkManager service...")
                # Ensure NetworkManager service is properly enabled; requires chroot context.
                # The service name might be 'NetworkManager.service'
                installation.enable_service('NetworkManager.service') # Simpler call if it exists and handles chroot


                self.installation_log.emit("Assuming bootloader setup is handled by profile or minimal installation steps...")
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
            if 'qt_handler' in locals() and 'archinstall_logger' in locals():
                archinstall_logger.removeHandler(qt_handler)


# MaiBloomInstallerApp and PostInstallThread remain largely the same as in your last provided version
# Small adjustment to MaiBloomInstallerApp.start_installation_process to pass "efi" status
# and to ensure the "wipe_disk" logic is clear for this mode.

class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.archinstall_gui_config = {} 
        self.post_install_script_path = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Mai Bloom OS Installer')
        self.setGeometry(100, 100, 750, 650) 

        main_layout = QVBoxLayout()

        title_label = QLabel("<b>Welcome to Mai Bloom OS Installation!</b>")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        main_layout.addWidget(QLabel("<small>This installer uses archinstall's library components directly. Please read explanations carefully.</small>"))

        disk_group = QGroupBox("Disk Setup")
        disk_layout = QVBoxLayout()

        scan_button = QPushButton("Scan for Available Disks")
        scan_button.setToolTip("Click to detect hard drives suitable for installation.")
        scan_button.clicked.connect(self.scan_and_populate_disks)
        disk_layout.addWidget(scan_button)

        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Select the target disk for installation. <b>ALL DATA ON THIS DISK WILL BE ERASED if 'Wipe Disk' is checked.</b>")
        disk_layout.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        disk_layout.addWidget(QLabel("<small>Ensure you select the correct disk. This is irreversible if 'Wipe Disk' is checked.</small>"))

        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk (Auto-partition & Format with default scheme)")
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("If checked, the selected disk will be completely erased and automatically partitioned (Boot, Root, Home).\nUncheck ONLY if you understand this mode does not currently support using existing partitions.")
        disk_layout.addWidget(self.wipe_disk_checkbox)
        disk_group.setLayout(disk_layout)
        main_layout.addWidget(disk_group)

        system_group = QGroupBox("System Configuration")
        system_layout = QGridLayout() 

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

        software_group = QGroupBox("Software Selection")
        software_layout = QVBoxLayout()

        self.profile_combo = QComboBox()
        self.profile_combo.setToolTip("Select a base system profile or desktop environment.\n'minimal' is a very basic system. Others install a full desktop.")
        self.profile_combo.addItems(["kde", "gnome", "xfce4", "minimal"])
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
            if col > 1: 
                col = 0
                row += 1
        software_layout.addLayout(app_cat_layout)
        software_group.setLayout(software_layout)
        main_layout.addWidget(software_group)

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

        log_group = QGroupBox("Installation Log")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.NoWrap) 
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group) 

        self.install_button = QPushButton("Start Installation")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold;")
        self.install_button.setToolTip("Begin the Mai Bloom OS installation with the selected settings.")
        self.install_button.clicked.connect(self.start_installation_process)
        main_layout.addWidget(self.install_button)

        self.setLayout(main_layout)
        self.scan_and_populate_disks() 

    def create_form_row(self, label_text, widget):
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        label.setFixedWidth(120) 
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        return row_layout

    def scan_and_populate_disks(self):
        self.log_output.append("Scanning for disks...")
        QApplication.processEvents()
        self.disk_combo.clear()
        try:
            result = subprocess.run(['lsblk', '-J', '-b', '-o', 'NAME,SIZE,TYPE,MODEL,PATH,TRAN,PKNAME'], # Added PKNAME
                                    capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            disks_found = 0
            for device in data.get('blockdevices', []):
                # Filter for actual disks, not partitions (PKNAME is null for whole disks)
                # and not loop devices, cd/dvd roms, and not USB by default for safety.
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
        self.log_output.ensureCursorVisible() 
        QApplication.processEvents() 

    def start_installation_process(self):
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        confirm_password = self.confirm_password_input.text()
        locale = self.locale_input.text().strip()
        kb_layout = self.keyboard_layout_input.text().strip()
        timezone = self.timezone_input.text().strip()

        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: 
            QMessageBox.warning(self, "Input Error", "Please select a target disk after scanning.")
            return
        disk_path_str = self.disk_combo.itemData(selected_disk_index) 

        profile_name = self.profile_combo.currentText()
        wipe_disk_checked = self.wipe_disk_checkbox.isChecked()

        if not all([hostname, username, password, locale, kb_layout, disk_path_str, timezone]):
            QMessageBox.warning(self, "Input Error", "Please fill in all required system and user fields.")
            return
        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match.")
            return

        if not wipe_disk_checked: # Explicitly check and prevent if not wiping for this mode
            QMessageBox.warning(self, "Unsupported Operation", 
                                "This installation mode currently only supports wiping the disk and auto-partitioning. "
                                "Using existing partitions is not implemented in this workflow. Please check 'Wipe selected disk' to proceed.")
            self.install_button.setEnabled(True) # Re-enable button
            return

        confirm_msg = (f"This will install Mai Bloom OS on <b>{disk_path_str}</b> with hostname <b>{hostname}</b>.\n"
                       f"Profile: <b>{profile_name}</b>.\n"
                       f"<b>ALL DATA ON {disk_path_str} WILL BE ERASED and the disk will be auto-partitioned (Boot, Root, Home)!</b>\n"
                       "Are you sure you want to proceed?")
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.log_output.append("Installation cancelled by user.")
            return

        self.install_button.setEnabled(False)
        self.log_output.clear()
        self.log_output.append("Starting installation preparation (granular library mode)...")

        self.archinstall_gui_config = {
            "hostname": hostname,
            "locale_config": {"kb_layout": kb_layout, "sys_lang": locale, "sys_enc": "UTF-8"},
            "timezone": timezone,
            "swap": True, # This isn't directly used by the granular example for partitioning but can be a general setting
            "users": [{"username": username, "password": password, "sudo": True}],
            "kernels": ["linux"],
            "packages": [],
            "disk_config": {"device_path": disk_path_str, "wipe": wipe_disk_checked}, # `wipe` must be true here
            "profile_config": {"profile": {"main": profile_name}} if profile_name else {},
            "network_config": {"type": "nm"}, 
            "efi": os.path.exists("/sys/firmware/efi"),
            "target_mountpoint": "/mnt/archinstall" 
        }
        
        selected_pkgs = []
        for category, checkbox in self.app_category_checkboxes.items():
            if checkbox.isChecked():
                selected_pkgs.extend(APP_CATEGORIES[category])
        if selected_pkgs:
            self.archinstall_gui_config["packages"] = list(set(selected_pkgs))
        
        self.log_output.append("GUI Configuration dictionary prepared for thread:")
        self.log_output.append(json.dumps(self.archinstall_gui_config, indent=2))

        self.installer_thread = ArchinstallThread(self.archinstall_gui_config)
        self.installer_thread.installation_log.connect(self.update_log)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message):
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Installation Complete", "Arch Linux base installation finished successfully!")
            if self.post_install_script_path:
                self.log_output.append("\n--- Installation successful. Proceeding to post-installation script. ---")
                mount_point_for_post_install = self.archinstall_gui_config.get("target_mountpoint", "/mnt/archinstall")
                self.run_post_install_script(mount_point_for_post_install)
            else:
                self.install_button.setEnabled(True)
                self.log_output.append("No post-installation script to run. System setup complete.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Arch Linux installation failed.\nSee log for details.\n{message}")
            self.install_button.setEnabled(True)

    def run_post_install_script(self, target_mount_point):
        self.log_output.append(f"\n--- Starting Post-Installation Script (Target: {target_mount_point}) ---")
        self.post_installer_thread = PostInstallThread(self.post_install_script_path, target_mount_point=target_mount_point)
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
        app_temp = QApplication.instance() 
        if not app_temp:
            app_temp = QApplication(sys.argv)
        QMessageBox.critical(None, "Root Access Required", "This installer must be run with root privileges (e.g., using sudo).\nPlease restart the application as root.")
        sys.exit(1)

    app = QApplication(sys.argv)
    installer = MaiBloomInstallerApp()
    installer.show()
    sys.exit(app.exec_())
