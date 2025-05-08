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
# This allows the GUI code itself to be parsed and run without crashing immediately.
class ArchinstallError(Exception): pass
class InstallerEngineThread(QThread): # Dummy Thread
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str, str)
    disk_scan_complete = pyqtSignal(dict)
    def __init__(self, *args, **kwargs): super().__init__()
    def run_disk_scan(self): self.disk_scan_complete.emit({}) # Simulate no disks found
    def start(self): self.installation_log.emit("Backend thread simulation started.", "INFO"); self.installation_finished.emit(False, "Backend Not Implemented")
    def stop(self): pass
    def isRunning(self): return False # Simulate not running for closeEvent
    def wait(self, *args): pass

# Dummy archinstall components needed for gather_settings placeholders
class DummyArchinstallModule: pass
class DummyArchinstallLibModels:
    class Bootloader: Grub = 'grub'; SystemdBoot = 'systemd-boot'
    class User: def __init__(self, *args, **kwargs): pass
    class ProfileConfiguration: def __init__(self, *args, **kwargs): pass
class DummyArchinstallLib:
    class locale: class LocaleConfiguration: def __init__(self, *args, **kwargs): pass
    class disk:
         class DiskLayoutConfiguration: def __init__(self, *args, **kwargs): pass
         class DiskLayoutType: Default = 'Default'; Pre_mount = 'Pre_mount'
         class WipeMode: Secure = 'Secure'
class DummySysInfo: @staticmethod def has_uefi(): return os.path.exists("/sys/firmware/efi")

# Assign dummy components
archinstall = DummyArchinstallModule()
archinstall.lib = DummyArchinstallLib()
archinstall.lib.models = DummyArchinstallLibModels()
archinstall.SysInfo = DummySysInfo
locale = archinstall.lib.locale
disk = archinstall.lib.disk
models = archinstall.lib.models

# Assign dummy argument keys (replace with actual constants in full script)
ARG_DISK_CONFIG = 'disk_config'; ARG_LOCALE_CONFIG = 'locale_config'; ARG_ROOT_PASSWORD = '!root-password'; ARG_USERS = '!users'; ARG_PROFILE_CONFIG = 'profile_config'; ARG_HOSTNAME = 'hostname'; ARG_PACKAGES = 'packages'; ARG_BOOTLOADER = 'bootloader'; ARG_TIMEZONE = 'timezone'; ARG_KERNE = 'kernels'; ARG_NTP = 'ntp'; ARG_SWAP = 'swap'; ARG_ENCRYPTION = 'disk_encryption'
# --- End Placeholder Definitions ---


# --- App Configuration (Copied for context) ---
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "code", "python", "gcc", "gdb", "base-devel"],
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"],
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}

def check_root(): return os.geteuid() == 0

