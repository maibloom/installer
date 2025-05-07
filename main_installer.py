#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import subprocess
import traceback
import logging

# --- Privilege Check ---
if os.geteuid() != 0:
    print("ERROR: Run with sudo."); sys.exit(1)
    # Minimal GUI error if possible
    try: from PyQt5.QtWidgets import QApplication,QMessageBox; a=QApplication.instance() or QApplication(sys.argv); QMessageBox.critical(None,"Root Required","Run with 'sudo'.");
    except Exception: pass
    sys.exit(1)

# --- Attempt Archinstall Import ---
try:
    import archinstall
    ARCHINSTALL_AVAILABLE = True
except ImportError:
    print("ERROR: 'archinstall' library not found.");
    try: from PyQt5.QtWidgets import QApplication,QMessageBox; a=QApplication.instance() or QApplication(sys.argv); QMessageBox.critical(None,"Error","'archinstall' not found.");
    except Exception: pass
    sys.exit(1)

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
# POST_INSTALL_SCRIPT_NAME = "final_setup.sh" # Removed

DEFAULT_CONFIG = { # Structure to align more closely with potential archinstall needs
    'os_name': 'Mai Bloom OS',
    'locale': 'en_US.UTF-8', 'keyboard_layout': 'us', # Moved from locale_config
    'mirror_region': 'Worldwide',
    'harddrives': [], # Target disk path(s) go here
    'disk_config': {'!layout': {}}, # Dict defining layout per disk
    'disk_encryption': None,
    'hostname': 'maibloom-pc',
    '!users': [],
    '!root-password': '',
    'profile': 'kde',
    '_app_categories': [], # GUI internal state
    'packages': [], # Final list passed to archinstall
    'timezone': 'Asia/Tehran',
    'kernels': ['linux'],
    'nic': 'NetworkManager',
    'audio': 'pipewire', # Simplified key? Check archinstall
    'swap': True,
    'bootloader': 'systemd-boot' if os.path.exists('/sys/firmware/efi') else 'grub',
    '_os_brand_name': 'Mai Bloom OS' # For branding inside chroot
}


# --- Stylesheet Constant ---
DARK_THEME_QSS="""QMainWindow,QWidget{font-size:10pt;background-color:#2E2E2E;color:#E0E0E0}QScrollArea{border:none}QGroupBox{border:1px solid #4A4A4A;border-radius:5px;margin-top:1ex;font-weight:bold;color:#00BFFF}QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;padding:0 5px;background-color:#2E2E2E}QLabel{color:#E0E0E0;margin-bottom:2px}QPushButton{padding:8px 15px;border-radius:4px;background-color:#555;color:#FFF;border:1px solid #686868;font-weight:bold}QPushButton:hover{background-color:#686868}QPushButton:disabled{background-color:#404040;color:#808080}QPushButton#InstallButton{background-color:#4CAF50;border-color:#388E3C}QPushButton#InstallButton:hover{background-color:#388E3C}QPlainTextEdit#LogOutput{background-color:#1C1C1C;color:#C0C0C0;border:1px solid #434343;font-family:"Monospace"}QLineEdit,QComboBox{padding:6px 8px;border:1px solid #555;border-radius:4px;background-color:#3D3D3D;color:#E0E0E0}QCheckBox{margin:5px 0;color:#E0E0E0}QCheckBox::indicator{width:16px;height:16px;background-color:#555;border:1px solid #686868;border-radius:3px}QCheckBox::indicator:checked{background-color:#007BFF}QProgressBar{text-align:center;padding:1px;border-radius:5px;background-color:#555;border:1px solid #686868;color:#E0E0E0;min-height:20px}QProgressBar::chunk{background-color:#007BFF;border-radius:4px}"""

# --- Text Constants ---
WELCOME_STEP_HTML=(f"<h2>Welcome to {APP_NAME}!</h2><p>Installer guide...</p><h3>Notes:</h3><ul><li>Internet recommended.</li><li>Backup data!</li><li>Disk ops may erase data.</li></ul><p>Click below to configure.</p>") # Adjusted text slightly
LANGUAGE_STEP_EXPLANATION="Select system language (menus, messages)."
KEYBOARD_STEP_EXPLANATION="Choose layout matching your keyboard."
SELECT_DISK_STEP_EXPLANATION="Choose install disk.<br><b style='color:yellow;'>Data may be erased.</b>"
APP_CATEGORIES_EXPLANATION="Select app types for initial setup."
SUMMARY_STEP_INTRO_TEXT="Review settings. <b style='color:yellow;'>Install button modifies disk!</b>" # Reverted for clarity


