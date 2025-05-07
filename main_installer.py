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
    QComboBox, QLineEdit, QCheckBox, QGridLayout # Import QGridLayout
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
    'profile_name': 'Desktop (KDE Plasma)', 'app_categories': [], # New config item
    'timezone_region': 'Asia', 'timezone_city': 'Tehran',
    'mirror_region_display_name': 'Worldwide', 'mirror_region_code': 'Worldwide',
    'root_password': '', 'user_password': ''
}

# --- Stylesheet Constant ---
DARK_THEME_QSS = """
    QMainWindow, QWidget { font-size: 10pt; background-color: #2E2E2E; color: #E0E0E0; }
    QStackedWidget > QWidget { background-color: #2E2E2E; }
    StepWidget QLabel { color: #E0E0E0; } 
    StepWidget QCheckBox { font-size: 11pt; padding: 3px; } /* Style for checkboxes in steps */
    QPushButton { padding: 9px 18px; border-radius: 5px; background-color: #555555; color: #FFFFFF; border: 1px solid #686868; font-weight: bold; }
    QPushButton:hover { background-color: #686868; }
    QPushButton:disabled { background-color: #404040; color: #808080; border-color: #505050; }
    QPushButton#InstallButton { background-color: #4CAF50; border-color: #388E3C; }
    QPushButton#InstallButton:hover { background-color: #388E3C; }
    QPlainTextEdit#LogOutput { background-color: #1C1C1C; color: #C0C0C0; border: 1px solid #434343; font-family: "Monospace"; }
    QLineEdit, QComboBox { padding: 6px 8px; border: 1px solid #555555; border-radius: 4px; background-color: #3D3D3D; color: #E0E0E0; }
    QComboBox::drop-down { border: none; background-color: #4A4A4A; }
    QComboBox QAbstractItemView { background-color: #3D3D3D; color: #E0E0E0; selection-background-color: #007BFF; }
    QCheckBox { margin-top: 5px; margin-bottom: 5px; color: #E0E0E0; }
    QCheckBox::indicator { width: 18px; height: 18px; background-color: #555; border: 1px solid #686868; border-radius: 3px;}
    QCheckBox::indicator:checked { background-color: #007BFF; }
    QProgressBar { text-align: center; padding: 1px; border-radius: 5px; background-color: #555555; border: 1px solid #686868; color: #E0E0E0; min-height: 20px; }
    QProgressBar::chunk { background-color: #007BFF; border-radius: 4px; }
    QSplitter::handle { background-color: #4A4A4A; } 
    QSplitter::handle:horizontal { width: 3px; }
"""

# --- Text Constants ---
WELCOME_STEP_HTML = (f"<h2>Welcome to {APP_NAME}!</h2><p>Installer guide...</p><h3>Notes:</h3><ul><li>Internet recommended.</li><li>Backup data!</li><li>Disk operations may erase data.</li></ul><p>Next-></p>")
LANGUAGE_STEP_EXPLANATION = "Select system language (menus, messages)."
KEYBOARD_STEP_EXPLANATION = "Choose layout matching your keyboard."
SELECT_DISK_STEP_EXPLANATION = "Choose install disk.<br><b style='color:yellow;'>Data may be erased.</b>"
APP_CATEGORIES_EXPLANATION = (
    "Select application categories you're interested in. This can help tailor your initial software setup "
    "by installing relevant packages or groups of packages for your needs. You can always install more later!"
)
SUMMARY_STEP_INTRO_TEXT = "Review settings. <b style='color:yellow;'>Install button modifies disk!</b>"

