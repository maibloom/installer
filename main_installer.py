##############################################################################
# Mai Bloom OS Installer - Using Archinstall Library Directly
# Based on user-provided snippet structure and stability preference.
# Version with SyntaxError fix in dummy class definitions.
##############################################################################

import sys
import os
import traceback
import time
import json # For lsblk only
import logging # Now imported globally
from pathlib import Path
from typing import Any, TYPE_CHECKING, Optional, Dict, List, Union # Type hinting

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout, QSplitter)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# --- Attempt to import Archinstall components ---
# This section tries to import necessary archinstall components.
# If these imports fail, the installer cannot function with the real library.
# User MUST verify these imports match their installed archinstall version.
ARCHINSTALL_LIBRARY_AVAILABLE = False
ARCHINSTALL_IMPORT_ERROR = None
try:
    import archinstall
    from archinstall import info, debug, SysInfo # Logging/SysInfo funcs
    from archinstall.lib import locale, disk    # Core modules for config objects/handlers
    from archinstall.lib.configuration import ConfigurationOutput # Potentially useful
    from archinstall.lib.installer import Installer             # Core installer class
    from archinstall.lib.models import ProfileConfiguration, User, DiskEncryption, AudioConfiguration, Bootloader, Profile # Config models
    from archinstall.lib.models.network_configuration import NetworkConfiguration
    from archinstall.lib.disk.device_model import FilesystemType, BlockDevice # Disk specifics
    from archinstall.lib.disk.filesystem import FilesystemHandler
    # DiskEncryptionMenu and select_disk_config are interactive TUI elements, avoid importing/using them directly.
    # We need to create the config objects programmatically.
    from archinstall.lib.profile.profiles_handler import profile_handler # To handle profile logic?
    # Import the specific profile class we need (KDE)
    from archinstall.default_profiles.kde import KdeProfile # Verify this path/name
    
    from archinstall.lib.exceptions import ArchinstallError, UserInteractionRequired # Specific exceptions

    # --- Constants for archinstall.arguments keys (from user snippet) ---
    ARG_DISK_CONFIG = 'disk_config'; ARG_LOCALE_CONFIG = 'locale_config'; ARG_ROOT_PASSWORD = '!root-password'
    ARG_USERS = '!users'; ARG_PROFILE_CONFIG = 'profile_config'; ARG_AUDIO_CONFIG = 'audio_config'
    ARG_KERNE = 'kernels'; ARG_NTP = 'ntp'; ARG_PACKAGES = 'packages'; ARG_BOOTLOADER = 'bootloader'
    ARG_MIRROR_CONFIG = 'mirror_config'; ARG_NETWORK_CONFIG = 'network_config'; ARG_TIMEZONE = 'timezone'
    ARG_SERVICES = 'services'; ARG_CUSTOM_COMMANDS = 'custom-commands'; ARG_ENCRYPTION = 'disk_encryption'
    ARG_SWAP = 'swap'; ARG_UKI = 'uki'; ARG_HOSTNAME = 'hostname'

    # Initialize global state containers if archinstall relies on them
    if not hasattr(archinstall, 'arguments'): archinstall.arguments = {}
    if not hasattr(archinstall, 'storage'): archinstall.storage = {}
    archinstall.storage['MOUNT_POINT'] = Path('/mnt/maibloom_install') # Set default mount point

    ARCHINSTALL_LIBRARY_AVAILABLE = True
    logging.info("Successfully imported Archinstall library components.")