# --- Utility Functions (Using Archinstall - CORRECTED get_keyboard_layouts) ---
def get_keyboard_layouts():
    """Gets keyboard layouts using archinstall, with fallback."""
    try:
        # This is the assumed archinstall function call
        layouts = archinstall.list_keyboard_languages()
        return sorted(layouts) if layouts else ["us"] # Return sorted list or fallback
    except AttributeError:
        print("WARN: archinstall.list_keyboard_languages function not found. Using fallback.")
    except Exception as e:
        # Log the specific error for debugging
        print(f"WARN: Error getting keyboard layouts via archinstall: {e}. Using fallback.")
    # Fallback list if try block fails
    return ["us", "uk", "de", "fr", "es", "ir", "fa"]

def get_locales(): print("WARN: get_locales() using curated list."); return ["en_US.UTF-8", "en_GB.UTF-8", "de_DE.UTF-8", "fa_IR.UTF-8"] # Curated
def get_block_devices_info():
    try: raw_devs=archinstall.list_block_devices(human_readable=False); devs=[];
         for p,d in raw_devs.items(): dtype=getattr(d,'type','').lower(); size=getattr(d,'size',0)
         if dtype=='disk' and isinstance(size,int) and size>(1*1024**3): devs.append({'name':p,'size':size,'type':dtype,'label':getattr(d,'label',None)})
         if not devs: print("WARN: No suitable disks found by archinstall.")
         return devs
    except Exception as e: print(f"ERROR get_block_devices_info: {e}"); return []
def get_mirror_regions(): try: r=archinstall.list_mirror_regions(); return r if r else {"Worldwide":"WW"} except Exception as e: print(f"WARN get_mirror_regions: {e}"); return {"Worldwide":"WW"}
def get_timezones(): try: z=archinstall.list_timezones(); return z if z else {"UTC":["UTC"]} except Exception as e: print(f"WARN get_timezones: {e}"); return {"UTC":["UTC"]}
def get_profiles(): try: p_dict=archinstall.profile.list_profiles(); p_list=[{"name":n,"desc":getattr(p,'desc','')} for n,p in p_dict.items() if not n.startswith('_')]; return p_list if p_list else [{"name":"Minimal","desc":"Basic"}] except Exception as e: print(f"WARN get_profiles: {e}"); return [{"name":"Minimal","description":"Basic system."}]

# --- Qt Log Handler ---
class QtLogHandler(logging.Handler):
    def __init__(self,log_signal):super().__init__();self.sig=log_signal;self.setFormatter(logging.Formatter('%(levelname)s:%(message)s'))
    def emit(self,record):self.sig.emit(self.format(record))

