import sys
import os
import traceback
import time
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox,
                             QMessageBox, QFileDialog, QTextEdit, QCheckBox,
                             QGroupBox, QGridLayout, QSplitter)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

# --- Attempt to import archinstall components ---
# USER ACTION REQUIRED: You must research your archinstall version's internal API.
# These are HYPOTHETICAL.
ARCHINSTALL_LIBRARY_AVAILABLE = False
disk_module_actual = None
packages_module_actual = None
profile_module_actual = None
system_config_module_actual = None
ArchinstallError_actual = Exception # Base exception for archinstall errors
UserInteractionRequired_actual = Exception # If archinstall tries to prompt

try:
    # Example: from archinstall.lib import disk as arch_disk_utils
    # Example: from archinstall.lib import packages as arch_pkg_utils
    # Example: from archinstall.lib import profile as arch_profile_utils
    # Example: from archinstall.lib.installer import Installer # A central class?
    # Example: from archinstall.lib.exceptions import ArchinstallError, UserInteractionRequired
    
    # For now, we'll assume these are found and assign them.
    # You MUST replace these with actual imports and potentially instantiate classes.
    
    # Let's simulate finding a disk module for the conceptual code
    # In a real scenario, you'd do: from archinstall.lib import disk as disk_module_actual
    # For this placeholder to run without archinstall fully installed for testing GUI structure:
    class MockArchinstallDiskModule:
        def get_all_blockdevices(self): # This function name is a common pattern
            print("MockArchinstallDiskModule: Simulating get_all_blockdevices()")
            # In a real scenario, this would return a list of archinstall's BlockDevice objects
            # Each object would have attributes like .path, .size, .model, .type, .read_only, etc.
            class MockBlockDevice:
                def __init__(self, path, size, model, dev_type, ro, children=None, pkname=None, tran='sata'):
                    self.path = Path(path)
                    self.name = path.split('/')[-1]
                    self.size = size # in bytes
                    self.model = model
                    self.type = dev_type # 'disk', 'part', 'rom', 'loop'
                    self.read_only = ro
                    self.is_partition = bool(pkname) # Simplified
                    self.pkname = pkname
                    self.mountpoint = None # For checking root fs
                    self.children = children if children else []
                    self.tran = tran

                def __repr__(self):
                    return f"<MockBlockDevice path={self.path} type={self.type} size={self.size}>"

            # Simulate some devices, including one that could be the live ISO
            live_iso_root_part = MockBlockDevice("/dev/sdc1", 2*1024**3, "Live ISO Part", "part", True, pkname="sdc")
            live_iso_root_part.mountpoint = "/" # Simulate it being mounted as root

            return [
                MockBlockDevice("/dev/sda", 20*1024**3, "VM Virtual HD", "disk", False),
                MockBlockDevice("/dev/sdb", 50*1024**3, "Another VM Disk", "disk", False, tran='nvme'),
                MockBlockDevice("/dev/sdc", 2*1024**3, "Live ISO (USB)", "disk", True, children=[live_iso_root_part], tran='usb'), # Read-only disk
                MockBlockDevice("/dev/loop0", 1*1024**3, "Loop Device", "loop", True)
            ]
    disk_module_actual = MockArchinstallDiskModule() # Replace with actual module
    # End of mock disk module

    # Similarly for other modules (these would be real imports)
    # packages_module_actual = archinstall.lib.packages 
    # profile_module_actual = archinstall.lib.profile
    # system_config_module_actual = ... (various modules for chfs, services, user, etc.)
    # ArchinstallError_actual = archinstall.lib.exceptions.ArchinstallError
    # UserInteractionRequired_actual = archinstall.lib.exceptions.UserInteractionRequired
    
    ARCHINSTALL_LIBRARY_AVAILABLE = True # Set to True if imports (or mocks) succeed

