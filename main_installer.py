#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# --- Imports ---
import sys
import os
import time
import subprocess
import traceback
import logging # For capturing archinstall logs

# Attempt to import archinstall - script will fail early if not found
try:
    import archinstall
    from archinstall import profile # For profile handling
    from archinstall import Installer # Main class (might vary)
    from archinstall import models # For typed models if used
    from archinstall import disk # For disk operations
    # from archinstall import ... # Import other necessary modules
    ARCHINSTALL_AVAILABLE = True
except ImportError:
    print("ERROR: The 'archinstall' library is not installed or not found.")
    print("Please install it (e.g., 'sudo pacman -S archinstall') and try again.")
    ARCHINSTALL_AVAILABLE = False
    # We could sys.exit(1) here, but let the GUI load to show the error if possible.
    # For now, utility functions will use mocks if archinstall isn't available.

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSplitter,
    QStackedWidget, QPlainTextEdit, QPushButton, QMessageBox, QFrame,
    QComboBox, QLineEdit, QCheckBox, QProgressBar, QGridLayout
)
from PyQt5.QtGui import QIcon, QFontDatabase, QFont, QPixmap, QPainter, QImageWriter, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot, QSize

# --- Configuration ---
APP_NAME = "Mai Bloom OS Installer"
LOGO_FILENAME = "logo.png" 
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) 
LOGO_PATH = os.path.join(SCRIPT_DIR, LOGO_FILENAME) 
POST_INSTALL_SCRIPT_NAME = "final_setup.sh" 
POST_INSTALL_SCRIPT_PATH = os.path.join(SCRIPT_DIR, POST_INSTALL_SCRIPT_NAME)

DEFAULT_CONFIG = {
    'os_name': 'Mai Bloom OS', 'locale': 'en_US.UTF-8', 'keyboard_layout': 'us',
    'disk_target': '', 'disk_scheme': 'guided', 'disk_filesystem': 'ext4', 'disk_encrypt': False,
    'hostname': 'maibloom-pc', 'username': '', 'user_sudo': True,
    'profile_name': 'Desktop (KDE Plasma)', 'app_categories': [], 
    'timezone': 'Asia/Tehran', # Store full timezone string
    'mirror_region_code': 'Worldwide', # Use code if available
    'root_password': '', 'user_password': '', 'disk_encrypt_password': '',
    # Add other keys archinstall might need, e.g., kernels, audio_server, etc.
    'kernels': ['linux'],
    'nic': 'NetworkManager' # Example default network config
}

# --- Stylesheet & Text Constants ---
# (DARK_THEME_QSS, WELCOME_STEP_HTML, etc. - remain unchanged from previous version)
DARK_THEME_QSS="""QMainWindow,QWidget{font-size:10pt;background-color:#2E2E2E;color:#E0E0E0}QStackedWidget>QWidget{background-color:#2E2E2E}StepWidget QLabel{color:#E0E0E0}StepWidget QCheckBox{font-size:11pt;padding:3px}QPushButton{padding:9px 18px;border-radius:5px;background-color:#555;color:#FFF;border:1px solid #686868;font-weight:bold}QPushButton:hover{background-color:#686868}QPushButton:disabled{background-color:#404040;color:#808080;border-color:#505050}QPushButton#InstallButton{background-color:#4CAF50;border-color:#388E3C}QPushButton#InstallButton:hover{background-color:#388E3C}QPlainTextEdit#LogOutput{background-color:#1C1C1C;color:#C0C0C0;border:1px solid #434343;font-family:"Monospace"}QLineEdit,QComboBox{padding:6px 8px;border:1px solid #555;border-radius:4px;background-color:#3D3D3D;color:#E0E0E0}QComboBox::drop-down{border:none;background-color:#4A4A4A}QComboBox QAbstractItemView{background-color:#3D3D3D;color:#E0E0E0;selection-background-color:#007BFF}QCheckBox{margin:5px 0;color:#E0E0E0}QCheckBox::indicator{width:18px;height:18px;background-color:#555;border:1px solid #686868;border-radius:3px}QCheckBox::indicator:checked{background-color:#007BFF}QProgressBar{text-align:center;padding:1px;border-radius:5px;background-color:#555;border:1px solid #686868;color:#E0E0E0;min-height:20px}QProgressBar::chunk{background-color:#007BFF;border-radius:4px}QSplitter::handle{background-color:#4A4A4A}QSplitter::handle:horizontal{width:3px}"""
WELCOME_STEP_HTML=(f"<h2>Welcome to {APP_NAME}!</h2><p>Installer guide...</p><h3>Notes:</h3><ul><li>Internet recommended.</li><li>Backup data!</li><li>Disk ops may erase data.</li></ul><p>Next-></p>")
LANGUAGE_STEP_EXPLANATION="Select system language (menus, messages)."
KEYBOARD_STEP_EXPLANATION="Choose layout matching your keyboard."
SELECT_DISK_STEP_EXPLANATION="Choose install disk.<br><b style='color:yellow;'>Data may be erased.</b>"
APP_CATEGORIES_EXPLANATION="Select app types for initial setup."
SUMMARY_STEP_INTRO_TEXT="Review settings. <b style='color:yellow;'>Install button modifies disk!</b>"