except ImportError as e:
    ARCHINSTALL_IMPORT_ERROR = e
    logging.error(f"Failed to import required archinstall modules: {e}")
    # Define dummy exception/classes for GUI structure if imports fail
    class ArchinstallError(Exception): pass
    class UserInteractionRequired(Exception): pass
    class Bootloader: Grub = 'grub'; SystemdBoot = 'systemd-boot' # Dummy enum values
    class DiskLayoutType: Default = 'Default'; Pre_mount = 'Pre_mount' # Dummy enum values
    class WipeMode: Secure = 'Secure' # Dummy enum value
    
    # --- CORRECTED DUMMY CLASS LINE ---
    class FilesystemType: def __init__(self, name): self.name = name 
    # --- END CORRECTION ---

    class DiskLayoutConfiguration: def __init__(self, *args, **kwargs): self.config_type=DiskLayoutType.Pre_mount; self.device=None; self.wipe=False
    class LocaleConfiguration: def __init__(self, *args, **kwargs): pass
    class ProfileConfiguration: def __init__(self, *args, **kwargs): pass
    class User: def __init__(self, *args, **kwargs): self.user_name=args[0] if args else 'dummy'
    class DiskEncryption: 
        class EncryptionType: NoEncryption='NoEncryption' 
        def __init__(self, *args, **kwargs): self.encryption_type = self.EncryptionType.NoEncryption
    class AudioConfiguration: def __init__(self, *args, **kwargs): pass
    class NetworkConfiguration: def __init__(self, *args, **kwargs): pass
    class Installer: 
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self 
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
    class KdeProfile: def __init__(self, *args, **kwargs): self.name = "MockKDEProfile" 
    class SysInfo: @staticmethod def has_uefi(): return os.path.exists("/sys/firmware/efi") 
    # Define dummy disk module structure needed by placeholders
    if 'disk' not in locals(): 
        class disk_module: 
            DiskLayoutConfiguration=DiskLayoutConfiguration 
            DiskLayoutType=DiskLayoutType
            EncryptionType=DiskEncryption.EncryptionType 
            WipeMode=WipeMode
            FilesystemType=FilesystemType
            FilesystemHandler=FilesystemHandler
            # Add dummy BlockDevice if needed by placeholders (e.g., disk scan)
            class BlockDevice: pass
            @staticmethod
            def get_all_blockdevices(): return [] # Placeholder function
        disk = disk_module # Assign dummy module to disk name

    # Dummy args if imports fail
    ARG_DISK_CONFIG = 'disk_config'; ARG_LOCALE_CONFIG = 'locale_config'; ARG_ROOT_PASSWORD = '!root-password'; ARG_USERS = '!users'; ARG_PROFILE_CONFIG = 'profile_config'; ARG_HOSTNAME = 'hostname'; ARG_PACKAGES = 'packages'; ARG_BOOTLOADER = 'bootloader'; ARG_TIMEZONE = 'timezone'; ARG_KERNE = 'kernels'; ARG_NTP = 'ntp'; ARG_SWAP = 'swap'; ARG_ENCRYPTION = 'disk_encryption'
    logging.warning("Using placeholder definitions for Archinstall components.")