except ImportError as e:
    print(f"WARNING: Failed to import actual archinstall modules: {e}", file=sys.stderr)
    print("         The installer will use MOCK functionality for demonstration.", file=sys.stderr)
    # Fallback to MOCKs if actual imports fail, allows GUI to run for dev
    if 'disk_module_actual' not in globals() or not disk_module_actual: # if specific import failed
        class MockArchinstallDiskModule: # Defined above
            def get_all_blockdevices(self):
                print("MockArchinstallDiskModule: Simulating get_all_blockdevices() in ImportError fallback")
                class MockBlockDevice:
                    def __init__(self, path, size, model, dev_type, ro, children=None, pkname=None, tran='sata'):
                        self.path = Path(path)
                        self.name = path.split('/')[-1]
                        self.size = size 
                        self.model = model
                        self.type = dev_type 
                        self.read_only = ro
                        self.is_partition = bool(pkname)
                        self.pkname = pkname
                        self.mountpoint = None
                        self.children = children if children else []
                        self.tran = tran
                    def __repr__(self): return f"<MockBlockDevice path={self.path} type={self.type} size={self.size}>"
                live_iso_root_part = MockBlockDevice("/dev/sdc1", 2*1024**3, "Live ISO Part", "part", True, pkname="sdc")
                live_iso_root_part.mountpoint = "/"
                return [ MockBlockDevice("/dev/sda", 20*1024**3, "VM Virtual HD", "disk", False),
                         MockBlockDevice("/dev/sdc", 2*1024**3, "Live ISO (USB)", "disk", True, children=[live_iso_root_part], tran='usb')]
        disk_module_actual = MockArchinstallDiskModule()
    
    # Define other mock modules/exceptions if necessary for GUI to function without full archinstall
    if 'ArchinstallError_actual' not in globals(): ArchinstallError_actual = Exception
    if 'UserInteractionRequired_actual' not in globals(): UserInteractionRequired_actual = Exception
    # ARCHINSTALL_LIBRARY_AVAILABLE will remain False or be set by successful partial imports

# --- App Configuration ---
APP_CATEGORIES = {
    "Daily Use": ["firefox", "vlc", "gwenview", "okular", "libreoffice-still", "ark", "kate"],
    "Programming": ["git", "vscode", "python", "gcc", "gdb", "base-devel"],
    "Gaming": ["steam", "lutris", "wine", "noto-fonts-cjk"],
    "Education": ["gcompris-qt", "kgeography", "stellarium", "kalgebra"]
}
DEFAULT_DESKTOP_ENVIRONMENT = "kde" # Mai Bloom OS default

def check_root(): return os.geteuid() == 0