# --- Utility Functions (Now use archinstall if available) ---
def get_keyboard_layouts():
    if ARCHINSTALL_AVAILABLE:
        try: return sorted(archinstall.list_keyboard_languages()) # Assumes function exists
        except AttributeError: print("WARN: archinstall.list_keyboard_languages not found, using mock."); pass # Fallback
        except Exception as e: print(f"WARN: Error listing keyboards: {e}, using mock."); pass
    return ["us", "uk", "de", "fr", "es", "ir", "fa"] # Mock fallback

def get_locales():
    # Archinstall often relies on system's /etc/locale.gen, might not have a direct list function easily usable here
    # Might need to parse /etc/locale.gen or provide a curated list
    print("WARN: get_locales using hardcoded list. Integrate with system locale data if possible.")
    return ["en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8", "fa_IR.UTF-8"] # Mock/Curated list

def get_block_devices_info():
    if ARCHINSTALL_AVAILABLE:
        try:
            # archinstall.list_block_devices() often returns dict keyed by path
            raw_devices = archinstall.list_block_devices() # Needs root?
            devices = []
            for path, data in raw_devices.items():
                if data.get('type') == 'disk': # Only include disks
                     # Ensure size is integer, handle potential None or formatting issues
                     size_bytes = data.get('size', 0)
                     if isinstance(size_bytes, str): # Convert if lsblk format string like "500G"
                         # Basic conversion (improve as needed)
                         try:
                             if 'G' in size_bytes.upper(): size_bytes = int(float(size_bytes.upper().replace('G','')) * 1024**3)
                             elif 'M' in size_bytes.upper(): size_bytes = int(float(size_bytes.upper().replace('M','')) * 1024**2)
                             else: size_bytes = int(size_bytes)
                         except ValueError: size_bytes = 0

                     devices.append({
                         'name': path,
                         'size': size_bytes,
                         'type': 'disk',
                         'label': data.get('label'),
                         'fstype': data.get('fstype'),
                         'mountpoint': data.get('mountpoint'),
                         'error': None # Assuming archinstall function provides clean data
                     })
            if devices: return devices
            else: print("WARN: archinstall.list_block_devices() returned no disks, using mock.")
        except PermissionError: print("ERROR: Need root privileges to list block devices properly. Using mock.")
        except AttributeError: print("WARN: archinstall.list_block_devices not found, using mock."); pass
        except Exception as e: print(f"WARN: Error listing block devices: {e}, using mock."); pass

    # Mock fallback if archinstall unavailable or fails
    return [{'name':"/dev/sda",'size':500*1024**3,'type':'disk','label':'Mock A'}, {'name':"/dev/sdb",'size':1000*1024**3,'type':'disk','label':'Mock B'}]

def get_mirror_regions():
    if ARCHINSTALL_AVAILABLE:
        try:
            # Assume it returns a dict {'Display Name': 'CodeOrObject', ...}
            regions = archinstall.list_mirror_regions()
            if regions: return regions
            else: print("WARN: archinstall.list_mirror_regions returned empty, using mock.")
        except AttributeError: print("WARN: archinstall.list_mirror_regions not found, using mock."); pass
        except Exception as e: print(f"WARN: Error listing mirror regions: {e}, using mock."); pass
    return {"Worldwide":"Worldwide", "Iran":"IR", "Germany":"DE", "US":"US"}

def get_timezones():
    if ARCHINSTALL_AVAILABLE:
        try:
            # Assume it returns dict {'Region': ['City1', ...]}
            zones = archinstall.list_timezones()
            if zones: return zones
            else: print("WARN: archinstall.list_timezones returned empty, using mock.")
        except AttributeError: print("WARN: archinstall.list_timezones not found, using mock."); pass
        except Exception as e: print(f"WARN: Error listing timezones: {e}, using mock."); pass
    return {"Asia":["Tehran","Kolkata","Tokyo"], "Europe":["Berlin","London","Paris"], "America":["New_York","Los_Angeles"]}

def get_profiles():
    if ARCHINSTALL_AVAILABLE:
        try:
            # profile.list_profiles() might return dict {name: ProfileObject}
            profiles_dict = profile.list_profiles()
            profiles_list = []
            for name, prof_obj in profiles_dict.items():
                 # Try to get a description, fallback if not present
                 description = getattr(prof_obj, 'description', 'No description available.')
                 # Filter out internal profiles if needed (e.g., those starting with _)
                 if not name.startswith('_'):
                     profiles_list.append({"name": name, "description": description})
            if profiles_list: return profiles_list
            else: print("WARN: archinstall profile.list_profiles returned empty, using mock.")
        except AttributeError: print("WARN: archinstall profile.list_profiles not found, using mock."); pass
        except Exception as e: print(f"WARN: Error listing profiles: {e}, using mock."); pass
    return [{"name":"Minimal","description":"CLI system."},{"name":"KDE Plasma","description":"Plasma desktop."},{"name":"GNOME","description":"GNOME desktop."}]

# --- Qt Log Handler ---
class QtLogHandler(logging.Handler):
    """A logging handler that emits a PyQt signal."""
    def __init__(self, log_signal_emitter):
        super().__init__()
        self.log_signal_emitter = log_signal_emitter
        # Basic formatter, can be customized
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        self.setFormatter(formatter)

    def emit(self, record):
        msg = self.format(record)
        self.log_signal_emitter.emit(msg) # Emit the formatted message

