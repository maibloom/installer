#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import subprocess
import traceback
import logging

# --- Privilege Check ---
if os.geteuid() != 0: print("ERROR: Run with sudo."); sys.exit(1)

# --- Attempt Archinstall Import ---
try: import archinstall; ARCHINSTALL_AVAILABLE = True
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

DEFAULT_CONFIG = { 'os_name': 'Mai Bloom OS', 'locale': 'en_US.UTF-8', 'keyboard_layout': 'us', 'mirror_region': 'Worldwide', 'harddrives': [], 'disk_config': {'!layout': {}}, 'disk_encryption': None, 'hostname': 'maibloom-pc', '!users': [], '!root-password': '', 'profile': 'kde', '_app_categories': [], 'packages': [], 'timezone': 'Asia/Tehran', 'kernels': ['linux'], 'nic': 'NetworkManager', 'audio': 'pipewire', 'swap': True, 'bootloader': 'systemd-boot' if os.path.exists('/sys/firmware/efi') else 'grub', '_os_brand_name': 'Mai Bloom OS' }

# --- Stylesheet Constant ---
DARK_THEME_QSS="""QMainWindow,QWidget{font-size:10pt;background-color:#2E2E2E;color:#E0E0E0}QScrollArea{border:none; background-color:#2E2E2E;} QScrollArea > QWidget > QWidget { background-color:#2E2E2E; } QGroupBox{border:1px solid #4A4A4A;border-radius:5px;margin-top:1ex;font-weight:bold;color:#00BFFF}QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;padding:0 5px;background-color:#2E2E2E}QLabel{color:#E0E0E0;margin-bottom:2px}QPushButton{padding:8px 15px;border-radius:4px;background-color:#555;color:#FFF;border:1px solid #686868;font-weight:bold}QPushButton:hover{background-color:#686868}QPushButton:disabled{background-color:#404040;color:#808080}QPushButton#InstallButton{background-color:#4CAF50;border-color:#388E3C}QPushButton#InstallButton:hover{background-color:#388E3C}QPlainTextEdit#LogOutput{background-color:#1C1C1C;color:#C0C0C0;border:1px solid #434343;font-family:"Monospace"}QLineEdit,QComboBox{padding:6px 8px;border:1px solid #555;border-radius:4px;background-color:#3D3D3D;color:#E0E0E0}QCheckBox{margin:5px 0;color:#E0E0E0}QCheckBox::indicator{width:16px;height:16px;background-color:#555;border:1px solid #686868;border-radius:3px}QCheckBox::indicator:checked{background-color:#007BFF}QProgressBar{text-align:center;padding:1px;border-radius:5px;background-color:#555;border:1px solid #686868;color:#E0E0E0;min-height:20px}QProgressBar::chunk{background-color:#007BFF;border-radius:4px}QSplitter::handle{background-color:#4A4A4A}QSplitter::handle:horizontal{width:3px}"""

# --- Text Constants ---
WELCOME_STEP_HTML = (f"<h2>Welcome to {APP_NAME}!</h2><p>Installer guide...</p><h3>Notes:</h3><ul><li>Internet recommended.</li><li>Backup data!</li><li>Disk ops may erase data.</li></ul><p>Configure below.</p>")
LANGUAGE_STEP_EXPLANATION = "Select system language (menus, messages)."
KEYBOARD_STEP_EXPLANATION = "Choose layout matching your keyboard."
SELECT_DISK_STEP_EXPLANATION = "Choose install disk.<br><b style='color:yellow;'>Data may be erased.</b>"
APP_CATEGORIES_EXPLANATION = "Select app types for initial setup (optional)."
SUMMARY_STEP_INTRO_TEXT = "Review settings. <b style='color:yellow;'>Install button modifies disk!</b>"

# --- Utility Functions (Using Archinstall) ---
def get_keyboard_layouts():
    try: return sorted(archinstall.list_keyboard_languages())
    except Exception as e: print(f"WARN kbd layouts: {e}"); return ["us"]
def get_locales(): print("WARN locales: using curated list."); return ["en_US.UTF-8", "fa_IR.UTF-8"]
def get_block_devices_info():
    try:
        raw=archinstall.list_block_devices(human_readable=False); devs=[]
        for p,d in raw.items():
            dt=getattr(d,'type','').lower(); sz=getattr(d,'size',0)
            if dt=='disk' and isinstance(sz,int) and sz>(1*1024**3): devs.append({'name':p,'size':sz,'lbl':getattr(d,'label',None)})
        if not devs: print("WARN: No disks found.")
        return devs
    except Exception as e: print(f"ERROR disks: {e}"); return []
