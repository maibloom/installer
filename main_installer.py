##############################################################################
# Mai Bloom OS Installer - GUI Interface
# Designed to work with an InstallerEngineThread using Archinstall library.
# Version with SyntaxError fix in dummy class definitions.
##############################################################################

import sys
import os
import traceback
import time
import json # Needed only if trigger_disk_scan uses lsblk directly as fallback
import logging # For __main__ block logging
from pathlib import Path
from typing import Any, TYPE_CHECKING, Optional, Dict, List, Union

# --- PyQt5 Imports ---
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout, QSplitter)
from PyQt5.QtCore import QThread, pyqtSignal, Qt # QThread needed for type hinting if checking thread state

# --- Placeholder Definitions ---
# These are needed so the GUI code can run standalone for testing/viewing,
# even if the backend thread and archinstall library aren't fully available yet.
# Replace these with actual imports and logic in your final integrated script.

ARCHINSTALL_LIBRARY_AVAILABLE = False # Assume library failed to load for standalone GUI
ARCHINSTALL_IMPORT_ERROR = "Placeholder - Check actual imports in full script"
DEFAULT_DESKTOP_ENVIRONMENT_PROFILE = "kde"

# Dummy/Placeholder classes and variables if archinstall library import fails
try:
    # In full script, real imports go here. If they fail, this except block runs.
    raise ImportError("Simulating import failure for placeholder setup") 