# --- Installer Engine Thread ---
class InstallerEngineThread(QThread):
    installation_finished = pyqtSignal(bool, str)
    installation_log = pyqtSignal(str)
    disk_scan_complete = pyqtSignal(dict)

    def __init__(self, installation_settings):
        super().__init__()
        self.settings = installation_settings
        self._running = True

    def log(self, message):
        self.installation_log.emit(message)

    def stop(self):
        self.log("Attempting to stop installation thread...")
        self._running = False

    def run_disk_scan(self): # Called by GUI, runs in GUI thread context via helper instance
        if not ARCHINSTALL_LIBRARY_AVAILABLE or not disk_module_actual:
            self.log("Archinstall disk library components not available. Disk scan skipped.")
            self.disk_scan_complete.emit({})
            return
        
        self.log("Starting disk scan using archinstall library functions...")
        processed_disks = {}
        try:
            # TODO: USER ACTION: Replace with actual archinstall disk listing call
            # This call should return a list of archinstall's BlockDevice objects or similar.
            # Example: block_devices = disk_module_actual.all_blockdevices()
            # Example: block_devices = disk_module_actual.get_hdds() # if such a func exists
            
            block_devices = disk_module_actual.get_all_blockdevices() # Using the (mocked or real) module

            self.log(f"Found {len(block_devices)} block devices. Filtering for suitable disks...")

            for device in block_devices:
                # These attribute names (.path, .type, .read_only, .size, .model, .is_partition, .mountpoint)
                # are common but you MUST verify them against the actual BlockDevice objects
                # returned by your archinstall version's disk functions.
                dev_path_str = str(device.path) # Ensure it's a string
                dev_type = getattr(device, 'type', 'unknown').lower()
                dev_ro = getattr(device, 'read_only', True)
                dev_is_partition = getattr(device, 'is_partition', bool(getattr(device, 'pkname', None))) # Check if it's a partition
                dev_model = getattr(device, 'model', 'Unknown Model')
                dev_size_bytes = getattr(device, 'size', 0)
                dev_tran = getattr(device, 'tran', 'unknown').lower()

                log_line = (f"  Checking: {dev_path_str}, Type: {dev_type}, RO: {dev_ro}, IsPart: {dev_is_partition}, "
                            f"Size: {dev_size_bytes}, Model: {dev_model}, Tran: {dev_tran}")

                # Filter for suitable installation targets
                if dev_type == 'disk' and not dev_ro and not dev_is_partition:
                    if dev_size_bytes < 10 * (1024**3): # Min 10GB
                        self.log(log_line + f" -> Skipping (Too small: {dev_size_bytes / (1024**3):.2f} GB)")
                        continue

                    # Heuristic to skip live ISO medium / current root
                    is_root_fs_device = False
                    if getattr(device, 'mountpoint', None) == '/':
                        is_root_fs_device = True
                    elif hasattr(device, 'children') and device.children:
                        for child in device.children:
                            if getattr(child, 'mountpoint', None) == '/':
                                is_root_fs_device = True
                                break
                    
                    if is_root_fs_device:
                        self.log(log_line + " -> Skipping (Appears to be current root FS)")
                        continue
                    
                    # Optional: Skip USB if not desired as primary install target
                    # if dev_tran == 'usb':
                    #     self.log(log_line + " -> Skipping (USB device)")
                    #     continue

                    processed_disks[dev_path_str] = {
                        "model": dev_model,
                        "size": f"{dev_size_bytes / (1024**3):.2f} GB", # Human-readable size
                        "path": dev_path_str # Store original path for later use
                    }
                    self.log(log_line + " -> Suitable disk found.")
                else:
                    self.log(log_line + " -> Skipping (Not a suitable disk type, or R/O, or is a partition).")
            
            if not processed_disks:
                self.log("No suitable disks found after filtering.")
            self.disk_scan_complete.emit(processed_disks)

        except Exception as e:
            self.log(f"Error during disk scan: {e}")
            self.log(traceback.format_exc())
            self.disk_scan_complete.emit({})


    def run(self): # This runs in a separate QThread
        if not ARCHINSTALL_LIBRARY_AVAILABLE:
            self.log("Archinstall library not available. Cannot proceed with installation.")
            self.installation_finished.emit(False, "Archinstall library import failed.")
            return
        
        self.log(f"Installation process started using archinstall library for '{self.settings.get('profile', 'N/A')}' profile...")
        mount_point = Path(self.settings.get("mount_point_base", "/mnt/archinstall")) # Standard mount point
        actual_mount_point_used = None

        try:
            # === Phase 1: Global Settings & Disk Preparation ===
            self.log(f"Phase 1: Target disk: {self.settings.get('target_disk_path')}, Wipe: {self.settings.get('wipe_disk')}")
            # TODO: USER ACTION: Set up archinstall's global configuration if its library functions rely on it.
            # Example: archinstall.lib.global_variables.storage['mount_point'] = mount_point
            # Example: archinstall.lib.global_variables.storage['DISK_LAYOUTS'] = { ... }
            # Example: archinstall.lib.global_variables.storage['TARGET_DISK'] = Path(self.settings.get('target_disk_path'))
            self.log("  (User TODO: Implement calls to archinstall.lib.disk for partitioning, formatting, mounting)")
            
            # This is highly conceptual. You need to map GUI choices (wipe, layout) to archinstall disk functions.
            # if disk_module_actual:
            #     target_block_device = disk_module_actual.BlockDevice(Path(self.settings.get('target_disk_path'))) # Hypothetical
            #     layout_configuration = { ... build this from self.settings ... }
            #     disk_module_actual.perform_partitioning(target_block_device, layout_configuration, wipe=self.settings.get('wipe_disk'))
            #     disk_module_actual.perform_formatting(target_block_device, layout_configuration)
            #     actual_mount_point_used = disk_module_actual.mount_target_volumes(target_block_device, layout_configuration, mount_point)
            # else:
            #     raise ArchinstallError_actual("Disk module not available.")
            self.log(f"  (Placeholder) Disk preparation for {self.settings.get('target_disk_path')} would happen here.")
            time.sleep(2) # Simulate disk prep
            actual_mount_point_used = mount_point # Assume success for placeholder
            self.log(f"  (Placeholder) System to be installed to: {actual_mount_point_used}")
            if not self._running: self.installation_finished.emit(False, "Installation stopped."); return


            # === Phase 2: Package Installation (Profiles + Additional) ===
            self.log(f"Phase 2: Installing profile '{self.settings.get('profile')}' and packages...")
            # TODO: USER ACTION: Implement calls to archinstall's profile and package installation modules.
            # Example:
            # if profile_module_actual and packages_module_actual:
            #     profile_obj = profile_module_actual.get_profile(actual_mount_point_used, self.settings.get('profile'))
            #     if not profile_obj: raise ArchinstallError_actual(f"Profile {self.settings.get('profile')} not found or failed to load.")
            #     profile_obj.install_profile_packages(additional_packages_list=self.settings.get('additional_packages', []))
            #     # Or more granular:
            #     # pkgs_to_install = profile_module_actual.get_profile_packages(self.settings.get('profile'))
            #     # pkgs_to_install.extend(self.settings.get('additional_packages', []))
            #     # packages_module_actual.pacstrap(actual_mount_point_used, list(set(pkgs_to_install)))
            # else:
            #     raise ArchinstallError_actual("Profile/Package modules not available.")
            self.log(f"  (Placeholder) Package installation for profile '{self.settings.get('profile')}' would happen here.")
            time.sleep(5) # Simulate package installation
            if not self._running: self.installation_finished.emit(False, "Installation stopped."); return


            # === Phase 3: System Configuration (in chroot) ===
            self.log("Phase 3: Configuring the installed system (hostname, locale, user, bootloader)...")
            # TODO: USER ACTION: Implement calls to archinstall modules for system configuration.
            # These functions often take mount_point as an argument or operate via an installer instance
            # that knows about the chroot environment.
            # Example:
            # configurer = system_config_module_actual.SystemConfigurer(actual_mount_point_used) # Hypothetical
            # configurer.set_hostname(self.settings.get('hostname'))
            # configurer.set_locale_and_keyboard(self.settings.get('locale'), self.settings.get('kb_layout'))
            # configurer.set_timezone(self.settings.get('timezone'))
            # configurer.create_user(self.settings.get('username'), self.settings.get('password'), sudo=True)
            # configurer.setup_bootloader(self.settings.get('bootloader'), is_efi=self.settings.get('is_efi'))
            # configurer.generate_fstab()
            self.log("  (Placeholder) System configuration (fstab, locale, user, bootloader) would happen here.")
            time.sleep(3)
            if not self._running: self.installation_finished.emit(False, "Installation stopped."); return

            self.log("Installation process completed successfully (conceptually via library calls)!")
            self.installation_finished.emit(True, "Installation successful (conceptual library mode)!")

        except UserInteractionRequired_actual as e:
            self.log(f"Error: Archinstall library required user interaction: {e}")
            self.log(traceback.format_exc())
            self.installation_finished.emit(False, f"Installation failed: Archinstall required user interaction.")
        except ArchinstallError_actual as e:
            self.log(f"Archinstall library error: {e}")
            self.log(traceback.format_exc())
            self.installation_finished.emit(False, f"Installation failed: {e}")
        except ImportError as e:
            self.log(f"Import error during installation: {e}. This may relate to 'loop import' issues or archinstall structure.")
            self.log(traceback.format_exc())
            self.installation_finished.emit(False, f"Library Import Error: {e}")
        except Exception as e:
            self.log(f"An unexpected error occurred during installation: {e}")
            self.log(traceback.format_exc())
            self.installation_finished.emit(False, f"An unexpected critical error occurred: {e}")
        finally:
            self.log("InstallerEngineThread finished execution.")
            # TODO: USER ACTION: Implement unmounting logic if mount_point was used
            # Example: if actual_mount_point_used and disk_module_actual:
            #    disk_module_actual.unmount_target_volumes(actual_mount_point_used)