def get_mirror_regions(): try: r=archinstall.list_mirror_regions(); return r if r else {"WW":"WW"} except Exception: return {"WW":"WW"}
def get_timezones(): try: z=archinstall.list_timezones(); return z if z else {"UTC":["UTC"]} except Exception: return {"UTC":["UTC"]}
def get_profiles(): try: pd=archinstall.profile.list_profiles(); pl=[{"n":n,"d":getattr(p,'desc','')} for n,p in pd.items() if not n.startswith('_')]; return pl if pl else [{"n":"Minimal","d":"Basic"}] except Exception: return [{"n":"Minimal","d":"Basic"}]

# --- Qt Log Handler ---
class QtLogHandler(logging.Handler):
    def __init__(self,log_signal):super().__init__();self.sig=log_signal;self.setFormatter(logging.Formatter('%(levelname)s:%(message)s'))
    def emit(self,record):self.sig.emit(self.format(record))

# --- Installation Thread ---
class InstallationThread(QThread):
    log_signal=pyqtSignal(str);progress_signal=pyqtSignal(int,str);finished_signal=pyqtSignal(bool,str)
    def __init__(self, config): super().__init__(); self.config=config
    def setup_logging(self): log=logging.getLogger('archinstall');log.setLevel(logging.INFO);
                           if not any(isinstance(h,QtLogHandler) for h in log.handlers): log.addHandler(QtLogHandler(self.log_signal)) # ; self.log_signal.emit("Log capture setup.") # Removed redundant emit
    def map_cats(self,cats): mapping={"Programming":["git","code"],"Gaming":["steam"],"Office":["libreoffice-fresh"],"Graphics":["gimp"]}; pkgs=set();[pkgs.update(mapping.get(c,[])) for c in cats]; return list(pkgs)
    def run(self):
        self.setup_logging(); self.log_signal.emit("Starting install..."); self.progress_signal.emit(0,"Prep...")
        try:
            conf=self.config.copy(); conf['keyboard_layout']=conf.pop('kb_layout',DEFAULT_CONFIG['keyboard_layout']); conf['locale']=conf.pop('sys_lang',DEFAULT_CONFIG['locale']); conf.pop('locale_config',None)
            conf['mirror_region']=conf.pop('mirror_region_code',DEFAULT_CONFIG['mirror_region']); conf.pop('mirror_region_display_name',None)
            disk=conf.pop('harddrives',[])[0] if conf.get('harddrives') else None;
            if not disk: raise ValueError("Disk missing.")
            fs=conf.pop('disk_filesystem',DEFAULT_CONFIG['disk_config']['filesystem'])
            conf['disk_config']={'!layout':{disk:{'wipe':True,'filesystem':{'format':fs}}}}
            if conf.get('disk_encrypt'): conf['disk_encryption']=[{'device':disk,'password':conf.pop('disk_encrypt_password'),'type':'luks'}]
            else: conf.pop('disk_encryption',None);conf.pop('disk_encrypt_password',None)
            users=[];
            if conf.get('username'): users.append({'username':conf.pop('username'),'password':conf.pop('user_password'),'sudo':conf.pop('user_sudo',True)})
            conf['!users']=users; conf['!root-password']=conf.pop('root_password')
            prof=conf.pop('profile_name',DEFAULT_CONFIG['profile']); conf['profile']=prof if prof!='Minimal' else None
            cat_pkgs=self.map_cats(conf.get('_app_categories',[])); add_pkgs=conf.get('packages',[])
            conf['packages']=list(set(cat_pkgs+add_pkgs)); brand=conf.pop('_os_brand_name','Mai Bloom OS')
            conf['custom_commands']=[f'sed -i \'s/^PRETTY_NAME=.*/PRETTY_NAME="{brand}"/\' /etc/os-release']
            keys_del=['_app_categories','disk_filesystem','disk_encrypt','username','user_password','user_sudo']; [conf.pop(k,None) for k in keys_del]
            log_cfg={k:v for k,v in conf.items() if k not in['!users','!root-password','disk_encryption']}; self.log_signal.emit(f"Final Conf: {log_cfg}"); self.progress_signal.emit(5,"Starting...")
            # --- MOCK INSTALL ---
            self.log_signal.emit("Calling archinstall (MOCK)..."); time.sleep(1); self.progress_signal.emit(10,"Disk..."); time.sleep(1); self.progress_signal.emit(40,"Pkgs..."); time.sleep(1); self.progress_signal.emit(80,"Config..."); time.sleep(1); self.progress_signal.emit(100,"Done..."); time.sleep(0.5)
            # --- End MOCK ---
            self.log_signal.emit("Install OK (sim)."); self.finished_signal.emit(True,f"{DEFAULT_CONFIG['os_name']} install OK (sim).")
        except Exception as e: self.log_signal.emit(f"FATAL err: {e}\n{traceback.format_exc()}"); self.finished_signal.emit(False,f"Install fail: {e}")