# --- Main Application Window (GUI using PyQt5) ---
class MaiBloomInstallerApp(QWidget):
    """Main GUI Window for the installer."""
    
    def __init__(self):
        super().__init__()
        self.installer_thread = None # Worker thread reference
        
        # Use a helper instance for non-threaded calls like disk scan
        # This uses the DUMMY InstallerEngineThread in this standalone context
        self._engine_helper = InstallerEngineThread({}) 
        self._engine_helper.disk_scan_complete.connect(self.on_disk_scan_complete)
        self._engine_helper.installation_log.connect(self.update_log_output) 
        
        # Global state used by the archinstall library approach
        # Initialize here if not done by library import block in full script
        if not hasattr(archinstall, 'arguments'): archinstall.arguments = {}

        self.init_ui() # Setup the user interface
        self.update_log_output("Welcome to Mai Bloom OS Installer!")
        
        # Initial check for library availability (using placeholder flag here)
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
             # In standalone GUI mode, we know it's not *really* loaded
             self.handle_library_load_error(is_placeholder=True) 
        else:
             # This part would run if the real imports succeed in the full script
             self.update_log_output("Archinstall library loaded successfully.")
             self.trigger_disk_scan() 

    def handle_library_load_error(self, is_placeholder=False):
        """Disables UI elements and shows error if library failed to load."""
        if is_placeholder:
             self.update_log_output("INFO: Running in GUI-only mode. Archinstall library not loaded.", "WARN")
             self.update_log_output("INFO: Disk Scan and Installation buttons will use placeholder logic.", "WARN")
             # Keep UI enabled for viewing/interaction with placeholders
             # self.install_button.setEnabled(False) # Or disable install if preferred
             # self.scan_disks_button.setEnabled(True) # Allow placeholder scan
        else:
             # This block runs if the real imports fail in the full script
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
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.NoWrap) # Easier to read logs
        self.log_output.setStyleSheet("font-family: monospace; background-color: #f0f0f0;") # Monospace font, light background
        log_layout_vbox.addWidget(self.log_output)
        log_group_box.setLayout(log_layout_vbox)
        # Add the log widget pane to the splitter
        splitter.addWidget(log_group_box)
        
        # Set initial size ratio for the panes
        splitter.setSizes([400, 450]) 
        
        # --- Bottom: Install Button ---
        self.install_button = QPushButton(f"Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT_PROFILE})")
        self.install_button.setStyleSheet("background-color: lightgreen; padding: 10px; font-weight: bold; border-radius: 5px;")
        self.install_button.setToolTip("Begin the installation process using the configured settings.")
        self.install_button.clicked.connect(self.start_installation)
        # Center the button using a QHBoxLayout with stretches
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.install_button)
        button_layout.addStretch()
        overall_layout.addLayout(button_layout)

    def create_form_row(self, label_text, widget):
        """Helper method to create a standard Label + Widget horizontal layout."""
        row_layout = QHBoxLayout()
        label = QLabel(label_text)
        label.setFixedWidth(120) # Consistent label width for alignment
        row_layout.addWidget(label)
        row_layout.addWidget(widget)
        return row_layout

    def trigger_disk_scan(self):
        """Initiates disk scan using archinstall library helper (or placeholder)."""
        self.update_log_output("GUI: Triggering disk scan...")
        self.scan_disks_button.setEnabled(False) # Disable button during scan
        try:
            # In the full script, this calls the engine helper's run_disk_scan.
            # That method MUST contain the actual calls to archinstall library.
            # This GUI code relies on the signal 'disk_scan_complete' being emitted.
            self._engine_helper.run_disk_scan() 
        except Exception as e: 
             self.update_log_output(f"Failed to initiate disk scan call: {e}", "ERROR")
             self.update_log_output(traceback.format_exc(), "ERROR")
             QMessageBox.critical(self, "Disk Scan Error", f"Failed to start disk scan: {e}")
             self.scan_disks_button.setEnabled(True) # Re-enable button on error

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

    def update_log_output(self, message: str, level: str = "INFO"):
        """Appends a message to the GUI log view, adding a level prefix."""
        prefix = "" if level == "INFO" else f"[{level}] "
        self.log_output.append(prefix + message)
        self.log_output.ensureCursorVisible() # Auto-scroll
        if level not in ["DEBUG", "CMD_OUT", "CMD_ERR", "CMD"]: # Avoid GUI freeze on high-frequency logs
             QApplication.processEvents()

    def gather_settings_and_populate_args(self) -> bool:
        """
        Gathers settings from GUI and populates archinstall.arguments.
        Returns True if successful, False otherwise.

        !!! CRITICAL USER IMPLEMENTATION AREA !!!
        This function requires detailed knowledge of the target archinstall version's
        internal API to correctly instantiate configuration objects (DiskLayoutConfiguration,
        LocaleConfiguration, User, ProfileConfiguration, etc.).
        The current implementation uses placeholders that MUST be replaced.
        """
        self.update_log_output("Gathering settings and preparing archinstall arguments...")
        # Use a temporary dict to gather raw GUI values
        gui_settings: Dict[str, Any] = {}
        
        # --- Disk ---
        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0: QMessageBox.warning(self, "Input Error", "Please select a target disk."); return False
        target_disk_path_str = self.disk_combo.itemData(selected_disk_index)
        if not target_disk_path_str: QMessageBox.warning(self, "Input Error", "Invalid disk selected."); return False
        gui_settings["target_disk_path"] = Path(target_disk_path_str) # Store as Path object
        gui_settings["wipe_disk"] = self.wipe_disk_checkbox.isChecked()

        # --- System & User ---
        gui_settings["hostname"] = self.hostname_input.text().strip()
        gui_settings["username"] = self.username_input.text().strip()
        gui_settings["password"] = self.password_input.text() # User & Root password
        gui_settings["locale"] = self.locale_input.text().strip()
        gui_settings["kb_layout"] = self.kb_layout_input.text().strip()
        gui_settings["timezone"] = self.timezone_input.text().strip()
        
        # --- Basic Input Validation ---
        if not gui_settings["hostname"]: QMessageBox.warning(self, "Input Error", "Hostname cannot be empty."); return False
        if not gui_settings["username"]: QMessageBox.warning(self, "Input Error", "Username cannot be empty."); return False
        if not gui_settings["password"]: QMessageBox.warning(self, "Input Error", "Password cannot be empty."); return False 
        if not gui_settings["locale"]: QMessageBox.warning(self, "Input Error", "Locale cannot be empty."); return False
        if not gui_settings["kb_layout"]: QMessageBox.warning(self, "Input Error", "Keyboard Layout cannot be empty."); return False
        if not gui_settings["timezone"]: QMessageBox.warning(self, "Input Error", "Timezone cannot be empty."); return False

        # --- Profile & Packages ---
        gui_settings["profile_name"] = DEFAULT_DESKTOP_ENVIRONMENT_PROFILE # Fixed profile
        additional_packages = []
        for cat_name, checkbox_widget in self.app_category_checkboxes.items():
            if checkbox_widget.isChecked():
                additional_packages.extend(APP_CATEGORIES.get(cat_name, []))
        base_essentials = ["sudo", "nano"] # Add some basics
        additional_packages = list(set(additional_packages + base_essentials))
        gui_settings["additional_packages"] = additional_packages

        # --- Populate archinstall.arguments (Critical Section) ---
        try:
            if not ARCHINSTALL_LIBRARY_AVAILABLE:
                 # Should not happen if button is enabled, but check anyway
                 raise ArchinstallError("Cannot populate arguments, library not loaded.")
                 
            # We need the global 'archinstall' module reference
            args = archinstall.arguments # Get reference to the global dictionary
            args.clear() # Clear previous arguments

            # --- Simple Arguments ---
            args[ARG_HOSTNAME] = gui_settings["hostname"]
            args[ARG_ROOT_PASSWORD] = gui_settings["password"]
            args[ARG_TIMEZONE] = gui_settings["timezone"]
            args[ARG_KERNE] = ['linux'] 
            args[ARG_NTP] = True
            args[ARG_SWAP] = True 
            args[ARG_PACKAGES] = gui_settings["additional_packages"]
            
            is_efi = archinstall.SysInfo.has_uefi() # Use the (potentially dummy) SysInfo
            # Use the (potentially dummy) Bootloader enum
            args[ARG_BOOTLOADER] = archinstall.lib.models.Bootloader.SystemdBoot if is_efi else archinstall.lib.models.Bootloader.Grub
            
            # --- Complex Arguments Requiring Object Instantiation ---
            # !!! USER ACTION REQUIRED: Replace placeholders below with actual object creation !!!

            # 1. LocaleConfiguration
            self.update_log_output("TODO: Create archinstall.lib.locale.LocaleConfiguration object.", "WARN")
            # args[ARG_LOCALE_CONFIG] = locale.LocaleConfiguration(...) # Replace with real constructor
            args[ARG_LOCALE_CONFIG] = {'kb_layout': gui_settings["kb_layout"], 'sys_lang': gui_settings["locale"], 'sys_enc': 'UTF-8'} # Placeholder

            # 2. User list (list of models.User objects)
            self.update_log_output("TODO: Create list of archinstall.lib.models.User objects.", "WARN")
            # args[ARG_USERS] = [ models.User(...) ] # Replace with real constructor
            args[ARG_USERS] = [{'username': gui_settings["username"], 'password': gui_settings["password"], 'sudo': True}] # Placeholder

            # 3. ProfileConfiguration
            self.update_log_output(f"TODO: Create archinstall.lib.models.ProfileConfiguration object for '{gui_settings['profile_name']}'.", "WARN")
            # args[ARG_PROFILE_CONFIG] = models.ProfileConfiguration(...) # Replace with real constructor
            args[ARG_PROFILE_CONFIG] = {'profile': {'main': gui_settings["profile_name"]}} # Placeholder

            # 4. DiskLayoutConfiguration (Most complex)
            self.update_log_output("TODO: Create archinstall.lib.disk.DiskLayoutConfiguration object.", "CRITICAL")
            # args[ARG_DISK_CONFIG] = disk.DiskLayoutConfiguration(...) # Replace with real constructor
            if gui_settings["wipe_disk"]:
                args[ARG_DISK_CONFIG] = {'config_type': disk.DiskLayoutType.Default, 'device': gui_settings["target_disk_path"], 'wipe': True} # Placeholder
            else:
                args[ARG_DISK_CONFIG] = {'config_type': disk.DiskLayoutType.Pre_mount} # Placeholder

            # 5. Optional Configurations (Set to None or create default objects)
            args[ARG_ENCRYPTION] = None 

            self.update_log_output("Attempted to populate archinstall.arguments (Placeholders Used!).", "WARN")
            return True # Allow proceeding even with placeholders for GUI testing

        except Exception as e: # Catch errors during object creation etc.
            self.update_log_output(f"Error preparing archinstall arguments: {e}", "ERROR")
            self.update_log_output(traceback.format_exc(), "ERROR")
            QMessageBox.critical(self, "Configuration Error", f"Failed to prepare installation configuration objects: {e}\n\nCheck archinstall API/version and TODO comments in code.")
            return False


    def start_installation(self):
        """Gathers settings, populates archinstall.arguments, confirms, and starts thread."""
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
             # This check might be redundant if button is disabled, but good practice
             QMessageBox.critical(self, "Error", "Archinstall library not loaded. Cannot install.")
             return

        # Populate the global arguments dictionary using the dedicated method
        if not self.gather_settings_and_populate_args():
             self.update_log_output("Configuration gathering/population failed. Installation aborted.", "ERROR")
             return # Stop if config population failed

        # Confirmation Dialog - Retrieve data using safe fallbacks
        target_disk_path_for_dialog = self.disk_combo.itemData(self.disk_combo.currentIndex()) or "N/A"
        wipe_disk_val = self.wipe_disk_checkbox.isChecked() # Use GUI state as fallback
        profile_name_for_dialog = DEFAULT_DESKTOP_ENVIRONMENT_PROFILE
        
        # Try to get more accurate info from populated args if possible
        try:
            disk_config_obj = archinstall.arguments.get(ARG_DISK_CONFIG)
            wipe_disk_val = getattr(disk_config_obj, 'wipe', wipe_disk_val) 
            profile_config_obj = archinstall.arguments.get(ARG_PROFILE_CONFIG)
            if isinstance(profile_config_obj, dict): # Check placeholder structure
                 profile_name_for_dialog = profile_config_obj.get('profile', {}).get('main', profile_name_for_dialog)
        except Exception: 
             pass # Ignore errors retrieving from potentially placeholder args

        wipe_warning = "YES (ENTIRE DISK WILL BE ERASED!)" if wipe_disk_val else "NO (Advanced - Using existing partitions)"
        confirm_msg = (f"Ready to install Mai Bloom OS ({profile_name_for_dialog}) using the archinstall library:\n\n"
                       f"  - Target Disk: {target_disk_path_for_dialog}\n"
                       f"  - Wipe Disk & Auto-Configure: {wipe_warning}\n\n"
                       "Ensure all selections are correct.\nPROCEED WITH INSTALLATION?")
        
        reply = QMessageBox.question(self, 'Confirm Installation', confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.update_log_output("Installation cancelled by user.")
            return

        # Start the installation thread
        self.install_button.setEnabled(False); self.scan_disks_button.setEnabled(False)
        self.log_output.clear(); self.update_log_output("Starting installation via archinstall library...")

        # Create thread (it will read the global archinstall.arguments)
        # Ensure the REAL InstallerEngineThread is used in the full script
        self.installer_thread = InstallerEngineThread() 
        self.installer_thread.installation_log.connect(self.update_log_output)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start() # Calls run() in a new thread

    def on_installation_finished(self, success, message):
        """Handles completion signal from the installer thread."""
        self.update_log_output(f"GUI: Installation finished signal. Success: {success}")
        if success:
            QMessageBox.information(self, "Installation Complete", message + "\nYou may now reboot.")
        else:
            log_content = self.log_output.toPlainText()
            last_log_lines = "\n".join(log_content.splitlines()[-20:]) # Show more log lines on error
            detailed_message = f"{message}\n\nLast log entries:\n---\n{last_log_lines}\n---"
            QMessageBox.critical(self, "Installation Failed", detailed_message)
            
        self.install_button.setEnabled(True); self.scan_disks_button.setEnabled(True)
        self.installer_thread = None 

        # Attempt unmount after completion/failure (best effort)
        try:
             # Need archinstall.storage available if it was successfully imported
             if ARCHINSTALL_LIBRARY_AVAILABLE and hasattr(archinstall, 'storage'):
                 mount_point = archinstall.storage.get('MOUNT_POINT')
                 if mount_point and Path(mount_point).is_mount():
                     self.update_log_output("Attempting final unmount...")
                     subprocess.run(["umount", "-R", str(mount_point)], capture_output=True, text=True, check=False)
                     self.update_log_output(f"Unmount attempt finished for {mount_point}.")
        except Exception as e:
             self.update_log_output(f"Error during final unmount attempt: {e}", "WARN")


    def select_post_install_script(self): # Optional post-install script selector (not used by engine now)
        """Allows user to select an optional script (currently unused)."""
        pass # Remove implementation if not needed, or keep as placeholder


    def closeEvent(self, event): # Graceful exit handling
        """Handle window close event, attempt to stop thread if running."""
        if self.installer_thread and self.installer_thread.isRunning():
            reply = QMessageBox.question(self, 'Installation in Progress',
                                         "An installation is currently running. Stopping now may leave the system in an inconsistent state. Are you sure you want to exit?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if hasattr(self.installer_thread, 'stop'):
                     self.installer_thread.stop() # Request thread to stop gracefully
                self.update_log_output("Attempting to wait for thread termination...")
                self.installer_thread.wait(2000) # Wait up to 2 seconds
                if self.installer_thread.isRunning():
                     self.update_log_output("Thread did not stop gracefully. Forcing exit.", "WARN")
                event.accept() # Close window
            else:
                event.ignore() # Keep window open
        else:
            event.accept() # Close window


if __name__ == '__main__':
    # Setup basic console logging for startup messages
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if not check_root():
        logging.error("Application must be run as root.")
        # Initialize minimal QApplication to show error message box
        app_temp = QApplication.instance();
        if not app_temp: app_temp = QApplication(sys.argv)
        QMessageBox.critical(None, "Root Access Required", "This installer must be run with root privileges.")
        sys.exit(1)
        
    app = QApplication(sys.argv)
    installer_gui = MaiBloomInstallerApp()
    installer_gui.show()
    sys.exit(app.exec_())