# --- Installation Thread ---
# (Remains unchanged from previous version, still uses MOCK calls)
class InstallationThread(QThread):
    log_signal = pyqtSignal(str); progress_signal = pyqtSignal(int, str); finished_signal = pyqtSignal(bool, str)
    def __init__(self, config): super().__init__(); self.config = config
    def setup_logging(self): log=logging.getLogger('archinstall');log.setLevel(logging.INFO);
                           if not any(isinstance(h,QtLogHandler) for h in log.handlers): log.addHandler(QtLogHandler(self.log_signal)); self.log_signal.emit("Log capture setup.")
    def map_categories_to_packages(self, cats): mapping={"Programming":["git","code"],"Gaming":["steam"],"Office":["libreoffice-fresh"],"Graphics":["gimp"]}; pkgs=set(); [pkgs.update(mapping.get(c,[])) for c in cats]; return list(pkgs)
    def run(self):
        self.setup_logging(); self.log_signal.emit("Starting install thread..."); self.progress_signal.emit(0,"Preparing...")
        try: ai_conf = self.config.copy(); ai_conf['keyboard_layout']=ai_conf.pop('kb_layout', DEFAULT_CONFIG['keyboard_layout']); ai_conf['locale']=ai_conf.pop('sys_lang', DEFAULT_CONFIG['locale']); ai_conf.pop('locale_config', None)
             ai_conf['mirror_region']=ai_conf.pop('mirror_region_code', DEFAULT_CONFIG['mirror_region']); ai_conf.pop('mirror_region_display_name', None)
             target_disk = ai_conf.pop('harddrives', [])[0] if ai_conf.get('harddrives') else None
             if not target_disk: raise ValueError("Target disk not specified.")
             filesystem = ai_conf.pop('disk_filesystem', DEFAULT_CONFIG['disk_config']['filesystem'])
             ai_conf['disk_config'] = {'!layout': { target_disk: {'wipe': True, 'filesystem': {'format': filesystem}}}}
             if ai_conf.get('disk_encrypt'): ai_conf['disk_encryption'] = [{'device': target_disk, 'password': ai_conf.pop('disk_encrypt_password'), 'type': 'luks'}]
             else: ai_conf.pop('disk_encryption', None); ai_conf.pop('disk_encrypt_password', None)
             users = [];
             if ai_conf.get('username'): users.append({'username': ai_conf['username'], 'password': ai_conf.pop('user_password'), 'sudo': ai_conf.pop('user_sudo')})
             ai_conf['!users'] = users; ai_conf['!root-password'] = ai_conf.pop('root_password')
             profile_name = ai_conf.pop('profile_name', DEFAULT_CONFIG['profile'])
             ai_conf['profile'] = profile_name if profile_name != 'Minimal' else None
             category_pkgs = self.map_categories_to_packages(ai_conf.get('_app_categories', [])); additional_pkgs = ai_conf.get('packages', [])
             ai_conf['packages'] = list(set(category_pkgs + additional_pkgs)); branding_name = ai_conf.pop('_os_brand_name', 'Mai Bloom OS')
             ai_conf['custom_commands'] = [f'sed -i \'s/^PRETTY_NAME=.*/PRETTY_NAME="{branding_name}"/\' /etc/os-release'] # Example branding command
             ai_conf.pop('_app_categories', None); ai_conf.pop('disk_filesystem', None); ai_conf.pop('disk_encrypt', None); ai_conf.pop('username', None); ai_conf.pop('user_sudo', None); # Clean up GUI keys
             log_cfg={k:v for k,v in ai_conf.items() if k not in ['!users','!root-password','disk_encryption'] and 'pass' not in k.lower()}
             self.log_signal.emit(f"Final Archinstall Config: {log_cfg}"); self.progress_signal.emit(5, "Starting installation...")
             # ---!!! CALL ACTUAL ARCHINSTALL !!!---
             self.log_signal.emit("Calling archinstall (MOCK)..."); time.sleep(1)
             self.progress_signal.emit(10,"Disk (mock)..."); time.sleep(1); self.progress_signal.emit(40,"Packages (mock)..."); time.sleep(2); self.progress_signal.emit(80,"Config (mock)..."); time.sleep(1); self.progress_signal.emit(100,"Done (mock)..."); time.sleep(0.5)
             self.log_signal.emit("Installation finished."); self.finished_signal.emit(True, f"{DEFAULT_CONFIG['os_name']} install complete (sim).")
        except Exception as e: self.log_signal.emit(f"FATAL error: {e}\n{traceback.format_exc()}"); self.finished_signal.emit(False, f"Install failed: {e}")

# --- Config Section Widget Base Class ---
class ConfigSectionWidget(QGroupBox):
    def __init__(self, title, config_ref, main_window_ref):
        super().__init__(title); self.config=config_ref; self.main_window=main_window_ref
        self.content_layout=QVBoxLayout(self); self.content_layout.setSpacing(10); self.content_layout.setContentsMargins(10,20,10,10)
    def load_ui_from_config(self): pass
    def save_config_from_ui(self): return True

# --- Concrete Config Section Widgets ---
class LocaleKeyboardSection(ConfigSectionWidget):
    def __init__(self, config, main_ref): super().__init__("🌍 Language & Keyboard", config, main_ref); layout=QGridLayout(); layout.setSpacing(10); layout.addWidget(QLabel("Locale:"),0,0); self.lc=QComboBox(); self.lc.addItems(get_locales()); layout.addWidget(self.lc,0,1); layout.addWidget(QLabel("Keyboard:"),1,0); self.kb=QComboBox(); self.kb.addItems(get_keyboard_layouts()); layout.addWidget(self.kb,1,1); self.content_layout.addLayout(layout)
    def load_ui_from_config(self): self.lc.setCurrentText(self.config.get('locale',DEFAULT_CONFIG['locale'])); self.kb.setCurrentText(self.config.get('keyboard_layout',DEFAULT_CONFIG['keyboard_layout']))
    def save_config_from_ui(self): lc=self.lc.currentText(); kb=self.kb.currentText(); self.config['locale']=lc; self.config['keyboard_layout']=kb; return bool(lc and kb or QMessageBox.warning(self,"","Select locale & keyboard."))