# --- Config Section Widget Base Class ---
class ConfigSectionWidget(QGroupBox): # (Unchanged)
    def __init__(self,title,cfg,main):super().__init__(title);self.cfg=cfg;self.main=main;self.layout=QVBoxLayout(self);self.layout.setSpacing(10);self.layout.setContentsMargins(10,20,10,10)
    def load(self):pass
    def save(self):return True

# --- Concrete Config Section Widgets ---
class LocaleKeyboardSection(ConfigSectionWidget): # (Condensed)
    def __init__(self,c,m):super().__init__("🌍 Lang & Kbd",c,m);grid=QGridLayout();grid.setSpacing(10);grid.addWidget(QLabel("Locale:"),0,0);self.lc=QComboBox();self.lc.addItems(get_locales());grid.addWidget(self.lc,0,1);grid.addWidget(QLabel("Keyboard:"),1,0);self.kb=QComboBox();self.kb.addItems(get_keyboard_layouts());grid.addWidget(self.kb,1,1);self.layout.addLayout(grid)
    def load(self): self.lc.setCurrentText(self.cfg.get('locale',DEFAULT_CONFIG['locale'])); self.kb.setCurrentText(self.cfg.get('keyboard_layout',DEFAULT_CONFIG['keyboard_layout']))
    def save(self): lc,kb=self.lc.currentText(),self.kb.currentText(); self.cfg['locale'],self.cfg['keyboard_layout']=lc,kb; return bool(lc and kb or QMessageBox.warning(self,"","Select locale & kbd."))
class DiskSection(ConfigSectionWidget): # (Condensed - Populate CORRECTED)
    def __init__(self,c,m):super().__init__("💾 Disk (Guided Wipe)",c,m);self.layout.addWidget(QLabel("<b style='color:yellow;'>WIPES DISK!</b>"));grid=QGridLayout();grid.setSpacing(10);grid.addWidget(QLabel("Disk:"),0,0);self.dc=QComboBox();grid.addWidget(self.dc,0,1);grid.addWidget(QLabel("FS:"),1,0);self.fs=QComboBox();self.fs.addItems(['ext4','btrfs','xfs']);grid.addWidget(self.fs,1,1);self.enc_cb=QCheckBox("Encrypt");grid.addWidget(self.enc_cb,2,0,1,2);self.enc_pw=QLineEdit();self.enc_pw.setPlaceholderText("Encrypt Pwd");self.enc_pw.setEchoMode(QLineEdit.Password);self.enc_pw.setEnabled(False);grid.addWidget(self.enc_pw,3,0,1,2);self.enc_cb.toggled.connect(self.enc_pw.setEnabled);self.layout.addLayout(grid);self.populate_disks()
    def populate_disks(self):
        cur=self.cfg.get('harddrives',[None])[0]; self.dc.clear(); self.devs=get_block_devices_info()
        # --- CORRECTED INDENTATION for 'if not self.devs:' ---
        if not self.devs:
            self.dc.addItem("No disks found.")
            self.dc.setEnabled(False)
            # self.disk_info_label was removed in condensation, maybe add back if needed
            return # Exit early if no devices
        # --- End Correction ---
        self.dc.setEnabled(True); sel=0
        for i,d in enumerate(self.devs): sz=d.get('size',0)/(1024**3); self.dc.addItem(f"{d['name']} ({sz:.1f}GB)",d['name']);
        if d['name']==cur: sel=i
        if self.dc.count()>0: self.dc.setCurrentIndex(sel)
    def load(self): self.populate_disks(); self.fs.setCurrentText(self.cfg.get('disk_filesystem',DEFAULT_CONFIG['disk_config']['filesystem'])); enc=self.cfg.get('disk_encryption')is not None; self.enc_cb.setChecked(enc); self.enc_pw.setEnabled(enc); self.enc_pw.clear()
    def save(self):
        if self.dc.currentIndex()<0 or not self.dc.currentData(): QMessageBox.warning(self,"","Select disk."); return False
        disk=self.dc.currentData(); self.cfg['harddrives']=[disk]; fs=self.fs.currentText(); self.cfg['disk_filesystem']=fs
        self.cfg['disk_encrypt']=self.enc_cb.isChecked()
        if self.cfg['disk_encrypt']: pw=self.enc_pw.text();
                                     if len(pw)<8: QMessageBox.warning(self,"","Encrypt pwd >= 8 chars."); return False
                                     self.cfg['disk_encrypt_password']=pw
        else: self.cfg.pop('disk_encrypt_password',None)
        return True
