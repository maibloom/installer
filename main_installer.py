#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import subprocess
import traceback
import logging

# --- Privilege & Import Checks ---
if os.geteuid() != 0: print("ERROR: Run with sudo."); sys.exit(1)
try:
    import archinstall
    # from archinstall import ... # Import specifics as needed
    ARCHINSTALL_AVAILABLE = True
except ImportError: print("ERROR: 'archinstall' library not found."); sys.exit(1)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSplitter,
    QScrollArea, QPlainTextEdit, QPushButton, QMessageBox, QFrame, QGroupBox,
    QComboBox, QLineEdit, QCheckBox, QGridLayout, QAction, QMenuBar
)
from PyQt5.QtGui import QIcon, QFontDatabase, QFont, QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot

# --- Configuration ---
APP_NAME = "Mai Bloom OS Installer (Simple)"
LOGO_FILENAME = "logo.png"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(SCRIPT_DIR, LOGO_FILENAME)

DEFAULT_CONFIG = { # Align keys with likely archinstall config names
    'locale': 'en_US.UTF-8', 'keyboard_layout': 'us',
    'mirror_region': 'Worldwide', # archinstall likely uses region code/name
    'harddrives': [], # List of target disks (e.g., ['/dev/sda'])
    'disk_config': {'!layout': {}}, # Placeholder for layout config, e.g. '/dev/sda': {'wipe': True, 'filesystem': 'ext4'}
    'disk_encryption': None, # {'password': '...', etc.}
    'hostname': 'maibloom-pc',
    '!users': [], # [{'username':'x','password':'y','sudo':True}]
    '!root-password': '',
    'profile': 'kde', # Profile name archinstall recognizes
    'packages': [], # Base list for additional/category packages
    'timezone': 'Asia/Tehran',
    'kernels': ['linux'],
    'nic': 'NetworkManager', # Or 'dhcpcd' etc.
    'audio': 'pipewire', # Common default
    'swap': True,
    'bootloader': 'systemd-boot' if os.path.exists('/sys/firmware/efi') else 'grub',
    # Custom GUI state (not passed directly to archinstall usually)
    '_app_categories': [],
    '_os_brand_name': 'Mai Bloom OS' # For branding inside chroot
}

# --- Stylesheet Constant ---
DARK_THEME_QSS="""QMainWindow, QWidget{background-color:#2E2E2E;color:#E0E0E0;font-size:10pt}QScrollArea{border:none}QGroupBox{border:1px solid #4A4A4A;border-radius:5px;margin-top:1ex;font-weight:bold;color:#00BFFF}QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;padding:0 5px;background-color:#2E2E2E}QLabel{color:#E0E0E0;margin-bottom:2px}QPushButton{padding:8px 15px;border-radius:4px;background-color:#555;color:#FFF;border:1px solid #686868;font-weight:bold}QPushButton:hover{background-color:#686868}QPushButton:disabled{background-color:#404040;color:#808080}QPushButton#InstallButton{background-color:#4CAF50;border-color:#388E3C}QPushButton#InstallButton:hover{background-color:#388E3C}QPlainTextEdit#LogOutput{background-color:#1C1C1C;color:#C0C0C0;border:1px solid #434343;font-family:"Monospace"}QLineEdit,QComboBox{padding:6px 8px;border:1px solid #555;border-radius:4px;background-color:#3D3D3D;color:#E0E0E0}QCheckBox{margin:5px 0;color:#E0E0E0}QCheckBox::indicator{width:16px;height:16px;background-color:#555;border:1px solid #686868;border-radius:3px}QCheckBox::indicator:checked{background-color:#007BFF}QProgressBar{text-align:center;padding:1px;border-radius:5px;background-color:#555;border:1px solid #686868;color:#E0E0E0;min-height:20px}QProgressBar::chunk{background-color:#007BFF;border-radius:4px}"""