# --- Main Application Window ---
class MaiBloomInstallerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.installation_settings = {}
        self.installer_thread = None
        # Create a persistent helper instance for non-threaded calls like disk scan
        self._engine_helper = InstallerEngineThread({}) 
        self._engine_helper.disk_scan_complete.connect(self.on_disk_scan_complete)
        self._engine_helper.installation_log.connect(self.update_log_output) # Log messages from scan
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f'Mai Bloom OS Installer (Library Mode - KDE Default)') # Title reflects KDE
        self.setGeometry(100, 100, 850, 700)
        layout = QVBoxLayout(self)

        log_group = QGroupBox("Installation Log")
        log_layout = QVBoxLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True); self.log_output.setLineWrapMode(QTextEdit.NoWrap)
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)

        controls_widget = QWidget()
        controls_main_layout = QVBoxLayout(controls_widget)

        disk_group_box = QGroupBox("Disk Setup")
        disk_layout = QVBoxLayout()
        self.scan_disks_button = QPushButton("Scan for Disks (using Archinstall lib)")
        self.scan_disks_button.clicked.connect(self.trigger_disk_scan)
        disk_layout.addWidget(self.scan_disks_button)
        self.disk_combo = QComboBox(); self.disk_combo.setToolTip("Select target disk.")
        disk_layout.addLayout(self.create_form_row("Target Disk:", self.disk_combo))
        self.wipe_disk_checkbox = QCheckBox("Wipe selected disk & auto-partition (standard layout)"); self.wipe_disk_checkbox.setChecked(True)
        disk_layout.addWidget(self.wipe_disk_checkbox)
        disk_group_box.setLayout(disk_layout)
        controls_main_layout.addWidget(disk_group_box)

        settings_group = QGroupBox("System Settings")
        settings_layout = QGridLayout()
        self.hostname_input = QLineEdit("maibloom-os"); settings_layout.addWidget(QLabel("Hostname:"), 0, 0); settings_layout.addWidget(self.hostname_input, 0, 1)
        self.username_input = QLineEdit("maiuser"); settings_layout.addWidget(QLabel("Username:"), 1, 0); settings_layout.addWidget(self.username_input, 1, 1)
        self.password_input = QLineEdit(); self.password_input.setPlaceholderText("Enter password"); self.password_input.setEchoMode(QLineEdit.Password)
        settings_layout.addWidget(QLabel("Password:"), 2, 0); settings_layout.addWidget(self.password_input, 2, 1)
        
        self.profile_combo = QComboBox()
        profiles = ["kde", "gnome", "xfce4", "minimal"] # Common archinstall profile names
        self.profile_combo.addItems(profiles)
        try: # Set KDE as default
            kde_index = profiles.index(DEFAULT_DESKTOP_ENVIRONMENT)
            self.profile_combo.setCurrentIndex(kde_index)
        except ValueError:
            self.update_log_output(f"Warning: Default DE '{DEFAULT_DESKTOP_ENVIRONMENT}' not in profile list.")
        settings_layout.addWidget(QLabel("Desktop Profile:"), 3, 0); settings_layout.addWidget(self.profile_combo, 3, 1)
        
        self.locale_input = QLineEdit("en_US.UTF-8"); settings_layout.addWidget(QLabel("Locale:"), 4,0); settings_layout.addWidget(self.locale_input, 4,1)
        self.kb_layout_input = QLineEdit("us"); settings_layout.addWidget(QLabel("Keyboard:"), 5,0); settings_layout.addWidget(self.kb_layout_input, 5,1)
        self.timezone_input = QLineEdit("UTC"); settings_layout.addWidget(QLabel("Timezone:"), 6,0); settings_layout.addWidget(self.timezone_input, 6,1)

        settings_group.setLayout(settings_layout)
        controls_main_layout.addWidget(settings_group)
        
        app_group = QGroupBox("Additional Applications")
        app_layout_grid = QGridLayout()
        self.app_category_checkboxes = {}
        row, col = 0,0
        for cat_name in APP_CATEGORIES.keys():
            self.app_category_checkboxes[cat_name] = QCheckBox(f"{cat_name} Apps")
            app_layout_grid.addWidget(self.app_category_checkboxes[cat_name], row, col)
            col +=1
            if col > 1: col = 0; row +=1
        app_group.setLayout(app_layout_grid)
        controls_main_layout.addWidget(app_group)
        controls_main_layout.addStretch()
        
        splitter = QSplitter(Qt.Horizontal); splitter.addWidget(controls_widget); splitter.addWidget(log_group)
        splitter.setSizes([400, 450]); layout.addWidget(splitter)

        self.install_button = QPushButton(f"Install Mai Bloom OS ({DEFAULT_DESKTOP_ENVIRONMENT} Default)")
        self.install_button.setStyleSheet("background-color: lightblue; padding: 10px; font-weight: bold;")
        self.install_button.clicked.connect(self.start_installation)
        layout.addWidget(self.install_button)

        if not ARCHINSTALL_LIBRARY_AVAILABLE:
            self.update_log_output("CRITICAL: Actual Archinstall library components failed to import. Using MOCK/Placeholder functionality. Installation will be simulated.")
            # self.install_button.setEnabled(False) # Keep enabled for demo flow with mocks
            # self.scan_disks_button.setEnabled(False)
            QMessageBox.warning(self, "Archinstall Library Not Loaded",
                                "Could not load actual archinstall library modules. The installer will run with mock data and simulate installation steps. "
                                "This is for UI demonstration only. Please check console for import errors.")
        else:
            self.update_log_output("Archinstall library components imported (or mocked successfully). Ready for setup.")
        
        self.trigger_disk_scan() # Initial scan on startup

    def create_form_row(self, label_text, widget):
        row_layout = QHBoxLayout(); label = QLabel(label_text); label.setFixedWidth(100)
        row_layout.addWidget(label); row_layout.addWidget(widget); return row_layout

    def trigger_disk_scan(self):
        self.update_log_output("GUI: Triggering disk scan...")
        self.scan_disks_button.setEnabled(False)
        # This call now uses the helper InstallerEngineThread instance's method.
        # It's still synchronous from the GUI's perspective as run_disk_scan itself isn't threaded.
        # If disk scanning in archinstall lib is slow, run_disk_scan should also be in a thread.
        # For now, assuming it's relatively quick.
        self._engine_helper.run_disk_scan() 

    def on_disk_scan_complete(self, disks_data):
        self.update_log_output(f"GUI: Disk scan signal received. Found {len(disks_data)} processed disk(s).")
        self.disk_combo.clear()
        if disks_data:
            for path_key, info_dict in disks_data.items():
                # Path_key is already the actual path like "/dev/sda"
                display_text = f"{path_key} - {info_dict.get('model', 'N/A')} ({info_dict.get('size', 'N/A')})"
                self.disk_combo.addItem(display_text, userData=path_key) # Store the path
        else:
            self.update_log_output("GUI: No suitable disks found by scan or scan failed.")
        self.scan_disks_button.setEnabled(True)

    def update_log_output(self, message):
        self.log_output.append(message)
        self.log_output.ensureCursorVisible()
        QApplication.processEvents()

    def gather_settings(self):
        settings = {}
        selected_disk_index = self.disk_combo.currentIndex()
        if selected_disk_index < 0:
            self.update_log_output("Error: No target disk selected in combobox.")
            return None
        settings["target_disk_path"] = self.disk_combo.itemData(selected_disk_index)
        if not settings["target_disk_path"]: # Double check if userData was actually set
            self.update_log_output("Error: Selected disk has no valid path data.")
            return None
            
        settings["wipe_disk"] = self.wipe_disk_checkbox.isChecked()
        settings["partitioning_options"] = "archinstall_default_efi" if settings["wipe_disk"] else "use_existing_or_fail" # This needs to map to archinstall lib logic

        settings["hostname"] = self.hostname_input.text().strip()
        settings["username"] = self.username_input.text().strip()
        settings["password"] = self.password_input.text()
        settings["profile"] = self.profile_combo.currentText() # This will be "kde" by default
        
        settings["locale"] = self.locale_input.text().strip()
        settings["kb_layout"] = self.kb_layout_input.text().strip()
        settings["timezone"] = self.timezone_input.text().strip()
        settings["is_efi"] = os.path.exists("/sys/firmware/efi")

        additional_packages = []
        for cat_name, checkbox_widget in self.app_category_checkboxes.items():
            if checkbox_widget.isChecked():
                additional_packages.extend(APP_CATEGORIES.get(cat_name, []))
        settings["additional_packages"] = list(set(additional_packages))
        
        # Ensure crucial base packages are considered if "minimal" profile is somehow chosen
        # or if the chosen DE profile is surprisingly bare.
        # Most DE profiles (kde, gnome) should pull these in.
        base_essentials = ["networkmanager", "sudo", "nano", "base", "linux", "linux-firmware"]
        if settings["profile"].lower() == "minimal":
             if not settings["is_efi"]: base_essentials.append("grub")
             else: base_essentials.append("efibootmgr")
        settings["additional_packages"] = list(set(settings["additional_packages"] + base_essentials))


        self.update_log_output(f"Installation settings gathered for profile '{settings['profile']}': {settings['target_disk_path']}")
        return settings

    def start_installation(self):
        current_settings = self.gather_settings()
        if not current_settings:
            QMessageBox.warning(self, "Configuration Incomplete", "Please select a target disk and ensure all settings are correct.")
            return

        if not ARCHINSTALL_LIBRARY_AVAILABLE:
             reply = QMessageBox.question(self, 'Confirm MOCK Installation',
                                     f"Archinstall library not loaded. This will only SIMULATE installation on {current_settings.get('target_disk_path','N/A')} "
                                     f"with profile {current_settings.get('profile','N/A')}.\n\nProceed with simulation?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        else:
            reply = QMessageBox.question(self, 'Confirm Installation',
                                        f"This will install Mai Bloom OS ({current_settings.get('profile','N/A')}) on:\n"
                                        f"DISK: {current_settings.get('target_disk_path','N/A')}\n"
                                        f"WIPE DISK: {'YES' if current_settings.get('wipe_disk') else 'NO (Advanced)'}\n\n"
                                        "PROCEED WITH INSTALLATION?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            self.update_log_output("Installation cancelled by user.")
            return

        self.install_button.setEnabled(False)
        self.scan_disks_button.setEnabled(False)
        self.log_output.clear()
        self.update_log_output("Starting installation process...")

        self.installer_thread = InstallerEngineThread(current_settings)
        self.installer_thread.installation_log.connect(self.update_log_output)
        self.installer_thread.installation_finished.connect(self.on_installation_finished)
        self.installer_thread.start()

    def on_installation_finished(self, success, message):
        self.update_log_output(f"GUI: Installation finished signal. Success: {success}, Message: {message}")
        if success:
            QMessageBox.information(self, "Installation Complete", message)
        else:
            QMessageBox.critical(self, "Installation Failed", message)
        self.install_button.setEnabled(True)
        self.scan_disks_button.setEnabled(True)


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

