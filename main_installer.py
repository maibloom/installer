import sys
import os
import traceback
import time
import json # For lsblk only
import logging
from pathlib import Path
from typing import Any, Optional, Dict, List, Union

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout, QSplitter)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# --- Attempt to import Archinstall components ---
# Based on user-provided working snippet + previous needs
ARCHINSTALL_LIBRARY_AVAILABLE = False
ARCHINSTALL_IMPORT_ERROR = None
try:
    import archinstall
    from archinstall import SysInfo
    from archinstall.lib import locale, disk # Core config/handler classes needed
    from archinstall.lib.installer import Installer
    from archinstall.lib.models import ProfileConfiguration, User, DiskEncryption, AudioConfiguration, Bootloader, Profile, NetworkConfiguration # Core models
    from archinstall.lib.disk.device_model import FilesystemType, BlockDevice # Disk specifics
    # DiskEncryptionMenu is INTERACTIVE - we need DiskEncryption model instead
    # from archinstall.lib.disk.encryption_menu import DiskEncryptionMenu 
    from archinstall.lib.disk.filesystem import FilesystemHandler
    # select_disk_config is INTERACTIVE - we need DiskLayoutConfiguration model instead
    # from archinstall.lib.interactions.disk_conf import select_disk_config 
    from archinstall.lib.profile.profiles_handler import profile_handler
    # Import the specific profile class we need (KDE)
    from archinstall.default_profiles.kde import KdeProfile # Verify this path/name
    
    from archinstall.lib.exceptions import ArchinstallError, UserInteractionRequired # Specific exceptions

    ARCHINSTALL_LIBRARY_AVAILABLE = True
    logging.info("Successfully imported Archinstall library components.")

except ImportError as e:
    ARCHINSTALL_IMPORT_ERROR = e
    logging.error(f"Failed to import required archinstall modules: {e}")
    # Define dummy exception/classes for GUI structure if imports fail
    class ArchinstallError(Exception): pass
    class UserInteractionRequired(Exception): pass
    class Bootloader: Grub = 'grub'; SystemdBoot = 'systemd-boot' 
    class DiskLayoutType: Default = 'Default'; Pre_mount = 'Pre_mount' 
    class WipeMode: Secure = 'Secure' 
    class FilesystemType: def __init__(self, name): self.name = name
    class DiskLayoutConfiguration: def __init__(self, *args, **kwargs): self.config_type=DiskLayoutType.Pre_mount; self.device=None; self.wipe=False
    class LocaleConfiguration: def __init__(self, *args, **kwargs): pass
    class ProfileConfiguration: def __init__(self, *args, **kwargs): pass
    class User: def __init__(self, *args, **kwargs): self.user_name=args[0] if args else 'dummy'
    class DiskEncryption: def __init__(self, *args, **kwargs): self.encryption_type = disk.EncryptionType.NoEncryption # Assuming EncryptionType exists
    class AudioConfiguration: def __init__(self, *args, **kwargs): pass
    class NetworkConfiguration: def __init__(self, *args, **kwargs): pass
    class Installer: 
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self # Simulate context manager
        def __exit__(self, exc_type, exc_val, exc_tb): pass
        def mount_ordered_layout(self): logging.info("Mock Installer: mount_ordered_layout()")
        def minimal_installation(self, *args, **kwargs): logging.info("Mock Installer: minimal_installation()")
        def add_additional_packages(self, *args, **kwargs): logging.info("Mock Installer: add_additional_packages()")
        def create_users(self, *args, **kwargs): logging.info("Mock Installer: create_users()")
        def add_bootloader(self, *args, **kwargs): logging.info("Mock Installer: add_bootloader()")
        def set_timezone(self, *args, **kwargs): logging.info("Mock Installer: set_timezone()")
        def user_set_pw(self, *args, **kwargs): logging.info("Mock Installer: user_set_pw()")
        def activate_time_synchronization(self, *args, **kwargs): logging.info("Mock Installer: activate_time_synchronization()")
        def enable_service(self, *args, **kwargs): logging.info("Mock Installer: enable_service()")
        def genfstab(self, *args, **kwargs): logging.info("Mock Installer: genfstab()")
    class FilesystemHandler: 
        def __init__(self, *args, **kwargs): pass
        def perform_filesystem_operations(self): logging.info("Mock FilesystemHandler: perform_filesystem_operations()")
    class profile_handler: 
        @staticmethod
        def install_profile_config(*args, **kwargs): logging.info("Mock profile_handler: install_profile_config()")
    class KdeProfile: def __init__(self, *args, **kwargs): self.name = "MockKDEProfile" # Mock profile needs a name attribute
    class SysInfo: @staticmethod def has_uefi(): return os.path.exists("/sys/firmware/efi") 
    # Need to ensure disk module exists for DiskLayoutType/EncryptionType enums
    if 'disk' not in locals(): class disk: class DiskLayoutType: Default = 'Default'; Pre_mount = 'Pre_mount'; class EncryptionType: NoEncryption='NoEncryption'; class WipeMode: Secure='Secure'