except ImportError as e:
    ARCHINSTALL_IMPORT_ERROR = e
    # --- Define Dummy Placeholders ---
    class ArchinstallError(Exception): pass
    class UserInteractionRequired(Exception): pass
    class Bootloader: Grub = 'grub'; SystemdBoot = 'systemd-boot' 
    class DiskLayoutType: Default = 'Default'; Pre_mount = 'Pre_mount' 
    class WipeMode: Secure = 'Secure' 
    
    # --- CORRECTED FilesystemType Dummy Class ---
    class FilesystemType: 
        def __init__(self, name: str):
            self.name = name
    # --- End Correction ---

    class DiskLayoutConfiguration: 
        # Add attributes needed by GUI/Engine placeholders if accessed
        def __init__(self, *args, **kwargs): 
            self.config_type=DiskLayoutType.Pre_mount
            self.device=kwargs.get('device', None)
            self.wipe=kwargs.get('wipe', False)
            self.fs_type=kwargs.get('fs_type', FilesystemType('unknown'))

    class LocaleConfiguration: 
        def __init__(self, kb_layout:str='us', sys_lang:str='en_US.UTF-8', sys_enc:str='UTF-8', *args, **kwargs):
            self.kb_layout = kb_layout
            self.sys_lang = sys_lang
            self.sys_enc = sys_enc

    class ProfileConfiguration: 
        def __init__(self, profile=None, *args, **kwargs): 
            # Give the dummy profile a 'name' attribute if accessed
            class DummyProfile: name="DummyProfile"
            self.profile = profile or DummyProfile()

    class User: 
        def __init__(self, user_name:str='dummy', password:str='', sudo:bool=False, *args, **kwargs): 
            self.user_name = user_name
            # Password should not be stored directly in real scenario
            self._password = password 
            self.sudo = sudo

    class DiskEncryption: 
        class EncryptionType: NoEncryption='NoEncryption' 
        def __init__(self, *args, **kwargs): self.encryption_type = self.EncryptionType.NoEncryption

    class Installer: # Dummy Installer
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self 
        def __exit__(self, exc_type, exc_val, exc_tb): pass
        # Add dummy methods if called by GUI/Engine placeholders
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
        def setup_swap(self, *args, **kwargs): logging.info("Mock Installer: setup_swap()")
        def sanity_check(self, *args, **kwargs): logging.info("Mock Installer: sanity_check()")
        # Add other methods used in engine thread if necessary

    class FilesystemHandler: # Dummy Handler
        def __init__(self, *args, **kwargs): pass
        def perform_filesystem_operations(self): logging.info("Mock FilesystemHandler: perform_filesystem_operations()")
    
    class profile_handler: # Dummy handler
        @staticmethod
        def install_profile_config(*args, **kwargs): logging.info("Mock profile_handler: install_profile_config()")
        # Add get_profile if gather_settings tries to use it
        @staticmethod
        def get_profile(name): 
            class DummyProfile: name=name
            return DummyProfile()
            
    class KdeProfile: # Dummy Profile class
         def __init__(self, *args, **kwargs): self.name = "MockKDEProfile" 
         def post_install(self, installation): logging.info("Mock KdeProfile: post_install()")

    class SysInfo: # Dummy SysInfo
        @staticmethod 
        def has_uefi(): return os.path.exists("/sys/firmware/efi") 

    # Define dummy modules if code tries `module.Class` syntax
    class DummyArchinstallModule: 
         # Assign classes to module if needed
         lib = None # Define lib attribute
         SysInfo = SysInfo 
         # Define arguments/storage if accessed via archinstall.arguments
         arguments = {} 
         storage = {'MOUNT_POINT': Path('/mnt/maibloom_install_fallback')}
    archinstall = DummyArchinstallModule() 

    class DummyDiskModule:
         DiskLayoutConfiguration=DiskLayoutConfiguration 
         DiskLayoutType=DiskLayoutType
         EncryptionType=DiskEncryption.EncryptionType 
         WipeMode=WipeMode
         FilesystemType=FilesystemType
         FilesystemHandler=FilesystemHandler
         class BlockDevice: pass # Dummy for type hints etc.
         @staticmethod # Make callable as disk.get_all_blockdevices()
         def get_all_blockdevices(): # Example placeholder function
             class MockBlockDevice: # Copied from engine placeholder
                 def __init__(self, path, size, model, dev_type, ro, **kwargs):
                    self.path = Path(path); self.size = size; self.model = model; self.type = dev_type; self.read_only = ro
                    self.pkname = kwargs.get('pkname'); self.tran = kwargs.get('tran', 'sata'); self.mountpoint=None; self.children=[]
             return [MockBlockDevice("/dev/mock_disk", 100*1024**3, "Mock Disk", "disk", False)]

    class DummyLocaleModule: LocaleConfiguration=LocaleConfiguration
    class DummyModelsModule: 
         User=User; ProfileConfiguration=ProfileConfiguration; DiskEncryption=DiskEncryption
         AudioConfiguration=AudioConfiguration; NetworkConfiguration=NetworkConfiguration; Bootloader=Bootloader
         Profile=KdeProfile # Assign dummy KdeProfile to Profile for simplicity
    class DummyProfileHandlerModule: profile_handler=profile_handler; KdeProfile=KdeProfile

    class DummyArchinstallLib: # Define dummy lib structure
        disk = DummyDiskModule
        locale = DummyLocaleModule
        models = DummyModelsModule
        profile = DummyProfileHandlerModule # Contains profile_handler and KdeProfile
        installer = Installer # Assign dummy Installer
        # Add other submodules if accessed e.g. exceptions, configuration
        exceptions = type('exceptions', (object,), {'ArchinstallError': ArchinstallError, 'UserInteractionRequired': UserInteractionRequired})()
        
    archinstall.lib = DummyArchinstallLib # Assign to main dummy module

    # Define dummy Argument constants
    ARG_DISK_CONFIG = 'disk_config'; ARG_LOCALE_CONFIG = 'locale_config'; ARG_ROOT_PASSWORD = '!root-password'; ARG_USERS = '!users'; ARG_PROFILE_CONFIG = 'profile_config'; ARG_HOSTNAME = 'hostname'; ARG_PACKAGES = 'packages'; ARG_BOOTLOADER = 'bootloader'; ARG_TIMEZONE = 'timezone'; ARG_KERNE = 'kernels'; ARG_NTP = 'ntp'; ARG_SWAP = 'swap'; ARG_ENCRYPTION = 'disk_encryption'
    logging.warning("Using placeholder definitions for Archinstall components due to import error.")
# --- End Placeholder Definitions ---


# --- App Configuration ---
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "code", "python", "gcc", "gdb", "base-devel"],
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"],
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}
DEFAULT_DESKTOP_ENVIRONMENT_PROFILE = "kde" # Mai Bloom OS default
MOUNT_POINT = Path('/mnt/maibloom_install') # Ensure consistent definition

def check_root(): return os.geteuid() == 0


