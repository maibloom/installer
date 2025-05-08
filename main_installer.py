import sys
import subprocess
import json
import os
import logging # Added for custom log handler
import traceback # Added for detailed error logging

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

# --- Archinstall Interaction Thread (Modified for Library Mode) ---
class ArchinstallThread(QThread):
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str)

    def __init__(self, config_dict):
        super().__init__()
        self.gui_config = config_dict # Renamed to avoid confusion with archinstall's own config objects

    def run(self):
        try:
            self.installation_log.emit("Initializing archinstall library mode...")

            # --- Import archinstall components ---
            # It's crucial that these imports themselves don't trigger the circular import
            # before we get a chance to configure things.
            from archinstall.lib.conf import ArchConfig
            from archinstall.lib.installer import Installer
            from archinstall.lib.logging import logger as archinstall_logger, setup_logfile_logger # Use setup_logfile_logger for basic setup
            
            # Import model classes
            from archinstall.lib.models.locale_configuration import LocaleConfiguration
            from archinstall.lib.models.user import User
            from archinstall.lib.models.disk_layout import DiskLayoutConfiguration
            from archinstall.lib.models.profile import ProfileConfiguration, Profile # Main Profile class might be ProfileDefinition or similar
            from archinstall.lib.models.network_configuration import NetworkConfiguration # Assuming this model exists
            # Add other models as needed (e.g., for bootloader, disk encryption, etc.)

            # --- 1. Setup Archinstall Logging ---
            # Remove existing handlers from archinstall_logger if any, to avoid duplicate logs or file logs
            for handler in list(archinstall_logger.handlers): # Iterate over a copy
                archinstall_logger.removeHandler(handler)
            
            # Add our custom Qt handler
            qt_handler = QtLogHandler(self.installation_log)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            qt_handler.setFormatter(formatter)
            archinstall_logger.addHandler(qt_handler)
            archinstall_logger.setLevel(logging.INFO) # Or DEBUG for more verbosity
            self.installation_log.emit("Archinstall logging redirected to GUI.")

            # --- 2. Create and Populate ArchConfig instance ---
            self.installation_log.emit("Populating ArchConfig for archinstall...")
            arch_cfg = ArchConfig() # Create a new, empty config object

            # Populate basic fields
            arch_cfg.hostname = self.gui_config.get("hostname")
            arch_cfg.timezone = self.gui_config.get("timezone")
            arch_cfg.swap = self.gui_config.get("swap", True)
            arch_cfg.kernels = self.gui_config.get("kernels", ["linux"])
            arch_cfg.packages = self.gui_config.get("packages", [])
            arch_cfg.silent = True # Crucial for non-interactive mode
            arch_cfg.automation = True # Also important for non-interactive mode

            # Locale Configuration
            lc_data = self.gui_config.get("locale_config", {})
            # Assuming LocaleConfiguration can be instantiated directly or has a simple constructor
            # If LocaleConfiguration.parse_arg is safe, it can be used. Otherwise, manual:
            arch_cfg.locale_config = LocaleConfiguration(
                kb_layout=lc_data.get("kb_layout"),
                sys_lang=lc_data.get("sys_lang"),
                sys_enc=lc_data.get("sys_enc", "UTF-8") # Archinstall might default this
            )
            
            # User Configuration
            users_list = []
            for user_d in self.gui_config.get("users", []):
                # User model might take keyword arguments directly
                users_list.append(User(
                    username=user_d.get("username"),
                    _password=user_d.get("password"), # Often internal attribute for raw password
                    sudo=user_d.get("sudo", True)
                ))
            arch_cfg.users = users_list
            
            # Disk Configuration
            disk_c_data = self.gui_config.get("disk_config")
            if disk_c_data:
                # Assuming DiskLayoutConfiguration.parse_arg was fixed and is safe to use
                arch_cfg.disk_config = DiskLayoutConfiguration.parse_arg(disk_c_data)
            
            # Profile Configuration - Attempting to bypass parse_arg
            profile_c_data = self.gui_config.get("profile_config", {}).get("profile", {})
            main_profile_name = profile_c_data.get("main")
            if main_profile_name:
                # This part is highly dependent on the actual structure of Profile and ProfileConfiguration
                # We need to create a Profile instance (or ProfileDefinition)
                # then assign it to the ProfileConfiguration instance.
                # Let's assume Profile takes a name/path.
                # The 'name' of the profile usually refers to the profile script/directory name.
                profile_instance = Profile(name=main_profile_name, path=f"/usr/lib/python{sys.version_major}.{sys.version_minor}/site-packages/archinstall/profiles/{main_profile_name}.py") # Path is a guess
                # Then, wrap it in ProfileConfiguration
                arch_cfg.profile_config = ProfileConfiguration(profile=profile_instance)
            else:
                arch_cfg.profile_config = ProfileConfiguration() # Default/empty

            # EFI and Bootloader
            arch_cfg.efi = self.gui_config.get("efi")
            arch_cfg.bootloader = self.gui_config.get("bootloader")

            # Network Configuration
            nc_data = self.gui_config.get("network_config", {})
            if nc_data.get("type"): # Assuming NetworkConfiguration model exists and takes 'type'
                 arch_cfg.network_config = NetworkConfiguration(type=nc_data.get("type"))
            else: # Default or minimal NetworkConfiguration
                 arch_cfg.network_config = NetworkConfiguration()


            self.installation_log.emit("ArchConfig populated.")
            # self.installation_log.emit(f"Effective ArchConfig (partial): {vars(arch_cfg)}") # Careful with logging whole objects

            # --- 3. Instantiate Installer ---
            self.installation_log.emit("Instantiating Installer...")
            # The Installer constructor typically takes the ArchConfig object directly
            installer = Installer(config=arch_cfg)

            # --- 4. Run Installation ---
            self.installation_log.emit("Starting Arch Linux installation process (library mode)...")
            # The `run()` method of the Installer should perform the whole installation.
            # It might raise exceptions on failure.
            installer.run() # This is the main call.

            self.installation_log.emit("Archinstall library execution completed successfully.")
            self.installation_finished.emit(True, "Arch Linux installation successful (via library mode)!")

        except ImportError as e:
            err_msg = f"ImportError during archinstall library setup: {str(e)}.\n"
            err_msg += "This can be due to an internal archinstall issue (like a circular import not bypassed by this mode) or a problem with your archinstall environment/version."
            err_msg += f"\nTraceback:\n{traceback.format_exc()}"
            self.installation_log.emit(err_msg)
            self.installation_finished.emit(False, err_msg)
        except Exception as e:
            err_msg = f"An critical error occurred during archinstall library execution: {str(e)}"
            err_msg += f"\nTraceback:\n{traceback.format_exc()}"
            self.installation_log.emit(err_msg)
            self.installation_finished.emit(False, err_msg)
        finally:
            # Clean up logging if necessary (remove our handler)
            if 'qt_handler' in locals() and 'archinstall_logger' in locals():
                archinstall_logger.removeHandler(qt_handler)