# --- Utility Functions ---
def get_keyboard_layouts(): return ["us", "uk", "de", "fr", "es", "ir", "fa"]
def get_locales(): return ["en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fa_IR.UTF-8"]
def get_block_devices_info():
    devices = []
    try:
        result = subprocess.run(['lsblk','-bndo','NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,LABEL'],capture_output=True,text=True,check=False,timeout=2)
        for line in result.stdout.strip().split('\n'):
            if not line.strip(): continue
            parts = [p.strip() for p in line.strip().split(None, 5)]; L = len(parts)
            if L < 3: continue; n,s,t=parts[0],parts[1],parts[2]; mp,fs,lbl=(parts[3] if L>3 and parts[3]!='None' else None),(parts[4] if L>4 and parts[4]!='None' else None),(parts[5] if L>5 and parts[5]!='None' else None)
            if t=='disk':
                try: sz=int(s)
                except ValueError: sz=0
                devices.append({'name':f"/dev/{n}",'size':sz,'type':t,'mountpoint':mp,'fstype':fs,'label':lbl,'error':'?' if sz==0 else None})
    except Exception as e: print(f"lsblk err: {e}")
    if not devices: return [{'name':"/dev/sda",'size':500*1024**3,'type':'disk','label':'Mock A'}, {'name':"/dev/sdb",'size':1000*1024**3,'type':'disk','label':'Mock B'}]
    return devices
def get_mirror_regions(): return {"Worldwide":"WW", "Iran":"IR", "Germany":"DE", "US":"US"}
def get_timezones(): return {"Asia":["Tehran","Kolkata","Tokyo"], "Europe":["Berlin","London","Paris"], "America":["New_York","Los_Angeles"]}
def get_profiles(): return [{"name":"Minimal","description":"CLI system."},{"name":"KDE Plasma","description":"Plasma desktop."},{"name":"GNOME","description":"GNOME desktop."}]

# --- Installation Thread ---
class InstallationThread(QThread): # (Unchanged)
    log_signal = pyqtSignal(str); progress_signal = pyqtSignal(int, str); finished_signal = pyqtSignal(bool, str)
    def __init__(self, config): super().__init__(); self.config = config
    def run(self):
        self.log_signal.emit("Installation thread started.")
        log_cfg = {k:v for k,v in self.config.items() if "pass" not in k.lower()}
        self.log_signal.emit(f"Config (secrets redacted): {log_cfg}"); self.progress_signal.emit(0, "Preparing...")
        try:
            os_name = self.config.get('os_name', 'Mai Bloom OS')
            mock_steps = [(10,"Disks prep..."),(20,"Formatting..."),(30,"Mounting..."),(40,"Mirrors..."),
                          (50,f"Install {os_name} base..."),(65,"fstab..."),(75,"Sys config..."),
                          (85,"Users..."),(90,f"Bootloader ({self.config.get('bootloader','GRUB')})..."),
                          (95,f"Profile: {self.config.get('profile_name','Minimal')}..."),(100,"Finalizing...")]
            for percent, task in mock_steps: self.log_signal.emit(task); self.progress_signal.emit(percent, task); time.sleep(0.5)
            self.log_signal.emit("OS install phase done (sim)."); self.finished_signal.emit(True, f"{os_name} core install phase complete (sim).")
        except Exception as e: self.log_signal.emit(f"ERROR: {e}\n{traceback.format_exc()}"); self.finished_signal.emit(False, f"Install failed: {e}")

# --- Step Widget Base Class ---
class StepWidget(QWidget): # (Unchanged from logo addition)
    def __init__(self, title, config_ref, main_window_ref):
        super().__init__(); self.title = title; self.config = config_ref; self.main_window = main_window_ref
        self.outer_layout = QVBoxLayout(self); self.outer_layout.setContentsMargins(25, 15, 25, 15)
        title_area_layout = QHBoxLayout(); title_area_layout.setSpacing(10); title_area_layout.setContentsMargins(0, 0, 0, 5)
        self.logo_label = QLabel(); logo_pixmap = QPixmap(LOGO_PATH)
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
class WelcomeStep(StepWidget): # (Unchanged)
    def __init__(self, config, main_ref): super().__init__("Welcome", config, main_ref); info=QLabel(WELCOME_STEP_HTML);info.setWordWrap(True);info.setTextFormat(Qt.RichText);self.content_layout.addWidget(info)