class DiskSection(ConfigSectionWidget):
    def __init__(self, config, main_ref): super().__init__("💾 Disk Setup (Guided Wipe)", config, main_ref); expl=QLabel("<b style='color:yellow;'>WIPES DISK!</b>"); expl.setTextFormat(Qt.RichText); self.content_layout.addWidget(expl); layout=QGridLayout(); layout.setSpacing(10); layout.addWidget(QLabel("Disk:"),0,0); self.dc=QComboBox(); layout.addWidget(self.dc,0,1); layout.addWidget(QLabel("FS:"),1,0); self.fs=QComboBox(); self.fs.addItems(['ext4','btrfs','xfs']); layout.addWidget(self.fs,1,1); self.enc_cb=QCheckBox("Encrypt"); layout.addWidget(self.enc_cb,2,0,1,2); self.enc_pw=QLineEdit(); self.enc_pw.setPlaceholderText("Encrypt Pwd"); self.enc_pw.setEchoMode(QLineEdit.Password); self.enc_pw.setEnabled(False); layout.addWidget(self.enc_pw,3,0,1,2); self.enc_cb.toggled.connect(self.enc_pw.setEnabled); self.content_layout.addLayout(layout); self.populate_disks()
    def populate_disks(self): cur=self.config.get('harddrives',[None])[0]; self.dc.clear(); devs=get_block_devices_info();
                          if not devs: self.dc.addItem("No disks."); self.dc.setEnabled(False); return
                          self.dc.setEnabled(True); sel=0;
                          for i,d in enumerate(devs): sz=d.get('size',0)/(1024**3); self.dc.addItem(f"{d['name']} ({sz:.1f}GB)",d['name']);
                          if d['name']==cur: sel=i
                          if self.dc.count()>0: self.dc.setCurrentIndex(sel)
    def load_ui_from_config(self): self.populate_disks(); self.fs.setCurrentText(self.config.get('disk_config',{}).get('filesystem',DEFAULT_CONFIG['disk_config']['filesystem'])); enc=self.config.get('disk_encryption')is not None; self.enc_cb.setChecked(enc); self.enc_pw.setEnabled(enc); self.enc_pw.clear()
    def save_config_from_ui(self):
        if self.dc.currentIndex()<0 or not self.dc.currentData(): QMessageBox.warning(self,"","Select disk."); return False
        disk=self.dc.currentData(); self.config['harddrives']=[disk]; fs=self.fs.currentText(); self.config['disk_config']={'!layout': {disk:{'wipe':True,'filesystem':{'format':fs}}}} # Simplified structure for config
        if self.enc_cb.isChecked(): pw=self.enc_pw.text();
                                     if len(pw)<8: QMessageBox.warning(self,"","Encrypt pwd >= 8 chars."); return False
                                     self.config['disk_encryption']={'password':pw}; # archinstall likely needs more detail (e.g., which partition)
        else: self.config['disk_encryption']=None
        return True