# --- Utility Functions (Using Archinstall) ---
# (Keep these as previously defined, using archinstall calls)
def get_keyboard_layouts(): try: return sorted(archinstall.list_keyboard_languages()) except Exception: return ["us"]
def get_locales(): return ["en_US.UTF-8", "en_GB.UTF-8", "fa_IR.UTF-8"] # Curated
def get_block_devices_info():
    try: raw_devs=archinstall.list_block_devices(human_readable=False); devs=[];
         for p,d in raw_devs.items(): dtype=getattr(d,'type','').lower(); size=getattr(d,'size',0)
         if dtype=='disk' and isinstance(size,int) and size>(1*1024**3): devs.append({'name':p,'size':size,'label':getattr(d,'label',None)})
         return devs
    except Exception as e: print(f"ERR disks: {e}"); return []
def get_mirror_regions(): try: r=archinstall.list_mirror_regions(); return r if r else {"Worldwide":"WW"} except Exception: return {"Worldwide":"WW"}
def get_timezones(): try: z=archinstall.list_timezones(); return z if z else {"UTC":["UTC"]} except Exception: return {"UTC":["UTC"]}
def get_profiles(): try: p_dict=archinstall.profile.list_profiles(); p_list=[{"name":n,"desc":getattr(p,'desc','')} for n,p in p_dict.items() if not n.startswith('_')]; return p_list if p_list else [{"name":"Minimal","desc":"Basic"}] except Exception: return [{"name":"Minimal","desc":"Basic"}]

# --- Qt Log Handler ---
class QtLogHandler(logging.Handler):
    def __init__(self,log_signal):super().__init__();self.sig=log_signal;self.setFormatter(logging.Formatter('%(levelname)s:%(message)s'))
    def emit(self,record):self.sig.emit(self.format(record))