class LanguageStep(StepWidget): # (Unchanged)
    def __init__(self,config,main_ref):super().__init__("System Language",config,main_ref);expl=QLabel(LANGUAGE_STEP_EXPLANATION);expl.setWordWrap(True);self.content_layout.addWidget(expl);self.content_layout.addWidget(QLabel("<b>Locale:</b>"));self.locale_combo=QComboBox();self.locale_combo.addItems(get_locales());self.locale_combo.setToolTip("Lang, formats.");self.content_layout.addWidget(self.locale_combo)
    def load_ui_from_config(self): self.locale_combo.setCurrentText(self.config.get('locale',DEFAULT_CONFIG['locale']))
    def save_config_from_ui(self): self.config['locale']=self.locale_combo.currentText(); return bool(self.config['locale'] or QMessageBox.warning(self,"","Select locale."))
class KeyboardStep(StepWidget): # (Unchanged)
    def __init__(self,config,main_ref):super().__init__("Keyboard Layout",config,main_ref);expl=QLabel(KEYBOARD_STEP_EXPLANATION);expl.setWordWrap(True);self.content_layout.addWidget(expl);self.content_layout.addWidget(QLabel("<b>Layout:</b>"));self.kb_layout_combo=QComboBox();self.kb_layout_combo.addItems(get_keyboard_layouts());self.kb_layout_combo.setToolTip("Match keyboard.");self.content_layout.addWidget(self.kb_layout_combo)
    def load_ui_from_config(self): self.kb_layout_combo.setCurrentText(self.config.get('keyboard_layout',DEFAULT_CONFIG['keyboard_layout']))
    def save_config_from_ui(self): self.config['keyboard_layout']=self.kb_layout_combo.currentText(); return bool(self.config['keyboard_layout'] or QMessageBox.warning(self,"","Select keyboard."))
class SelectDiskStep(StepWidget): # (Unchanged)
    def __init__(self,config,main_ref):super().__init__("Select Target Disk",config,main_ref);expl=QLabel(SELECT_DISK_STEP_EXPLANATION);expl.setWordWrap(True);expl.setTextFormat(Qt.RichText);self.content_layout.addWidget(expl);self.disk_combo=QComboBox();self.content_layout.addWidget(self.disk_combo);self.disk_info_label=QLabel("Disk details...");self.disk_info_label.setStyleSheet("color:#AAAAAA;");self.content_layout.addWidget(self.disk_info_label);self.devices_data=[];self.disk_combo.currentIndexChanged.connect(self.update_disk_info_display)
    def on_entry(self): self.populate_disk_list()
    def populate_disk_list(self):cur=self.config.get('disk_target');self.disk_combo.clear();self.devices_data=get_block_devices_info();
                             if not self.devices_data: self.disk_combo.addItem("No disks.");self.disk_combo.setEnabled(False);self.disk_info_label.setText("N/A");return
                             self.disk_combo.setEnabled(True);sel_idx=0;
                             for i,d in enumerate(self.devices_data):sz=d.get('size',0)/(1024**3);lbl=f" ({d.get('label','')})"if d.get('label')else"";self.disk_combo.addItem(f"{d['name']}{lbl} ({sz:.1f}GB)",d['name']);
                             if d['name']==cur:sel_idx=i
                             if self.disk_combo.count()>0: self.disk_combo.setCurrentIndex(sel_idx); self.update_disk_info_display(self.disk_combo.currentIndex())
    def update_disk_info_display(self,index):
        if index<0: self.disk_info_label.setText("No disk.");return
        d_name=self.disk_combo.itemData(index);d=next((x for x in self.devices_data if x['name']==d_name),None)
        if not d: self.disk_info_label.setText(f"Info unavailable.");return
        sz=d.get('size',0)/(1024**3);self.disk_info_label.setText(f"{d['name']} ({sz:.1f}GB)")
    def load_ui_from_config(self): self.populate_disk_list()
    def save_config_from_ui(self):
        if self.disk_combo.currentIndex()<0 or not self.disk_combo.currentData():QMessageBox.warning(self,"","Select disk.");return False
        self.config['disk_target']=self.disk_combo.currentData();return True