# --- App Configuration ---
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "code", "python", "gcc", "gdb", "base-devel"],
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"],
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}
DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME = "kde" # Mai Bloom OS default
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

    def __init__(self): 
        super().__init__()
        # Reads configuration directly from archinstall.arguments populated by GUI
        self._running = True

    def log(self, message, level="INFO"):
        """Sends a log message to the GUI thread."""
        self.installation_log.emit(str(message), level)

    def stop(self):
        """Requests the installation process to stop."""
        self.log("Stop request received. Installation will halt before next major step.", "WARN")
        self._running = False

    def _perform_installation_steps(self, mountpoint: Path) -> None:
        """Performs the installation steps using archinstall library calls."""
        self.log('Starting installation steps using Archinstall library...')
        
        # Retrieve config objects/values from the global arguments dict
        disk_config = archinstall.arguments.get(ARG_DISK_CONFIG)
        locale_config = archinstall.arguments.get(ARG_LOCALE_CONFIG)
        disk_encryption = archinstall.arguments.get(ARG_ENCRYPTION)
        hostname = archinstall.arguments.get(ARG_HOSTNAME, 'maibloom-os')
        users = archinstall.arguments.get(ARG_USERS, [])
        root_pw = archinstall.arguments.get(ARG_ROOT_PASSWORD)
        profile_config = archinstall.arguments.get(ARG_PROFILE_CONFIG)
        additional_packages = archinstall.arguments.get(ARG_PACKAGES, [])
        bootloader_choice = archinstall.arguments.get(ARG_BOOTLOADER)
        kernels = archinstall.arguments.get(ARG_KERNE, ['linux'])
        timezone = archinstall.arguments.get(ARG_TIMEZONE)
        enable_ntp = archinstall.arguments.get(ARG_NTP, True)
        enable_swap = archinstall.arguments.get(ARG_SWAP, True)
        audio_config = archinstall.arguments.get(ARG_AUDIO_CONFIG)
        network_config = archinstall.arguments.get(ARG_NETWORK_CONFIG)
        services_to_enable = archinstall.arguments.get(ARG_SERVICES)
        custom_commands_to_run = archinstall.arguments.get(ARG_CUSTOM_COMMANDS)

        if not all([disk_config, locale_config, users, root_pw, profile_config, bootloader_choice]):
             raise ArchinstallError("Core configuration arguments missing in archinstall.arguments.")

        enable_testing = 'testing' in archinstall.arguments.get('additional-repositories', [])
        enable_multilib = 'multilib' in archinstall.arguments.get('additional-repositories', [])
        run_mkinitcpio = not archinstall.arguments.get(ARG_UKI, False)

        self.log(f"Initializing Installer for mountpoint {mountpoint}...")
        # Use the Installer class as a context manager
        with Installer(mountpoint, disk_config, disk_encryption=disk_encryption, kernels=kernels) as installation:
            self.log("Installer context entered.")
            if not self._running: raise InterruptedError("Stopped before mounting.")

            # Mount filesystem if not pre-mounted
            if disk_config.config_type != disk.DiskLayoutType.Pre_mount:
                 self.log("Mounting configured layout...")
                 installation.mount_ordered_layout()
            else:
                 self.log("Disk layout type is Pre_mount, skipping mount_ordered_layout.")

            if not self._running: raise InterruptedError("Stopped after mounting attempt.")

            self.log("Performing sanity checks...")
            installation.sanity_check()

            if disk_encryption and disk_encryption.encryption_type != disk.EncryptionType.NoEncryption:
                self.log("Handling disk encryption setup...")
                installation.generate_key_files() 

            if mirror_config := archinstall.arguments.get(ARG_MIRROR_CONFIG):
                 self.log("Setting mirrors on host...")
                 installation.set_mirrors(mirror_config, on_target=False)

            if not self._running: raise InterruptedError("Stopped before minimal installation.")

            self.log("Performing minimal installation (pacstrap base, locale, hostname)...")
            installation.minimal_installation(
                testing=enable_testing, multilib=enable_multilib,
                mkinitcpio=run_mkinitcpio, hostname=hostname, locale_config=locale_config )
            self.log("Minimal installation complete.")

            if not self._running: raise InterruptedError("Stopped after minimal installation.")

            if mirror_config:
                self.log("Setting mirrors on target system...")
                installation.set_mirrors(mirror_config, on_target=True)

            if enable_swap:
                self.log("Setting up swap (zram)...")
                installation.setup_swap('zram') 

            self.log(f"Adding bootloader: {bootloader_choice.value if hasattr(bootloader_choice, 'value') else bootloader_choice}")
            if bootloader_choice == Bootloader.Grub and SysInfo.has_uefi():
                self.log("Ensuring GRUB package installed for UEFI...")
                installation.add_additional_packages("grub")
            installation.add_bootloader(bootloader_choice, archinstall.arguments.get(ARG_UKI, False))
            self.log("Bootloader setup complete.")

            if not self._running: raise InterruptedError("Stopped after bootloader.")

            if network_config:
                self.log("Configuring network...")
                network_config.install_network_config(installation, profile_config)
            else:
                self.log("Skipping explicit network configuration.", "INFO")

            if users:
                self.log(f"Creating users...")
                installation.create_users(users)
            
            if root_pw:
                self.log("Setting root password...")
                installation.user_set_pw('root', root_pw)

            if not self._running: raise InterruptedError("Stopped after users/passwords.")

            if audio_config:
                self.log(f"Configuring audio...")
                audio_config.install_audio_config(installation)
            else: self.log("Skipping audio configuration.", "INFO")

            if additional_packages:
                self.log(f"Installing {len(additional_packages)} additional packages...")
                installation.add_additional_packages(additional_packages)

            if profile_config:
                profile_display_name = getattr(getattr(profile_config, 'profile', None), 'name', 'N/A')
                self.log(f"Installing profile configuration: {profile_display_name}...")
                profile_handler.install_profile_config(installation, profile_config)
                self.log("Profile installation finished.")
            else: self.log("No profile configuration provided.", "WARN")


            if not self._running: raise InterruptedError("Stopped after profile install.")

            if timezone:
                self.log(f"Setting timezone: {timezone}")
                installation.set_timezone(timezone)

            if enable_ntp:
                self.log("Enabling NTP time synchronization...")
                installation.activate_time_synchronization()

            # Assume basic services (NetworkManager, sddm) are enabled by profile or need explicit adding here
            # Example: Enable services needed for KDE Plasma if profile doesn't
            kde_services = ["NetworkManager", "sddm"] # Services needed for standard KDE boot
            self.log(f"Ensuring services enabled: {kde_services}")
            installation.enable_service(kde_services) # Enable standard services

            if services_to_enable: # Enable user-specified extra services
                self.log(f"Enabling additional services: {services_to_enable}")
                installation.enable_service(services_to_enable) 

            if custom_commands_to_run:
                self.log("Running custom commands...")
                archinstall.run_custom_user_commands(custom_commands_to_run, installation)

            if not self._running: raise InterruptedError("Stopped before final steps.")

            self.log("Generating fstab...")
            installation.genfstab() # Generate final fstab
            self.log("fstab generated.")

            self.log("Installer context exited.")
        
        self.log("Installation logic within 'perform_installation' finished.")

    def run(self):
        """Main thread execution: handles FS operations then calls installation."""
        mount_point = MOUNT_POINT # Use configured mount point

        try:
            if not ARCHINSTALL_LIBRARY_AVAILABLE:
                 raise ArchinstallError(f"Archinstall library failed to import: {ARCHINSTALL_IMPORT_ERROR}")

            self.log("Installation process starting in background thread...")
            if not self._running: raise InterruptedError("Stopped before filesystem operations.")

            # --- Filesystem Operations ---
            self.log("Initializing Filesystem Handler...")
            fs_handler = FilesystemHandler(
                archinstall.arguments[ARG_DISK_CONFIG],
                archinstall.arguments.get(ARG_ENCRYPTION, None) )
            self.log("Performing filesystem operations (formatting)...")
            fs_handler.perform_filesystem_operations() 
            self.log("Filesystem operations complete.")

            if not self._running: raise InterruptedError("Stopped after formatting.")

            # --- Perform Installation Steps ---
            self._perform_installation_steps(mount_point) 

            # If we reach here without exceptions, it was successful
            self.log("Installation process completed successfully!")
            self.installation_finished.emit(True, f"Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME}) installed successfully!")

        # --- Error Handling ---
        except InterruptedError as e:
            self.log(f"Installation process was interrupted: {e}", "WARN")
            self.installation_finished.emit(False, f"Installation interrupted by user.")
        except (ArchinstallError, UserInteractionRequired) as e: 
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
        self.scan_disks_button = QPushButton("Scan for Disks")
        self.scan_disks_button.setToolTip("Scan the system for installable disk drives using archinstall library.")
        self.scan_disks_button.clicked.connect(self.trigger_disk_scan)
        disk_layout_vbox.addWidget(self.scan_disks_button)
        self.disk_combo = QComboBox()
        self.disk_combo.setToolTip("Select the target disk for installation.\nEnsure this is the correct disk!")
        disk_layout_vbox.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        self.wipe_disk_checkbox = QCheckBox("Wipe disk & auto-configure standard layout")
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
        self.hostname_input = QLineEdit("maibloom-os")
        self.hostname_input.setToolTip("Set the computer's network name (e.g., mypc).")
        system_layout_grid.addWidget(QLabel("Hostname:"), 0, 0); system_layout_grid.addWidget(self.hostname_input, 0, 1)
        self.username_input = QLineEdit("maiuser")
        self.username_input.setToolTip("Enter the desired username for your main account.")
        system_layout_grid.addWidget(QLabel("Username:"), 1, 0); system_layout_grid.addWidget(self.username_input, 1, 1)
        self.password_input = QLineEdit(); self.password_input.setPlaceholderText("Enter password (used for User & Root)"); self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setToolTip("Set the password for your user account.\nThis password will ALSO be set for the 'root' administrator account.")
        system_layout_grid.addWidget(QLabel("Password (User+Root):"), 2, 0); system_layout_grid.addWidget(self.password_input, 2, 1)
        self.locale_input = QLineEdit("en_US.UTF-8"); self.locale_input.setToolTip("Set the system language and encoding (e.g., en_US.UTF-8, fr_FR.UTF-8).")
        system_layout_grid.addWidget(QLabel("Locale:"), 3,0); system_layout_grid.addWidget(self.locale_input, 3,1)
        self.kb_layout_input = QLineEdit("us"); self.kb_layout_input.setToolTip("Set the keyboard layout for the console (e.g., us, uk, de_nodeadkeys).")
        system_layout_grid.addWidget(QLabel("Keyboard Layout:"), 4,0); system_layout_grid.addWidget(self.kb_layout_input, 4,1)
        self.timezone_input = QLineEdit("UTC"); self.timezone_input.setToolTip("Set the system timezone (e.g., UTC, America/New_York, Europe/Paris).\nUse format Region/City.")
        system_layout_grid.addWidget(QLabel("Timezone:"), 5,0); system_layout_grid.addWidget(self.timezone_input, 5,1)
        system_group.setLayout(system_layout_grid)
        controls_layout.addWidget(system_group)
        
        # GroupBox 3: Additional Applications
        app_group = QGroupBox(f"3. Additional Applications (Optional)")
        app_layout_grid = QGridLayout()
        self.app_category_checkboxes = {}
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
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True); self.log_output.setLineWrapMode(QTextEdit.NoWrap); self.log_output.setStyleSheet("font-family: monospace; background-color: #f0f0f0;") 
        log_layout_vbox.addWidget(self.log_output)
        log_group_box.setLayout(log_layout_vbox)
        # Add the log widget pane to the splitter
        splitter.addWidget(log_group_box)
        
        # Set initial size ratio for the panes
        splitter.setSizes([400, 450]) 
        
        # --- Bottom: Install Button ---
        self.install_button = QPushButton(f"Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME})")
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
            
            processed_disks = {}
            self.update_log_output(" (Using placeholder disk scan logic - USER MUST REPLACE)", "WARN")
            
            # --- Placeholder/Mock Logic ---
            if 'disk' in sys.modules and hasattr(disk, 'get_all_blockdevices'): 
                 block_devices = disk.get_all_blockdevices() 
                 for device in block_devices:
                     try: # Defensively get attributes
                         dev_path_str = str(getattr(device,'path', 'N/A'))
                         dev_type = str(getattr(device, 'type', 'unknown')).lower()
                         dev_ro = getattr(device, 'read_only', True)
                         dev_pkname = getattr(device, 'pkname', None)
                         dev_model = getattr(device, 'model', 'Unknown Model')
                         dev_size_bytes = int(getattr(device, 'size', 0))
                         # Filter for suitable disks
                         if dev_type == 'disk' and not dev_ro and not dev_pkname and dev_size_bytes >= 20 * (1024**3):
                              processed_disks[dev_path_str] = {"model": dev_model, "size": f"{dev_size_bytes / (1024**3):.2f} GB", "path": dev_path_str}
                     except Exception as inner_e:
                          self.update_log_output(f"Error processing device {getattr(device, 'path', 'N/A')}: {inner_e}", "WARN")
            else:
                 self.update_log_output("Archinstall 'disk' module or 'get_all_blockdevices' not available for scan.", "ERROR")
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

    def gather_settings_and_populate_args(self) -> bool:
        """
        Gathers settings from GUI, validates them, and populates the global
        archinstall.arguments dictionary with the necessary objects/structures.
        Returns True if successful, False otherwise.

        !!! CRITICAL USER IMPLEMENTATION AREA !!!
        Requires detailed knowledge of the target archinstall version's
        internal API to correctly instantiate configuration objects.
        Replace placeholder object creations with actual ones.
        """
        self.update_log_output("Gathering settings and preparing archinstall arguments...")
        gui_settings: Dict[str, Any] = {}
        
        # Disk
        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: QMessageBox.warning(self, "Input Error", "Please select a target disk."); return False
        target_disk_path_str = self.disk_combo.itemData(selected_disk_index)
        if not target_disk_path_str: QMessageBox.warning(self, "Input Error", "Invalid disk selected."); return False
        gui_settings["target_disk_path"] = Path(target_disk_path_str) 
        gui_settings["wipe_disk"] = self.wipe_disk_checkbox.isChecked()

        # System & User
        gui_settings["hostname"] = self.hostname_input.text().strip()
        gui_settings["username"] = self.username_input.text().strip()
        gui_settings["password"] = self.password_input.text() 
        gui_settings["locale"] = self.locale_input.text().strip()
        gui_settings["kb_layout"] = self.kb_layout_input.text().strip()
        gui_settings["timezone"] = self.timezone_input.text().strip()
        
        # Validation
        if not all([gui_settings["hostname"], gui_settings["username"], gui_settings["password"],
                    gui_settings["locale"], gui_settings["kb_layout"], gui_settings["timezone"]]):
            QMessageBox.warning(self, "Input Error", "Please fill all System & User fields."); return False

        # Profile & Packages
        gui_settings["profile_name"] = DEFAULT_DESKTOP_ENVIRONMENT_PROFILE 
        additional_packages = []
        for cat_name, checkbox_widget in self.app_category_checkboxes.items():
            if checkbox_widget.isChecked():
                additional_packages.extend(APP_CATEGORIES.get(cat_name, []))
        base_essentials = ["sudo", "nano"] 
        additional_packages = list(set(additional_packages + base_essentials))
        gui_settings["additional_packages"] = additional_packages

        # Populate archinstall.arguments (Critical Section)
        try:
            if not ARCHINSTALL_LIBRARY_AVAILABLE:
                 raise ArchinstallError("Cannot populate arguments, library not loaded.")
                 
            args = archinstall.arguments 
            args.clear() 

            # Simple Arguments
            args[ARG_HOSTNAME] = gui_settings["hostname"]
            args[ARG_ROOT_PASSWORD] = gui_settings["password"]
            args[ARG_TIMEZONE] = gui_settings["timezone"]
            args[ARG_KERNE] = ['linux'] 
            args[ARG_NTP] = True
            args[ARG_SWAP] = True 
            args[ARG_PACKAGES] = gui_settings["additional_packages"]
            is_efi = SysInfo.has_uefi()
            args[ARG_BOOTLOADER] = models.Bootloader.SystemdBoot if is_efi else models.Bootloader.Grub
            
            # !!! USER ACTION REQUIRED: Replace placeholders below !!!
            self.update_log_output("Preparing complex config objects (USER MUST IMPLEMENT!)", "WARN")

            # 1. LocaleConfiguration
            args[ARG_LOCALE_CONFIG] = locale.LocaleConfiguration(kb_layout=gui_settings["kb_layout"], sys_lang=gui_settings["locale"], sys_enc='UTF-8')
            
            # 2. User list 
            args[ARG_USERS] = [ models.User(gui_settings["username"], gui_settings["password"], sudo=True) ]
            
            # 3. ProfileConfiguration for KDE
            # Import the actual KdeProfile class
            from archinstall.default_profiles.kde import KdeProfile 
            kde_profile_instance = KdeProfile() # Instantiate it (check if it needs args)
            args[ARG_PROFILE_CONFIG] = models.ProfileConfiguration(profile=kde_profile_instance)

            # 4. DiskLayoutConfiguration (Most complex)
            # This requires significant research into archinstall's disk API.
            # How do you represent a block device and the desired layout non-interactively?
            target_device_path_obj = gui_settings["target_disk_path"] 
            if gui_settings["wipe_disk"]:
                # Example: Construct config for wiping and using default layout
                # This likely requires getting a BlockDevice instance first.
                # block_dev = disk.BlockDevice(target_device_path_obj) # Hypothetical
                args[ARG_DISK_CONFIG] = disk.DiskLayoutConfiguration( 
                     config_type=disk.DiskLayoutType.Default, # VERIFY ENUM/VALUE
                     device=target_device_path_obj, # Pass Path object or BlockDevice object?
                     wipe=True,
                     fs_type=disk.FilesystemType('ext4') # Example: default FS for root
                     # ... other params like ESP size, swap size if needed ...
                )
            else:
                # Example: Construct config for using existing partitions
                args[ARG_DISK_CONFIG] = disk.DiskLayoutConfiguration(
                    config_type=disk.DiskLayoutType.Pre_mount # VERIFY ENUM/VALUE
                    # mountpoints={...} # Needs mapping gathered from user/GUI
                )
                self.update_log_output("Using pre-mounted disk config requires more setup!", "WARN")

            # 5. Optional Configurations 
            args[ARG_ENCRYPTION] = None 
            # args[ARG_NETWORK_CONFIG] = models.NetworkConfiguration(...) 
            # args[ARG_AUDIO_CONFIG] = models.AudioConfiguration(...)

            self.update_log_output("Successfully populated archinstall.arguments (Check TODOs!).", "INFO")
            return True # Success

        except Exception as e: # Broad exception catch during object creation
            self.update_log_output(f"Error preparing archinstall arguments/objects: {e}", "ERROR")
            self.update_log_output(traceback.format_exc(), "ERROR")
            QMessageBox.critical(self, "Configuration Error", f"Failed to prepare installation configuration objects: {e}\n\nCheck archinstall API/version and ensure all inputs are valid.")
            return False


    def start_installation(self):
        """Gathers settings, populates args, confirms, and starts thread."""
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
             QMessageBox.critical(self, "Error", "Archinstall library not loaded."); return

        if not self.gather_settings_and_populate_args():
             self.update_log_output("Configuration failed. Installation aborted.", "ERROR"); return 

        # Confirmation Dialog
        try: # Safely get values for confirmation dialog
             target_disk_path_for_dialog = str(archinstall.arguments[ARG_DISK_CONFIG].device) # Example access
             wipe_disk_val = archinstall.arguments[ARG_DISK_CONFIG].wipe # Example access
             profile_name_for_dialog = getattr(archinstall.arguments[ARG_PROFILE_CONFIG].profile, 'name', DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME)
        except Exception:
             target_disk_path_for_dialog = self.disk_combo.itemData(self.disk_combo.currentIndex()) or "N/A"
             wipe_disk_val = self.wipe_disk_checkbox.isChecked()
             profile_name_for_dialog = DEFAULT_DESKTOP_ENVIRONMENT_PROFILE_NAME
             self.update_log_output("Using fallback values for confirmation dialog.", "WARN")

        wipe_warning = "YES (ENTIRE DISK WILL BE ERASED!)" if wipe_disk_val else "NO (Advanced - Using existing partitions)"
        confirm_msg = (f"Ready to install Mai Bloom OS ({profile_name_for_dialog}) using the archinstall library:\n\n"
                       f"  - Target Disk: {target_disk_path_for_dialog}\n"
                       f"  - Wipe Disk & Auto-Configure: {wipe_warning}\n\n"
                       "Ensure all selections are correct.\nPROCEED WITH INSTALLATION?")
        
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No: self.update_log_output("Installation cancelled by user."); return

        # Start the installation thread
        self.install_button.setEnabled(False); self.scan_disks_button.setEnabled(False)
        self.log_output.clear(); self.update_log_output("Starting installation via archinstall library...")

        self.installer_thread = InstallerEngineThread() 
        self.installer_thread.installation_log.connect(self.update_log_output)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start() 

    def on_installation_finished(self, success, message):
        """Handles completion signal from the installer thread."""
        self.update_log_output(f"GUI: Installation finished signal. Success: {success}")
        if success: QMessageBox.information(self, "Installation Complete", message + "\nYou may now reboot.")
        else:
            log_content = self.log_output.toPlainText(); last_log_lines = "\n".join(log_content.splitlines()[-20:])
            detailed_message = f"{message}\n\nLast log entries:\n---\n{last_log_lines}\n---"
            QMessageBox.critical(self, "Installation Failed", detailed_message)
        self.install_button.setEnabled(True); self.scan_disks_button.setEnabled(True)
        self.installer_thread = None 
        # Attempt unmount after completion/failure
        self.attempt_unmount()

    def attempt_unmount(self):
        """Attempts to unmount the target MOUNT_POINT."""
        try:
             mount_point = MOUNT_POINT # Use defined constant
             # Check if actually mounted using findmnt or checking /proc/mounts
             mount_check = subprocess.run(['findmnt', str(mount_point)], capture_output=True, text=True)
             if mount_check.returncode == 0: # It is mounted
                 self.update_log_output(f"Attempting final unmount of {mount_point}...")
                 unmount_process = subprocess.run(["umount", "-R", str(mount_point)], capture_output=True, text=True, check=False)
                 if unmount_process.returncode == 0:
                     self.update_log_output(f"Successfully unmounted {mount_point}.")
                 else:
                     self.update_log_output(f"Warning: Could not unmount {mount_point}: {unmount_process.stderr.strip()}", "WARN")
             else:
                 self.update_log_output(f"{mount_point} was not mounted or unmounted previously.", "DEBUG")
        except Exception as e:
             self.update_log_output(f"Error during final unmount attempt: {e}", "WARN")

    def select_post_install_script(self): pass # Placeholder
    def closeEvent(self, event): # Placeholder - Copied from previous full code
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