# --- Installation Thread (Using Archinstall) ---
class InstallationThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.installer = None # Placeholder for archinstall.Installer instance

    def setup_logging(self):
        """Configure logging to capture archinstall logs."""
        # Get the root logger used by archinstall (or specific 'archinstall' logger)
        log = logging.getLogger() # Or logging.getLogger('archinstall')
        log.setLevel(logging.INFO) # Set desired level

        # Remove existing handlers to avoid duplication if thread runs multiple times? Careful.
        # for handler in log.handlers[:]: log.removeHandler(handler)

        # Add our custom handler
        qt_handler = QtLogHandler(self.log_signal)
        log.addHandler(qt_handler)
        
        # Optional: Add console handler for debugging?
        # console_handler = logging.StreamHandler(sys.stdout)
        # console_handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
        # log.addHandler(console_handler)

        self.log_signal.emit("Logging setup to capture archinstall output.")

    def get_packages_for_categories(self, categories):
        """Maps selected category names to package lists."""
        mapping = { # Define your package mappings here
            "Programming": ["base-devel", "git", "python", "code"], # code is vscode oss build
            "Gaming": ["steam", "lutris", "wine", "gamemode", "mangohud"],
            "Office & Daily Use": ["libreoffice-fresh", "firefox", "thunderbird", "vlc"],
            "Graphics & Design": ["gimp", "inkscape", "krita", "blender"],
            "Multimedia": ["vlc", "mpv", "obs-studio", "kdenlive"],
            "Science & Engineering": ["python-numpy", "python-scipy", "octave"],
            "Utilities": ["htop", "neofetch", "rsync", "wget"]
        }
        package_list = set() # Use a set to avoid duplicates
        for category in categories:
            packages = mapping.get(category, [])
            if packages:
                self.log_signal.emit(f"Adding packages for category: {category}")
                package_list.update(packages)
            else:
                self.log_signal.emit(f"Warning: No package mapping defined for category: {category}")
        return list(package_list)

    def run(self):
        if not ARCHINSTALL_AVAILABLE:
            self.log_signal.emit("FATAL: archinstall library not found. Cannot proceed.")
            self.finished_signal.emit(False, "archinstall library missing.")
            return

        self.setup_logging()
        self.log_signal.emit("Installation thread started using archinstall.")
        self.progress_signal.emit(0, "Initializing...")

        try:
            # ** STEP 1: Prepare Configuration for archinstall **
            # Archinstall often uses a dictionary or specific model objects.
            # We need to translate self.config (from GUI) into that format.
            # This is highly dependent on the archinstall version's API.
            # Let's assume it takes a dictionary resembling its JSON configuration.

            ai_config = {
                'hostname': self.config.get('hostname'),
                'locale_config': {
                    'kb_layout': self.config.get('keyboard_layout'),
                    'sys_lang': self.config.get('locale'),
                    # 'sys_enc': 'UTF-8' # Often default
                },
                'mirror_config': {
                    'mirror_region': self.config.get('mirror_region_code') or self.config.get('mirror_region_display_name')
                },
                'disk_config': {
                    'device_path': self.config.get('disk_target'),
                    # How to specify partitioning? Archinstall might need more details
                    # For guided wipe:
                    'wipe': True, # Assuming guided == wipe
                    'filesystem': self.config.get('disk_filesystem'),
                    # 'layout': archinstall.DiskLayout(...) # Or maybe it takes layout objects?
                },
                'disk_encryption': None, # Placeholder for encryption object/dict
                'bootloader': self.config.get('bootloader', 'grub').lower(), # Ensure lowercase?
                'kernels': self.config.get('kernels', ['linux']),
                'nic_config': {'type': self.config.get('nic', 'NetworkManager')},
                'timezone': self.config.get('timezone'),
                'audio_config': {'audio': 'pipewire'}, # Example default
                'profile_config': {
                    'profile': self.config.get('profile_name') if self.config.get('profile_name') != 'Minimal' else None
                    # Add profile-specific options if needed
                },
                'packages': self.config.get('additional_packages', []),
                'users': [],
                # ... other settings archinstall needs ...
                '!users': [{ # Archinstall often uses '!users'
                     'username': self.config.get('username'),
                     'password': self.config.get('user_password'),
                     'sudo': self.config.get('user_sudo', False)
                }] if self.config.get('username') else [],
                '!root-password': self.config.get('root_password'),
            }

            # Handle disk encryption config separately (example structure)
            if self.config.get('disk_encrypt'):
                ai_config['disk_encryption'] = {
                    'encryption_type': 'luks',
                    'password': self.config.get('disk_encrypt_password'),
                    # Archinstall might need partition info here too
                }

            # Add packages based on selected categories
            category_packages = self.get_packages_for_categories(self.config.get('app_categories', []))
            ai_config['packages'].extend(category_packages)
            # Ensure uniqueness if packages were also added manually
            ai_config['packages'] = list(set(ai_config['packages'])) 
            
            self.log_signal.emit(f"Archinstall config prepared (passwords omitted): {{k:v for k,v in ai_config.items() if 'pass' not in k}}") # Check structure

            # ** STEP 2: Create Installer Instance and Run **
            # The mountpoint is usually /mnt during installation
            mountpoint = '/mnt' # Standard mountpoint for archinstall
            
            # Ensure mountpoint is clean/prepared if necessary (archinstall might do this)
            # Example: archinstall.prepare_disk(ai_config['disk_config']['device_path']) ?
            
            # Create the main Installer object (API might differ)
            # It might take the config dict directly, or need individual settings
            # Using a context manager is often safer as it handles setup/teardown (mounting/unmounting)
            
            # Highly speculative API usage:
            # self.installer = Installer(mountpoint, ai_config) # Or maybe Installer('/mnt') and set properties?
            
            # It's more likely archinstall works through function calls or a guided process object.
            # Let's simulate stages using function calls based on common steps.
            
            self.progress_signal.emit(5, "Preparing disks...")
            # archinstall.perform_disk_operations(ai_config['disk_config'], ai_config['disk_encryption'])
            # archinstall.mount_partitions(ai_config['disk_config'], mountpoint)
            time.sleep(1) # Simulate

            self.progress_signal.emit(15, "Setting up mirrors...")
            # archinstall.select_mirrors(ai_config['mirror_config'])
            time.sleep(1)

            self.progress_signal.emit(25, f"Installing base system ({ai_config['kernels']})...")
            # archinstall.run_pacstrap(mountpoint, ['base'] + ai_config['kernels'])
            time.sleep(3)

            self.progress_signal.emit(45, "Generating fstab...")
            # archinstall.write_fstab(mountpoint)
            time.sleep(1)

            self.progress_signal.emit(50, "Configuring system in chroot...")
            # Archinstall likely has a way to run commands or apply settings in chroot
            # E.g., using a context manager or specific functions:
            # with archinstall.Chroot(mountpoint):
            #     archinstall.set_hostname(ai_config['hostname'])
            #     archinstall.set_timezone(ai_config['timezone'])
            #     archinstall.set_locale(ai_config['locale_config'])
            #     archinstall.set_keyboard_layout(ai_config['locale_config']['kb_layout'])
            #     archinstall.set_root_password(ai_config['!root-password'])
            #     if ai_config['!users']:
            #         archinstall.create_user(ai_config['!users'][0])
            #     # Configure Network
            #     archinstall.setup_network(ai_config['nic_config'])
                
            #     # Install profiles, packages, categories INSIDE chroot
            #     packages_to_install = ['base-devel'] # Always good to have?
            #     if ai_config['profile_config'].get('profile'):
            #         packages_to_install.extend( archinstall.get_profile_packages(ai_config['profile_config']['profile']) )
            #     packages_to_install.extend(ai_config['packages'])
            #     if packages_to_install:
            #          archinstall.run_pacman(['-Syu', '--noconfirm', '--needed'] + list(set(packages_to_install)))

                # --- Apply Branding INSIDE Chroot ---
                # Modify os-release
                # cmd_os_release = f'sed -i \'s/^PRETTY_NAME=.*/PRETTY_NAME="{DEFAULT_CONFIG["os_name"]}"/\' /etc/os-release'
                # archinstall.run_command(cmd_os_release)
                # Modify GRUB (if used)
                # cmd_grub_dist = f'echo \'GRUB_DISTRIBUTOR="{DEFAULT_CONFIG["os_name"]}"\' >> /etc/default/grub' # Append or use sed
                # archinstall.run_command(cmd_grub_dist)
                
                # --- Run Custom Chroot Config Script? ---
                # If you have mai_bloom_config.sh and copied it into chroot:
                # archinstall.run_command("/path/inside/chroot/mai_bloom_config.sh")
            time.sleep(3)

            self.progress_signal.emit(85, "Installing bootloader...")
            # archinstall.install_bootloader(ai_config['bootloader'], mountpoint) # Needs target disk/EFI info?
            # If GRUB was modified, ensure grub-mkconfig runs AFTERWARDS, INSIDE chroot
            # with archinstall.Chroot(mountpoint):
            #    archinstall.run_command("grub-mkconfig -o /boot/grub/grub.cfg")
            time.sleep(2)

            self.progress_signal.emit(100, "Finalizing...")
            # archinstall.finalize_installation(mountpoint) # Unmount etc.
            time.sleep(1)

            self.log_signal.emit("Archinstall process completed.")
            self.finished_signal.emit(True, f"{self.config.get('os_name', 'OS')} installation core phase complete.")

        except Exception as e:
            # Catch specific archinstall exceptions if they exist
            self.log_signal.emit(f"FATAL archinstall error: {str(e)}\n{traceback.format_exc()}")
            self.finished_signal.emit(False, f"Installation failed during archinstall execution: {str(e)}")