# --- App Configuration ---
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "code", "python", "gcc", "gdb", "base-devel"],
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"],
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}
DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME = "kde" 
MOUNT_POINT = Path('/mnt/maibloom_install') 

def check_root(): return os.geteuid() == 0

# --- Installer Engine Thread (Uses Archinstall Library Based on User Snippet) ---
class InstallerEngineThread(QThread):
    """
    This thread orchestrates the installation using archinstall library objects
    created and passed by the GUI. It follows the user's example snippet workflow.
    """
    installation_finished = pyqtSignal(bool, str) 
    installation_log = pyqtSignal(str, str)       

    def __init__(self, config_objects: Dict[str, Any]): # Expects dict of constructed objects
        super().__init__()
        self.config = config_objects # Store the pre-made config objects
        self._running = True

    def log(self, message, level="INFO"):
        self.installation_log.emit(str(message), level)

    def stop(self):
        self.log("Stop request received. Installation will halt before next major step.", "WARN")
        self._running = False

    def run(self):
        """Main thread execution logic."""
        self.log(f"Installation thread started for profile '{self.config.get('profile_name', 'N/A')}'.")
        mountpoint = MOUNT_POINT # Use the configured mount point

        try:
            if not ARCHINSTALL_LIBRARY_AVAILABLE:
                 raise ArchinstallError(f"Archinstall library components failed to import.")

            # --- Retrieve constructed configuration objects ---
            # These MUST be valid objects created by the GUI's gather_settings method
            disk_config: disk.DiskLayoutConfiguration = self.config['disk_config']
            disk_encryption: Optional[disk.DiskEncryption] = self.config.get('disk_encryption') # Optional
            locale_config: locale.LocaleConfiguration = self.config['locale_config']
            profile_config: ProfileConfiguration = self.config['profile_config'] # KDE profile config object
            user_list: List[User] = self.config['user_list'] # Should be list of User objects
            root_pw: str = self.config['root_pw']
            hostname: str = self.config['hostname']
            additional_packages: List[str] = self.config.get('additional_packages', [])
            bootloader: Bootloader = self.config['bootloader']
            kernels: List[str] = self.config.get('kernels', ['linux'])
            timezone: str = self.config['timezone']
            ntp_enabled: bool = self.config.get('ntp_enabled', True)
            swap_enabled: bool = self.config.get('swap_enabled', True)
            # services_to_enable: List[str] = self.config.get('services_to_enable', []) # Add if GUI configures this

            self.log("Configuration objects received.", "DEBUG")
            if not self._running: raise InterruptedError("Stopped before filesystem operations.")

            # --- Filesystem Operations ---
            self.log("Initializing Filesystem Handler...")
            fs_handler = disk.FilesystemHandler(disk_config, disk_encryption)
            self.log("Performing filesystem operations (formatting)...")
            fs_handler.perform_filesystem_operations() # Formats based on disk_config
            self.log("Filesystem operations complete.")

            if not self._running: raise InterruptedError("Stopped after formatting.")

            # --- Installation using Installer context ---
            self.log(f"Initializing Installer for mountpoint {mountpoint}...")
            with Installer(mountpoint, disk_config, disk_encryption=disk_encryption, kernels=kernels) as installation:
                self.log("Installer context entered.")
                if not self._running: raise InterruptedError("Stopped before mounting.")

                # 1. Mount Layout (if not Pre_mount)
                # Check type using the actual object/enum from archinstall.lib.disk
                if disk_config.config_type != disk.DiskLayoutType.Pre_mount:
                     self.log("Mounting configured layout...")
                     installation.mount_ordered_layout()

                if not self._running: raise InterruptedError("Stopped after mounting.")

                # 2. Minimal Installation (Base + Hostname/Locale)
                self.log("Performing minimal installation (base system)...")
                installation.minimal_installation(hostname=hostname, locale_config=locale_config)
                self.log("Minimal installation complete.")

                # 3. Add Additional Packages (early step? Check snippet order)
                if additional_packages:
                     self.log(f"Installing {len(additional_packages)} additional packages...")
                     installation.add_additional_packages(additional_packages)
                
                if not self._running: raise InterruptedError("Stopped after packages/minimal.")

                # 4. Install Profile (KDE)
                self.log(f"Installing profile configuration for '{getattr(profile_config.profile, 'name', 'N/A')}'...")
                # This uses the ProfileConfiguration object created by the GUI
                profile_handler.install_profile_config(installation, profile_config)
                self.log("Profile installation finished.")

                # 5. Create Users (using User objects created by GUI)
                if user_list:
                     self.log(f"Creating users...")
                     installation.create_users(user_list)
                
                # 6. Set Root Password
                if root_pw:
                    self.log("Setting root password...")
                    installation.user_set_pw('root', root_pw)

                if not self._running: raise InterruptedError("Stopped after users/passwords.")
                
                # 7. Configure Timezone & NTP
                if timezone:
                    self.log(f"Setting timezone: {timezone}")
                    installation.set_timezone(timezone)
                if ntp_enabled:
                    self.log("Enabling NTP time synchronization...")
                    installation.activate_time_synchronization()

                # 8. Bootloader
                self.log(f"Adding bootloader: {bootloader.value if hasattr(bootloader, 'value') else bootloader}")
                if bootloader == Bootloader.Grub and SysInfo.has_uefi():
                    self.log("Ensuring GRUB package installed for UEFI...")
                    installation.add_additional_packages("grub") # Ensure grub pkg exists
                installation.add_bootloader(bootloader, False) # False for non-UKI default
                self.log("Bootloader setup finished.")

                # 9. Network (Using NetworkManager assumed by default packages)
                self.log("Enabling NetworkManager service...")
                installation.enable_service("NetworkManager") # Ensure NetworkManager service is enabled

                # 10. Display Manager (SDDM for KDE)
                self.log("Enabling Display Manager (SDDM for KDE)...")
                installation.enable_service("sddm")

                if not self._running: raise InterruptedError("Stopped before fstab.")

                # 11. Generate fstab
                self.log("Generating fstab...")
                installation.genfstab()
                self.log("fstab generated.")

                # End of Installer context manager (handles cleanup/unmounting?)
                self.log("Installer context exited.")
            
            # Final success
            self.log("Installation logic completed successfully!")
            self.installation_finished.emit(True, f"Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME}) installed successfully!")

        # --- Error Handling ---
        except InterruptedError as e:
            self.log(f"Installation process was interrupted: {e}", "WARN")
            self.installation_finished.emit(False, f"Installation interrupted by user.")
        except (ArchinstallError, UserInteractionRequired) as e: # Catch specific library errors
            self.log(f"Archinstall Library Error: {type(e).__name__} - {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")
            self.installation_finished.emit(False, f"Installation failed: {e}")
        except KeyError as e: 
            self.log(f"Configuration key missing during installation: {e}", "ERROR")
            self.log(traceback.format_exc(), "ERROR")
            self.installation_finished.emit(False, f"Configuration Error: Missing key '{e}' needed by installer.")
        except Exception as e: # General catch-all
            self.log(f"An unexpected critical error occurred: {type(e).__name__}: {e}", "CRITICAL_ERROR")
            self.log(traceback.format_exc(), "CRITICAL_ERROR")
            self.installation_finished.emit(False, f"A critical error occurred: {e}")
        finally:
            self.log("InstallerEngineThread finished execution.", "INFO")