# --- (Add other refined step widgets here: MirrorRegion, Partitioning, Filesystem, Encryption, RootPassword, CreateUser, Timezone, Profile) ---
class ProfileSelectionStep(StepWidget): # Placeholder for actual profile selection
    def __init__(self, config, main_ref):
        super().__init__("System Profile", config, main_ref)
        expl = QLabel("Choose a base system profile (e.g., Desktop, Server). This sets up a group of core packages."); expl.setWordWrap(True); self.content_layout.addWidget(expl)
        self.profile_combo = QComboBox(); self.content_layout.addWidget(self.profile_combo)
        self.profiles_data = get_profiles()
        for p in self.profiles_data: self.profile_combo.addItem(f"{p['name']} - {p['description']}", userData=p['name']) # Store name as userData
    def load_ui_from_config(self):
        p_name = self.config.get('profile_name', DEFAULT_CONFIG['profile_name'])
        idx = self.profile_combo.findData(p_name)
        if idx != -1: self.profile_combo.setCurrentIndex(idx)
        elif self.profile_combo.count() > 0: self.profile_combo.setCurrentIndex(0)
    def save_config_from_ui(self):
        self.config['profile_name'] = self.profile_combo.currentData()
        if not self.config['profile_name']: self.config['profile_name'] = self.profiles_data[0]['name'] if self.profiles_data else "Minimal" # Fallback
        return True

# --- NEW: AppCategoriesStep ---
class AppCategoriesStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("Application Categories 📦", config, main_ref)
        
        expl_label = QLabel(APP_CATEGORIES_EXPLANATION)
        expl_label.setWordWrap(True)
        self.content_layout.addWidget(expl_label)

        self.categories_with_emojis = {
            "Education": "🎓",
            "Programming": "💻",
            "Gaming": "🎮",
            "Office & Daily Use": "📄",
            "Graphics & Design": "🎨",
            "Multimedia": "🎬",
            "Science & Engineering": "🔬",
            "Utilities": "🔧"
        }
        
        self.checkboxes = {} # Store checkboxes to retrieve state
        
        # Use QGridLayout for better alignment if many checkboxes
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)
        
        row, col = 0, 0
        for name, emoji in self.categories_with_emojis.items():
            checkbox = QCheckBox(f"{emoji} {name}")
            self.checkboxes[name] = checkbox
            grid_layout.addWidget(checkbox, row, col)
            col += 1
            if col >= 2: # Arrange in 2 columns
                col = 0
                row += 1
        
        self.content_layout.addLayout(grid_layout)

    def load_ui_from_config(self):
        selected_categories = self.config.get('app_categories', [])
        for name, checkbox in self.checkboxes.items():
            checkbox.setChecked(name in selected_categories)

    def save_config_from_ui(self):
        selected_cats = []
        for name, checkbox in self.checkboxes.items():
            if checkbox.isChecked():
                selected_cats.append(name)
        self.config['app_categories'] = selected_cats
        # No validation needed, selection is optional
        return True

