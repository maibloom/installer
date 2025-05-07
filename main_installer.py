#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# --- Imports ---
import sys
import os
import time
import subprocess
import traceback
import logging # For capturing archinstall logs

# --- Privilege Check ---
if os.geteuid() != 0:
    print("ERROR: This installer requires root privileges.")
    print("Please run using: sudo python main.py")
    sys.exit(1)

# --- Attempt Archinstall Import ---
try:
    import archinstall
    # Import specific components if their API is known and stable
    # from archinstall import profile, Installer, models, disk, SysCommand, run_pacman
    ARCHINSTALL_AVAILABLE = True
except ImportError:
    print("ERROR: The 'archinstall' library is not installed or not found.")
    print("Please install it (e.g., 'sudo pacman -S archinstall') and restart.")
    # We exit here now because the utility functions *require* archinstall
    sys.exit(1)

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
# POST_INSTALL_SCRIPT_NAME = "final_setup.sh" # Removed, aiming for archinstall integration
# POST_INSTALL_SCRIPT_PATH = os.path.join(SCRIPT_DIR, POST_INSTALL_SCRIPT_NAME)

DEFAULT_CONFIG = { # Structure to align more closely with potential archinstall needs
    'os_name': 'Mai Bloom OS',
    'locale_config': {'sys_lang': 'en_US.UTF-8', 'kb_layout': 'us'},
    'mirror_config': {'mirror_region': 'Worldwide'}, # Use region code/name archinstall expects
    'disk_config': {'device_path': None, 'wipe': True, 'filesystem': 'ext4'}, # Simplified for guided
    'disk_encryption': None, # Example: {'password': '...', 'type': 'luks'}
    'hostname': 'maibloom-pc',
    '!users': [], # List of user dicts e.g. [{'username':'x','password':'y','sudo':True}]
    '!root-password': '',
    'profile_config': {'profile': 'kde', 'greeter': None}, # Example profile structure
    'app_categories': [], # Custom data, needs mapping to packages
    'packages': [], # For additional packages + category packages
    'timezone': 'Asia/Tehran',
    'kernels': ['linux'],
    'nic': 'NetworkManager',
    'audio_config': {'audio': 'pipewire'},
    # Add any other top-level keys archinstall expects: 'swap', 'bootloader', etc.
    'swap': True, # Example
    'bootloader': 'systemd-boot' if os.path.exists('/sys/firmware/efi') else 'grub', # Auto-detect example
}

# --- Stylesheet Constant ---
# (DARK_THEME_QSS remains the same)
DARK_THEME_QSS="""QMainWindow,QWidget{font-size:10pt;background-color:#2E2E2E;color:#E0E0E0}QStackedWidget>QWidget{background-color:#2E2E2E}StepWidget QLabel{color:#E0E0E0}StepWidget QCheckBox{font-size:11pt;padding:3px}QPushButton{padding:9px 18px;border-radius:5px;background-color:#555;color:#FFF;border:1px solid #686868;font-weight:bold}QPushButton:hover{background-color:#686868}QPushButton:disabled{background-color:#404040;color:#808080;border-color:#505050}QPushButton#InstallButton{background-color:#4CAF50;border-color:#388E3C}QPushButton#InstallButton:hover{background-color:#388E3C}QPlainTextEdit#LogOutput{background-color:#1C1C1C;color:#C0C0C0;border:1px solid #434343;font-family:"Monospace"}QLineEdit,QComboBox{padding:6px 8px;border:1px solid #555;border-radius:4px;background-color:#3D3D3D;color:#E0E0E0}QComboBox::drop-down{border:none;background-color:#4A4A4A}QComboBox QAbstractItemView{background-color:#3D3D3D;color:#E0E0E0;selection-background-color:#007BFF}QCheckBox{margin:5px 0;color:#E0E0E0}QCheckBox::indicator{width:18px;height:18px;background-color:#555;border:1px solid #686868;border-radius:3px}QCheckBox::indicator:checked{background-color:#007BFF}QProgressBar{text-align:center;padding:1px;border-radius:5px;background-color:#555;border:1px solid #686868;color:#E0E0E0;min-height:20px}QProgressBar::chunk{background-color:#007BFF;border-radius:4px}QSplitter::handle{background-color:#4A4A4A}QSplitter::handle:horizontal{width:3px}"""