# --- Installation Thread ---
class InstallationThread(QThread):
    log_signal = pyqtSignal(str); progress_signal = pyqtSignal(int, str); finished_signal = pyqtSignal(bool, str)
    def __init__(self, config): super().__init__(); self.config = config
    def setup_logging(self): log=logging.getLogger('archinstall'); log.setLevel(logging.INFO);
                           if not any(isinstance(h,QtLogHandler) for h in log.handlers): log.addHandler(QtLogHandler(self.log_signal)); self.log_signal.emit("Log capture setup.")
    def map_categories_to_packages(self, cats): mapping={"Programming":["git","code"],"Gaming":["steam"],"Office":["libreoffice-fresh"],"Graphics":["gimp"]}; pkgs=set(); [pkgs.update(mapping.get(c,[])) for c in cats]; return list(pkgs)

    def run(self):
        self.setup_logging(); self.log_signal.emit("Starting install thread..."); self.progress_signal.emit(0,"Preparing...")
        try:
            # 1. Prepare the final config dict for archinstall
            ai_conf = self.config.copy()
            
            # Consolidate locale/keyboard if archinstall expects that
            ai_conf['keyboard_layout'] = ai_conf.pop('kb_layout', DEFAULT_CONFIG['locale_config']['kb_layout'])
            ai_conf['locale'] = ai_conf.pop('sys_lang', DEFAULT_CONFIG['locale_config']['sys_lang'])
            ai_conf.pop('locale_config', None) # Remove the GUI structure key
            
            # Consolidate disk config - THIS IS HIGHLY SPECULATIVE
            # Assuming archinstall wants a dict like {'/dev/sda': {'wipe': True, ...}}
            target_disk = ai_conf.pop('harddrives', [])[0] if ai_conf.get('harddrives') else None
            if not target_disk: raise ValueError("Target disk not specified.")
            filesystem = ai_conf.pop('disk_filesystem', DEFAULT_CONFIG['disk_config']['filesystem'])
            ai_conf['disk_config'] = {'!layout': { target_disk: {'wipe': True, 'filesystem': {'format': filesystem}}}}
            
            # Encryption setup (adjust based on actual archinstall structure)
            if ai_conf.get('disk_encrypt'): ai_conf['disk_encryption'] = [{'device': target_disk, 'password': ai_conf.pop('disk_encrypt_password'), 'type': 'luks'}]
            else: ai_conf.pop('disk_encryption', None); ai_conf.pop('disk_encrypt_password', None)
            
            # User setup
            users = []
            if ai_conf.get('username'): users.append({'username': ai_conf['username'], 'password': ai_conf.pop('user_password'), 'sudo': ai_conf.pop('user_sudo')})
            ai_conf['!users'] = users
            ai_conf['!root-password'] = ai_conf.pop('root_password')
            
            # Profile
            profile_name = ai_conf.pop('profile_name', DEFAULT_CONFIG['profile'])
            ai_conf['profile'] = profile_name if profile_name != 'Minimal' else None

            # Packages
            category_pkgs = self.map_categories_to_packages(ai_conf.get('_app_categories', []))
            additional_pkgs = ai_conf.get('packages', []) # Keep packages key if needed
            ai_conf['packages'] = list(set(category_pkgs + additional_pkgs))
            
            # Branding/Config commands to run inside chroot
            # Archinstall *might* have a key for this, e.g., 'post_chroot_commands' or 'custom_commands'
            # Or we might need to call a function like archinstall.run_command(cmd, chroot=True) later
            # Let's assume a key for simplicity:
            branding_name = ai_conf.pop('_os_brand_name', 'Mai Bloom OS')
            ai_conf['custom_commands'] = [
                f'sed -i \'s/^PRETTY_NAME=.*/PRETTY_NAME="{branding_name}"/\' /etc/os-release',
                # f'sed -i \'s/^NAME=.*/NAME="{branding_name}"/\' /etc/os-release', # Optional
                # f'echo \'GRUB_DISTRIBUTOR="{branding_name}"\' >> /etc/default/grub', # Append or sed
                # 'grub-mkconfig -o /boot/grub/grub.cfg' # If GRUB is used and command needed
            ]
            
            # Clean up keys not used by archinstall's main function
            ai_conf.pop('mirror_region_display_name', None); ai_conf.pop('mirror_region_code', None) # Assuming 'mirror_region' is used
            ai_conf.pop('_app_categories', None) # Remove the GUI helper key

            log_cfg={k:v for k,v in ai_conf.items() if k not in ['!users','!root-password','disk_encryption']}
            self.log_signal.emit(f"Final Archinstall Config: {log_cfg}")
            self.progress_signal.emit(5, "Starting installation...")

            # ---!!! CALL ACTUAL ARCHINSTALL !!!---
            # Replace MOCK with the real call, e.g.:
            # archinstall.perform_installation(config=ai_conf, mount_point='/mnt', ...)
            self.log_signal.emit("Calling archinstall (MOCK)..."); time.sleep(1)
            self.progress_signal.emit(10,"Disk (mock)..."); time.sleep(1)
            self.progress_signal.emit(40,"Packages (mock)..."); time.sleep(2)
            self.progress_signal.emit(80,"Config (mock)..."); time.sleep(1)
            self.progress_signal.emit(100,"Done (mock)..."); time.sleep(0.5)
            # --- End MOCK ---

            self.log_signal.emit("Installation finished."); self.finished_signal.emit(True, f"{DEFAULT_CONFIG['os_name']} install complete (sim).")
        except Exception as e: self.log_signal.emit(f"FATAL error: {e}\n{traceback.format_exc()}"); self.finished_signal.emit(False, f"Install failed: {e}")


# --- Step Widget Base Class (removed logo logic) ---
class ConfigSectionWidget(QGroupBox): # Use QGroupBox for sections
    def __init__(self, title, config_ref, main_window_ref):
        super().__init__(title)
        self.config = config_ref
        self.main_window = main_window_ref
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setSpacing(10)
        self.content_layout.setContentsMargins(10, 20, 10, 10) # Adjusted margins for groupbox title
        # Optional: Add logo here if still desired per section? Seems cluttered.
        # self.logo_label = QLabel(); ...; self.content_layout.addWidget(self.logo_label)

    def load_ui_from_config(self): pass # Subclasses implement
    def save_config_from_ui(self): return True # Subclasses implement validation