class UserAccountsStep(StepWidget): # (Simplified)
    def __init__(self,config,main_ref):super().__init__("User Accounts",config,main_ref);self.content_layout.addWidget(QLabel("<b>Hostname:</b>"));self.hostname_edit=QLineEdit();self.hostname_edit.setPlaceholderText("maibloom-pc");self.content_layout.addWidget(self.hostname_edit);self.content_layout.addSpacing(10);self.content_layout.addWidget(QLabel("<b>Root Password:</b>"));self.root_password_edit=QLineEdit();self.root_password_edit.setEchoMode(QLineEdit.Password);self.content_layout.addWidget(self.root_password_edit);self.root_password_confirm_edit=QLineEdit();self.root_password_confirm_edit.setEchoMode(QLineEdit.Password);self.root_password_confirm_edit.setPlaceholderText("Confirm");self.content_layout.addWidget(self.root_password_confirm_edit);self.content_layout.addSpacing(10);self.content_layout.addWidget(QLabel("<b>Create User:</b>"));self.username_edit=QLineEdit();self.username_edit.setPlaceholderText("Username (optional)");self.content_layout.addWidget(self.username_edit);self.user_password_edit=QLineEdit();self.user_password_edit.setEchoMode(QLineEdit.Password);self.user_password_edit.setPlaceholderText("User password");self.content_layout.addWidget(self.user_password_edit);self.user_password_confirm_edit=QLineEdit();self.user_password_confirm_edit.setEchoMode(QLineEdit.Password);self.user_password_confirm_edit.setPlaceholderText("Confirm");self.content_layout.addWidget(self.user_password_confirm_edit);self.sudo_checkbox=QCheckBox("Admin (sudo)");self.sudo_checkbox.setChecked(True);self.content_layout.addWidget(self.sudo_checkbox)
    def load_ui_from_config(self):self.hostname_edit.setText(self.config.get('hostname',DEFAULT_CONFIG['hostname']));self.username_edit.setText(self.config.get('username',DEFAULT_CONFIG['username']));self.sudo_checkbox.setChecked(self.config.get('user_sudo',DEFAULT_CONFIG['user_sudo']));self.root_password_edit.clear();self.root_password_confirm_edit.clear();self.user_password_edit.clear();self.user_password_confirm_edit.clear()
    def save_config_from_ui(self):hn=self.hostname_edit.text().strip();rpw=self.root_password_edit.text();usr=self.username_edit.text().strip();upw=self.user_password_edit.text();
                             if not hn or not all(c.isalnum()or c=='-'for c in hn)or hn[0]=='-'or hn[-1]=='-':QMessageBox.warning(self,"","Invalid hostname.");return False
                             if len(rpw)<8 or rpw!=self.root_password_confirm_edit.text():QMessageBox.warning(self,"","Root pwd err.");return False
                             self.config['hostname']=hn;self.config['root_password']=rpw;
                             if usr:
                                 if not usr.islower()or not all(c.isalnum()or c in'-_'for c in usr):QMessageBox.warning(self,"","User: lc,alnum,-,_")
                                 if len(upw)<8 or upw!=self.user_password_confirm_edit.text():QMessageBox.warning(self,"","User pwd err.");return False
                                 self.config['username']=usr;self.config['user_password']=upw;self.config['user_sudo']=self.sudo_checkbox.isChecked()
                             else:self.config.pop('username',None);self.config.pop('user_password',None);self.config.pop('user_sudo',None)
                             return True

class SummaryStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("Installation Summary", config, main_ref)
        expl = QLabel(SUMMARY_STEP_INTRO_TEXT); expl.setWordWrap(True); expl.setTextFormat(Qt.RichText); self.content_layout.addWidget(expl)
        self.summary_text_edit = QPlainTextEdit(); self.summary_text_edit.setReadOnly(True); self.summary_text_edit.setStyleSheet("font-family:'monospace';font-size:9pt;color:#E0E0E0;background-color:#2A2A2A;")
        self.content_layout.addWidget(self.summary_text_edit)
    def on_entry(self):
        lines = [f"--- {self.config.get('os_name', APP_NAME)} Config Summary ---"]
        order = {
            'locale': "Locale", 'keyboard_layout': "Keyboard", 'mirror_region_display_name': "Mirror Region",
            'disk_target': "Target Disk", 'disk_scheme': "Partitioning", 'disk_filesystem': "Root FS", 'disk_encrypt': "Encryption",
            'hostname': "Hostname", 'root_password': "Root Password",
            'username': "Username", 'user_password': "User Password", 'user_sudo': "User Sudo",
            'timezone': "Timezone", 'profile_name': "Profile", 
            'app_categories': "App Categories", # Added
            'additional_packages': "Extra Packages",
        }
        for key, display_name in order.items():
            if key in self.config or key == 'username' or key == 'app_categories': # Ensure app_categories is checked
                value = self.config.get(key)
                formatted_value = ""
                if key == 'username' and not value: display_name = "New User Creation"; formatted_value = "Skipped"
                elif "password" in key.lower() and value: formatted_value = "<set>"
                elif isinstance(value, bool): formatted_value = "Yes" if value else "No"
                elif isinstance(value, list): formatted_value = ", ".join(value) if value else "<none>" # Handles app_categories list
                elif value is None or str(value).strip() == "": formatted_value = "<not set>"
                else: formatted_value = str(value)
                lines.append(f"{display_name:<25}: {formatted_value}")
        lines.append(f"\n--- Target: {self.config.get('disk_target','<NO DISK>')} ---")
        lines.append("\n--- WARNING ---\nProceeding will modify disk!"); self.summary_text_edit.setPlainText("\n".join(lines))

