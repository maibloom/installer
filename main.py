#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import subprocess
import traceback

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSplitter,
    QStackedWidget, QPlainTextEdit, QPushButton, QMessageBox, QFrame,
    QComboBox, QLineEdit, QCheckBox, QProgressBar
)
from PyQt5.QtGui import QIcon, QFontDatabase, QFont, QPixmap, QPainter, QImageWriter
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# --- Configuration ---
APP_NAME = "Mai Bloom OS Installer"
LOGO_FILENAME = "logo.png"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) # Use abspath for robustness
LOGO_PATH = os.path.join(SCRIPT_DIR, LOGO_FILENAME)
POST_INSTALL_SCRIPT_NAME = "final_setup.sh" # User-provided script
POST_INSTALL_SCRIPT_PATH = os.path.join(SCRIPT_DIR, POST_INSTALL_SCRIPT_NAME)


DEFAULT_CONFIG = {
    'os_name': 'Mai Bloom OS',
    'locale': 'en_US.UTF-8',
    'keyboard_layout': 'us',
    'disk_target': '',
    'disk_scheme': 'guided',
    'disk_filesystem': 'ext4',
    'disk_encrypt': False,
    'hostname': 'maibloom-pc',
    'username': '',
    'user_sudo': True,
    'profile_name': 'Desktop (KDE Plasma)',
    'timezone_region': 'Asia',
    'timezone_city': 'Tehran',
    'mirror_region_display_name': 'Worldwide',
    'mirror_region_code': 'Worldwide',
    'root_password': '',
    'user_password': ''
}

# --- Utility Functions ---
def get_keyboard_layouts(): return ["us", "uk", "de", "fr", "es", "ir", "fa"]
def get_locales(): return ["en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fa_IR.UTF-8"]