# PostInstallThread remains the same as it deals with subprocesses after archinstall completes.
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
            target_script_path = os.path.join(self.target_mount_point, "tmp", script_basename)
            os.makedirs(os.path.join(self.target_mount_point, "tmp"), exist_ok=True)
            subprocess.run(["cp", self.script_path, target_script_path], check=True)
            self.post_install_log.emit(f"Copied post-install script to {target_script_path}")
            chroot_script_internal_path = os.path.join("/tmp", script_basename)
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
            self.post_install_log.emit(f"Error running post-install script: {str(e)}\n{traceback.format_exc()}")
            self.post_install_finished.emit(False, f"Error running post-install script: {str(e)}")
        finally:
            if 'target_script_path' in locals() and os.path.exists(target_script_path):
                try:
                    os.remove(target_script_path)
                    self.post_install_log.emit(f"Cleaned up: {target_script_path}")
                except OSError as e:
                    self.post_install_log.emit(f"Warning: Could not remove temporary script {target_script_path}: {e}")


class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.archinstall_config_dict = {} # Changed name to reflect it's a dictionary for the GUI
        self.post_install_script_path = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Mai Bloom OS Installer')
        self.setGeometry(100, 100, 750, 650) 

        main_layout = QVBoxLayout()

        title_label = QLabel("<b>Welcome to Mai Bloom OS Installation!</b>")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        main_layout.addWidget(QLabel("<small>This installer will guide you through setting up Mai Bloom OS (Arch Linux based). Please read explanations carefully.</small>"))

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
        self.profile_combo.addItems(["kde", "gnome", "xfce4", "minimal", "server", "i3"]) 
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
            result = subprocess.run(['lsblk', '-J', '-b', '-o', 'NAME,SIZE,TYPE,MODEL,PATH,TRAN'],
                                    capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            disks_found = 0
            for device in data.get('blockdevices', []):
                if device.get('type') == 'disk' and device.get('tran') not in ['usb'] : 
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
        # --- Basic Validation ---
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
        disk_path = self.disk_combo.itemData(selected_disk_index) # Renamed to disk_path

        profile_name = self.profile_combo.currentText() # Renamed to profile_name
        wipe_disk = self.wipe_disk_checkbox.isChecked()

        if not all([hostname, username, password, locale, kb_layout, disk_path, timezone]):
            QMessageBox.warning(self, "Input Error", "Please fill in all required system and user fields.")
            return

        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match.")
            return

        # --- Confirmation ---
        confirm_msg = (f"This will install Mai Bloom OS on <b>{disk_path}</b> with hostname <b>{hostname}</b>.\n"
                       f"Profile: <b>{profile_name}</b>.\n")
        if wipe_disk:
            confirm_msg += f"<b>ALL DATA ON {disk_path} WILL BE ERASED and the disk will be auto-partitioned!</b>\n"
        else:
            confirm_msg += f"<b>The disk {disk_path} will NOT be wiped. You must have compatible pre-existing partitions. This is an ADVANCED option.</b>\n"
        confirm_msg += "Are you sure you want to proceed?"

        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg,
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            self.log_output.append("Installation cancelled by user.")
            return

        self.install_button.setEnabled(False)
        self.log_output.clear()
        self.log_output.append("Starting installation preparation for library mode...")

        # --- Prepare configuration dictionary for ArchinstallThread ---
        self.archinstall_config_dict = {
            "hostname": hostname,
            "locale_config": {
                "kb_layout": kb_layout,
                "sys_enc": "UTF-8", # Usually UTF-8
                "sys_lang": locale
            },
            "timezone": timezone,
            "swap": True, # Let archinstall manage swap, can be made configurable
            "users": [
                {
                    "username": username,
                    "password": password, 
                    "sudo": True
                }
            ],
            "kernels": ["linux"], 
            "packages": [], # Will be populated by categories
            # EFI and bootloader will be determined and added next
        }

        # Disk configuration part for the dictionary
        if wipe_disk:
            self.archinstall_config_dict["disk_config"] = {
                "config_type": "default_layout",
                "device_path": disk_path,
                "wipe": True
            }
        else:
            self.archinstall_config_dict["disk_config"] = {
                "config_type": "manual_partitioning"
            }
        
        # Profile configuration for the dictionary
        if profile_name:
             self.archinstall_config_dict["profile_config"] = {
                 "profile": {"main": profile_name}
             }

        # Network configuration (defaulting to NetworkManager)
        self.archinstall_config_dict["network_config"] = {"type": "nm"}


        # Add packages from selected categories
        selected_packages = []
        for category, checkbox in self.app_category_checkboxes.items():
            if checkbox.isChecked():
                selected_packages.extend(APP_CATEGORIES[category])
        if selected_packages:
            self.archinstall_config_dict["packages"] = list(set(selected_packages))

        # EFI/BIOS detection for the dictionary
        if os.path.exists("/sys/firmware/efi"):
            self.archinstall_config_dict["efi"] = True
            self.archinstall_config_dict["bootloader"] = "systemd-boot"
            self.log_output.append("UEFI system detected. Will configure for systemd-boot.")
        else:
            self.archinstall_config_dict["efi"] = False
            self.archinstall_config_dict["bootloader"] = "grub"
            self.log_output.append("BIOS system detected (or UEFI not found). Will configure for GRUB.")
        
        self.log_output.append("GUI Configuration dictionary prepared:")
        self.log_output.append(json.dumps(self.archinstall_config_dict, indent=2))

        # --- Start Archinstall in a separate thread using library mode ---
        self.installer_thread = ArchinstallThread(self.archinstall_config_dict) # Pass the dict
        self.installer_thread.installation_log.connect(self.update_log)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message):
        self.update_log(message)
        if success:
            QMessageBox.information(self, "Installation Complete", "Arch Linux base installation finished successfully!")
            if self.post_install_script_path:
                self.log_output.append("\n--- Installation successful. Proceeding to post-installation script. ---")
                # Ensure mount point is correctly fetched if archinstall changes it (library mode might not update self.archinstall_config_dict)
                # For now, using the default, but this might need adjustment if archinstall in lib mode exposes final mountpoint.
                mount_point_for_post_install = "/mnt/archinstall" # Default
                if "disk_config" in self.archinstall_config_dict and \
                   "config_type" in self.archinstall_config_dict["disk_config"] and \
                   self.archinstall_config_dict["disk_config"]["config_type"] == "manual_partitioning":
                       self.log_output.append("Manual partitioning was used. Post-install script needs to be aware of user-defined mount points.")
                # It's hard to get the dynamic mount_point from archinstall library mode without specific return or global state inspection.
                # PostInstallThread defaults to /mnt/archinstall which is archinstall's typical mount point.
                self.run_post_install_script(mount_point_for_post_install)
            else:
                self.install_button.setEnabled(True)
                self.log_output.append("No post-installation script to run. System setup complete.")
        else:
            QMessageBox.critical(self, "Installation Failed", f"Arch Linux installation failed.\nSee log for details.\n{message}")
            self.install_button.setEnabled(True)

    def run_post_install_script(self, target_mount_point): # Added target_mount_point argument
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