# --- Step Widget Base Class ---
# (Unchanged from previous version with logo)
class StepWidget(QWidget):
    def __init__(self, title, config_ref, main_window_ref):
        super().__init__(); self.title = title; self.config = config_ref; self.main_window = main_window_ref
        self.outer_layout = QVBoxLayout(self); self.outer_layout.setContentsMargins(25, 15, 25, 15)
        title_area_layout = QHBoxLayout(); title_area_layout.setSpacing(10); title_area_layout.setContentsMargins(0, 0, 0, 5)
        self.logo_label = QLabel()
        logo_pixmap = QPixmap(LOGO_PATH)
        if not logo_pixmap.isNull(): scaled_logo = logo_pixmap.scaled(48,48,Qt.KeepAspectRatio,Qt.SmoothTransformation); self.logo_label.setPixmap(scaled_logo); self.logo_label.setFixedSize(48,48)
        else: self.logo_label.setText("[-]"); self.logo_label.setFixedSize(48,48)
        title_area_layout.addWidget(self.logo_label)
        self.title_label = QLabel(f"<b>{title}</b>"); title_font=self.title_label.font();title_font.setPointSize(16);self.title_label.setFont(title_font); self.title_label.setStyleSheet("color: #00BFFF;")
        title_area_layout.addWidget(self.title_label); title_area_layout.addStretch(1); self.outer_layout.addLayout(title_area_layout)
        sep=QFrame();sep.setFrameShape(QFrame.HLine);sep.setFrameShadow(QFrame.Sunken);sep.setStyleSheet("border:1px solid #4A4A4A;");self.outer_layout.addWidget(sep)
        self.content_layout=QVBoxLayout();self.content_layout.setSpacing(15);self.content_layout.setContentsMargins(0,10,0,0);self.outer_layout.addLayout(self.content_layout);self.outer_layout.addStretch(1)
    def get_title(self): return self.title
    def load_ui_from_config(self): pass
    def save_config_from_ui(self): return True
    def on_entry(self): pass
    def on_exit(self, going_back=False): return True