def get_block_devices_info():
    devices = []
    try:
        result = subprocess.run(
            ['lsblk', '-bndo', 'NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL'],
            capture_output=True, text=True, check=False, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            if not line.strip(): continue
            parts = [p.strip() for p in line.strip().split(None, 5)]
            if len(parts) < 3: continue
            name, size_str, type_ = parts[0], parts[1], parts[2]
            mountpoint = parts[3] if len(parts) > 3 and parts[3] != 'None' else None
            fstype = parts[4] if len(parts) > 4 and parts[4] != 'None' else None
            label = parts[5] if len(parts) > 5 and parts[5] != 'None' else None
            if type_ == 'disk':
                try: size_bytes = int(size_str)
                except ValueError: size_bytes = 0
                devices.append({
                    'name': f"/dev/{name}", 'size': size_bytes, 'type': type_,
                    'mountpoint': mountpoint, 'fstype': fstype, 'label': label,
                    'error': 'Unknown size' if size_bytes == 0 and "GiB" not in size_str and "MiB" not in size_str else None
                })
    except Exception as e: print(f"lsblk error: {e}")
    if not devices:
        return [
            {'name': "/dev/sda", 'size': 500 * 1024**3, 'type': 'disk', 'label': 'Mock Disk 1 (500GB)'},
            {'name': "/dev/sdb", 'size': 1000 * 1024**3, 'type': 'disk', 'label': 'Mock Disk 2 (1TB)'}
        ]
    return devices

def get_mirror_regions(): return {"Worldwide": "Worldwide", "Iran": "IR", "Germany": "DE", "United States": "US"}
def get_timezones(): return {"Asia": ["Tehran", "Kolkata", "Tokyo"], "Europe": ["Berlin", "London", "Paris"], "America": ["New_York", "Los_Angeles"]}
def get_profiles():
    return [
        {"name": "Minimal", "description": "A very basic command-line system, ideal for servers or custom builds."},
        {"name": "Desktop (KDE Plasma)", "description": "A feature-rich and customizable KDE Plasma desktop environment."},
        {"name": "Desktop (GNOME)", "description": "A modern and user-friendly GNOME desktop environment."},
    ]

# --- Installation Thread ---
class InstallationThread(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def run(self):
        self.log_signal.emit("Installation thread started.")
        log_cfg = {k:v for k,v in self.config.items() if "pass" not in k.lower()}
        self.log_signal.emit(f"Config (secrets redacted): {log_cfg}")
        self.progress_signal.emit(0, "Preparing...")
        try:
            os_name = self.config.get('os_name', 'Mai Bloom OS')
            mock_steps = [ (5, "Initializing hardware..."), (10, "Checking disk prerequisites..."),
                (20, "Partitioning selected disk..."), (30, "Formatting partitions..."),
                (40, "Mounting filesystems..."),(50, f"Fetching packages for {os_name}..."),
                (65, "Installing base system..."),(75, "Configuring system (locale, time, hostname)..."),
                (85, "Setting up users and permissions..."),(90, f"Installing bootloader ({self.config.get('bootloader', 'GRUB')})..."),
                (95, f"Installing profile: {self.config.get('profile_name', 'Minimal')}..."),
                (100, "Finalizing installation setup...") ]
            for percent, task in mock_steps:
                self.log_signal.emit(task)
                self.progress_signal.emit(percent, task)
                time.sleep(0.8) # Simulate work

            self.log_signal.emit("OS installation phase completed successfully (simulated).")
            self.finished_signal.emit(True, f"{os_name} core installation phase complete (simulated).")
        except Exception as e:
            self.log_signal.emit(f"ERROR: {str(e)}\n{traceback.format_exc()}")
            self.finished_signal.emit(False, f"Installation failed: {str(e)}")

# --- Step Widget Base Class ---
class StepWidget(QWidget):
    def __init__(self, title, config_ref, main_window_ref):
        super().__init__()
        self.title = title
        self.config = config_ref
        self.main_window = main_window_ref
        self.outer_layout = QVBoxLayout(self)
        self.outer_layout.setContentsMargins(25, 20, 25, 20) # More padding
        self.content_layout = QVBoxLayout()
        self.content_layout.setSpacing(15) # More spacing
        title_label = QLabel(f"<b>{title}</b>")
        font = title_label.font(); font.setPointSize(16); title_label.setFont(font) # Larger title
        title_label.setStyleSheet("margin-bottom: 15px; color: #E0E0E0;") # Light title color
        self.outer_layout.addWidget(title_label)
        self.outer_layout.addLayout(self.content_layout)
        self.outer_layout.addStretch(1)

    def get_title(self): return self.title
    def load_ui_from_config(self): pass
    def save_config_from_ui(self): return True
    def on_entry(self): pass
    def on_exit(self, going_back=False): return True

# --- Concrete Step Widgets (More focused, more explanations) ---
class WelcomeStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("Welcome", config, main_ref)
        # APP_NAME is global
        welcome_text = (
            f"<h2>Welcome to the {APP_NAME}!</h2>"
            "<p>This installer will guide you through setting up Mai Bloom OS on your computer. "
            "We'll configure a few essential settings step-by-step.</p>"
            "<h3>Before you begin:</h3>"
            "<ul>"
            "<li>Ensure your computer is connected to the <b>internet</b> (recommended for fetching the latest software and profiles).</li>"
            "<li><b>Back up any important data!</b> The installation process, especially disk partitioning, can lead to data loss if not handled carefully.</li>"
            "<li>This installer will help you prepare your disk, but if you have a complex existing setup, you might need manual partitioning beforehand.</li>"
            "</ul>"
            "<p>Click 'Next' to start the configuration process.</p>"
        )
        info_label = QLabel(welcome_text)
        info_label.setWordWrap(True)
        info_label.setTextFormat(Qt.RichText) # Allow HTML for better formatting
        self.content_layout.addWidget(info_label)

# Example of breaking down a step: Language & Keyboard could be two separate steps
class LanguageStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("System Language", config, main_ref)
        explanation = QLabel(
            "Please select the primary language for your Mai Bloom OS installation. "
            "This will determine the language used for system messages, menus, and applications "
            "that support localization."
        )
        explanation.setWordWrap(True)
        self.content_layout.addWidget(explanation)
        self.content_layout.addWidget(QLabel("<b>System Language (Locale):</b>"))
        self.locale_combo = QComboBox()
        self.locale_combo.addItems(get_locales())
        self.locale_combo.setToolTip("Controls language, number formats, date/time formats, etc.")
        self.content_layout.addWidget(self.locale_combo)

    def load_ui_from_config(self):
        self.locale_combo.setCurrentText(self.config.get('locale', DEFAULT_CONFIG['locale']))
    def save_config_from_ui(self):
        self.config['locale'] = self.locale_combo.currentText()
        if not self.config['locale']:
            QMessageBox.warning(self, "Selection Missing", "Please select a system language/locale.")
            return False
        return True

class KeyboardStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("Keyboard Layout", config, main_ref)
        explanation = QLabel(
            "Choose the keyboard layout that matches your physical keyboard. "
            "This ensures that keys produce the expected characters, which is crucial for typing "
            "passwords and commands correctly."
        )
        explanation.setWordWrap(True)
        self.content_layout.addWidget(explanation)
        self.content_layout.addWidget(QLabel("<b>Keyboard Layout:</b>"))
        self.kb_layout_combo = QComboBox()
        self.kb_layout_combo.addItems(get_keyboard_layouts())
        self.kb_layout_combo.setToolTip("Select the layout corresponding to your keyboard hardware.")
        self.content_layout.addWidget(self.kb_layout_combo)

    def load_ui_from_config(self):
        self.kb_layout_combo.setCurrentText(self.config.get('keyboard_layout', DEFAULT_CONFIG['keyboard_layout']))
    def save_config_from_ui(self):
        self.config['keyboard_layout'] = self.kb_layout_combo.currentText()
        if not self.config['keyboard_layout']:
            QMessageBox.warning(self, "Selection Missing", "Please select a keyboard layout.")
            return False
        return True

# (Other step classes would be similarly refactored and defined here)
# MirrorRegionStep, SelectDiskStep, PartitionSchemeStep, FilesystemEncryptionStep,
# RootPasswordStep, CreateUserStep, TimezoneStep, ProfileSelectionStep, SummaryStep, InstallProgressStep
# For brevity, I'm not rewriting all of them but the principle is:
# 1. More descriptive text using QLabels.
# 2. Fewer options per slide if a step was too dense.

# Placeholder for other steps (you would implement these based on the previous versions,
# breaking them down and adding more explanation)
class SelectDiskStep(StepWidget): # Example
    def __init__(self, config, main_ref):
        super().__init__("Select Target Disk", config, main_ref)
        expl = QLabel("Choose the physical disk drive where Mai Bloom OS will be installed. "
                      "<b>All data on the chosen disk might be erased depending on the next steps.</b> "
                      "Ensure you select the correct one.")
        expl.setWordWrap(True); self.content_layout.addWidget(expl)
        self.disk_combo = QComboBox(); self.content_layout.addWidget(self.disk_combo)
        self.disk_info_label = QLabel("Disk details..."); self.content_layout.addWidget(self.disk_info_label)
        self.devices_data = []
    def on_entry(self): self.populate_disk_list()
    def populate_disk_list(self):
        # ... (similar to previous DiskSetupStep's populate_disk_list) ...
        current_selection_name = self.config.get('disk_target')
        self.disk_combo.clear(); self.devices_data = get_block_devices_info()
        if not self.devices_data:
            self.disk_combo.addItem("No suitable disks found."); self.disk_combo.setEnabled(False); self.disk_info_label.setText("No disks available.")
            return
        self.disk_combo.setEnabled(True); selected_idx = 0
        for i, dev in enumerate(self.devices_data):
            size_gb = dev.get('size',0) / (1024**3) if dev.get('size',0) > 0 else 0
            label = f" ({dev.get('label', '')})" if dev.get('label') else ""
            self.disk_combo.addItem(f"{dev['name']}{label} ({size_gb:.1f} GB)", userData=dev['name'])
            if dev['name'] == current_selection_name: selected_idx = i
        if self.disk_combo.count() > 0: self.disk_combo.setCurrentIndex(selected_idx)
        self.update_disk_info_display(self.disk_combo.currentIndex())
    def update_disk_info_display(self, index):
        # ... (similar to previous DiskSetupStep's update_disk_info_display) ...
        if index < 0 or not self.devices_data or index >= len(self.devices_data):
            self.disk_info_label.setText("No disk selected."); return
        selected_dev_name = self.disk_combo.itemData(index)
        dev_data = next((d for d in self.devices_data if d['name'] == selected_dev_name), None)
        if not dev_data: self.disk_info_label.setText(f"Details for {selected_dev_name} not found."); return
        size_gb = dev_data.get('size',0) / (1024**3) if dev_data.get('size',0) > 0 else 0
        info = [f"<b>Path:</b> {dev_data['name']}", f"<b>Size:</b> {size_gb:.1f} GB"]
        self.disk_info_label.setText("<br>".join(info))

    def load_ui_from_config(self): self.populate_disk_list()
    def save_config_from_ui(self):
        if self.disk_combo.currentIndex() < 0 or not self.disk_combo.currentData():
            QMessageBox.warning(self, "Disk Error", "Please select a target disk."); return False
        self.config['disk_target'] = self.disk_combo.currentData()
        return True

# --- Summary Step --- (largely the same, but good to have)
class SummaryStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("Installation Summary", config, main_ref)
        self.summary_text_edit = QPlainTextEdit()
        self.summary_text_edit.setReadOnly(True)
        self.summary_text_edit.setStyleSheet("font-family: 'monospace'; font-size: 9pt; color: #E0E0E0; background-color: #2E2E2E;")
        
        expl_label = QLabel(
            "You are about to install Mai Bloom OS with the following settings. "
            "Please review them carefully. <b style='color:yellow;'>Once you click 'Install', the process will begin and may erase data on the selected disk.</b>"
        )
        expl_label.setWordWrap(True)
        expl_label.setTextFormat(Qt.RichText)
        self.content_layout.addWidget(expl_label)
        self.content_layout.addWidget(self.summary_text_edit)

    def on_entry(self): # Refresh summary when step is shown
        summary_lines = [f"--- {self.config.get('os_name', APP_NAME)} Configuration Summary ---"]
        key_order_and_names = {
            'locale': "Locale", 'keyboard_layout': "Keyboard", 'mirror_region_display_name': "Mirror Region",
            'disk_target': "Target Disk", 'disk_scheme': "Partitioning", 'disk_filesystem': "Root FS", 'disk_encrypt': "Encryption",
            'hostname': "Hostname", 'root_password': "Root Password",
            'username': "Username", 'user_password': "User Password", 'user_sudo': "User Sudo",
            'timezone': "Timezone", 'profile_name': "Profile", 'additional_packages': "Extra Packages",
        }
        for k, name in key_order_and_names.items():
            v = self.config.get(k)
            if k.endswith("password") and v: v = "<set>"
            elif isinstance(v, bool): v = "Yes" if v else "No"
            elif isinstance(v, list): v = ", ".join(v) if v else "<none>"
            elif v is None or str(v).strip() == "": v = "<not set>"
            if k == 'username' and v == "<not set>": name = "New User"; v = "Skipped"
            summary_lines.append(f"{name:<25}: {v}")
        if not self.config.get('username') and "New Username" not in [val for key, val in key_order_and_names.items() if key=='username']:
             summary_lines.append(f"{'New User Creation':<25}: Skipped")
        summary_lines.append(f"\n--- Target Disk: {self.config.get('disk_target', '<NO DISK SELECTED>')} ---")
        self.summary_text_edit.setPlainText("\n".join(summary_lines))

# --- InstallProgressStep --- (largely the same)
class InstallProgressStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("Installation Progress", config, main_ref)
        self.status_label = QLabel("Installation starting..."); font = self.status_label.font(); font.setPointSize(12); self.status_label.setFont(font); self.status_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar(); self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0); self.progress_bar.setTextVisible(True); self.progress_bar.setFormat("Waiting... %p%")
        self.content_layout.addWidget(self.progress_bar)

    def update_ui_progress(self, val, task):
        self.progress_bar.setValue(val); self.progress_bar.setFormat(f"{task} - %p%")
        self.status_label.setText(f"Task: {task}")
        if val == 100 and "complete" not in task.lower() and "success" not in task.lower(): self.status_label.setText(f"{task} (Finalizing...)")
    def set_final_status(self, suc, msg):
        self.progress_bar.setValue(100); self.progress_bar.setFormat(msg.split('\n')[0] if suc else "Error - Check Logs")
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {'#4CAF50' if suc else '#F44336'}; font-weight: bold;") # Green/Red


# --- Main Application Window ---
class MaiBloomOSInstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_data = DEFAULT_CONFIG.copy()
        self.current_step_idx = -1
        self.installation_thread = None
        self.post_install_thread = None # For the .sh script
        self.step_widgets_instances = []
        self.init_ui()
        self.populate_steps()
        if self.step_widgets_instances:
            self.select_step(0, force_show=True)

    def init_ui(self):
        self.setWindowTitle(APP_NAME)
        if os.path.exists(LOGO_PATH): self.setWindowIcon(QIcon(LOGO_PATH))
        self.setMinimumSize(1100, 700) # Adjusted for side terminal

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal splitter for Config Area | Terminal Log
        main_splitter = QSplitter(Qt.Horizontal, central_widget)
        
        # Left Pane: Config Area + Navigation Buttons
        self.config_area_widget = QWidget()
        config_area_layout = QVBoxLayout(self.config_area_widget)
        config_area_layout.setContentsMargins(0,0,0,0) # No margins for the container

        self.config_stack_widget = QStackedWidget()
        config_area_layout.addWidget(self.config_stack_widget, 1) # Stacked widget takes most space

        nav_buttons_layout = QHBoxLayout()
        nav_buttons_layout.setContentsMargins(10, 5, 10, 10) # Padding for buttons
        self.prev_button = QPushButton("⬅ Previous")
        self.prev_button.clicked.connect(self.navigate_prev)
        self.next_button = QPushButton("Next ➡")
        self.next_button.clicked.connect(self.navigate_next)
        self.install_button = QPushButton(f"🚀 Install {self.config_data.get('os_name', 'Mai Bloom OS')}")
        self.install_button.clicked.connect(self.confirm_and_start_installation)
        
        nav_buttons_layout.addStretch(1)
        nav_buttons_layout.addWidget(self.prev_button)
        nav_buttons_layout.addWidget(self.next_button)
        nav_buttons_layout.addWidget(self.install_button)
        config_area_layout.addLayout(nav_buttons_layout)
        
        main_splitter.addWidget(self.config_area_widget)

        # Right Pane: Terminal Log Output
        self.log_output_edit = QPlainTextEdit()
        self.log_output_edit.setReadOnly(True)
        log_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        log_font.setPointSize(9)
        self.log_output_edit.setFont(log_font)
        main_splitter.addWidget(self.log_output_edit)
        
        main_splitter.setSizes([650, 450]) # Initial sizes for config area | log
        main_splitter.setStretchFactor(0, 2) # Config area takes more relative space
        main_splitter.setStretchFactor(1, 1) # Log area takes less

        # Set main_splitter as the central layout for central_widget
        outer_layout = QHBoxLayout(central_widget) # Use QHBoxLayout for the splitter
        outer_layout.addWidget(main_splitter)
        central_widget.setLayout(outer_layout)


        self.appendToLog(f"{APP_NAME} started. Welcome!", "INFO")
        self.apply_dark_theme()

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { 
                font-size: 10pt; 
                background-color: #2E2E2E; /* Dark grey background */
                color: #E0E0E0; /* Light grey text */
            }
            QStackedWidget > QWidget { /* Ensure step widgets also get dark background */
                background-color: #2E2E2E;
            }
            /* Specific styling for labels within StepWidget's content_layout if needed */
            StepWidget QLabel { color: #E0E0E0; }
            StepWidget > QLabel { /* The main title label of a step */
                 color: #00A0E0; /* A distinct light blue for step titles */
            }
            QPushButton { 
                padding: 9px 18px; border-radius: 5px; 
                background-color: #555555; /* Medium grey buttons */
                color: #FFFFFF; border: 1px solid #686868; 
                font-weight: bold;
            }
            QPushButton:hover { background-color: #686868; }
            QPushButton:disabled { background-color: #404040; color: #808080; border-color: #505050; }
            QPushButton#InstallButton { background-color: #4CAF50; border-color: #388E3C; } /* Green */
            QPushButton#InstallButton:hover { background-color: #388E3C; }
            
            QPlainTextEdit#LogOutput { 
                background-color: #1C1C1C; /* Even darker for log */
                color: #C0C0C0; /* Lighter grey text for log */
                border: 1px solid #434343;
                font-family: "Monospace", "Courier New", "Courier", monospace;
            }
            QLineEdit, QComboBox { 
                padding: 6px 8px; border: 1px solid #555555; 
                border-radius: 4px; background-color: #3D3D3D; color: #E0E0E0;
            }
            QComboBox::drop-down { border: none; background-color: #4A4A4A; }
            QComboBox QAbstractItemView { /* Dropdown list style */
                background-color: #3D3D3D; color: #E0E0E0; selection-background-color: #007BFF;
            }
            QCheckBox { margin-top: 5px; margin-bottom: 5px; color: #E0E0E0; }
            QCheckBox::indicator { width: 16px; height: 16px; background-color: #555; border: 1px solid #686868; border-radius: 3px;}
            QCheckBox::indicator:checked { background-color: #007BFF; }

            QProgressBar { 
                text-align: center; padding: 1px; border-radius: 5px; 
                background-color: #555555; border: 1px solid #686868; 
                color: #E0E0E0; min-height: 20px;
            }
            QProgressBar::chunk { background-color: #007BFF; border-radius: 4px; }
            QSplitter::handle { background-color: #4A4A4A; } 
            QSplitter::handle:horizontal { width: 3px; }
        """)
        self.log_output_edit.setObjectName("LogOutput")
        self.install_button.setObjectName("InstallButton")


    def populate_steps(self):
        # More focused steps as per request 3 & 4
        self.step_definitions = [
            WelcomeStep,
            LanguageStep,         # Split from LanguageKeyboardStep
            KeyboardStep,         # Split from LanguageKeyboardStep
            MirrorRegionStep,
            SelectDiskStep,       # Split from DiskSetupStep
            # PartitionSchemeStep,  # TODO: Implement (for guided vs manual choice)
            # FilesystemEncryptionStep, # TODO: Implement (options for chosen scheme)
            UserAccountsStep,     # This itself could be "RootPasswordStep", then "CreateUserStep"
            TimezoneStep,
            ProfileSelectionStep,
            SummaryStep,
            InstallProgressStep
        ]
        self.step_widgets_instances = []
        for i, StepClass in enumerate(self.step_definitions):
            inst = StepClass(self.config_data, self)
            self.step_widgets_instances.append(inst)
            self.config_stack_widget.addWidget(inst)
            # No QListWidget for steps anymore

    def select_step(self, index, force_show=False): # Renamed from select_step_in_list
        if not (0 <= index < len(self.step_widgets_instances)): return

        is_target_install = isinstance(self.step_widgets_instances[index], InstallProgressStep)
        is_curr_summ = self.current_step_idx >=0 and isinstance(self.step_widgets_instances[self.current_step_idx], SummaryStep)
        
        if is_target_install and not is_curr_summ and not force_show:
             return # Don't jump to install unless from summary or forced

        self.current_step_idx = index
        self.config_stack_widget.setCurrentIndex(index)
        
        curr_widget = self.step_widgets_instances[index]
        curr_widget.load_ui_from_config()
        curr_widget.on_entry()
        self.update_navigation_buttons()

    def update_navigation_buttons(self):
        is_first = (self.current_step_idx == 0)
        if not (0 <= self.current_step_idx < len(self.step_widgets_instances)):
            self.prev_button.setEnabled(False); self.next_button.setVisible(False); self.install_button.setVisible(False)
            return
        curr_w = self.step_widgets_instances[self.current_step_idx]
        is_summ = isinstance(curr_w, SummaryStep); is_inst = isinstance(curr_w, InstallProgressStep)
        
        self.prev_button.setEnabled(not is_first and not is_inst)
        self.next_button.setVisible(not is_summ and not is_inst)
        self.install_button.setVisible(is_summ and not is_inst)
        if is_inst: # Disable all nav if on install progress
            self.prev_button.setEnabled(False)
            self.next_button.setVisible(False)
            self.install_button.setVisible(False)

    def navigate_next(self):
        curr_w = self.step_widgets_instances[self.current_step_idx]
        if not curr_w.on_exit() or not curr_w.save_config_from_ui(): return
        if self.current_step_idx < len(self.step_widgets_instances) - 1:
            self.select_step(self.current_step_idx + 1)

    def navigate_prev(self):
        curr_w = self.step_widgets_instances[self.current_step_idx]
        if not curr_w.on_exit(going_back=True): return
        if self.current_step_idx > 0:
            self.select_step(self.current_step_idx - 1)

    def confirm_and_start_installation(self):
        curr_w = self.step_widgets_instances[self.current_step_idx]
        if not isinstance(curr_w, SummaryStep): return
        curr_w.on_entry()
        reply = QMessageBox.question(self, "Confirm Installation", f"Review summary. Start installing {self.config_data.get('os_name', APP_NAME)}?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            for i, step in enumerate(self.step_widgets_instances):
                if isinstance(step, InstallProgressStep):
                    self.select_step(i, force_show=True)
                    self.start_backend_installation()
                    break

    def start_backend_installation(self):
        self.appendToLog("Starting OS installation process...", "INFO")
        self.update_navigation_buttons()
        self.installation_thread = InstallationThread(self.config_data.copy())
        self.installation_thread.log_signal.connect(lambda msg: self.appendToLog(msg, "INSTALL"))
        prog_w = self.step_widgets_instances[self.current_step_idx]
        if isinstance(prog_w, InstallProgressStep):
             self.installation_thread.progress_signal.connect(prog_w.update_ui_progress)
             self.installation_thread.finished_signal.connect(prog_w.set_final_status)
        self.installation_thread.finished_signal.connect(self.on_installation_finished)
        self.installation_thread.start()

    def on_installation_finished(self, success, message):
        self.appendToLog(f"OS Installation Finished: Success={success}, Message='{message}'", "RESULT")
        prog_w = self.step_widgets_instances[self.current_step_idx]
        if isinstance(prog_w, InstallProgressStep): # Update final status on progress page
            prog_w.set_final_status(success, message)

        if success:
            # Run post-installation script
            self.run_final_setup_script() # This will handle its own messages
            # Final message after post-install script is also handled within that function
        else:
            QMessageBox.critical(self, "Installation Failed", message + "\n\nPlease check the logs for details.")
        # Nav buttons remain disabled, user should reboot or close.

    def run_final_setup_script(self):
        self.appendToLog(f"Attempting to run final setup script: {POST_INSTALL_SCRIPT_NAME}", "INFO")
        if not os.path.exists(POST_INSTALL_SCRIPT_PATH):
            self.appendToLog(f"Script '{POST_INSTALL_SCRIPT_NAME}' not found at '{POST_INSTALL_SCRIPT_PATH}'. Skipping.", "WARN")
            QMessageBox.information(self, "Installation Complete",
                                    f"{self.config_data.get('os_name', APP_NAME)} installed successfully.\n"
                                    f"Final setup script '{POST_INSTALL_SCRIPT_NAME}' was not found and was skipped.\n\n"
                                    "You may now reboot your system.")
            return

        if not os.access(POST_INSTALL_SCRIPT_PATH, os.X_OK):
            self.appendToLog(f"Script '{POST_INSTALL_SCRIPT_NAME}' is not executable. Attempting to make it executable.", "WARN")
            try:
                os.chmod(POST_INSTALL_SCRIPT_PATH, 0o755) # rwxr-xr-x
                self.appendToLog(f"Made '{POST_INSTALL_SCRIPT_NAME}' executable.", "INFO")
            except Exception as e:
                self.appendToLog(f"Failed to make script executable: {e}. Cannot run.", "ERROR")
                QMessageBox.critical(self, "Final Setup Script Error",
                                     f"Could not make '{POST_INSTALL_SCRIPT_NAME}' executable.\n"
                                     "Please check permissions or run it manually after reboot.\n"
                                     f"{self.config_data.get('os_name', APP_NAME)} core installation was successful.")
                return

        self.appendToLog(f"Executing: {POST_INSTALL_SCRIPT_PATH} (This may require privileges if the script uses sudo internally)", "INFO")
        QMessageBox.information(self, "Final Setup", f"The OS installation is complete. Now, a final setup script ('{POST_INSTALL_SCRIPT_NAME}') will be executed for pre-reboot configurations. Its output will appear in the terminal log.")
        
        # Run in a new thread to keep GUI responsive and stream output
        self.post_install_thread = QThread() # Generic QThread
        worker = ScriptRunner(POST_INSTALL_SCRIPT_PATH) # Worker object
        worker.moveToThread(self.post_install_thread)

        worker.log_signal.connect(lambda msg: self.appendToLog(msg, "POST_SCRIPT"))
        worker.finished_signal.connect(self.on_final_setup_script_finished)
        
        self.post_install_thread.started.connect(worker.run)
        self.post_install_thread.start()

    def on_final_setup_script_finished(self, exit_code):
        if exit_code == 0:
            self.appendToLog(f"Final setup script '{POST_INSTALL_SCRIPT_NAME}' completed successfully.", "RESULT")
            QMessageBox.information(self, "Setup Complete",
                                    f"{self.config_data.get('os_name', APP_NAME)} installed and final setup script completed.\n\n"
                                    "You may now reboot your system.")
        else:
            self.appendToLog(f"Final setup script '{POST_INSTALL_SCRIPT_NAME}' finished with error code {exit_code}.", "ERROR")
            QMessageBox.warning(self, "Final Setup Script Issue",
                                 f"The final setup script '{POST_INSTALL_SCRIPT_NAME}' finished with an error (code: {exit_code}).\n"
                                 "Please check the logs. The main OS installation was successful.\n\n"
                                 "You may need to address these issues manually after rebooting.")
        if self.post_install_thread:
            self.post_install_thread.quit()
            self.post_install_thread.wait()


    def appendToLog(self, txt, lvl="DEBUG"):
        ts = time.strftime("%H:%M:%S", time.localtime())
        self.log_output_edit.appendPlainText(f"[{ts}][{lvl.upper()}] {txt}")
        sb = self.log_output_edit.verticalScrollBar(); sb.setValue(sb.maximum())
        if lvl.upper() in ["ERROR", "FATAL", "RESULT", "WARN", "INFO", "POST_SCRIPT"]: QApplication.processEvents()

    def closeEvent(self, event):
        # Check both installation and post-install threads
        if (self.installation_thread and self.installation_thread.isRunning()) or \
           (self.post_install_thread and self.post_install_thread.isRunning()):
            if QMessageBox.question(self, "Exit", "A setup process is running. Abort?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                self.appendToLog("User aborted during a running process.", "WARN")
                # Add logic to attempt to stop threads if possible/safe
                event.accept()
            else: event.ignore()
        else: super().closeEvent(event)

# Worker for running the post-install script in a thread
class ScriptRunner(QObject): # QObject for signals/slots
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int) # exit_code

    def __init__(self, script_path):
        super().__init__()
        self.script_path = script_path

    @pyqtSlot() # Make it a slot
    def run(self):
        try:
            process = subprocess.Popen([self.script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            for line in iter(process.stdout.readline, ''):
                self.log_signal.emit(line.strip())
            process.stdout.close()
            return_code = process.wait()
            self.finished_signal.emit(return_code)
        except Exception as e:
            self.log_signal.emit(f"Error running script {self.script_path}: {e}")
            self.log_signal.emit(traceback.format_exc())
            self.finished_signal.emit(-1) # Indicate an exception occurred


# --- Main Execution Block ---
def create_dummy_logo_if_missing():
    if not os.path.exists(LOGO_PATH):
        print(f"Warning: Logo '{LOGO_PATH}' not found. Creating dummy.")
        try:
            pixmap = QPixmap(128, 128); fill_color = QColor("#1A1A2E"); pixmap.fill(fill_color) # Dark blueish
            painter = QPainter(pixmap); font = QFont("Arial", 60, QFont.Bold); painter.setFont(font)
            pen_color = QColor("#E0E0E0"); painter.setPen(pen_color)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "MB"); painter.end()
            if not pixmap.save(LOGO_PATH): print(f"Failed to save dummy logo at {LOGO_PATH}.")
            else: print(f"Created dummy logo at {LOGO_PATH}")
        except Exception as e: print(f"Could not create dummy logo: {e}.")


if __name__ == '__main__':
    # Import QColor and QObject if not already at the top
    from PyQt5.QtGui import QColor 
    from PyQt5.QtCore import QObject, pyqtSlot 

    app = QApplication(sys.argv)
    create_dummy_logo_if_missing()
    main_win = MaiBloomOSInstallerWindow()
    main_win.show()
    sys.exit(app.exec_())