class UserSection(ConfigSectionWidget):
    def __init__(self, config, main_ref): super().__init__("👤 User & Hostname", config, main_ref); layout=QGridLayout(); layout.setSpacing(10); layout.addWidget(QLabel("Hostname:"),0,0); self.hn=QLineEdit(); layout.addWidget(self.hn,0,1); layout.addWidget(QLabel("Root Pwd:"),1,0); self.rp=QLineEdit(); self.rp.setEchoMode(QLineEdit.Password); layout.addWidget(self.rp,1,1); layout.addWidget(QLabel("Confirm:"),2,0); self.rpc=QLineEdit(); self.rpc.setEchoMode(QLineEdit.Password); layout.addWidget(self.rpc,2,1); layout.addWidget(QLabel("Username:"),3,0); self.un=QLineEdit(); self.un.setPlaceholderText("Leave blank if none"); layout.addWidget(self.un,3,1); layout.addWidget(QLabel("User Pwd:"),4,0); self.up=QLineEdit(); self.up.setEchoMode(QLineEdit.Password); layout.addWidget(self.up,4,1); layout.addWidget(QLabel("Confirm:"),5,0); self.upc=QLineEdit(); self.upc.setEchoMode(QLineEdit.Password); layout.addWidget(self.upc,5,1); self.sudo=QCheckBox("Admin (sudo)"); layout.addWidget(self.sudo,6,0,1,2); self.content_layout.addLayout(layout)
    def load_ui_from_config(self): self.hn.setText(self.config.get('hostname',DEFAULT_CONFIG['hostname'])); users=self.config.get('!users',[]); self.un.setText(users[0]['username'] if users else ''); self.sudo.setChecked(users[0]['sudo'] if users else True); self.rp.clear(); self.rpc.clear(); self.up.clear(); self.upc.clear()
    def save_config_from_ui(self): hn=self.hn.text().strip();rp=self.rp.text();usr=self.un.text().strip();up=self.up.text();
                             if not hn: QMessageBox.warning(self,"","Need hostname."); return False
                             if len(rp)<8 or rp!=self.rpc.text(): QMessageBox.warning(self,"","Root pwd err."); return False
                             self.config['hostname']=hn; self.config['!root-password']=rp; users=[]
                             if usr:
                                 if len(up)<8 or up!=self.upc.text(): QMessageBox.warning(self,"","User pwd err."); return False
                                 users.append({'username':usr,'password':up,'sudo':self.sudo.isChecked()})
                             self.config['!users']=users; return True
class ProfileAppsSection(ConfigSectionWidget):
     def __init__(self, config, main_ref): super().__init__("🖥️ Profile & Applications", config, main_ref); layout=QVBoxLayout(); layout.setSpacing(10); layout.addWidget(QLabel("Base Profile:")); self.prof_cb=QComboBox(); self.profs=get_profiles(); [self.prof_cb.addItem(p['desc'],p['name'])for p in self.profs]; layout.addWidget(self.prof_cb); layout.addWidget(QLabel("App Categories (Optional):")); self.cats={"Programming":"💻","Gaming":"🎮","Office":"📄","Graphics":"🎨"}; self.cbs={}; grid=QGridLayout();r,c=0,0;
                                         for n,e in self.cats.items():cb=QCheckBox(f"{e} {n}");self.cbs[n]=cb;grid.addWidget(cb,r,c);c+=1;
                                         if c>=2:c=0;r+=1
                                         layout.addLayout(grid); self.content_layout.addLayout(layout)
     def load_ui_from_config(self):idx=self.prof_cb.findData(self.config.get('profile',DEFAULT_CONFIG['profile']));self.prof_cb.setCurrentIndex(idx if idx!=-1 else 0);sel=self.config.get('_app_categories',[]);[cb.setChecked(n in sel)for n,cb in self.cbs.items()]
     def save_config_from_ui(self):self.config['profile']=self.prof_cb.currentData()or(self.profs[0]['name']if self.profs else None);self.config['_app_categories']=[n for n,cb in self.cbs.items() if cb.isChecked()];return True