# --- Text Constants ---
# (WELCOME_STEP_HTML, etc. remain the same)
WELCOME_STEP_HTML=(f"<h2>Welcome to {APP_NAME}!</h2><p>Installer guide...</p><h3>Notes:</h3><ul><li>Internet recommended.</li><li>Backup data!</li><li>Disk ops may erase data.</li></ul><p>Next-></p>")
LANGUAGE_STEP_EXPLANATION="Select system language (menus, messages)."
KEYBOARD_STEP_EXPLANATION="Choose layout matching your keyboard."
SELECT_DISK_STEP_EXPLANATION="Choose install disk.<br><b style='color:yellow;'>Data may be erased.</b>"
APP_CATEGORIES_EXPLANATION="Select app types for initial setup."
SUMMARY_STEP_INTRO_TEXT="Review settings. <b style='color:yellow;'>Install button modifies disk!</b>"


# --- Utility Functions (Using Archinstall) ---
# Note: These might raise exceptions if archinstall fails or APIs change.
# The GUI steps calling these should ideally handle potential empty lists/errors.

def get_keyboard_layouts():
    try: return sorted(archinstall.list_keyboard_languages())
    except Exception as e: print(f"ERROR getting keyboard layouts: {e}"); return ["us"] # Fallback

def get_locales():
    # Might need to parse /etc/locale.gen or provide curated list if archinstall doesn't expose this easily
    print("WARN: get_locales() using curated list.")
    return ["en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fa_IR.UTF-8"]

def get_block_devices_info():
    try:
        # Assuming list_block_devices needs root and returns dict {path: obj}
        raw_devices = archinstall.list_block_devices(human_readable=False)
        devices = []
        for path, data_obj in raw_devices.items():
            dtype = getattr(data_obj, 'type', '').lower()
            size = getattr(data_obj, 'size', 0)
            if dtype == 'disk' and isinstance(size, int) and size > (1 * 1024**3): # Basic filter: disks > 1GB
                devices.append({'name': path, 'size': size, 'type': dtype,
                                'label': getattr(data_obj, 'label', None)})
        if not devices: print("WARN: archinstall found no suitable disks.")
        return devices
    except Exception as e:
        print(f"ERROR getting block devices: {e}. Check permissions and archinstall API.")
        return [] # Return empty on error

def get_mirror_regions():
    try:
        regions = archinstall.list_mirror_regions() # Assume returns dict {'Display': 'Code'}
        return regions if regions else {"Worldwide":"Worldwide"}
    except Exception as e: print(f"ERROR getting mirror regions: {e}"); return {"Worldwide":"Worldwide"}

def get_timezones():
    try:
        zones = archinstall.list_timezones() # Assume returns dict {'Region': ['City',...]}
        return zones if zones else {"UTC": ["UTC"]}
    except Exception as e: print(f"ERROR getting timezones: {e}"); return {"UTC": ["UTC"]}

def get_profiles():
    try:
        profiles_dict = archinstall.profile.list_profiles() # Assumed API
        profiles_list = [{"name": n, "description": getattr(p,'desc','')}
                         for n,p in profiles_dict.items() if not n.startswith('_')]
        return profiles_list if profiles_list else [{"name":"Minimal","description":"Basic system."}]
    except Exception as e: print(f"ERROR getting profiles: {e}"); return [{"name":"Minimal","description":"Basic system."}]

# --- Qt Log Handler ---
class QtLogHandler(logging.Handler):
    def __init__(self, log_signal_emitter):
        super().__init__(); self.log_signal_emitter = log_signal_emitter
        self.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    def emit(self, record): self.log_signal_emitter.emit(self.format(record))