# --- Concrete Config Section Widgets ---
# (These are now QGroupBox subclasses, placed within the scroll area)
class LocaleKeyboardSection(ConfigSectionWidget):
    def __init__(self, config, main_ref):
        super().__init__("🌍 Language & Keyboard", config, main_ref)
        layout = QGridLayout(); layout.setSpacing(10) # Use grid for alignment
        layout.addWidget(QLabel("System Locale:"), 0, 0); self.locale_combo=QComboBox(); self.locale_combo.addItems(get_locales()); layout.addWidget(self.locale_combo, 0, 1)
        layout.addWidget(QLabel("Keyboard Layout:"), 1, 0); self.kb_combo=QComboBox(); self.kb_combo.addItems(get_keyboard_layouts()); layout.addWidget(self.kb_combo, 1, 1)
        self.content_layout.addLayout(layout)
    def load_ui_from_config(self): self.locale_combo.setCurrentText(self.config.get('locale', DEFAULT_CONFIG['locale'])); self.kb_combo.setCurrentText(self.config.get('keyboard_layout', DEFAULT_CONFIG['keyboard_layout']))
    def save_config_from_ui(self): self.config['locale']=self.locale_combo.currentText(); self.config['keyboard_layout']=self.kb_combo.currentText(); return bool(self.config['locale'] and self.config['keyboard_layout'])

class DiskSection(ConfigSectionWidget):
    def __init__(self, config, main_ref):
        super().__init__("💾 Disk Setup (Guided Wipe)", config, main_ref)
        expl = QLabel("<b style='color:yellow;'>WARNING: This will WIPE the selected disk.</b> Choose carefully."); expl.setTextFormat(Qt.RichText); self.content_layout.addWidget(expl)
        layout = QGridLayout(); layout.setSpacing(10)
        layout.addWidget(QLabel("Target Disk:"), 0, 0); self.disk_combo=QComboBox(); layout.addWidget(self.disk_combo, 0, 1)
        layout.addWidget(QLabel("Filesystem:"), 1, 0); self.fs_combo=QComboBox(); self.fs_combo.addItems(['ext4','btrfs','xfs']); layout.addWidget(self.fs_combo, 1, 1)
        self.encrypt_cb=QCheckBox("Encrypt Disk (LUKS)"); layout.addWidget(self.encrypt_cb, 2, 0, 1, 2)
        self.encrypt_pw=QLineEdit(); self.encrypt_pw.setPlaceholderText("Encryption Passphrase (if checked)"); self.encrypt_pw.setEchoMode(QLineEdit.Password); self.encrypt_pw.setEnabled(False); layout.addWidget(self.encrypt_pw, 3, 0, 1, 2)
        self.encrypt_cb.toggled.connect(self.encrypt_pw.setEnabled)
        self.content_layout.addLayout(layout); self.populate_disks()
    def populate_disks(self): cur=self.config.get('harddrives',[None])[0]; self.disk_combo.clear(); devs=get_block_devices_info();
                          if not devs: self.disk_combo.addItem("No disks found."); self.disk_combo.setEnabled(False); return
                          self.disk_combo.setEnabled(True); sel=0;
                          for i,d in enumerate(devs): sz=d.get('size',0)/(1024**3); self.disk_combo.addItem(f"{d['name']} ({sz:.1f}GB)",d['name']);
                          if d['name']==cur: sel=i
                          if self.disk_combo.count()>0: self.disk_combo.setCurrentIndex(sel)
    def load_ui_from_config(self): self.populate_disks(); self.fs_combo.setCurrentText(self.config.get('disk_config',{}).get('filesystem',DEFAULT_CONFIG['disk_config']['filesystem'])); enc=self.config.get('disk_encryption') is not None; self.encrypt_cb.setChecked(enc); self.encrypt_pw.setEnabled(enc); self.encrypt_pw.clear()
    def save_config_from_ui(self):
        if self.disk_combo.currentIndex()<0 or not self.disk_combo.currentData(): QMessageBox.warning(self,"","Select disk."); return False
        disk=self.disk_combo.currentData(); self.config['harddrives']=[disk]; fs=self.fs_combo.currentText(); self.config['disk_config']={'!layout': {disk:{'wipe':True,'filesystem':{'format':fs}}}}
        if self.encrypt_cb.isChecked(): pw=self.encrypt_pw.text();
                                     if len(pw)<8: QMessageBox.warning(self,"","Encrypt pwd >= 8 chars."); return False
                                     self.config['disk_encryption']={'password':pw}; # archinstall needs more detail here
        else: self.config['disk_encryption']=None
        return True