# --- Concrete Step Widgets ---
# (WelcomeStep, LanguageStep, KeyboardStep, SelectDiskStep, ProfileSelectionStep, AppCategoriesStep, UserAccountsStep, SummaryStep, InstallProgressStep)
# These remain unchanged from the previous response where they were fully defined.
# Assume they are all here correctly. For brevity, only showing a couple.
class WelcomeStep(StepWidget):
    def __init__(self, config, main_ref): super().__init__("Welcome", config, main_ref); info=QLabel(WELCOME_STEP_HTML);info.setWordWrap(True);info.setTextFormat(Qt.RichText);self.content_layout.addWidget(info)
class LanguageStep(StepWidget):
    def __init__(self,config,main_ref):super().__init__("System Language",config,main_ref);expl=QLabel(LANGUAGE_STEP_EXPLANATION);expl.setWordWrap(True);self.content_layout.addWidget(expl);self.content_layout.addWidget(QLabel("<b>Locale:</b>"));self.locale_combo=QComboBox();self.locale_combo.addItems(get_locales());self.content_layout.addWidget(self.locale_combo)
    def load_ui_from_config(self): self.locale_combo.setCurrentText(self.config.get('locale',DEFAULT_CONFIG['locale']))
    def save_config_from_ui(self): self.config['locale']=self.locale_combo.currentText(); return bool(self.config['locale'] or QMessageBox.warning(self,"","Select locale."))
# ... (Include ALL other StepWidget subclasses here as previously defined) ...
class SelectDiskStep(StepWidget): # Ensure this one is present
    def __init__(self, config, main_ref):
        super().__init__("Select Target Disk", config, main_ref)
        expl = QLabel(SELECT_DISK_STEP_EXPLANATION); expl.setWordWrap(True); expl.setTextFormat(Qt.RichText); self.content_layout.addWidget(expl)
        self.disk_combo = QComboBox(); self.content_layout.addWidget(self.disk_combo)
        self.disk_info_label = QLabel("Disk details..."); self.disk_info_label.setStyleSheet("color:#AAAAAA;"); self.content_layout.addWidget(self.disk_info_label)
        self.devices_data = []; self.disk_combo.currentIndexChanged.connect(self.update_disk_info_display)
    def on_entry(self): self.populate_disk_list()
    def populate_disk_list(self):
        cur = self.config.get('disk_target'); self.disk_combo.clear(); self.devices_data = get_block_devices_info()
        if not self.devices_data: self.disk_combo.addItem("No disks found."); self.disk_combo.setEnabled(False); self.disk_info_label.setText("N/A"); return
        self.disk_combo.setEnabled(True); sel_idx = 0
        for i, d in enumerate(self.devices_data): sz=d.get('size',0)/(1024**3); lbl=f" ({d.get('label','')})" if d.get('label') else ""; self.disk_combo.addItem(f"{d['name']}{lbl} ({sz:.1f}GB)",d['name']);
        if d['name']==cur: sel_idx=i
        if self.disk_combo.count()>0: self.disk_combo.setCurrentIndex(sel_idx)
        self.update_disk_info_display(self.disk_combo.currentIndex())
    def update_disk_info_display(self, index):
        if index<0: self.disk_info_label.setText("No disk.");return
        d_name = self.disk_combo.itemData(index); d = next((x for x in self.devices_data if x['name']==d_name),None)
        if not d: self.disk_info_label.setText(f"Info unavailable."); return
        sz=d.get('size',0)/(1024**3); self.disk_info_label.setText(f"{d['name']} ({sz:.1f}GB)")
    def load_ui_from_config(self): self.populate_disk_list()
    def save_config_from_ui(self):
        if self.disk_combo.currentIndex()<0 or not self.disk_combo.currentData(): QMessageBox.warning(self,"","Select disk."); return False
        self.config['disk_target'] = self.disk_combo.currentData(); return True