# --- Installation Thread (Simplified using Archinstall) ---
class InstallationThread(QThread):
    log_signal = pyqtSignal(str); progress_signal = pyqtSignal(int, str); finished_signal = pyqtSignal(bool, str)

    def __init__(self, config):
        super().__init__(); self.config = config

    def setup_logging(self):
        log = logging.getLogger('archinstall') # Capture archinstall's logger
        log.setLevel(logging.INFO)
        # Clear existing handlers added by archinstall maybe? Or just add ours.
        # Check if our handler is already present to avoid duplicates if run again
        if not any(isinstance(h, QtLogHandler) for h in log.handlers):
            qt_handler = QtLogHandler(self.log_signal)
            log.addHandler(qt_handler)
        self.log_signal.emit("Archinstall log capture setup.")

    def map_categories_to_packages(self, categories):
        # Keep this mapping logic separate
        mapping = {"Programming": ["base-devel", "git", "python", "code"], "Gaming": ["steam", "lutris"], "Office & Daily Use": ["libreoffice-fresh", "firefox"],"Graphics & Design": ["gimp", "inkscape"]}
        pkgs = set()
        for cat in categories: pkgs.update(mapping.get(cat, []))
        return list(pkgs)

    def run(self):
        self.setup_logging()
        self.log_signal.emit("Installation thread started using archinstall library.")
        self.progress_signal.emit(0, "Preparing configuration...")

        try:
            # ** STEP 1: Finalize Configuration Dictionary for archinstall **
            ai_conf = self.config.copy() # Start with GUI config

            # Map GUI choices to exact archinstall keys/structures
            # Locale/Keyboard might be under 'locale_config' or top-level
            ai_conf['keyboard_layout'] = ai_conf.pop('locale_config', {}).get('kb_layout', DEFAULT_CONFIG['locale_config']['kb_layout'])
            ai_conf['sys_lang'] = ai_conf.pop('locale_config', {}).get('sys_lang', DEFAULT_CONFIG['locale_config']['sys_lang'])
            # Mirror might need code, not display name
            ai_conf['mirror_region'] = ai_conf.pop('mirror_config', {}).get('mirror_region', DEFAULT_CONFIG['mirror_config']['mirror_region'])
            # Disk config might need more detail for archinstall's partitioning
            disk_conf = ai_conf.pop('disk_config', {})
            ai_conf['disk_layouts'] = {disk_conf.get('device_path'): {'wipe': True, 'filesystem': {'format': disk_conf.get('filesystem')}}} if disk_conf.get('device_path') else {} # Example structure
            # Encryption
            if self.config.get('disk_encrypt'):
                ai_conf['disk_encryption'] = [{'device': disk_conf.get('device_path'), 'password': self.config.get('disk_encrypt_password'), 'encryption_type': 'luks'}] # Example
            else: ai_conf['disk_encryption'] = None
            # Users need specific format
            users = []
            if ai_conf.get('username'): users.append({'username': ai_conf['username'], 'password': ai_conf.get('user_password'), 'sudo': ai_conf.get('user_sudo', False)})
            ai_conf['!users'] = users # Use archinstall's common key
            ai_conf['!root-password'] = ai_conf.get('root_password')
            # Profile
            ai_conf['profile'] = ai_conf.pop('profile_config', {}).get('profile')
            if ai_conf['profile'] == 'Minimal': ai_conf['profile'] = None # Or specific minimal profile name?
            # Combine packages
            category_pkgs = self.map_categories_to_packages(ai_conf.get('app_categories', []))
            additional_pkgs = ai_conf.get('additional_packages', [])
            ai_conf['packages'] = list(set(category_pkgs + additional_pkgs))

            # Remove keys used only by GUI?
            ai_conf.pop('os_name', None); ai_conf.pop('disk_scheme', None); ai_conf.pop('app_categories', None)
            # ... potentially remove others not directly used by perform_installation

            self.log_signal.emit("Configuration finalized for archinstall.")
            # Log non-sensitive parts for debugging
            loggable_conf = {k:v for k,v in ai_conf.items() if 'pass' not in k and k!='disk_encryption'}
            self.log_signal.emit(f"Final archinstall config (secrets omitted): {loggable_conf}")

            # ** STEP 2: Execute archinstall **
            self.progress_signal.emit(5, "Starting installation...")

            # This is the core call. It assumes archinstall has a function/method
            # that takes the configuration and handles the entire process.
            # The exact function and arguments NEED VERIFICATION.
            # It might raise exceptions on failure.
            
            # Example Possibility 1: Function call
            # archinstall.perform_installation(ai_conf, mount_point='/mnt', ...)
            
            # Example Possibility 2: Installer class
            # installer = archinstall.Installer('/mnt', ai_conf)
            # installer.install() # This might handle disk prep, mount, pacstrap, config, bootloader...

            # Mocking the call for now, assuming it blocks until done or error
            self.log_signal.emit("Calling archinstall.perform_installation (MOCK)...")
            time.sleep(2) # Simulate initial setup
            self.progress_signal.emit(10, "Disk setup (mock)...")
            time.sleep(3)
            self.progress_signal.emit(40, "Package install (mock)...")
            time.sleep(5)
            self.progress_signal.emit(80, "System config (mock)...")
            time.sleep(3)
            self.progress_signal.emit(100, "Finalizing (mock)...")
            time.sleep(1)
            # In reality, progress would come from archinstall logs/hooks

            self.log_signal.emit("Mock archinstall process completed.")
            self.finished_signal.emit(True, f"{DEFAULT_CONFIG['os_name']} installation finished (simulated).")

        except Exception as e:
            self.log_signal.emit(f"FATAL archinstall execution error: {str(e)}\n{traceback.format_exc()}")
            self.finished_signal.emit(False, f"Installation failed: {str(e)}")