class UserSection(ConfigSectionWidget):
    def __init__(self, config, main_ref):
        super().__init__("👤 User & Hostname", config, main_ref)
        layout = QGridLayout(); layout.setSpacing(10)
        layout.addWidget(QLabel("Hostname:"),0,0); self.hn=QLineEdit(); layout.addWidget(self.hn,0,1)
        layout.addWidget(QLabel("Root Pwd:"),1,0); self.rp=QLineEdit(); self.rp.setEchoMode(QLineEdit.Password); layout.addWidget(self.rp,1,1)
        layout.addWidget(QLabel("Confirm Root:"),2,0); self.rpc=QLineEdit(); self.rpc.setEchoMode(QLineEdit.Password); layout.addWidget(self.rpc,2,1)
        layout.addWidget(QLabel("Username:"),3,0); self.un=QLineEdit(); self.un.setPlaceholderText("Leave blank for no user"); layout.addWidget(self.un,3,1)
        layout.addWidget(QLabel("User Pwd:"),4,0); self.up=QLineEdit(); self.up.setEchoMode(QLineEdit.Password); layout.addWidget(self.up,4,1)
        layout.addWidget(QLabel("Confirm User:"),5,0); self.upc=QLineEdit(); self.upc.setEchoMode(QLineEdit.Password); layout.addWidget(self.upc,5,1)
        self.sudo=QCheckBox("Grant Admin (sudo)"); layout.addWidget(self.sudo,6,0,1,2)
        self.content_layout.addLayout(layout)
    def load_ui_from_config(self): self.hn.setText(self.config.get('hostname',DEFAULT_CONFIG['hostname'])); users=self.config.get('!users',[]); self.un.setText(users[0]['username'] if users else ''); self.sudo.setChecked(users[0]['sudo'] if users else True); self.rp.clear(); self.rpc.clear(); self.up.clear(); self.upc.clear()
    def save_config_from_ui(self):
        hn=self.hn.text().strip(); rp=self.rp.text(); usr=self.un.text().strip(); up=self.up.text();
        if not hn: QMessageBox.warning(self,"","Need hostname."); return False
        if len(rp)<8 or rp!=self.rpc.text(): QMessageBox.warning(self,"","Root pwd err."); return False
        self.config['hostname']=hn; self.config['!root-password']=rp; users=[]
        if usr:
            if len(up)<8 or up!=self.upc.text(): QMessageBox.warning(self,"","User pwd err."); return False
            users.append({'username':usr,'password':up,'sudo':self.sudo.isChecked()})
        self.config['!users']=users; return True