# --- Main Application Window (GUI using PyQt5) ---
class MaiBloomInstallerApp(QWidget):
    """Main GUI Window for the installer."""
    
    def __init__(self):
        super().__init__()
        self.installer_thread = None # Worker thread reference
        
        # Initialize UI elements first before potentially showing error messages
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
        self.install_button = QPushButton(f"Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE})")
        
        # Use a helper instance for non-threaded calls like disk scan
        # Ensure the dummy/real InstallerEngineThread is defined before this class
        self._engine_helper = InstallerEngineThread() 
        self._engine_helper.disk_scan_complete.connect(self.on_disk_scan_complete)
        self._engine_helper.installation_log.connect(self.update_log_output_slot) # Connect to slot

        self.init_ui() # Setup the user interface layout
        self.update_log_output("Welcome to Mai Bloom OS Installer!")
        
        # Initial check for library availability
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
             self.handle_library_load_error() # Show warning/disable UI
        else:
             self.update_log_output("Archinstall library assumed loaded (or using mocks).")
             self.trigger_disk_scan() # Trigger initial scan

    def handle_library_load_error(self):
        """Shows error if library failed to load."""
        # This is called if the top-level import fails
        self.update_log_output(f"CRITICAL ERROR: Archinstall library not loaded: {ARCHINSTALL_IMPORT_ERROR}", "ERROR")
        QMessageBox.critical(self, "Startup Error", 
                             f"Failed to load essential Archinstall library components:\n{ARCHINSTALL_IMPORT_ERROR}\n\n"
                             "Please ensure Archinstall is correctly installed for the Python environment and accessible.\n"
                             "The installer cannot function.")
        # Disable buttons - other widgets might be usable for viewing layout
        self.install_button.setEnabled(False)
        self.scan_disks_button.setEnabled(False)

    def init_ui(self):
        """Sets up the GUI widgets and layouts."""
        self.setWindowTitle(f'Mai Bloom OS Installer ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE} via Archinstall Lib)')
        self.setGeometry(100, 100, 850, 700) # Window size and position
        overall_layout = QVBoxLayout(self) # Main layout for the window

        # --- Top Title ---
        title_label = QLabel(f"<b>Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE})</b>")
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
        self.scan_disks_button.setToolTip("Scan the system for installable disk drives using archinstall library.")
        self.scan_disks_button.clicked.connect(self.trigger_disk_scan)
        disk_layout_vbox.addWidget(self.scan_disks_button)
        self.disk_combo.setToolTip("Select the target disk for installation.\nEnsure this is the correct disk!")
        disk_layout_vbox.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
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
        row, col = 0,0
        for cat_name in APP_CATEGORIES.keys():
            self.app_category_checkboxes[cat_name] = QCheckBox(f"{cat_name}")
            pkg_list_tooltip = f"Install: {', '.join(APP_CATEGORIES[cat_name][:4])}"
            if len(APP_CATEGORIES[cat_name]) > 4: pkg_list_tooltip += "..."
            self.app_category_checkboxes[cat_name].setToolTip(pkg_list_tooltip)
            app_layout_grid.addWidget(self.app_category_checkboxes[cat_name], row, col)
            col +=1
            if col > 1: col = 0; row +=1
        app_group.setLayout(app_layout_grid)
        controls_layout.addWidget(app_group)
        
        controls_layout.addStretch(1); splitter.addWidget(controls_widget)

        # --- Right Pane: Log Output ---
        log_group_box = QGroupBox("Installation Log"); log_layout_vbox = QVBoxLayout()
        self.log_output.setReadOnly(True); self.log_output.setLineWrapMode(QTextEdit.NoWrap); self.log_output.setStyleSheet("font-family: monospace; background-color: #f0f0f0;") 
        log_layout_vbox.addWidget(self.log_output); log_group_box.setLayout(log_layout_vbox)
        splitter.addWidget(log_group_box)
        splitter.setSizes([400, 450]) 
        
        # --- Bottom: Install Button ---
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold; border-radius: 5px;")
        self.install_button.setToolTip("Begin the installation process using the configured settings.")
        self.install_button.clicked.connect(self.start_installation)
        button_layout = QHBoxLayout(); button_layout.addStretch(); button_layout.addWidget(self.install_button); button_layout.addStretch(); overall_layout.addLayout(button_layout)

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
            # This call needs to execute the *actual* archinstall disk listing function.
            # The helper's run_disk_scan method needs to be implemented for this.
            self._engine_helper.run_disk_scan() 
        except Exception as e: 
             self.update_log_output(f"Failed to initiate disk scan call: {e}", "ERROR")
             self.update_log_output(traceback.format_exc(), "ERROR")
             QMessageBox.critical(self, "Disk Scan Error", f"Failed to start disk scan: {e}")
             self.scan_disks_button.setEnabled(True) # Re-enable button on error

    @pyqtSlot(dict) # Explicitly define slot signature
    def on_disk_scan_complete(self, disks_data: Dict[str, Dict]):
        """Slot to handle the result of the disk scan signal."""
        self.update_log_output(f"GUI: Disk scan finished. Populating {len(disks_data)} suitable disk(s).")
        self.disk_combo.clear()
        if disks_data:
            for path_key, info_dict in sorted(disks_data.items()): # Sort by path
                display_text = f"{path_key} - {info_dict.get('model', 'N/A')} ({info_dict.get('size', 'N/A')})"
                self.disk_combo.addItem(display_text, userData=path_key) # Store path in userData
        else:
            self.update_log_output("GUI: No suitable disks found by scan.", "WARN")
        self.scan_disks_button.setEnabled(True) # Re-enable button

    @pyqtSlot(str, str) # Slot for log messages from thread
    def update_log_output(self, message: str, level: str = "INFO"):
        """Appends a message to the GUI log view, adding a level prefix."""
        prefix = "" if level == "INFO" else f"[{level}] "
        self.log_output.append(prefix + message)
        self.log_output.ensureCursorVisible() # Auto-scroll
        # Only process events for non-debug messages to avoid lag
        if level not in ["DEBUG", "CMD_OUT", "CMD_ERR", "CMD"]: 
             QApplication.processEvents()

    def gather_settings_and_create_config_objects(self) -> Optional[Dict[str, Any]]:
        """
        Gathers settings from GUI, validates them, and attempts to create the
        necessary archinstall configuration objects.
        Returns a dictionary of config objects/values if successful, None otherwise.

        !!! CRITICAL USER IMPLEMENTATION AREA !!!
        Replace placeholder object creations with actual ones based on archinstall API.
        """
        self.update_log_output("Gathering settings and creating archinstall config objects...")
        config_objects: Dict[str, Any] = {}
        # --- Disk ---
        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: QMessageBox.warning(self, "Input Error", "Please select a target disk."); return None
        target_disk_path_str = self.disk_combo.itemData(selected_disk_index)
        if not target_disk_path_str: QMessageBox.warning(self, "Input Error", "Invalid disk selected."); return None
        target_disk_path = Path(target_disk_path_str) 
        wipe_disk_flag = self.wipe_disk_checkbox.isChecked()
        config_objects["target_disk_path"] = target_disk_path # Store for reference if needed

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
        
        # Store simple values directly in the config dict for the thread
        config_objects["hostname"] = hostname
        config_objects["root_pw"] = password # User password is used for root
        config_objects["timezone"] = timezone
        config_objects["kernels"] = ['linux'] 
        config_objects["ntp_enabled"] = True
        config_objects["swap_enabled"] = True 
        config_objects["additional_packages"] = additional_packages
        config_objects["profile_name"] = profile_name # Store for logging/reference

        # --- Create Configuration Objects (Critical Section) ---
        try:
            if not ARCHINSTALL_LIBRARY_AVAILABLE:
                 raise ArchinstallError("Cannot create config objects, library not loaded.")
                 
            is_efi = SysInfo.has_uefi()
            config_objects["bootloader"] = models.Bootloader.SystemdBoot if is_efi else models.Bootloader.Grub
            
            # 1. LocaleConfiguration
            self.log("TODO: Verify/Implement archinstall.lib.locale.LocaleConfiguration instantiation.", "WARN")
            config_objects['locale_config'] = locale.LocaleConfiguration(
                kb_layout=kb_layout, sys_lang=locale_str, sys_enc='UTF-8' )
            
            # 2. User list
            self.log("TODO: Verify/Implement archinstall.lib.models.User instantiation.", "WARN")
            config_objects['user_list'] = [ models.User(username, password, sudo=True) ]
            
            # 3. ProfileConfiguration for KDE
            self.log(f"TODO: Verify/Implement archinstall.lib.models.ProfileConfiguration for '{profile_name}'.", "WARN")
            # Import the actual KdeProfile class (ensure import at top works)
            kde_profile_instance = KdeProfile() # Check KdeProfile constructor args
            config_objects['profile_config'] = models.ProfileConfiguration(profile=kde_profile_instance)

            # 4. DiskLayoutConfiguration (Most Complex)
            self.log("TODO: Verify/Implement archinstall.lib.disk.DiskLayoutConfiguration instantiation.", "CRITICAL")
            if wipe_disk_flag:
                config_objects['disk_config'] = disk.DiskLayoutConfiguration(
                     config_type=disk.DiskLayoutType.Default, # Verify
                     device=target_disk_path, 
                     wipe=True,
                     fs_type=disk.FilesystemType('ext4') # Verify
                )
            else:
                config_objects['disk_config'] = disk.DiskLayoutConfiguration(
                    config_type=disk.DiskLayoutType.Pre_mount # Verify
                    # Needs mountpoints dict for pre-mount
                )

            # 5. Optional Configurations 
            config_objects['disk_encryption'] = None 
            # config_objects['network_config'] = models.NetworkConfiguration(...) 
            # config_objects['audio_config'] = models.AudioConfiguration(...)

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
             QMessageBox.critical(self, "Error", "Archinstall library not loaded."); return

        config_objects = self.gather_settings_and_create_config_objects()
        if not config_objects:
             self.update_log_output("Configuration failed. Installation aborted.", "ERROR"); return 

        # Confirmation Dialog
        try: # Safely get values for confirmation
             target_disk_path_for_dialog = str(config_objects.get('disk_config').device) # Example
             wipe_disk_val = config_objects.get('disk_config').wipe # Example
             profile_name_for_dialog = config_objects.get('profile_name', 'N/A')
        except Exception:
             target_disk_path_for_dialog = self.disk_combo.itemData(self.disk_combo.currentIndex()) or "N/A"
             wipe_disk_val = self.wipe_disk_checkbox.isChecked()
             profile_name_for_dialog = DEFAULT_DESKTOP_ENVIRONMENT_PROFILE
             self.update_log_output("Using fallback values for confirmation dialog.", "WARN")

        wipe_warning = "YES (ENTIRE DISK WILL BE ERASED!)" if wipe_disk_val else "NO (Advanced - Using existing partitions)"
        confirm_msg = (f"Ready to install Mai Bloom OS ({profile_name_for_dialog}) using the archinstall library:\n\n"
                       f"  - Target Disk: {target_disk_path_for_dialog}\n"
                       f"  - Wipe Disk & Auto-Configure: {wipe_warning}\n\n"
                       "Ensure all selections are correct.\nPROCEED WITH INSTALLATION?")
        
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No: self.update_log_output("Installation cancelled by user."); return

        self.install_button.setEnabled(False); self.scan_disks_button.setEnabled(False)
        self.log_output.clear(); self.update_log_output("Starting installation via archinstall library...")

        # Create thread, passing the dictionary of created config objects
        self.installer_thread = InstallerEngineThread(config_objects) 
        self.installer_thread.installation_log.connect(self.update_log_output_slot) # Connect signal
        self.installer_thread.installation_finished.connect(self.on_installation_finished) # Connect signal
        self.installer_thread.start() 

    @pyqtSlot(bool, str) # Define slot signature
    def on_installation_finished(self, success: bool, message: str):
        """Slot to handle completion signal from the installer thread."""
        self.update_log_output(f"GUI: Installation finished signal. Success: {success}")
        if success:
            QMessageBox.information(self, "Installation Complete", message + "\nYou may now reboot.")
        else:
            log_content = self.log_output.toPlainText(); last_log_lines = "\n".join(log_content.splitlines()[-20:])
            detailed_message = f"{message}\n\nLast log entries:\n---\n{last_log_lines}\n---"
            QMessageBox.critical(self, "Installation Failed", detailed_message)
            
        self.install_button.setEnabled(True); self.scan_disks_button.setEnabled(True)
        self.installer_thread = None 
        self.attempt_unmount() # Attempt unmount after job is done

    def attempt_unmount(self):
        """Attempts to unmount the target MOUNT_POINT."""
        # ... (implementation from previous response) ...
        try:
             mount_point = MOUNT_POINT 
             mount_check = subprocess.run(['findmnt', str(mount_point)], capture_output=True, text=True)
             if mount_check.returncode == 0: 
                 self.update_log_output(f"Attempting final unmount of {mount_point}...")
                 unmount_process = subprocess.run(["umount", "-R", str(mount_point)], capture_output=True, text=True, check=False)
                 if unmount_process.returncode == 0: self.update_log_output(f"Successfully unmounted {mount_point}.")
                 elif "not mounted" not in (unmount_process.stderr or "").lower(): self.update_log_output(f"Warning: Could not unmount {mount_point}: {unmount_process.stderr.strip()}", "WARN")
                 else: self.update_log_output(f"{mount_point} was not mounted.", "DEBUG")
        except Exception as e: self.update_log_output(f"Error during final unmount attempt: {e}", "WARN")

    def select_post_install_script(self): pass # Placeholder
    def closeEvent(self, event): # Placeholder - Copied from previous
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