# --- Step Widget Base Class ---
class StepWidget(QWidget): # (Unchanged from logo version)
    def __init__(self, title, config_ref, main_window_ref): super().__init__(); self.title=title; self.config=config_ref; self.main_window=main_window_ref; self.outer_layout=QVBoxLayout(self); self.outer_layout.setContentsMargins(25,15,25,15); title_area=QHBoxLayout(); title_area.setSpacing(10); title_area.setContentsMargins(0,0,0,5); self.logo_lbl=QLabel(); logo_pix=QPixmap(LOGO_PATH);
                               if not logo_pix.isNull(): scaled=logo_pix.scaled(48,48,Qt.KeepAspectRatio,Qt.SmoothTransformation); self.logo_lbl.setPixmap(scaled); self.logo_lbl.setFixedSize(48,48)
                               else: self.logo_lbl.setText("[-]"); self.logo_lbl.setFixedSize(48,48)
                               title_area.addWidget(self.logo_lbl); self.title_lbl=QLabel(f"<b>{title}</b>"); font=self.title_lbl.font(); font.setPointSize(16); self.title_lbl.setFont(font); self.title_lbl.setStyleSheet("color:#00BFFF;"); title_area.addWidget(self.title_lbl); title_area.addStretch(1); self.outer_layout.addLayout(title_area); sep=QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken); sep.setStyleSheet("border:1px solid #4A4A4A;"); self.outer_layout.addWidget(sep); self.content_layout=QVBoxLayout(); self.content_layout.setSpacing(15); self.content_layout.setContentsMargins(0,10,0,0); self.outer_layout.addLayout(self.content_layout); self.outer_layout.addStretch(1)
    def get_title(self): return self.title
    def load_ui_from_config(self): pass
    def save_config_from_ui(self): return True
    def on_entry(self): pass
    def on_exit(self, going_back=False): return True

# --- Concrete Step Widgets ---
# (Define WelcomeStep, LanguageStep, KeyboardStep, SelectDiskStep, UserAccountsStep, ProfileSelectionStep, AppCategoriesStep, SummaryStep, InstallProgressStep here)
# (These are mostly unchanged from previous versions, ensure they use DEFAULT_CONFIG for defaults and save to self.config)
# ... (Assume all step widgets are defined here as before)...
# Example: WelcomeStep
class WelcomeStep(StepWidget):
    def __init__(self, config, main_ref): super().__init__("Welcome", config, main_ref); info=QLabel(WELCOME_STEP_HTML);info.setWordWrap(True);info.setTextFormat(Qt.RichText);self.content_layout.addWidget(info)
# Example: AppCategoriesStep
class AppCategoriesStep(StepWidget):
    def __init__(self, config, main_ref):
        super().__init__("Application Categories 📦", config, main_ref)
        expl = QLabel(APP_CATEGORIES_EXPLANATION); expl.setWordWrap(True); self.content_layout.addWidget(expl)
        self.categories = {"Education":"🎓","Programming":"💻","Gaming":"🎮","Office & Daily Use":"📄","Graphics":"🎨","Multimedia":"🎬","Science":"🔬","Utilities":"🔧"}
        self.checkboxes = {}; grid = QGridLayout(); grid.setSpacing(10); r,c=0,0
        for n,e in self.categories.items(): cb=QCheckBox(f"{e} {n}"); self.checkboxes[n]=cb; grid.addWidget(cb,r,c); c+=1;
        if c>=2: c=0; r+=1
        self.content_layout.addLayout(grid)
    def load_ui_from_config(self): sel=self.config.get('app_categories',[]); [cb.setChecked(n in sel) for n,cb in self.checkboxes.items()]
    def save_config_from_ui(self): self.config['app_categories']=[n for n,cb in self.checkboxes.items() if cb.isChecked()]; return True