class UserSection(ConfigSectionWidget): # (Condensed)
    def __init__(self,c,m):super().__init__("👤 User & Hostname",c,m);grid=QGridLayout();grid.setSpacing(10);grid.addWidget(QLabel("Hostname:"),0,0);self.hn=QLineEdit();grid.addWidget(self.hn,0,1);grid.addWidget(QLabel("Root Pwd:"),1,0);self.rp=QLineEdit();self.rp.setEchoMode(QLineEdit.Password);grid.addWidget(self.rp,1,1);grid.addWidget(QLabel("Confirm:"),2,0);self.rpc=QLineEdit();self.rpc.setEchoMode(QLineEdit.Password);grid.addWidget(self.rpc,2,1);grid.addWidget(QLabel("Username:"),3,0);self.un=QLineEdit();self.un.setPlaceholderText("Optional");grid.addWidget(self.un,3,1);grid.addWidget(QLabel("User Pwd:"),4,0);self.up=QLineEdit();self.up.setEchoMode(QLineEdit.Password);grid.addWidget(self.up,4,1);grid.addWidget(QLabel("Confirm:"),5,0);self.upc=QLineEdit();self.upc.setEchoMode(QLineEdit.Password);grid.addWidget(self.upc,5,1);self.sudo=QCheckBox("Admin");grid.addWidget(self.sudo,6,0,1,2);self.layout.addLayout(grid)
    def load(self):self.hn.setText(self.cfg.get('hostname',DEFAULT_CONFIG['hostname']));users=self.cfg.get('!users',[]);self.un.setText(users[0]['username']if users else'');self.sudo.setChecked(users[0]['sudo']if users else True);self.rp.clear();self.rpc.clear();self.up.clear();self.upc.clear()
    def save(self):hn=self.hn.text().strip();rp=self.rp.text();usr=self.un.text().strip();up=self.up.text();
                 if not hn: QMessageBox.warning(self,"","Need hostname."); return False
                 if len(rp)<8 or rp!=self.rpc.text(): QMessageBox.warning(self,"","Root pwd err."); return False
                 self.cfg['hostname']=hn; self.cfg['!root-password']=rp; users=[]
                 if usr:
                     if len(up)<8 or up!=self.upc.text(): QMessageBox.warning(self,"","User pwd err."); return False
                     users.append({'username':usr,'password':up,'sudo':self.sudo.isChecked()})
                 self.cfg['!users']=users; self.cfg.pop('user_password',None); self.cfg.pop('root_password',None); self.cfg.pop('username',None); self.cfg.pop('user_sudo',None); return True # Clean up temp keys
class ProfileAppsSection(ConfigSectionWidget): # (Condensed)
     def __init__(self,c,m):super().__init__("🖥️ Profile & Apps",c,m);layout=QVBoxLayout();layout.setSpacing(10);layout.addWidget(QLabel("Profile:"));self.cb=QComboBox();self.profs=get_profiles();[self.cb.addItem(p['desc'],p['name'])for p in self.profs];layout.addWidget(self.cb);layout.addWidget(QLabel("Categories:"));self.cats={"Prog":"💻","Game":"🎮","Office":"📄","Graphics":"🎨"};self.cbs={};grid=QGridLayout();r,c=0,0;
                                for n,e in self.cats.items():chk=QCheckBox(f"{e}{n}");self.cbs[n]=chk;grid.addWidget(chk,r,c);c+=1;
                                if c>=2:c=0;r+=1
                                layout.addLayout(grid);self.layout.addLayout(layout)
     def load(self):idx=self.cb.findData(self.cfg.get('profile',DEFAULT_CONFIG['profile']));self.cb.setCurrentIndex(idx if idx!=-1 else 0);sel=self.cfg.get('_app_categories',[]);[cb.setChecked(n in sel)for n,cb in self.cbs.items()]
     def save(self):self.cfg['profile']=self.cb.currentData()or(self.profs[0]['name']if self.profs else None);self.cfg['_app_categories']=[n for n,cb in self.cbs.items() if cb.isChecked()];return True