class InstallProgressStep(StepWidget): # (Unchanged)
    def __init__(self,config,main_ref):super().__init__("Installation Progress",config,main_ref);self.status_label=QLabel("Starting...");font=self.status_label.font();font.setPointSize(12);self.status_label.setFont(font);self.status_label.setAlignment(Qt.AlignCenter);self.content_layout.addWidget(self.status_label);self.progress_bar=QProgressBar();self.progress_bar.setRange(0,100);self.progress_bar.setTextVisible(True);self.progress_bar.setFormat("Waiting... %p%");self.content_layout.addWidget(self.progress_bar)
    def update_ui_progress(self,val,task):self.progress_bar.setValue(val);self.progress_bar.setFormat(f"{task} - %p%");self.status_label.setText(f"Task: {task}")
    def set_final_status(self,suc,msg):self.progress_bar.setValue(100);self.progress_bar.setFormat(msg.split('\n')[0] if suc else"Error!");self.status_label.setText(msg);self.status_label.setStyleSheet(f"color:{'#4CAF50'if suc else'#F44336'};font-weight:bold;")

# --- Main Application Window ---
class MaiBloomOSInstallerWindow(QMainWindow): # (populate_steps updated)
    def __init__(self):super().__init__();self.config_data=DEFAULT_CONFIG.copy();self.current_step_idx=-1;self.installation_thread=None;self.post_install_thread=None;self.step_widgets_instances=[];self.init_ui();self.populate_steps();
                 if self.step_widgets_instances:self.select_step(0,force_show=True)
    def init_ui(self):self.setWindowTitle(APP_NAME);self.setMinimumSize(1100,700);
                   if os.path.exists(LOGO_PATH):self.setWindowIcon(QIcon(LOGO_PATH));
                   central=QWidget();self.setCentralWidget(central);main_splitter=QSplitter(Qt.Horizontal,central);self.cfg_area=QWidget();cfg_layout=QVBoxLayout(self.cfg_area);cfg_layout.setContentsMargins(0,0,0,0);self.cfg_stack=QStackedWidget();cfg_layout.addWidget(self.cfg_stack,1);nav_layout=QHBoxLayout();nav_layout.setContentsMargins(10,5,10,10);self.prev_btn=QPushButton("⬅ Prev");self.prev_btn.clicked.connect(self.navigate_prev);self.next_btn=QPushButton("Next ➡");self.next_btn.clicked.connect(self.navigate_next);self.inst_btn=QPushButton(f"🚀 Install");self.inst_btn.clicked.connect(self.confirm_and_start_installation);nav_layout.addStretch(1);nav_layout.addWidget(self.prev_btn);nav_layout.addWidget(self.next_btn);nav_layout.addWidget(self.inst_btn);cfg_layout.addLayout(nav_layout);main_splitter.addWidget(self.cfg_area);self.log_out=QPlainTextEdit();self.log_out.setReadOnly(True);log_f=QFontDatabase.systemFont(QFontDatabase.FixedFont);log_f.setPointSize(9);self.log_out.setFont(log_f);main_splitter.addWidget(self.log_out);main_splitter.setSizes([650,450]);main_splitter.setStretchFactor(0,2);main_splitter.setStretchFactor(1,1);outer_layout=QHBoxLayout(central);outer_layout.addWidget(main_splitter);central.setLayout(outer_layout);self.appendToLog(f"{APP_NAME} started.","INFO");self.apply_dark_theme()
    def apply_dark_theme(self):self.setStyleSheet(DARK_THEME_QSS);self.log_out.setObjectName("LogOutput");self.inst_btn.setObjectName("InstallButton")
    def populate_steps(self):
        self.step_definitions = [
            WelcomeStep, LanguageStep, KeyboardStep, SelectDiskStep, # Add other refined disk steps
            ProfileSelectionStep, # Add other steps like MirrorRegion, Timezone etc.
            AppCategoriesStep,    # NEW STEP
            UserAccountsStep,     # Ideally split UserAccountsStep too
            SummaryStep, InstallProgressStep
        ]
        self.step_widgets_instances = []
        for StepCls in self.step_definitions: inst=StepCls(self.config_data,self); self.step_widgets_instances.append(inst); self.cfg_stack.addWidget(inst)
    def select_step(self,idx,force_show=False):
        if not(0<=idx<len(self.step_widgets_instances)):return
        is_target_inst=isinstance(self.step_widgets_instances[idx],InstallProgressStep);is_curr_summ=self.current_step_idx>=0 and isinstance(self.step_widgets_instances[self.current_step_idx],SummaryStep)
        if is_target_inst and not is_curr_summ and not force_show:return
        self.current_step_idx=idx;self.cfg_stack.setCurrentIndex(idx);curr_w=self.step_widgets_instances[idx];curr_w.load_ui_from_config();curr_w.on_entry();self.update_navigation_buttons()
    def update_navigation_buttons(self):is_first=(self.current_step_idx==0);is_inst=False;is_summ=False;
                                   if 0<=self.current_step_idx<len(self.step_widgets_instances):curr_w=self.step_widgets_instances[self.current_step_idx];is_summ=isinstance(curr_w,SummaryStep);is_inst=isinstance(curr_w,InstallProgressStep)
                                   self.prev_btn.setEnabled(not is_first and not is_inst);self.next_btn.setVisible(not is_summ and not is_inst);self.inst_btn.setVisible(is_summ and not is_inst)
                                   if is_inst:self.prev_btn.setEnabled(False);self.next_btn.setVisible(False);self.inst_btn.setVisible(False)
    def navigate_next(self):curr_w=self.step_widgets_instances[self.current_step_idx];
                        if not curr_w.on_exit()or not curr_w.save_config_from_ui():return
                        if self.current_step_idx<len(self.step_widgets_instances)-1:self.select_step(self.current_step_idx+1)
    def navigate_prev(self):
        if not self.step_widgets_instances[self.current_step_idx].on_exit(going_back=True):return
        if self.current_step_idx>0:self.select_step(self.current_step_idx-1)
    def confirm_and_start_installation(self):
        if not isinstance(self.step_widgets_instances[self.current_step_idx],SummaryStep):return
        self.step_widgets_instances[self.current_step_idx].on_entry() # Refresh summary
        if QMessageBox.question(self,"Confirm Install",f"Start installing {self.config_data.get('os_name',APP_NAME)}?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            for i,s in enumerate(self.step_widgets_instances):
                if isinstance(s,InstallProgressStep):self.select_step(i,force_show=True);self.start_backend_installation();break
    def start_backend_installation(self):self.appendToLog("Starting OS install...","INFO");self.update_navigation_buttons();self.installation_thread=InstallationThread(self.config_data.copy());self.installation_thread.log_signal.connect(lambda m:self.appendToLog(m,"INSTALL"));prog_w=self.step_widgets_instances[self.current_step_idx];
                                   if isinstance(prog_w,InstallProgressStep):self.installation_thread.progress_signal.connect(prog_w.update_ui_progress);self.installation_thread.finished_signal.connect(prog_w.set_final_status)
                                   self.installation_thread.finished_signal.connect(self.on_installation_finished);self.installation_thread.start()
    def on_installation_finished(self,suc,msg):self.appendToLog(f"OS Install Done: Success={suc}","RESULT");prog_w=self.step_widgets_instances[self.current_step_idx];
                                      if isinstance(prog_w,InstallProgressStep):prog_w.set_final_status(suc,msg)
                                      if suc:self.run_final_setup_script()
                                      else:QMessageBox.critical(self,"Install Failed",msg+"\nCheck logs.")
    def run_final_setup_script(self):self.appendToLog(f"Running {POST_INSTALL_SCRIPT_NAME}...","INFO");
                               if not os.path.exists(POST_INSTALL_SCRIPT_PATH):self.appendToLog(f"Script not found. Skipping.","WARN");QMessageBox.information(self,"Complete",f"{self.config_data.get('os_name',APP_NAME)} installed. Final script skipped.\nReboot.");return
                               if not os.access(POST_INSTALL_SCRIPT_PATH,os.X_OK):
                                   try:os.chmod(POST_INSTALL_SCRIPT_PATH,0o755);self.appendToLog("chmod OK.","INFO")
                                   except Exception as e:self.appendToLog(f"chmod failed: {e}.","ERROR");QMessageBox.critical(self,"Error",f"Cannot run {POST_INSTALL_SCRIPT_NAME}.\nOS install OK.");return
                               QMessageBox.information(self,"Final Setup",f"OS install OK. Running {POST_INSTALL_SCRIPT_NAME}...")
                               self.post_install_thread=QThread();worker=ScriptRunner(POST_INSTALL_SCRIPT_PATH);worker.moveToThread(self.post_install_thread);worker.log_signal.connect(lambda m:self.appendToLog(m,"POST_SCRIPT"));worker.finished_signal.connect(self.on_final_setup_script_finished);self.post_install_thread.started.connect(worker.run);self.post_install_thread.start()
    def on_final_setup_script_finished(self,exit_code):
        if exit_code==0:self.appendToLog(f"{POST_INSTALL_SCRIPT_NAME} OK.","RESULT");QMessageBox.information(self,"Complete",f"{self.config_data.get('os_name',APP_NAME)} install & final setup OK.\nReboot.")
        else:self.appendToLog(f"{POST_INSTALL_SCRIPT_NAME} Error (code {exit_code}).","ERROR");QMessageBox.warning(self,"Warning",f"{POST_INSTALL_SCRIPT_NAME} error ({exit_code}). Check logs.\nOS install OK.")
        if self.post_install_thread:self.post_install_thread.quit();self.post_install_thread.wait()
    def appendToLog(self,txt,lvl="DEBUG"):ts=time.strftime("%H:%M:%S");self.log_out.appendPlainText(f"[{ts}][{lvl.upper()}] {txt}");sb=self.log_out.verticalScrollBar();sb.setValue(sb.maximum());QApplication.processEvents()
    def closeEvent(self,event):busy=(self.installation_thread and self.installation_thread.isRunning())or(self.post_install_thread and self.post_install_thread.isRunning());
                          if busy and QMessageBox.question(self,"Exit","Process running. Abort?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:self.appendToLog("User aborted.","WARN");event.accept()
                          elif not busy:super().closeEvent(event)
                          else:event.ignore()

# --- Worker for Script Runner ---
class ScriptRunner(QObject): # (Unchanged)
    log_signal=pyqtSignal(str);finished_signal=pyqtSignal(int)
    def __init__(self,script_path):super().__init__();self.script_path=script_path
    @pyqtSlot()
    def run(self):
        try:proc=subprocess.Popen([self.script_path],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,universal_newlines=True,shell=False);
            for line in iter(proc.stdout.readline,''):self.log_signal.emit(line.strip())
            proc.stdout.close();rc=proc.wait();self.finished_signal.emit(rc)
        except Exception as e:self.log_signal.emit(f"Script error: {e}\n{traceback.format_exc()}");self.finished_signal.emit(-1)

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    if not os.path.exists(LOGO_PATH): print(f"Warning: Logo '{LOGO_FILENAME}' missing at '{LOGO_PATH}'.")
    main_win = MaiBloomOSInstallerWindow()
    main_win.show()
    sys.exit(app.exec_())