# --- Main Application Window ---
class MaiBloomOSInstallerWindow(QMainWindow):
    def __init__(self): super().__init__(); self.config_data=DEFAULT_CONFIG.copy(); self.installation_thread=None; self.init_ui()
    def init_ui(self): self.setWindowTitle(f"{APP_NAME}"); self.setMinimumSize(1000,700);
                   if os.path.exists(LOGO_PATH): self.setWindowIcon(QIcon(LOGO_PATH));
                   central=QWidget(); self.setCentralWidget(central); main_layout=QVBoxLayout(central); self.setup_menus();
                   main_splitter=QSplitter(Qt.Horizontal); scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll_w=QWidget(); scroll_l=QVBoxLayout(scroll_w); scroll_l.setSpacing(15); scroll_l.setContentsMargins(15,15,15,15);
                   self.config_sections=[LocaleKeyboardSection(self.config_data,self), DiskSection(self.config_data,self), UserSection(self.config_data,self), ProfileAppsSection(self.config_data,self)]; # Add all sections
                   for sec in self.config_sections: scroll_l.addWidget(sec)
                   scroll_l.addStretch(1); scroll.setWidget(scroll_w); main_splitter.addWidget(scroll); self.log_out=QPlainTextEdit(); self.log_out.setReadOnly(True); log_f=QFontDatabase.systemFont(QFontDatabase.FixedFont);log_f.setPointSize(9);self.log_out.setFont(log_f); main_splitter.addWidget(self.log_out); main_splitter.setSizes([550,450]); main_splitter.setStretchFactor(0,1); main_splitter.setStretchFactor(1,1); main_layout.addWidget(main_splitter,1); btn_layout=QHBoxLayout(); btn_layout.addStretch(1); self.inst_btn=QPushButton("🚀 Install"); self.inst_btn.clicked.connect(self.confirm_and_start_installation); btn_layout.addWidget(self.inst_btn); main_layout.addLayout(btn_layout); self.appendToLog(f"{APP_NAME} ready.","INFO"); self.apply_dark_theme(); self.load_all_sections()
    def setup_menus(self): menu=self.menuBar(); fm=menu.addMenu("&File"); ex=QAction("E&xit",self);ex.triggered.connect(self.close);fm.addAction(ex); hm=menu.addMenu("&Help"); ab=QAction("&About",self);ab.triggered.connect(self.show_about);hm.addAction(ab)
    def show_about(self): QMessageBox.about(self,f"About {APP_NAME}",f"<b>{APP_NAME}</b><p>Installer using archinstall library.</p>")
    def apply_dark_theme(self): self.setStyleSheet(DARK_THEME_QSS); self.log_out.setObjectName("LogOutput"); self.inst_btn.setObjectName("InstallButton")
    def load_all_sections(self): self.appendToLog("Loading config...","DEBUG"); [sec.load_ui_from_config() for sec in self.config_sections]
    def save_and_validate_all_sections(self): self.appendToLog("Saving config...","DEBUG");
                                        for sec in self.config_sections:
                                            if not sec.save_config_from_ui(): self.appendToLog(f"Validation failed: {sec.title()}","ERROR"); QMessageBox.warning(self,"Error",f"Check settings in '{sec.title()}'."); return False
                                        self.appendToLog("Config saved.","INFO"); return True
    def confirm_and_start_installation(self):
        if not self.save_and_validate_all_sections(): return
        summary="Config Summary:\n" + "\n".join([f"- {k}: {'<set>' if 'pass' in k else v}" for k,v in self.config_data.items() if k not in ['disk_encryption']]) # Basic summary
        if QMessageBox.question(self,"Confirm Install",f"Start install with this config?\n{summary}\n\n<font color='red'><b>WARNING: Disk(s) WILL be modified!</b></font>",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.start_backend_installation()
    def start_backend_installation(self): self.appendToLog("Starting install thread...","INFO"); self.inst_btn.setEnabled(False); self.installation_thread=InstallationThread(self.config_data.copy()); self.installation_thread.log_signal.connect(lambda m: self.appendToLog(m,"INSTALL")); self.installation_thread.finished_signal.connect(self.on_installation_finished); self.installation_thread.start() # Add progress connection if display added
    def on_installation_finished(self, suc, msg): self.appendToLog(f"Install Done: Success={suc}","RESULT"); self.inst_btn.setEnabled(True);
                                          if suc: QMessageBox.information(self,"Complete",f"{self.config_data.get('os_name',APP_NAME)} install OK.\nReboot.")
                                          else: QMessageBox.critical(self,"Failed", msg+"\nCheck logs.")
    def appendToLog(self, txt, lvl="DEBUG"): ts=time.strftime("%H:%M:%S"); self.log_out.appendPlainText(f"[{ts}][{lvl.upper()}] {txt}"); sb=self.log_out.verticalScrollBar();sb.setValue(sb.maximum()); QApplication.processEvents()
    def closeEvent(self, event): busy=(self.installation_thread and self.installation_thread.isRunning());
                          if busy and QMessageBox.question(self,"Exit","Install running. Abort?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.appendToLog("User aborted.","WARN"); event.accept()
                          elif not busy: super().closeEvent(event)
                          else: event.ignore()

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    if not os.path.exists(LOGO_PATH): print(f"Warning: Logo '{LOGO_FILENAME}' missing.")
    # Root and archinstall checks are at the top
    main_win = MaiBloomOSInstallerWindow()
    main_win.show()
    sys.exit(app.exec_())