# (Include *all* other necessary step widgets here)
class LanguageStep(StepWidget): # Example
    def __init__(self,config,main_ref):super().__init__("System Language",config,main_ref);expl=QLabel(LANGUAGE_STEP_EXPLANATION);expl.setWordWrap(True);self.content_layout.addWidget(expl);self.content_layout.addWidget(QLabel("<b>Locale:</b>"));self.locale_combo=QComboBox();self.locale_combo.addItems(get_locales());self.content_layout.addWidget(self.locale_combo)
    def load_ui_from_config(self): self.locale_combo.setCurrentText(self.config.get('locale_config',{}).get('sys_lang', DEFAULT_CONFIG['locale_config']['sys_lang']))
    def save_config_from_ui(self): self.config['locale_config'] = self.config.get('locale_config',{}); self.config['locale_config']['sys_lang']=self.locale_combo.currentText(); return bool(self.config['locale_config']['sys_lang'] or QMessageBox.warning(self,"","Select locale."))
class KeyboardStep(StepWidget): # Example
    def __init__(self,config,main_ref):super().__init__("Keyboard Layout",config,main_ref);expl=QLabel(KEYBOARD_STEP_EXPLANATION);expl.setWordWrap(True);self.content_layout.addWidget(expl);self.content_layout.addWidget(QLabel("<b>Layout:</b>"));self.kb_layout_combo=QComboBox();self.kb_layout_combo.addItems(get_keyboard_layouts());self.content_layout.addWidget(self.kb_layout_combo)
    def load_ui_from_config(self): self.kb_layout_combo.setCurrentText(self.config.get('locale_config',{}).get('kb_layout', DEFAULT_CONFIG['locale_config']['kb_layout']))
    def save_config_from_ui(self): self.config['locale_config'] = self.config.get('locale_config',{}); self.config['locale_config']['kb_layout']=self.kb_layout_combo.currentText(); return bool(self.config['locale_config']['kb_layout'] or QMessageBox.warning(self,"","Select keyboard."))
class SelectDiskStep(StepWidget): # Example
    def __init__(self, config, main_ref): super().__init__("Select Disk", config, main_ref);expl=QLabel(SELECT_DISK_STEP_EXPLANATION); expl.setWordWrap(True); expl.setTextFormat(Qt.RichText); self.content_layout.addWidget(expl); self.disk_combo=QComboBox(); self.content_layout.addWidget(self.disk_combo); self.disk_info=QLabel("..."); self.content_layout.addWidget(self.disk_info); self.devs=[]; self.disk_combo.currentIndexChanged.connect(self.upd_info)
    def on_entry(self): self.pop_disks()
    def pop_disks(self): cur=self.config.get('disk_config',{}).get('device_path'); self.disk_combo.clear(); self.devs=get_block_devices_info();
                        if not self.devs: self.disk_combo.addItem("No disks."); self.disk_combo.setEnabled(False); return
                        self.disk_combo.setEnabled(True); sel_idx=0;
                        for i,d in enumerate(self.devs): sz=d.get('size',0)/(1024**3); self.disk_combo.addItem(f"{d['name']} ({sz:.1f}GB)", d['name']);
                        if d['name']==cur: sel_idx=i
                        if self.disk_combo.count()>0: self.disk_combo.setCurrentIndex(sel_idx); self.upd_info(sel_idx)
    def upd_info(self,idx): dev_name=self.disk_combo.itemData(idx); d=next((x for x in self.devs if x['name']==dev_name),None); self.disk_info.setText(f"{dev['name']} Size: {d.get('size',0)/(1024**3):.1f}GB" if d else "Info N/A")
    def load_ui_from_config(self): self.pop_disks()
    def save_config_from_ui(self):
        if self.disk_combo.currentIndex()<0 or not self.disk_combo.currentData(): QMessageBox.warning(self,"","Select disk."); return False
        self.config['disk_config']=self.config.get('disk_config',{}); self.config['disk_config']['device_path']=self.disk_combo.currentData(); return True