class ProfileAppsSection(ConfigSectionWidget):
     def __init__(self, config, main_ref):
        super().__init__("🖥️ Profile & Applications", config, main_ref)
        layout = QVBoxLayout(); layout.setSpacing(10)
        layout.addWidget(QLabel("Base System Profile:"))
        self.prof_combo=QComboBox(); self.profs=get_profiles(); [self.prof_combo.addItem(p['desc'], p['name']) for p in self.profs]
        layout.addWidget(self.prof_combo)
        layout.addWidget(QLabel("Application Categories (Optional):"))
        self.cats={"Programming":"💻","Gaming":"🎮","Office":"📄","Graphics":"🎨"}; self.cbs={}; grid=QGridLayout(); r,c=0,0
        for n,e in self.cats.items(): cb=QCheckBox(f"{e} {n}"); self.cbs[n]=cb; grid.addWidget(cb,r,c); c+=1;
        if c>=2: c=0;r+=1
        layout.addLayout(grid)
        self.content_layout.addLayout(layout)
     def load_ui_from_config(self): idx=self.prof_combo.findData(self.config.get('profile',DEFAULT_CONFIG['profile'])); self.prof_combo.setCurrentIndex(idx if idx!=-1 else 0); sel=self.config.get('_app_categories',[]); [cb.setChecked(n in sel) for n,cb in self.cbs.items()]
     def save_config_from_ui(self): self.config['profile']=self.prof_combo.currentData()or(self.profs[0]['name']if self.profs else None); self.config['_app_categories']=[n for n,cb in self.cbs.items() if cb.isChecked()]; return True