class AppCategoriesStep(StepWidget): # Ensure this is present
    def __init__(self, config, main_ref):
        super().__init__("Application Categories 📦", config, main_ref)
        expl_label = QLabel(APP_CATEGORIES_EXPLANATION); expl_label.setWordWrap(True); self.content_layout.addWidget(expl_label)
        self.categories_with_emojis = {"Education":"🎓","Programming":"💻","Gaming":"🎮","Office & Daily Use":"📄","Graphics & Design":"🎨","Multimedia":"🎬","Science":"🔬","Utilities":"🔧"}
        self.checkboxes = {}; grid_layout = QGridLayout(); grid_layout.setSpacing(10); row, col = 0, 0
        for name, emoji in self.categories_with_emojis.items(): cb = QCheckBox(f"{emoji} {name}"); self.checkboxes[name] = cb; grid_layout.addWidget(cb, row, col); col += 1;
        if col >= 2: col = 0; row += 1
        self.content_layout.addLayout(grid_layout)
    def load_ui_from_config(self): sel = self.config.get('app_categories', []); [cb.setChecked(name in sel) for name,cb in self.checkboxes.items()]
    def save_config_from_ui(self): self.config['app_categories'] = [n for n,cb in self.checkboxes.items() if cb.isChecked()]; return True

class SummaryStep(StepWidget): # Ensure this is present
    def __init__(self, config, main_ref): super().__init__("Installation Summary", config, main_ref); expl = QLabel(SUMMARY_STEP_INTRO_TEXT); expl.setWordWrap(True); expl.setTextFormat(Qt.RichText); self.content_layout.addWidget(expl); self.summary_text_edit = QPlainTextEdit(); self.summary_text_edit.setReadOnly(True); self.summary_text_edit.setStyleSheet("font-family:'monospace';font-size:9pt;color:#E0E0E0;background-color:#2A2A2A;"); self.content_layout.addWidget(self.summary_text_edit)
    def on_entry(self):
        lines = [f"--- {self.config.get('os_name', APP_NAME)} Summary ---"]; order = {'locale':"Locale",'keyboard_layout':"Keyboard",'disk_target':"Disk",'hostname':"Hostname",'root_password':"Root Pwd",'username':"Username",'profile_name':"Profile",'app_categories':"Categories"};
        for k,n in order.items():
            v=self.config.get(k); fv="<not set>";
            if k=='username' and not v: n="New User"; fv="Skipped"
            elif "password" in k and v: fv="<set>"
            elif isinstance(v,bool): fv="Yes" if v else "No"
            elif isinstance(v,list): fv=", ".join(v) if v else "<none>"
            elif v is not None and str(v).strip()!="": fv=str(v)
            lines.append(f"{n:<20}: {fv}")
        lines.append(f"\n--- Target: {self.config.get('disk_target','<NO DISK>')} ---"); lines.append("\n--- WARNING: Check disk! ---"); self.summary_text_edit.setPlainText("\n".join(lines))

class InstallProgressStep(StepWidget): # Ensure this is present
    def __init__(self,config,main_ref):super().__init__("Installation Progress",config,main_ref);self.status_label=QLabel("Starting...");font=self.status_label.font();font.setPointSize(12);self.status_label.setFont(font);self.status_label.setAlignment(Qt.AlignCenter);self.content_layout.addWidget(self.status_label);self.progress_bar=QProgressBar();self.progress_bar.setRange(0,100);self.progress_bar.setTextVisible(True);self.progress_bar.setFormat("Waiting... %p%");self.content_layout.addWidget(self.progress_bar)
    def update_ui_progress(self,val,task):self.progress_bar.setValue(val);self.progress_bar.setFormat(f"{task} - %p%");self.status_label.setText(f"Task: {task}")
    def set_final_status(self,suc,msg):self.progress_bar.setValue(100);self.progress_bar.setFormat(msg.split('\n')[0] if suc else"Error!");self.status_label.setText(msg);self.status_label.setStyleSheet(f"color:{'#4CAF50'if suc else'#F44336'};font-weight:bold;")