# Need Filesystem/Encryption Step here
class UserAccountsStep(StepWidget): # Example
    def __init__(self,config,main_ref):super().__init__("Users",config,main_ref);self.content_layout.addWidget(QLabel("<b>Hostname:</b>"));self.hn=QLineEdit();self.content_layout.addWidget(self.hn);self.content_layout.addWidget(QLabel("<b>Root Pwd:</b>"));self.rp=QLineEdit();self.rp.setEchoMode(QLineEdit.Password);self.content_layout.addWidget(self.rp);self.rpc=QLineEdit();self.rpc.setEchoMode(QLineEdit.Password);self.rpc.setPlaceholderText("Confirm");self.content_layout.addWidget(self.rpc);self.content_layout.addWidget(QLabel("<b>Create User:</b>"));self.un=QLineEdit();self.un.setPlaceholderText("Username (opt)");self.content_layout.addWidget(self.un);self.up=QLineEdit();self.up.setEchoMode(QLineEdit.Password);self.up.setPlaceholderText("User pwd");self.content_layout.addWidget(self.up);self.upc=QLineEdit();self.upc.setEchoMode(QLineEdit.Password);self.upc.setPlaceholderText("Confirm");self.content_layout.addWidget(self.upc);self.sudo=QCheckBox("Admin");self.sudo.setChecked(True);self.content_layout.addWidget(self.sudo)
    def load_ui_from_config(self):self.hn.setText(self.config.get('hostname',DEFAULT_CONFIG['hostname']));self.un.setText(self.config.get('!users',[{}])[0].get('username','') if self.config.get('!users') else '');self.sudo.setChecked(self.config.get('!users',[{}])[0].get('sudo',True) if self.config.get('!users') else True);self.rp.clear();self.rpc.clear();self.up.clear();self.upc.clear()
    def save_config_from_ui(self):hn=self.hn.text().strip();rp=self.rp.text();usr=self.un.text().strip();up=self.up.text();
                             if not hn or not all(c.isalnum()or c=='-'for c in hn)or hn[0]=='-'or hn[-1]=='-':QMessageBox.warning(self,"","Invalid hostname.");return False
                             if len(rp)<8 or rp!=self.rpc.text():QMessageBox.warning(self,"","Root pwd err.");return False
                             self.config['hostname']=hn;self.config['!root-password']=rp;users=[]
                             if usr:
                                 if not usr.islower()or not all(c.isalnum()or c in'-_'for c in usr):QMessageBox.warning(self,"","User: lc,alnum,-,_")
                                 if len(up)<8 or up!=self.upc.text():QMessageBox.warning(self,"","User pwd err.");return False
                                 users.append({'username':usr,'password':up,'sudo':self.sudo.isChecked()})
                             self.config['!users']=users;return True
class SummaryStep(StepWidget): # Updated Summary
    def __init__(self,config,main_ref):super().__init__("Summary",config,main_ref);expl=QLabel(SUMMARY_STEP_INTRO_TEXT);expl.setWordWrap(True);expl.setTextFormat(Qt.RichText);self.content_layout.addWidget(expl);self.summary_edit=QPlainTextEdit();self.summary_edit.setReadOnly(True);self.summary_edit.setStyleSheet("font-family:'monospace';font-size:9pt;color:#E0E0E0;background-color:#2A2A2A;");self.content_layout.addWidget(self.summary_edit)
    def on_entry(self):
        lines=[f"--- {self.config.get('os_name',APP_NAME)} Summary ---"];order={'locale_config.sys_lang':"Locale",'locale_config.kb_layout':"Keyboard",'disk_config.device_path':"Disk",'hostname':"Hostname",'!root-password':"Root Pwd",'!users':"Users",'profile':"Profile",'packages':"Extra Pkgs",'app_categories':"Categories",'timezone':"Timezone"}
        for k,n in order.items():
            v=self.config;keys=k.split('.'); # Navigate nested dicts if needed
            try: 
                for key in keys: v=v[key]
            except (KeyError, TypeError, IndexError): v = None # Handle missing keys/indices
            
            fv="<not set>";
            if k=='!users': fv=f"{len(v)} user(s)" if v else "None"
            elif "pass" in k and v: fv="<set>"
            elif isinstance(v,bool): fv="Yes" if v else "No"
            elif isinstance(v,list): fv=", ".join(v) if v else "<none>"
            elif v is not None and str(v).strip()!="": fv=str(v)
            lines.append(f"{n:<20}: {fv}")
        lines.append("\n--- WARNING: Check disk! ---");self.summary_edit.setPlainText("\n".join(lines))
class InstallProgressStep(StepWidget): # Unchanged
    def __init__(self,config,main_ref):super().__init__("Progress",config,main_ref);self.lbl=QLabel("Starting...");f=self.lbl.font();f.setPointSize(12);self.lbl.setFont(f);self.lbl.setAlignment(Qt.AlignCenter);self.content_layout.addWidget(self.lbl);self.bar=QProgressBar();self.bar.setRange(0,100);self.bar.setTextVisible(True);self.bar.setFormat("Waiting... %p%");self.content_layout.addWidget(self.bar)
    def update_ui_progress(self,val,task):self.bar.setValue(val);self.bar.setFormat(f"{task}-%p%");self.lbl.setText(f"Task: {task}")
    def set_final_status(self,suc,msg):self.bar.setValue(100);self.bar.setFormat(msg.split('\n')[0] if suc else"Error!");self.lbl.setText(msg);self.lbl.setStyleSheet(f"color:{'#4CAF50'if suc else'#F44336'};font-weight:bold;")