# --- Main Application Window (GUI using PyQt5) ---
class MaiBloomInstallerApp(QWidget):
    """Main GUI Window for the installer."""
    
    def __init__(self):
        super().__init__()
        self.installer_thread = None # Worker thread reference
        
        # Initialize UI elements
        self.hostname_input = QLineEdit("maibloom-os")
        self.username_input = QLineEdit("maiuser")
        self.password_input = QLineEdit()
        self.locale_input = QLineEdit("en_US.UTF-8")
        self.kb_layout_input = QLineEdit("us")
        self.timezone_input = QLineEdit("UTC")
        self.disk_combo = QComboBox()
        self.scan_disks_button = QPushButton("Scan for Disks")
        self.wipe_disk_checkbox = QCheckBox("Wipe disk & auto-configure standard layout")
        self.app_category_checkboxes: Dict[str, QCheckBox] = {}
        self.log_output = QTextEdit()
        self.install_button = QPushButton(f"Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME})")

        self.init_ui() # Setup the user interface layout
        self.update_log_output("Welcome to Mai Bloom OS Installer!")
        
        # Initial check for library availability
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
             self.handle_library_load_error()
        else:
             self.update_log_output("Archinstall library loaded successfully.")
             self.trigger_disk_scan() # Trigger initial scan

    def handle_library_load_error(self):
        """Disables UI elements and shows error if library failed to load."""
        self.update_log_output(f"CRITICAL ERROR: Archinstall library not loaded: {ARCHINSTALL_IMPORT_ERROR}", "ERROR")
        QMessageBox.critical(self, "Startup Error", 
                             f"Failed to load essential Archinstall library components:\n{ARCHINSTALL_IMPORT_ERROR}\n\n"
                             "Please ensure Archinstall is correctly installed for the Python environment and accessible.\n"
                             "The installer cannot function.")
        self.install_button.setEnabled(False)
        self.scan_disks_button.setEnabled(False)
        for child in self.findChildren(QWidget): # Disable all inputs
             if isinstance(child, (QLineEdit, QComboBox, QCheckBox, QPushButton)):
                  child.setEnabled(False)

    def init_ui(self):
        """Sets up the GUI widgets and layouts."""
        self.setWindowTitle(f'Mai Bloom OS Installer ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME} via Archinstall Lib)')
        self.setGeometry(100, 100, 850, 700) # Window size and position
        overall_layout = QVBoxLayout(self) # Main layout for the window

        # --- Top Title ---
        title_label = QLabel(f"<b>Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME})</b>")
        title_label.setAlignment(Qt.AlignCenter)
        overall_layout.addWidget(title_label)
        overall_layout.addWidget(QLabel("<small>This installer uses the <b>archinstall</b> Python library directly for setup.</small>"))
        
        # --- Main Area (Splitter: Controls | Log) ---
        splitter = QSplitter(Qt.Horizontal)
        overall_layout.addWidget(splitter)

        # --- Left Pane: Controls ---
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)

        # GroupBox 1: Disk Setup
        disk_group = QGroupBox("1. Disk Selection & Preparation")
        disk_layout_vbox = QVBoxLayout()
        # Scan button already initialized in __init__
        self.scan_disks_button.setToolTip("Scan the system for installable disk drives using archinstall library.")
        self.scan_disks_button.clicked.connect(self.trigger_disk_scan)
        disk_layout_vbox.addWidget(self.scan_disks_button)
        # Disk combo box already initialized
        self.disk_combo.setToolTip("Select the target disk for installation.\nEnsure this is the correct disk!")
        disk_layout_vbox.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        # Wipe checkbox already initialized
        self.wipe_disk_checkbox.setChecked(True)
        self.wipe_disk_checkbox.setToolTip("IMPORTANT: This option attempts to instruct archinstall library to ERASE the selected disk\n"
                                           "and create a standard partition layout (e.g., EFI, Swap, Root).\n"
                                           "This requires correct implementation of DiskLayoutConfiguration in gather_settings().")
        disk_layout_vbox.addWidget(self.wipe_disk_checkbox)
        disk_group.setLayout(disk_layout_vbox)
        controls_layout.addWidget(disk_group)

        # GroupBox 2: System & User Configuration
        system_group = QGroupBox("2. System & User Details"); 
        system_layout_grid = QGridLayout()
        # Widgets already initialized
        self.hostname_input.setToolTip("Set the computer's network name (e.g., mypc).")
        system_layout_grid.addWidget(QLabel("Hostname:"), 0, 0); system_layout_grid.addWidget(self.hostname_input, 0, 1)
        self.username_input.setToolTip("Enter the desired username for your main account.")
        system_layout_grid.addWidget(QLabel("Username:"), 1, 0); system_layout_grid.addWidget(self.username_input, 1, 1)
        self.password_input.setPlaceholderText("Enter password (used for User & Root)"); self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setToolTip("Set the password for your user account.\nThis password will ALSO be set for the 'root' administrator account.")
        system_layout_grid.addWidget(QLabel("Password (User+Root):"), 2, 0); system_layout_grid.addWidget(self.password_input, 2, 1)
        self.locale_input.setToolTip("Set the system language and encoding (e.g., en_US.UTF-8, fr_FR.UTF-8).")
        system_layout_grid.addWidget(QLabel("Locale:"), 3,0); system_layout_grid.addWidget(self.locale_input, 3,1)
        self.kb_layout_input.setToolTip("Set the keyboard layout for the console (e.g., us, uk, de_nodeadkeys).")
        system_layout_grid.addWidget(QLabel("Keyboard Layout:"), 4,0); system_layout_grid.addWidget(self.kb_layout_input, 4,1)
        self.timezone_input.setToolTip("Set the system timezone (e.g., UTC, America/New_York, Europe/Paris).\nUse format Region/City.")
        system_layout_grid.addWidget(QLabel("Timezone:"), 5,0); system_layout_grid.addWidget(self.timezone_input, 5,1)
        system_group.setLayout(system_layout_grid)
        controls_layout.addWidget(system_group)
        
        # GroupBox 3: Additional Applications
        app_group = QGroupBox(f"3. Additional Applications (Optional)")
        app_layout_grid = QGridLayout()
        # Checkboxes created here
        row, col = 0,0
        for cat_name in APP_CATEGORIES.keys():
            self.app_category_checkboxes[cat_name] = QCheckBox(f"{cat_name}")
            pkg_list_tooltip = f"Install: {', '.join(APP_CATEGORIES[cat_name][:4])}" # Show first few packages
            if len(APP_CATEGORIES[cat_name]) > 4: pkg_list_tooltip += "..."
            self.app_category_checkboxes[cat_name].setToolTip(pkg_list_tooltip)
            app_layout_grid.addWidget(self.app_category_checkboxes[cat_name], row, col)
            col +=1
            if col > 1: col = 0; row +=1 # Arrange in 2 columns
        app_group.setLayout(app_layout_grid)
        controls_layout.addWidget(app_group)
        
        # Add stretch to push controls towards the top
        controls_layout.addStretch(1) 
        # Add the controls widget pane to the splitter
        splitter.addWidget(controls_widget)

        # --- Right Pane: Log Output ---
        log_group_box = QGroupBox("Installation Log")
        log_layout_vbox = QVBoxLayout()
        # Log widget initialized in __init__
        self.log_output.setReadOnly(True); self.log_output.setLineWrapMode(QTextEdit.NoWrap); self.log_output.setStyleSheet("font-family: monospace; background-color: #f0f0f0;") 
        log_layout_vbox.addWidget(self.log_output)
        log_group_box.setLayout(log_layout_vbox)
        # Add the log widget pane to the splitter
        splitter.addWidget(log_group_box)
        
        # Set initial size ratio for the panes
        splitter.setSizes([400, 450]) 
        
        # --- Bottom: Install Button ---
        # Install button initialized in __init__
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold; border-radius: 5px;")
        self.install_button.setToolTip("Begin the installation process using the configured settings.")
        self.install_button.clicked.connect(self.start_installation)
        # Center the button using a QHBoxLayout with stretches
        button_layout = QHBoxLayout(); button_layout.addStretch(); button_layout.addWidget(self.install_button); button_layout.addStretch()
        overall_layout.addLayout(button_layout)

    def create_form_row(self, label_text, widget):
        """Helper method to create a standard Label + Widget horizontal layout."""
        row_layout = QHBoxLayout(); label = QLabel(label_text); label.setFixedWidth(120) 
        row_layout.addWidget(label); row_layout.addWidget(widget); return row_layout

    def trigger_disk_scan(self):
        """Initiates disk scan using archinstall library helper (or placeholder)."""
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
            self.update_log_output("Disk Scan unavailable: Archinstall library not loaded.", "ERROR"); return
            
        self.update_log_output("GUI: Requesting disk scan via archinstall library...")
        self.scan_disks_button.setEnabled(False) # Disable button during scan
        try:
            # --- USER ACTION REQUIRED ---
            # Replace the placeholder logic below with DIRECT calls to archinstall's
            # disk listing function(s). This method runs synchronously in the GUI thread.
            # If the library call is slow, it should be moved to its own thread.
            
            processed_disks = {}
            self.update_log_output(" (Using placeholder disk scan logic - USER MUST REPLACE)", "WARN")
            
            # --- Placeholder/Mock Logic (REMOVE WHEN IMPLEMENTING REAL SCAN) ---
            if 'disk' in sys.modules: # Check if our dummy or real module is loaded
                 # Hypothetical call structure:
                 # all_devices = archinstall.lib.disk.all_blockdevices() # Replace with actual function
                 
                 # Using placeholder function from dummy class for demo
                 block_devices = disk.get_all_blockdevices() # Assuming disk module is imported as 'disk'

                 # Filtering logic (adapt attributes to real BlockDevice object)
                 for device in block_devices:
                     try:
                         dev_path_str = str(getattr(device,'path', 'N/A'))
                         dev_type = str(getattr(device, 'type', 'unknown')).lower()
                         dev_ro = getattr(device, 'read_only', True)
                         dev_pkname = getattr(device, 'pkname', None)
                         dev_model = getattr(device, 'model', 'Unknown Model')
                         dev_size_bytes = int(getattr(device, 'size', 0))
                         # Filter for suitable disks (example criteria)
                         if dev_type == 'disk' and not dev_ro and not dev_pkname and dev_size_bytes >= 20 * (1024**3):
                              processed_disks[dev_path_str] = {"model": dev_model, "size": f"{dev_size_bytes / (1024**3):.2f} GB", "path": dev_path_str}
                     except Exception as inner_e:
                          self.update_log_output(f"Error processing device {getattr(device, 'path', 'N/A')}: {inner_e}", "WARN")
            else:
                 self.update_log_output("Archinstall 'disk' module not available for scan.", "ERROR")
            # --- End Placeholder/Mock Logic ---
            
            self.on_disk_scan_complete(processed_disks) 

        except Exception as e:
            self.update_log_output(f"Disk Scan Error: {e}", "ERROR")
            self.update_log_output(traceback.format_exc(), "ERROR")
            self.on_disk_scan_complete({}) # Send empty results on error
            QMessageBox.critical(self, "Disk Scan Error", f"Failed to scan disks using archinstall library: {e}")
        finally:
            self.scan_disks_button.setEnabled(True) # Re-enable button

    def on_disk_scan_complete(self, disks_data: Dict[str, Dict]):
        """Slot to handle the result of the disk scan signal or direct call."""
        self.update_log_output(f"GUI: Disk scan finished. Populating {len(disks_data)} suitable disk(s).")
        self.disk_combo.clear()
        if disks_data:
            for path_key, info_dict in sorted(disks_data.items()): # Sort by path
                display_text = f"{path_key} - {info_dict.get('model', 'N/A')} ({info_dict.get('size', 'N/A')})"
                self.disk_combo.addItem(display_text, userData=path_key) # Store path in userData
        else:
            self.update_log_output("GUI: No suitable disks found by scan.", "WARN")

    def update_log_output(self, message: str, level: str = "INFO"):
        """Appends a message to the GUI log view, adding a level prefix."""
        prefix = "" if level == "INFO" else f"[{level}] "
        self.log_output.append(prefix + message)
        self.log_output.ensureCursorVisible() # Auto-scroll
        if level not in ["DEBUG", "CMD_OUT", "CMD_ERR", "CMD"]: 
             QApplication.processEvents()

    def gather_settings_and_create_config_objects(self) -> Optional[Dict[str, Any]]:
        """
        Gathers settings from GUI, validates them, and attempts to create the
        necessary archinstall configuration objects.
        Returns a dictionary of config objects/values if successful, None otherwise.

        !!! CRITICAL USER IMPLEMENTATION AREA !!!
        Requires detailed knowledge of archinstall's internal API.
        Replace placeholder object creations with actual ones.
        """
        self.update_log_output("Gathering settings and creating archinstall config objects...")
        config_objects: Dict[str, Any] = {}
        # --- Disk ---
        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: QMessageBox.warning(self, "Input Error", "Please select a target disk."); return None
        target_disk_path = Path(self.disk_combo.itemData(selected_disk_index)) # Get Path object
        if not target_disk_path: QMessageBox.warning(self, "Input Error", "Invalid disk selected."); return None
        wipe_disk_flag = self.wipe_disk_checkbox.isChecked()

        # --- System & User ---
        hostname = self.hostname_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text() 
        locale_str = self.locale_input.text().strip()
        kb_layout = self.kb_layout_input.text().strip()
        timezone = self.timezone_input.text().strip()
        
        # --- Validation ---
        if not all([hostname, username, password, locale_str, kb_layout, timezone]):
            QMessageBox.warning(self, "Input Error", "Please fill all System & User fields."); return None

        # --- Profile & Packages ---
        profile_name = DEFAULT_DESKTOP_ENVIRONMENT_PROFILE 
        additional_packages = []
        for cat_name, checkbox_widget in self.app_category_checkboxes.items():
            if checkbox_widget.isChecked():
                additional_packages.extend(APP_CATEGORIES.get(cat_name, []))
        base_essentials = ["sudo", "nano"] 
        additional_packages = list(set(additional_packages + base_essentials))
        config_objects["additional_packages"] = additional_packages # Store list directly

        # --- Create Configuration Objects (Critical Section) ---
        try:
            if not ARCHINSTALL_LIBRARY_AVAILABLE:
                 raise ArchinstallError("Cannot create config objects, library not loaded.")
                 
            # Store simple values
            config_objects["hostname"] = hostname
            config_objects["root_pw"] = password
            config_objects["timezone"] = timezone
            config_objects["kernels"] = ['linux'] 
            config_objects["ntp_enabled"] = True
            config_objects["swap_enabled"] = True 
            
            is_efi = SysInfo.has_uefi()
            config_objects["bootloader"] = models.Bootloader.SystemdBoot if is_efi else models.Bootloader.Grub
            
            # --- Complex Object Creation (USER MUST IMPLEMENT) ---
            
            # 1. LocaleConfiguration
            self.log("TODO: Create archinstall.lib.locale.LocaleConfiguration object.", "WARN")
            config_objects['locale_config'] = locale.LocaleConfiguration(
                kb_layout=kb_layout, sys_lang=locale_str, sys_enc='UTF-8' )
            
            # 2. User list (list of models.User objects)
            self.log("TODO: Create list of archinstall.lib.models.User objects.", "WARN")
            config_objects['user_list'] = [ models.User(username, password, sudo=True) ]
            
            # 3. ProfileConfiguration for KDE
            self.log(f"TODO: Create archinstall.lib.models.ProfileConfiguration for '{profile_name}'.", "WARN")
            # You might need to import the actual profile class, e.g., KdeProfile
            # kde_profile_instance = KdeProfile() # Or KdeProfile(options...) if needed
            # config_objects['profile_config'] = models.ProfileConfiguration(profile=kde_profile_instance)
            # Placeholder: Assuming simple structure works (unlikely for complex profiles)
            config_objects['profile_config'] = {'profile': {'main': profile_name}} 

            # 4. DiskLayoutConfiguration (Most complex)
            self.log("TODO: Create archinstall.lib.disk.DiskLayoutConfiguration object.", "CRITICAL")
            if wipe_disk_flag:
                # Placeholder for "wipe & default layout". Requires research!
                config_objects['disk_config'] = disk.DiskLayoutConfiguration(
                     config_type=disk.DiskLayoutType.Default, # VERIFY ENUM/VALUE
                     device=target_disk_path, 
                     wipe=True,
                     fs_type=disk.FilesystemType('ext4'), # Specify root FS type?
                     # ... other params for default layout ...
                )
                self.log("Created DISK config (Wipe/Auto) - PLACEHOLDER NEEDS IMPLEMENTATION", "WARN")
            else:
                # Placeholder for "use existing". Requires research!
                config_objects['disk_config'] = disk.DiskLayoutConfiguration(
                    config_type=disk.DiskLayoutType.Pre_mount, # VERIFY ENUM/VALUE
                    # mountpoints={...} # Needs mapping from user or detection
                )
                self.log("Created DISK config (Use Existing) - PLACEHOLDER NEEDS IMPLEMENTATION", "WARN")

            # 5. Optional Configurations (Set to None or default objects)
            config_objects['disk_encryption'] = None 
            # config_objects['network_config'] = models.NetworkConfiguration(nic='NetworkManager') 
            # config_objects['audio_config'] = models.AudioConfiguration(audio='pipewire')

            # Add profile name for logging/display later
            config_objects['profile_name'] = profile_name 

            self.update_log_output("Successfully created configuration objects (Check TODOs!).", "INFO")
            return config_objects # Return the dictionary of created objects

        except ImportError as e:
             self.update_log_output(f"Import Error creating config objects: {e}", "ERROR"); return None
        except Exception as e: 
            self.update_log_output(f"Error creating config objects: {e}", "ERROR")
            self.update_log_output(traceback.format_exc(), "ERROR")
            QMessageBox.critical(self, "Configuration Error", f"Failed to create installation configuration objects: {e}\n\nCheck archinstall API/version and TODO comments.")
            return None


    def start_installation(self):
        """Gathers settings, creates config objects, confirms, and starts thread."""
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
             QMessageBox.critical(self, "Error", "Archinstall library not loaded. Cannot install.")
             return

        # Create the configuration objects based on GUI settings
        config_objects = self.gather_settings_and_create_config_objects()
        if not config_objects:
             self.update_log_output("Configuration creation failed. Installation aborted.", "ERROR")
             return # Stop if config creation failed

        # Confirmation Dialog 
        target_disk_path_for_dialog = str(config_objects.get('disk_config', {}).device or "N/A") # Example access
        wipe_disk_val = getattr(config_objects.get('disk_config'), 'wipe', False) # Example access
        profile_name_for_dialog = config_objects.get('profile_name', 'N/A')

        wipe_warning = "YES (ENTIRE DISK WILL BE ERASED!)" if wipe_disk_val else "NO (Advanced - Using existing partitions)"
        confirm_msg = (f"Ready to install Mai Bloom OS ({profile_name_for_dialog}) using the archinstall library:\n\n"
                       f"  - Target Disk: {target_disk_path_for_dialog}\n"
                       f"  - Wipe Disk & Auto-Configure: {wipe_warning}\n\n"
                       "Ensure all selections are correct.\nPROCEED WITH INSTALLATION?")
        
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.update_log_output("Installation cancelled by user."); return

        # Start the installation thread, passing the created config objects
        self.install_button.setEnabled(False); self.scan_disks_button.setEnabled(False)
        self.log_output.clear(); self.update_log_output("Starting installation via archinstall library...")

        self.installer_thread = InstallerEngineThread(config_objects) 
        self.installer_thread.installation_log.connect(self.update_log_output)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start() 

    def on_installation_finished(self, success, message):
        """Handles completion signal from the installer thread."""
        self.update_log_output(f"GUI: Installation finished signal. Success: {success}")
        if success:
            QMessageBox.information(self, "Installation Complete", message + "\nYou may now reboot.")
        else:
            log_content = self.log_output.toPlainText()
            last_log_lines = "\n".join(log_content.splitlines()[-20:])
            detailed_message = f"{message}\n\nLast log entries:\n---\n{last_log_lines}\n---"
            QMessageBox.critical(self, "Installation Failed", detailed_message)
            
        self.install_button.setEnabled(True); self.scan_disks_button.setEnabled(True)
        self.installer_thread = None 

        # Attempt unmount after completion/failure (best effort)
        try:
             # Need mount point info (might be in config_objects or a default)
             mount_point_to_unmount = MOUNT_POINT # Use default
             if Path(mount_point_to_unmount).is_mount(): 
                 self.update_log_output("Attempting final unmount...")
                 subprocess.run(["umount", "-R", str(mount_point_to_unmount)], capture_output=True, text=True, check=False)
                 self.update_log_output(f"Unmount attempt finished for {mount_point_to_unmount}.")
        except Exception as e:
             self.update_log_output(f"Error during final unmount attempt: {e}", "WARN")

    # select_post_install_script remains unchanged, currently unused by engine
    def select_post_install_script(self): pass
    # closeEvent remains unchanged
    def closeEvent(self, event): 
        if self.installer_thread and self.installer_thread.isRunning():
            reply = QMessageBox.question(self, 'Installation in Progress', "Installation running. Exit anyway?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if hasattr(self.installer_thread, 'stop'): self.installer_thread.stop()
                self.installer_thread.wait(1000) 
                event.accept()
            else: event.ignore()
        else: event.accept()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    if not check_root():
        logging.error("Application must be run as root.")
        app_temp = QApplication.instance();
        if not app_temp: app_temp = QApplication(sys.argv)
        QMessageBox.critical(None, "Root Access Required", "This installer must be run with root privileges.")
        sys.exit(1)
    app = QApplication(sys.argv)
    installer_gui = MaiBloomInstallerApp()
    installer_gui.show()
    sys.exit(app.exec_())