# --- Main Application Window ---
class MaiBloomOSInstallerWindow(QMainWindow):
    def __init__(self): super().__init__(); self.cfg=DEFAULT_CONFIG.copy(); self.inst_thread=None; self.init_ui()
    def init_ui(self): self.setWindowTitle(f"{APP_NAME}"); self.setMinimumSize(1000,700); # Slightly smaller min width
                   if os.path.exists(LOGO_PATH): self.setWindowIcon(QIcon(LOGO_PATH));
                   central=QWidget(); self.setCentralWidget(central); main_layout=QVBoxLayout(central); self.setup_menus();
                   splitter=QSplitter(Qt.Horizontal); scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll_w=QWidget(); scroll_l=QVBoxLayout(scroll_w); scroll_l.setSpacing(15); scroll_l.setContentsMargins(15,15,15,15);
                   self.sections=[LocaleKeyboardSection(self.cfg,self),DiskSection(self.cfg,self),UserSection(self.cfg,self),ProfileAppsSection(self.cfg,self)]; # Add all sections
                   for sec in self.sections: scroll_l.addWidget(sec)
                   scroll_l.addStretch(1); scroll.setWidget(scroll_w); splitter.addWidget(scroll); self.log=QPlainTextEdit(); self.log.setReadOnly(True); log_f=QFontDatabase.systemFont(QFontDatabase.FixedFont);log_f.setPointSize(9);self.log.setFont(log_f); splitter.addWidget(self.log); splitter.setSizes([500,500]); splitter.setStretchFactor(0,1); splitter.setStretchFactor(1,1); main_layout.addWidget(splitter,1); btn_layout=QHBoxLayout(); btn_layout.addStretch(1); self.inst_btn=QPushButton("🚀 Install"); self.inst_btn.clicked.connect(self.confirm_start); btn_layout.addWidget(self.inst_btn); main_layout.addLayout(btn_layout); self.log_append(f"{APP_NAME} ready.","INFO"); self.apply_theme(); self.load_all()
    def setup_menus(self): menu=self.menuBar();fm=menu.addMenu("&File");ex=QAction("E&xit",self);ex.triggered.connect(self.close);fm.addAction(ex);hm=menu.addMenu("&Help");ab=QAction("&About",self);ab.triggered.connect(self.about);hm.addAction(ab)
    def about(self): QMessageBox.about(self,f"About",f"<b>{APP_NAME}</b><p>Installer.")
    def apply_theme(self): self.setStyleSheet(DARK_THEME_QSS); self.log.setObjectName("LogOutput"); self.inst_btn.setObjectName("InstallButton")
    def load_all(self): self.log_append("Loading config...","DEBUG"); [sec.load() for sec in self.sections]
    def save_all(self): self.log_append("Saving config...","DEBUG");
                      for sec in self.sections:
                          if not sec.save(): self.log_append(f"Validation failed: {sec.title()}","ERROR"); QMessageBox.warning(self,"Error",f"Check '{sec.title()}'."); return False
                      self.log_append("Config saved.","INFO"); return True
    def confirm_start(self):
        if not self.save_all(): return
        summary="\n".join([f"- {k}: {'<set>'if'pass'in k else self.cfg.get(k)}" for k in ['locale','keyboard_layout','harddrives','hostname','profile'] if k in self.cfg]) # Basic summary
        if QMessageBox.question(self,"Confirm Install",f"Start install?\n{summary}\n\n<font color='red'><b>WIPES DISK!</b></font>",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.start_install()
    def start_install(self): self.log_append("Starting install thread...","INFO"); self.inst_btn.setEnabled(False); self.inst_thread=InstallationThread(self.cfg.copy()); self.inst_thread.log_signal.connect(lambda m:self.log_append(m,"INSTALL")); self.inst_thread.finished_signal.connect(self.on_install_done); self.inst_thread.start() # Add progress later
    def on_install_done(self, suc, msg): self.log_append(f"Install Done: Success={suc}","RESULT"); self.inst_btn.setEnabled(True);
                                      if suc: QMessageBox.information(self,"Complete",f"{self.cfg.get('os_name',APP_NAME)} install OK.\nReboot.")
                                      else: QMessageBox.critical(self,"Failed", msg+"\nCheck logs.")
    def log_append(self, txt, lvl="DEBUG"): ts=time.strftime("%H:%M:%S"); self.log.appendPlainText(f"[{ts}][{lvl.upper()}] {txt}"); sb=self.log.verticalScrollBar();sb.setValue(sb.maximum()); QApplication.processEvents()
    def closeEvent(self, event): busy=(self.inst_thread and self.inst_thread.isRunning());
                          if busy and QMessageBox.question(self,"Exit","Install running. Abort?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes: self.log_append("User aborted.","WARN"); event.accept()
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