# --- Main Application Window ---
class MaiBloomOSInstallerWindow(QMainWindow): # Keep unchanged from previous version
    def __init__(self): super().__init__(); self.config_data=DEFAULT_CONFIG.copy(); self.current_step_idx=-1; self.installation_thread=None; self.post_install_thread=None; self.step_widgets_instances=[]; self.init_ui(); self.populate_steps();
                 if self.step_widgets_instances: self.select_step(0, force_show=True)
    def init_ui(self): self.setWindowTitle(APP_NAME); self.setMinimumSize(1100, 700);
                   if os.path.exists(LOGO_PATH): self.setWindowIcon(QIcon(LOGO_PATH));
                   central=QWidget(); self.setCentralWidget(central); main_splitter=QSplitter(Qt.Horizontal, central); self.cfg_area=QWidget(); cfg_layout=QVBoxLayout(self.cfg_area); cfg_layout.setContentsMargins(0,0,0,0); self.cfg_stack=QStackedWidget(); cfg_layout.addWidget(self.cfg_stack, 1); nav_layout=QHBoxLayout(); nav_layout.setContentsMargins(10,5,10,10); self.prev_btn=QPushButton("⬅ Prev"); self.prev_btn.clicked.connect(self.navigate_prev); self.next_btn=QPushButton("Next ➡"); self.next_btn.clicked.connect(self.navigate_next); self.inst_btn=QPushButton(f"🚀 Install"); self.inst_btn.clicked.connect(self.confirm_and_start_installation); nav_layout.addStretch(1); nav_layout.addWidget(self.prev_btn); nav_layout.addWidget(self.next_btn); nav_layout.addWidget(self.inst_btn); cfg_layout.addLayout(nav_layout); main_splitter.addWidget(self.cfg_area); self.log_out=QPlainTextEdit(); self.log_out.setReadOnly(True); log_f=QFontDatabase.systemFont(QFontDatabase.FixedFont); log_f.setPointSize(9); self.log_out.setFont(log_f); main_splitter.addWidget(self.log_out); main_splitter.setSizes([650,450]); main_splitter.setStretchFactor(0,2); main_splitter.setStretchFactor(1,1); outer_layout=QHBoxLayout(central); outer_layout.addWidget(main_splitter); central.setLayout(outer_layout); self.appendToLog(f"{APP_NAME} started.", "INFO"); self.apply_dark_theme()
    def apply_dark_theme(self): self.setStyleSheet(DARK_THEME_QSS); self.log_out.setObjectName("LogOutput"); self.inst_btn.setObjectName("InstallButton")
    def populate_steps(self):
        self.step_definitions = [ WelcomeStep, LanguageStep, KeyboardStep, SelectDiskStep, # Add more disk steps
                                  UserAccountsStep, ProfileSelectionStep, AppCategoriesStep, # Add Timezone, Mirror etc.
                                  SummaryStep, InstallProgressStep ]
        self.step_widgets_instances = []
        for StepCls in self.step_definitions: inst=StepCls(self.config_data,self); self.step_widgets_instances.append(inst); self.cfg_stack.addWidget(inst)
    def select_step(self, idx, force_show=False):
        if not(0<=idx<len(self.step_widgets_instances)): return
        is_target_inst=isinstance(self.step_widgets_instances[idx],InstallProgressStep); is_curr_summ=self.current_step_idx>=0 and isinstance(self.step_widgets_instances[self.current_step_idx],SummaryStep)
        if is_target_inst and not is_curr_summ and not force_show: return
        self.current_step_idx=idx; self.cfg_stack.setCurrentIndex(idx); curr_w=self.step_widgets_instances[idx]; curr_w.load_ui_from_config(); curr_w.on_entry(); self.update_navigation_buttons()
    def update_navigation_buttons(self): is_first=(self.current_step_idx==0); is_inst=False; is_summ=False;
                                   if 0<=self.current_step_idx<len(self.step_widgets_instances): curr_w=self.step_widgets_instances[self.current_step_idx]; is_summ=isinstance(curr_w,SummaryStep); is_inst=isinstance(curr_w,InstallProgressStep)
                                   self.prev_btn.setEnabled(not is_first and not is_inst); self.next_btn.setVisible(not is_summ and not is_inst); self.inst_btn.setVisible(is_summ and not is_inst)
                                   if is_inst: self.prev_btn.setEnabled(False); self.next_btn.setVisible(False); self.inst_btn.setVisible(False)
    def navigate_next(self): curr_w=self.step_widgets_instances[self.current_step_idx];
                        if not curr_w.on_exit() or not curr_w.save_config_from_ui(): return
                        if self.current_step_idx < len(self.step_widgets_instances)-1: self.select_step(self.current_step_idx+1)
    def navigate_prev(self):
        if not self.step_widgets_instances[self.current_step_idx].on_exit(going_back=True): return
        if self.current_step_idx > 0: self.select_step(self.current_step_idx-1)
    def confirm_and_start_installation(self):
        if not isinstance(self.step_widgets_instances[self.current_step_idx],SummaryStep): return
        self.step_widgets_instances[self.current_step_idx].on_entry() # Refresh summary
        if QMessageBox.question(self,"Confirm Install",f"Start installing {self.config_data.get('os_name',APP_NAME)}?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            for i,s in enumerate(self.step_widgets_instances):
                if isinstance(s,InstallProgressStep): self.select_step(i,force_show=True); self.start_backend_installation(); break
    def start_backend_installation(self): self.appendToLog("Starting OS install...","INFO"); self.update_navigation_buttons(); self.installation_thread = InstallationThread(self.config_data.copy()); self.installation_thread.log_signal.connect(lambda m: self.appendToLog(m,"INSTALL")); prog_w=self.step_widgets_instances[self.current_step_idx];
                                    if isinstance(prog_w,InstallProgressStep): self.installation_thread.progress_signal.connect(prog_w.update_ui_progress); self.installation_thread.finished_signal.connect(prog_w.set_final_status)
                                    self.installation_thread.finished_signal.connect(self.on_installation_finished); self.installation_thread.start()
    def on_installation_finished(self, suc, msg):
        self.appendToLog(f"OS Install Done: Success={suc}","RESULT"); prog_w=self.step_widgets_instances[self.current_step_idx];
        if isinstance(prog_w, InstallProgressStep): prog_w.set_final_status(suc, msg)
        # Removed call to run_final_setup_script - assuming archinstall handles everything now
        if suc: QMessageBox.information(self,"Complete",f"{self.config_data.get('os_name',APP_NAME)} install complete.\nReboot system.")
        else: QMessageBox.critical(self,"Install Failed", msg+"\nCheck logs.")
        # Optionally re-enable prev button to review summary/config if install failed?
        # self.prev_btn.setEnabled(True) # Allow going back from progress screen ONLY if failed?

    # run_final_setup_script and related logic/worker can be removed if not needed
    # def run_final_setup_script(self): ...
    # def on_final_setup_script_finished(self, exit_code): ...
    # class ScriptRunner(QObject): ... # Remove this class

    def appendToLog(self, txt, lvl="DEBUG"): ts=time.strftime("%H:%M:%S"); self.log_out.appendPlainText(f"[{ts}][{lvl.upper()}] {txt}"); sb=self.log_out.verticalScrollBar();sb.setValue(sb.maximum()); QApplication.processEvents()
    def closeEvent(self, event): busy=(self.installation_thread and self.installation_thread.isRunning());# or (self.post_install_thread and self.post_install_thread.isRunning()); # Remove post_install check
                          if busy and QMessageBox.question(self,"Exit","Process running. Abort?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.appendToLog("User aborted.","WARN"); event.accept()
                          elif not busy: super().closeEvent(event)
                          else: event.ignore()

# --- Worker class for post-install script (REMOVED) ---
# class ScriptRunner(QObject): ...

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    if not os.path.exists(LOGO_PATH): print(f"Warning: Logo '{LOGO_FILENAME}' missing.")
    if not ARCHINSTALL_AVAILABLE: QMessageBox.critical(None,f"{APP_NAME} Error","Fatal: 'archinstall' library not found."); sys.exit(1)
    if os.geteuid() != 0: QMessageBox.critical(None, f"{APP_NAME} Error", "Fatal: This installer requires root privileges (run with sudo)."); sys.exit(1)

    main_win = MaiBloomOSInstallerWindow()
    main_win.show()
    sys.exit(app.exec_())