# --- Main Application Window (Simplified UI Flow) ---
class MaiBloomOSInstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_data = DEFAULT_CONFIG.copy()
        self.installation_thread = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"{APP_NAME} - Configuration"); self.setMinimumSize(1000, 750)
        if os.path.exists(LOGO_PATH): self.setWindowIcon(QIcon(LOGO_PATH))
        central = QWidget(); self.setCentralWidget(central)
        main_layout = QVBoxLayout(central) # Main layout is vertical

        # --- Top Menu Bar ---
        self.setup_menus()

        # --- Main Splitter (Config Scroll Area | Log Output) ---
        main_splitter = QSplitter(Qt.Horizontal)

        # --- Left Side: Scroll Area for Config Sections ---
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget(); scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15); scroll_layout.setContentsMargins(15, 15, 15, 15)

        # Add Configuration Sections (using QGroupBox subclass)
        self.config_sections = [
            LocaleKeyboardSection(self.config_data, self),
            DiskSection(self.config_data, self),
            UserSection(self.config_data, self),
            ProfileAppsSection(self.config_data, self),
            # Add more sections: Timezone, Mirrors, Bootloader etc.
        ]
        for section in self.config_sections:
            scroll_layout.addWidget(section)
        scroll_layout.addStretch(1) # Push sections to top
        scroll_area.setWidget(scroll_widget)
        main_splitter.addWidget(scroll_area) # Add scroll area to splitter

        # --- Right Side: Log Output ---
        self.log_out = QPlainTextEdit(); self.log_out.setReadOnly(True)
        log_font = QFontDatabase.systemFont(QFontDatabase.FixedFont); log_font.setPointSize(9); self.log_out.setFont(log_font)
        main_splitter.addWidget(self.log_out)

        main_splitter.setSizes([550, 450]); main_splitter.setStretchFactor(0, 1); main_splitter.setStretchFactor(1, 1)
        main_layout.addWidget(main_splitter, 1) # Splitter takes most space

        # --- Bottom: Install Button ---
        button_layout = QHBoxLayout(); button_layout.addStretch(1)
        self.install_button = QPushButton(f"🚀 Start Installation"); self.install_button.clicked.connect(self.confirm_and_start_installation)
        button_layout.addWidget(self.install_button); main_layout.addLayout(button_layout)

        self.appendToLog(f"{APP_NAME} ready.", "INFO"); self.apply_dark_theme()
        self.load_all_sections() # Load initial default/saved config

    def setup_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        exit_action = QAction("E&xit", self); exit_action.triggered.connect(self.close); file_menu.addAction(exit_action)
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self); about_action.triggered.connect(self.show_about); help_menu.addAction(about_action)

    def show_about(self): QMessageBox.about(self, f"About {APP_NAME}", f"<b>{APP_NAME}</b><p>A graphical installer for Mai Bloom OS, using the archinstall library.</p>")

    def apply_dark_theme(self): self.setStyleSheet(DARK_THEME_QSS); self.log_out.setObjectName("LogOutput"); self.install_button.setObjectName("InstallButton")

    def load_all_sections(self):
        self.appendToLog("Loading configuration into UI...", "DEBUG")
        for section in self.config_sections: section.load_ui_from_config()

    def save_and_validate_all_sections(self):
        self.appendToLog("Saving & Validating configuration...", "DEBUG")
        for section in self.config_sections:
            if not section.save_config_from_ui():
                self.appendToLog(f"Validation failed in section: {section.title()}", "ERROR")
                QMessageBox.warning(self, "Configuration Error", f"Please check the settings in the '{section.title()}' section.")
                return False # Stop on first validation error
        self.appendToLog("Configuration saved and validated.", "INFO")
        return True

    def confirm_and_start_installation(self):
        if not self.save_and_validate_all_sections(): return

        # Create a summary text
        summary_lines=[f"--- {self.config_data.get('os_name',APP_NAME)} Final Config ---"]
        order={'locale':"Locale",'keyboard_layout':"Keyboard",'harddrives':"Disk(s)",'hostname':"Hostname",'!root-password':"Root Pwd",'!users':"Users",'profile':"Profile",'packages':"Packages",'timezone':"Timezone"}
        for k,n in order.items():
            v=self.config_data.get(k)
            fv="<not set>";
            if k=='!users':fv=f"{len(v)} user(s)"if v else"None"
            elif "pass" in k and v:fv="<set>"
            elif isinstance(v,bool):fv="Yes"if v else"No"
            elif isinstance(v,list):fv=", ".join(v)if v else"<none>"
            elif v is not None and str(v).strip()!="":fv=str(v)
            summary_lines.append(f"{n:<15}: {fv}")
        summary_lines.append(f"\nTarget Disk(s): {self.config_data.get('harddrives')}")
        summary_text = "\n".join(summary_lines)

        reply=QMessageBox.question(self,"Confirm Install",f"Start installation with this config?\n\n{summary_text}\n\n<font color='red'><b>WARNING: Disk(s) will be modified!</b></font>",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if reply==QMessageBox.Yes: self.start_backend_installation()

    def start_backend_installation(self):
        self.appendToLog("Starting OS install thread...","INFO")
        self.install_button.setEnabled(False) # Disable button during install
        # Disable config sections? Maybe not needed if install runs quickly or modals are used.
        
        self.installation_thread = InstallationThread(self.config_data.copy())
        self.installation_thread.log_signal.connect(lambda m: self.appendToLog(m,"INSTALL"))
        # Need a way to display progress - maybe add a status bar?
        # For simplicity, log output is the main feedback now.
        # self.installation_thread.progress_signal.connect(self.update_progress_display) # Need progress display widget
        self.installation_thread.finished_signal.connect(self.on_installation_finished)
        self.installation_thread.start()

    def on_installation_finished(self, suc, msg):
        self.appendToLog(f"OS Install Done: Success={suc}","RESULT")
        if suc: QMessageBox.information(self,"Complete",f"{self.config_data.get('os_name',APP_NAME)} install complete.\nReboot system.")
        else: QMessageBox.critical(self,"Install Failed", msg+"\nCheck logs.")
        self.install_button.setEnabled(True) # Re-enable button

    def appendToLog(self, txt, lvl="DEBUG"): ts=time.strftime("%H:%M:%S"); self.log_out.appendPlainText(f"[{ts}][{lvl.upper()}] {txt}"); sb=self.log_out.verticalScrollBar();sb.setValue(sb.maximum()); QApplication.processEvents()

    def closeEvent(self, event):
        if self.installation_thread and self.installation_thread.isRunning():
            if QMessageBox.question(self,"Exit","Install running. Abort?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.appendToLog("User aborted.","WARN"); event.accept()
            else: event.ignore()
        else: super().closeEvent(event)

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    if not os.path.exists(LOGO_PATH): print(f"Warning: Logo '{LOGO_FILENAME}' missing.")
    # Checks for root and archinstall are at the top
    main_win = MaiBloomOSInstallerWindow()
    main_win.show()
    sys.exit(app.exec_())