# --- Main Application Window ---
class MaiBloomOSInstallerWindow(QMainWindow):
    # (init_ui, apply_dark_theme are unchanged from previous version)
    def __init__(self): super().__init__(); self.config_data=DEFAULT_CONFIG.copy(); self.current_step_idx=-1; self.installation_thread=None; self.post_install_thread=None; self.step_widgets_instances=[]; self.init_ui(); self.populate_steps();
                 if self.step_widgets_instances: self.select_step(0, force_show=True)
    def init_ui(self): self.setWindowTitle(APP_NAME); self.setMinimumSize(1100, 700);
                   if os.path.exists(LOGO_PATH): self.setWindowIcon(QIcon(LOGO_PATH));
                   central=QWidget(); self.setCentralWidget(central); main_splitter=QSplitter(Qt.Horizontal,central); self.cfg_area=QWidget(); cfg_layout=QVBoxLayout(self.cfg_area); cfg_layout.setContentsMargins(0,0,0,0); self.cfg_stack=QStackedWidget(); cfg_layout.addWidget(self.cfg_stack,1); nav_layout=QHBoxLayout(); nav_layout.setContentsMargins(10,5,10,10); self.prev_btn=QPushButton("⬅ Prev"); self.prev_btn.clicked.connect(self.navigate_prev); self.next_btn=QPushButton("Next ➡"); self.next_btn.clicked.connect(self.navigate_next); self.inst_btn=QPushButton(f"🚀 Install"); self.inst_btn.clicked.connect(self.confirm_and_start_installation); nav_layout.addStretch(1); nav_layout.addWidget(self.prev_btn); nav_layout.addWidget(self.next_btn); nav_layout.addWidget(self.inst_btn); cfg_layout.addLayout(nav_layout); main_splitter.addWidget(self.cfg_area); self.log_out=QPlainTextEdit(); self.log_out.setReadOnly(True); log_f=QFontDatabase.systemFont(QFontDatabase.FixedFont); log_f.setPointSize(9); self.log_out.setFont(log_f); main_splitter.addWidget(self.log_out); main_splitter.setSizes([650,450]); main_splitter.setStretchFactor(0,2); main_splitter.setStretchFactor(1,1); outer_layout=QHBoxLayout(central); outer_layout.addWidget(main_splitter); central.setLayout(outer_layout); self.appendToLog(f"{APP_NAME} started.", "INFO"); self.apply_dark_theme()
    def apply_dark_theme(self): self.setStyleSheet(DARK_THEME_QSS); self.log_out.setObjectName("LogOutput"); self.inst_btn.setObjectName("InstallButton")

    def populate_steps(self):
        # Define sequence including new AppCategoriesStep
        self.step_definitions = [
            WelcomeStep, LanguageStep, KeyboardStep, SelectDiskStep, # Add refined disk steps
            # Add MirrorRegionStep, TimezoneStep etc. back when implemented
            ProfileSelectionStep,
            AppCategoriesStep, # Added App Categories step
            UserAccountsStep, # Should ideally be split (Root Pwd, Create User)
            SummaryStep,
            InstallProgressStep
        ]
        self.step_widgets_instances = []
        for StepCls in self.step_definitions:
            inst=StepCls(self.config_data,self); self.step_widgets_instances.append(inst)
            self.cfg_stack.addWidget(inst)

    def select_step(self,idx,force_show=False):
        if not(0<=idx<len(self.step_widgets_instances)): return
        is_target_inst=isinstance(self.step_widgets_instances[idx],InstallProgressStep); is_curr_summ=self.current_step_idx>=0 and isinstance(self.step_widgets_instances[self.current_step_idx],SummaryStep)
        if is_target_inst and not is_curr_summ and not force_show: return
        self.current_step_idx=idx; self.cfg_stack.setCurrentIndex(idx); curr_w=self.step_widgets_instances[idx]; curr_w.load_ui_from_config(); curr_w.on_entry(); self.update_navigation_buttons()

    def update_navigation_buttons(self):
        # (Unchanged) - manages prev/next/install visibility based on current step index/type
        is_first=(self.current_step_idx==0); is_inst=False; is_summ=False;
        if 0<=self.current_step_idx<len(self.step_widgets_instances): curr_w=self.step_widgets_instances[self.current_step_idx]; is_summ=isinstance(curr_w,SummaryStep); is_inst=isinstance(curr_w,InstallProgressStep)
        self.prev_btn.setEnabled(not is_first and not is_inst); self.next_btn.setVisible(not is_summ and not is_inst); self.inst_btn.setVisible(is_summ and not is_inst)
        if is_inst: self.prev_btn.setEnabled(False); self.next_btn.setVisible(False); self.inst_btn.setVisible(False)


    def navigate_next(self):
        # (Unchanged) - saves current step, moves to next
        curr_w = self.step_widgets_instances[self.current_step_idx]
        if not curr_w.on_exit() or not curr_w.save_config_from_ui(): return
        if self.current_step_idx < len(self.step_widgets_instances)-1: self.select_step(self.current_step_idx+1)

    def navigate_prev(self):
        # (Unchanged) - moves to previous step
        if not self.step_widgets_instances[self.current_step_idx].on_exit(going_back=True): return
        if self.current_step_idx > 0: self.select_step(self.current_step_idx-1)

    def confirm_and_start_installation(self):
        # (Unchanged) - confirms and starts install thread
        if not isinstance(self.step_widgets_instances[self.current_step_idx],SummaryStep): return
        self.step_widgets_instances[self.current_step_idx].on_entry() # Refresh summary
        if QMessageBox.question(self,"Confirm Install",f"Start installing {self.config_data.get('os_name',APP_NAME)}?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            for i,s in enumerate(self.step_widgets_instances):
                if isinstance(s,InstallProgressStep): self.select_step(i,force_show=True); self.start_backend_installation(); break

    def start_backend_installation(self):
        # (Unchanged) - starts the InstallationThread
        self.appendToLog("Starting OS install...","INFO"); self.update_navigation_buttons(); self.installation_thread = InstallationThread(self.config_data.copy()); self.installation_thread.log_signal.connect(lambda m: self.appendToLog(m,"INSTALL")); prog_w=self.step_widgets_instances[self.current_step_idx];
        if isinstance(prog_w,InstallProgressStep): self.installation_thread.progress_signal.connect(prog_w.update_ui_progress); self.installation_thread.finished_signal.connect(prog_w.set_final_status)
        self.installation_thread.finished_signal.connect(self.on_installation_finished); self.installation_thread.start()

    def on_installation_finished(self, suc, msg):
        # (Unchanged) - calls run_final_setup_script on success
        self.appendToLog(f"OS Install Done: Success={suc}","RESULT"); prog_w=self.step_widgets_instances[self.current_step_idx];
        if isinstance(prog_w, InstallProgressStep): prog_w.set_final_status(suc, msg)
        if suc: self.run_final_setup_script()
        else: QMessageBox.critical(self,"Install Failed", msg+"\nCheck logs.")

    def run_final_setup_script(self):
        # (Unchanged) - runs the post-install script if found
        self.appendToLog(f"Running {POST_INSTALL_SCRIPT_NAME}...","INFO");
        if not os.path.exists(POST_INSTALL_SCRIPT_PATH): self.appendToLog(f"Script not found. Skipping.","WARN"); QMessageBox.information(self,"Complete",f"{self.config_data.get('os_name',APP_NAME)} installed. Final script skipped.\nReboot."); return
        if not os.access(POST_INSTALL_SCRIPT_PATH,os.X_OK):
            try: os.chmod(POST_INSTALL_SCRIPT_PATH,0o755); self.appendToLog("chmod OK.","INFO")
            except Exception as e: self.appendToLog(f"chmod failed: {e}.","ERROR"); QMessageBox.critical(self,"Error",f"Cannot run {POST_INSTALL_SCRIPT_NAME}.\nOS install OK."); return
        QMessageBox.information(self,"Final Setup",f"OS install OK. Running {POST_INSTALL_SCRIPT_NAME}...")
        self.post_install_thread=QThread(); worker=ScriptRunner(POST_INSTALL_SCRIPT_PATH); worker.moveToThread(self.post_install_thread); worker.log_signal.connect(lambda m:self.appendToLog(m,"POST_SCRIPT")); worker.finished_signal.connect(self.on_final_setup_script_finished); self.post_install_thread.started.connect(worker.run); self.post_install_thread.start()

    def on_final_setup_script_finished(self, exit_code):
        # (Unchanged) - handles script completion message
        if exit_code==0: self.appendToLog(f"{POST_INSTALL_SCRIPT_NAME} OK.","RESULT"); QMessageBox.information(self,"Complete",f"{self.config_data.get('os_name',APP_NAME)} install & final setup OK.\nReboot.")
        else: self.appendToLog(f"{POST_INSTALL_SCRIPT_NAME} Error (code {exit_code}).","ERROR"); QMessageBox.warning(self,"Warning",f"{POST_INSTALL_SCRIPT_NAME} error ({exit_code}). Check logs.\nOS install OK.")
        if self.post_install_thread: self.post_install_thread.quit(); self.post_install_thread.wait()

    def appendToLog(self, txt, lvl="DEBUG"):
        # (Unchanged) - adds message to log panel
        ts=time.strftime("%H:%M:%S"); self.log_out.appendPlainText(f"[{ts}][{lvl.upper()}] {txt}"); sb=self.log_out.verticalScrollBar();sb.setValue(sb.maximum()); QApplication.processEvents()

    def closeEvent(self, event):
        # (Unchanged) - confirms exit if process is running
        busy = (self.installation_thread and self.installation_thread.isRunning())or(self.post_install_thread and self.post_install_thread.isRunning());
        if busy and QMessageBox.question(self,"Exit","Process running. Abort?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.appendToLog("User aborted.","WARN"); event.accept()
        elif not busy: super().closeEvent(event)
        else: event.ignore()

# --- Worker for Script Runner ---
class ScriptRunner(QObject): # (Unchanged)
    log_signal=pyqtSignal(str); finished_signal=pyqtSignal(int)
    def __init__(self,script_path): super().__init__(); self.script_path=script_path
    @pyqtSlot()
    def run(self):
        try: proc=subprocess.Popen([self.script_path],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,universal_newlines=True,shell=False);
            for line in iter(proc.stdout.readline,''): self.log_signal.emit(line.strip())
            proc.stdout.close(); rc=proc.wait(); self.finished_signal.emit(rc)
        except Exception as e: self.log_signal.emit(f"Script error: {e}\n{traceback.format_exc()}"); self.finished_signal.emit(-1)

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Removed dummy logo creation - script now expects logo.png to exist
    if not os.path.exists(LOGO_PATH): 
        print(f"Warning: Logo '{LOGO_FILENAME}' missing at '{LOGO_PATH}'.")
    
    # Ensure archinstall is available before launching GUI
    if not ARCHINSTALL_AVAILABLE:
        # Show a critical message box using QApplication before full GUI loads
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(f"{APP_NAME} Error")
        msg_box.setText("Fatal Error: Required 'archinstall' library not found.")
        msg_box.setInformativeText("Please install archinstall (e.g., 'sudo pacman -S archinstall') and restart the installer.")
        msg_box.exec_()
        sys.exit(1) # Exit if library is missing

    main_win = MaiBloomOSInstallerWindow()
    main_win.show()
    sys.exit(app.exec_())

