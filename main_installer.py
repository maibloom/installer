import sys
import subprocess
import json
import tempfile
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QStackedWidget, QMessageBox, QProgressBar, QTextEdit,
    QStyleFactory, QGroupBox, QCheckBox, QScrollArea, QCompleter # Added QCheckBox, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# --- Helper Functions ---
def bytes_to_human_readable(size_bytes):
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    i = 0
    try: size_bytes_num = float(size_bytes)
    except (ValueError, TypeError): return "N/A"
    while size_bytes_num >= 1024 and i < len(size_name) - 1:
        size_bytes_num /= 1024.0
        i += 1
    return f"{size_bytes_num:.1f} {size_name[i]}"

def get_system_timezones():
    try:
        result = subprocess.run(["timedatectl", "list-timezones"], capture_output=True, text=True, check=True, timeout=5)
        timezones = [tz.strip() for tz in result.stdout.splitlines() if tz.strip()]
        return sorted(timezones)
    except Exception as e: # Catch all exceptions for this helper
        print(f"Could not get system timezones: {e}")
        return ["Etc/UTC"] # Fallback

# --- ArchInstallThread Class (for running archinstall) ---
class ArchInstallThread(QThread):
    log_update = pyqtSignal(str)
    installation_finished = pyqtSignal(bool, str)

    def __init__(self, config_dict, parent=None):
        super().__init__(parent)
        self.config_dict = config_dict
        self.config_file_path = None
        self._is_running = True

    def run(self):
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', prefix='mai_bloom_archinstall_') as tmp_file:
                json.dump(self.config_dict, tmp_file, indent=2)
                self.config_file_path = tmp_file.name
            self.log_update.emit(f"Archinstall configuration saved to: {self.config_file_path}\n")
            command = ["archinstall", "--config", self.config_file_path, "--silent"] # Add --verbose for more logs if needed
            self.log_update.emit(f"Executing command: {' '.join(command)}\n")
            self.log_update.emit("--- Installation Started (Output from archinstall) ---\n")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            while self._is_running:
                line = process.stdout.readline()
                if line: self.log_update.emit(line)
                else:
                    if process.poll() is not None: break
            for remaining_line in process.stdout: self.log_update.emit(remaining_line)
            process.stdout.close()
            return_code = process.wait()
            self.log_update.emit("\n--- Installation Ended ---\n")
            if return_code == 0:
                self.log_update.emit("Archinstall process completed successfully.")
                self.installation_finished.emit(True, "Installation successful! Mai Bloom OS is ready.")
            else:
                self.log_update.emit(f"Archinstall process failed with exit code: {return_code}")
                self.installation_finished.emit(False, f"Installation failed (exit code: {return_code}).")
        except FileNotFoundError:
            self.log_update.emit("\nError: 'archinstall' command not found.")
            self.installation_finished.emit(False, "'archinstall' command not found.")
        except Exception as e:
            self.log_update.emit(f"\nAn error occurred during the installation thread: {str(e)}")
            self.installation_finished.emit(False, f"A critical error occurred: {str(e)}")
        finally:
            if self.config_file_path and os.path.exists(self.config_file_path):
                try: os.remove(self.config_file_path); self.log_update.emit(f"Temporary config file removed.\n")
                except OSError as e: self.log_update.emit(f"Error removing temp config file: {e}\n")
    def stop(self): self._is_running = False

# --- MaiBloomInstaller Class ---
class MaiBloomInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mai Bloom OS Installer")
        self.setGeometry(100, 100, 800, 600) # Slightly wider for new step
        self.setMinimumSize(750, 550)
        self.install_thread = None

        QApplication.setStyle(QStyleFactory.create('Fusion'))

        self.config = {
            "language": "English (US)", "keyboard_layout": None,
            "timezone": None, # Will store "Continent/City" e.g. "Asia/Tehran"
            "disk_target": None, "partition_scheme": "automatic",
            "hostname": "maibloom-pc", "username": None, "password": None,
            "desktop_environment": "KDE Plasma (Mai Bloom Default)",
            "app_categories": [], # For new application categories step
            "additional_packages": [] # Merged list for archinstall
        }

        self.main_layout = QVBoxLayout(self)
        self.stacked_widget = QStackedWidget(); self.main_layout.addWidget(self.stacked_widget)

        self.welcome_page = QWidget(); self.lang_kb_page = QWidget()
        self.timezone_page = QWidget(); self.partition_page = QWidget()
        self.hostname_page = QWidget(); self.user_page = QWidget()
        self.desktop_page = QWidget();
        self.app_categories_page = QWidget() # New page for app categories
        self.summary_page = QWidget(); self.progress_page = QWidget()
        self.complete_page = QWidget()

        self.nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous"); self.prev_button.clicked.connect(self.prev_step_clicked)
        self.next_button = QPushButton("Next"); self.next_button.clicked.connect(self.next_step_clicked)
        self.install_button = QPushButton("Install Mai Bloom OS"); self.install_button.clicked.connect(self.confirm_installation)
        self.install_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        self.restart_button = QPushButton("Restart Now"); self.restart_button.clicked.connect(self.restart_system)
        self.restart_button.setStyleSheet("background-color: #007BFF; color: white; padding: 10px; font-weight: bold;")
        self.nav_layout.addWidget(self.prev_button); self.nav_layout.addStretch()
        self.nav_layout.addWidget(self.next_button); self.nav_layout.addWidget(self.install_button)
        self.nav_layout.addWidget(self.restart_button); self.main_layout.addLayout(self.nav_layout)

        self.steps_config_map = [
            (self.welcome_page, self.create_welcome_step),
            (self.lang_kb_page, self.create_language_keyboard_step),
            (self.timezone_page, self.create_timezone_step),
            (self.partition_page, self.create_partition_step),
            (self.hostname_page, self.create_hostname_step),
            (self.user_page, self.create_user_step),
            (self.desktop_page, self.create_desktop_step),
            (self.app_categories_page, self.create_app_categories_step), # New step added here
            (self.summary_page, self.create_install_summary_step),
            (self.progress_page, self.create_installation_progress_step),
            (self.complete_page, self.create_installation_complete_step)
        ]
        for pw, cf in self.steps_config_map: QVBoxLayout(pw).setContentsMargins(20,20,20,20); cf(pw.layout()); self.stacked_widget.addWidget(pw)

        self.current_step_index = 0
        self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons()

    def get_available_drives(self):
        drives = []
        try:
            result = subprocess.run(["lsblk", "-Jbo", "NAME,SIZE,MODEL,TYPE,RO,RM,PATH,FSTYPE,MOUNTPOINT"], capture_output=True, text=True, check=True, timeout=5)
            data = json.loads(result.stdout); active_mountpoints = ['/', '/boot', '/home', '/var', '/usr', '/run/archiso/bootmnt']
            running_os_disk_path = None
            for dev_info in data.get("blockdevices", []):
                if dev_info.get("mountpoint") in active_mountpoints:
                    pkname = dev_info.get("pkname")
                    if pkname:
                         for d in data.get("blockdevices", []):
                             if d.get("name") == pkname and d.get("type") == "disk": running_os_disk_path = d.get("path"); break
                    elif dev_info.get("type") == "disk": running_os_disk_path = dev_info.get("path")
                    if running_os_disk_path: print(f"Debug: Found OS on {running_os_disk_path} via {dev_info.get('mountpoint')}"); break
            for dev in data.get("blockdevices", []):
                if dev.get("type") == "disk" and not dev.get("ro", False):
                    if dev.get("name", "").startswith("loop"): continue
                    dev_path = dev.get("path", f"/dev/{dev.get('name')}")
                    if dev_path == running_os_disk_path: print(f"Debug: Skipping live OS disk: {dev_path}"); continue
                    model = dev.get("model", "Unknown"); size = bytes_to_human_readable(dev.get("size",0))
                    drives.append({"path": dev_path, "display": f"{dev_path} ({model}) - {size}", "size": dev.get("size",0)})
        except Exception as e: print(f"Drive detection error: {e}"); QMessageBox.warning(self, "Drive Error", f"Could not list drives: {e}")
        return sorted(drives, key=lambda x: x["path"])

    def update_nav_buttons(self):
        curr = self.stacked_widget.widget(self.current_step_index)
        first = self.current_step_index == 0
        summary = curr == self.summary_page
        progress = curr == self.progress_page
        complete = curr == self.complete_page

        self.prev_button.setEnabled(not first and not progress and not complete)
        self.next_button.setVisible(not summary and not progress and not complete)
        self.install_button.setVisible(summary)
        self.restart_button.setVisible(complete)

        if progress or complete: self.prev_button.setVisible(False)
        
        if curr == self.partition_page:
            self.next_button.setEnabled(hasattr(self, 'disk_combo') and self.disk_combo.count() > 0 and self.disk_combo.currentData() is not None)
        elif curr == self.timezone_page:
             self.next_button.setEnabled(hasattr(self, 'timezone_combo') and self.timezone_combo.currentText() not in ["Select Timezone...", "Could not load timezones."])
        elif not (progress or complete or summary): self.next_button.setEnabled(True)


    def validate_current_step(self):
        curr = self.stacked_widget.widget(self.current_step_index)
        if curr == self.lang_kb_page:
            if self.kb_layout_combo.currentText() in ["Select...", ""]: QMessageBox.warning(self, "Input Error", "Select keyboard layout."); return False
            self.config["language"] = self.lang_combo.currentText(); self.config["keyboard_layout"] = self.kb_layout_combo.currentText()
        elif curr == self.timezone_page:
            tz = self.timezone_combo.currentText()
            if tz in ["Select Timezone...", "Could not load timezones.", ""]: QMessageBox.warning(self, "Input Error", "Select a valid timezone."); return False
            self.config["timezone"] = tz
        elif curr == self.partition_page:
            if not (hasattr(self, 'disk_combo') and self.disk_combo.currentData()): QMessageBox.warning(self, "Input Error", "Select target disk."); return False
            self.config["disk_target"] = self.disk_combo.currentData()
        elif curr == self.hostname_page:
            if not self.hostname_input.text().strip(): QMessageBox.warning(self, "Input Error", "Hostname empty."); return False
            self.config["hostname"] = self.hostname_input.text().strip()
        elif curr == self.user_page:
            if not self.username_input.text().strip(): QMessageBox.warning(self, "Input Error", "Username empty."); return False
            if not self.password_input.text(): QMessageBox.warning(self, "Input Error", "Password empty."); return False
            if self.password_input.text() != self.password_confirm_input.text(): QMessageBox.warning(self, "Input Error", "Passwords do not match."); return False
            self.config["username"] = self.username_input.text().strip(); self.config["password"] = self.password_input.text()
        elif curr == self.app_categories_page: # Validation for this step (optional selections)
            self.config["app_categories"] = [cb.text() for cb in self.app_cat_checkboxes if cb.isChecked()]
        return True

    def next_step_clicked(self):
        if not self.validate_current_step(): self.update_nav_buttons(); return
        if self.current_step_index < self.stacked_widget.count() - 1:
            if self.stacked_widget.widget(self.current_step_index + 1) == self.summary_page: self.update_summary_contents()
            self.current_step_index += 1
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons()

    def prev_step_clicked(self):
        if self.current_step_index > 0:
            # If on summary, validate current (which is summary) before going back to ensure data is gathered for display
            # No, validation happens on "Next", not needed for "Prev" generally.
            self.current_step_index -= 1
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons()

    def create_styled_label(self, text, pt_size=12, align=Qt.AlignLeft, title=False): # Shorter param names
        lbl = QLabel(text); font = lbl.font(); font.setPointSize(pt_size)
        if title: font.setBold(True)
        lbl.setFont(font); lbl.setAlignment(align)
        if title: lbl.setStyleSheet("margin-bottom: 10px; color: #2c3e50; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px;")
        return lbl

    def create_welcome_step(self, layout):
        layout.addWidget(self.create_styled_label("Welcome to Mai Bloom OS Installer!", 20, Qt.AlignCenter, True))
        intro_html = ("<p>This installer will guide you through setting up Mai Bloom OS, "
                      "a user-friendly Arch Linux based distribution featuring the powerful and elegant KDE Plasma desktop environment.</p>"
                      "<p><b>Before you begin:</b> Please ensure any important data on the target computer is securely backed up. "
                      "The installation process will erase the selected hard drive.</p>"
                      "<p>Click 'Next' to start configuring your installation.</p>")
        intro_lbl = QLabel(intro_html); intro_lbl.setWordWrap(True); layout.addWidget(intro_lbl); layout.addStretch()
        
    def create_language_keyboard_step(self, layout):
        layout.addWidget(self.create_styled_label("Language & Keyboard Setup", 18, Qt.AlignCenter, True))
        box = QGroupBox("Localization Settings"); l = QVBoxLayout()
        l.addWidget(QLabel("<b>Installation Language:</b>")); self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English (US)", "Español (España)", "Français (France)", "Deutsch (Deutschland)"])
        self.lang_combo.setCurrentText(self.config.get("language", "English (US)")); l.addWidget(self.lang_combo); l.addSpacing(15)
        l.addWidget(QLabel("<b>Keyboard Layout:</b>")); self.kb_layout_combo = QComboBox()
        self.kb_layout_combo.addItems(["Select...", "us", "gb", "es", "fr", "de", "it", "ru", "ir", "dvorak"]) # 'gb' more common than 'uk' for xkb, 'ir' for Iran
        self.kb_layout_combo.setCurrentText(self.config.get("keyboard_layout") if self.config.get("keyboard_layout") else "Select...")
        l.addWidget(self.kb_layout_combo); box.setLayout(l); layout.addWidget(box); layout.addStretch()

    def create_timezone_step(self, layout):
        layout.addWidget(self.create_styled_label("Timezone Configuration", 18, Qt.AlignCenter, True))
        box = QGroupBox("Select Your System Timezone"); l = QVBoxLayout()
        l.addWidget(QLabel("<b>Timezone:</b> (Type to search)"))
        self.timezone_combo = QComboBox(); self.timezone_combo.setEditable(True)
        self.timezone_combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.timezone_combo.completer().setFilterMode(Qt.MatchContains)
        
        available_timezones = get_system_timezones()
        default_tz_preference = ["Asia/Tehran", "Etc/UTC"] # User's location, then UTC
        
        if available_timezones:
            self.timezone_combo.addItems(["Select Timezone..."] + available_timezones)
            current_config_tz = self.config.get("timezone")
            final_selection = "Select Timezone..."

            if current_config_tz and current_config_tz in available_timezones:
                final_selection = current_config_tz
            else: # Attempt to pre-select
                try:
                    local_tz_result = subprocess.run(["timedatectl", "show", "-p", "Timezone", "--value"], capture_output=True, text=True, check=True, timeout=2)
                    local_tz = local_tz_result.stdout.strip()
                    if local_tz in available_timezones: final_selection = local_tz
                except Exception: pass # Ignore if timedatectl fails for preselection

                if final_selection == "Select Timezone...": # If still not set
                    for pref_tz in default_tz_preference:
                        if pref_tz in available_timezones: final_selection = pref_tz; break
                
                if final_selection == "Select Timezone..." and len(available_timezones) > 0 : # Absolute fallback
                    final_selection = available_timezones[0]

            self.timezone_combo.setCurrentText(final_selection)
            if final_selection != "Select Timezone...": self.config["timezone"] = final_selection # Pre-fill config
        else:
            self.timezone_combo.addItem("Could not load timezones."); self.timezone_combo.setEnabled(False)
        
        self.timezone_combo.currentIndexChanged.connect(lambda: self.update_nav_buttons())
        l.addWidget(self.timezone_combo); box.setLayout(l); layout.addWidget(box); layout.addStretch()

    def create_partition_step(self, layout):
        layout.addWidget(self.create_styled_label("Disk Setup: Target & Partitioning", 18, Qt.AlignCenter, True))
        box = QGroupBox("Installation Target Disk"); l = QVBoxLayout()
        l.addWidget(QLabel("<b>Select Target Disk:</b> (Existing data will be erased!)"))
        self.disk_combo = QComboBox(); available_drives = self.get_available_drives()
        if not available_drives:
            self.disk_combo.addItem("No suitable drives found/error."); self.disk_combo.setEnabled(False)
        else:
            self.disk_combo.addItem("Select a disk...", None)
            for drive in available_drives: self.disk_combo.addItem(drive["display"], userData=drive["path"])
        self.disk_combo.currentIndexChanged.connect(lambda: self.update_nav_buttons())
        l.addWidget(self.disk_combo); l.addSpacing(15)
        warn_html = ("<p><b><font color='#c0392b'>WARNING:</font> The ENTIRE selected disk will be AUTOMATICALLY ERASED and partitioned.</b></p>"
                     "<p>All existing data on this disk will be permanently lost. Mai Bloom OS will set up a standard layout suitable for KDE Plasma, including:</p>"
                     "<ul><li>EFI System Partition (for booting)</li>"
                     "<li>Root partition (<code>/</code>) for the OS</li>"
                     "<li>Home partition (<code>/home</code>) for your personal files</li>"
                     "<li>Swap partition (for virtual memory)</li></ul>"
                     "<p>Please ensure you have backed up any critical data before proceeding.</p>")
        info_lbl = QLabel(warn_html); info_lbl.setWordWrap(True); l.addWidget(info_lbl)
        box.setLayout(l); layout.addWidget(box); layout.addStretch()

    def create_hostname_step(self, layout):
        layout.addWidget(self.create_styled_label("Network Name (Hostname)", 18, Qt.AlignCenter, True))
        box = QGroupBox("Computer Identification"); l = QVBoxLayout()
        l.addWidget(QLabel("<b>Enter a hostname for this computer:</b> (e.g., <code>maibloom-desktop</code>)"))
        self.hostname_input = QLineEdit(self.config.get("hostname", "maibloom-pc"))
        self.hostname_input.setPlaceholderText("my-computer-name")
        l.addWidget(self.hostname_input)
        info = QLabel("The hostname is a unique name that identifies your computer on your local network."); info.setWordWrap(True)
        l.addWidget(info); box.setLayout(l); layout.addWidget(box); layout.addStretch()

    def create_user_step(self, layout):
        layout.addWidget(self.create_styled_label("Create Your User Account", 18, Qt.AlignCenter, True))
        box = QGroupBox("User Details"); l = QVBoxLayout()
        l.addWidget(QLabel("<b>Username:</b> (e.g., <code>bloom</code>, lowercase, no spaces)"))
        self.username_input = QLineEdit(self.config.get("username", "")); self.username_input.setPlaceholderText("yourusername")
        l.addWidget(self.username_input); l.addSpacing(10)
        l.addWidget(QLabel("<b>Password:</b> (Choose a strong password)")); self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password); self.password_input.setPlaceholderText("Enter password")
        l.addWidget(self.password_input); l.addSpacing(10)
        l.addWidget(QLabel("<b>Confirm Password:</b>")); self.password_confirm_input = QLineEdit()
        self.password_confirm_input.setEchoMode(QLineEdit.Password); self.password_confirm_input.setPlaceholderText("Re-enter password")
        l.addWidget(self.password_confirm_input); box.setLayout(l); layout.addWidget(box); layout.addStretch()

    def create_desktop_step(self, layout):
        layout.addWidget(self.create_styled_label("Desktop Environment: KDE Plasma", 18, Qt.AlignCenter, True))
        box = QGroupBox("Your Mai Bloom OS Experience"); l = QVBoxLayout()
        info_html = ("<p>Mai Bloom OS is optimized for the <b>KDE Plasma Desktop Environment</b>.</p>"
                     "<p>KDE Plasma offers a visually appealing, highly customizable, and feature-rich experience. "
                     "All core KDE Plasma components will be installed to provide a complete desktop.</p>"
                     "<p>In the next step, you can select optional application bundles.</p>")
        info_lbl = QLabel(info_html); info_lbl.setWordWrap(True); l.addWidget(info_lbl)
        box.setLayout(l); layout.addWidget(box); layout.addStretch()

    def create_app_categories_step(self, layout):
        layout.addWidget(self.create_styled_label("Select Application Bundles (Optional)", 18, Qt.AlignCenter, True))
        
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True)
        scroll_content = QWidget(); scroll_layout = QVBoxLayout(scroll_content)
        
        box = QGroupBox("Choose software categories to include in your installation:"); box.setStyleSheet("QGroupBox { font-weight: bold; }")
        categories_layout = QVBoxLayout()
        
        self.app_categories = {
            "Education": "Includes tools like an office suite, reference managers, and learning software.",
            "Programming & Development": "Essentials for developers: code editors, version control, and common runtimes.",
            "Gaming": "Installs Steam, Lutris, Wine, and other gaming utilities for the best experience.",
            "Daily Use & Productivity": "Web browser, email, office suite, media players, and general utilities.",
            "Graphics & Design": "Software for image editing, vector graphics, 3D modeling, and digital painting.",
            "Multimedia Production": "Tools for audio recording/editing, video editing, and screen recording."
        }
        self.app_cat_checkboxes = []
        for cat_name, cat_desc in self.app_categories.items():
            cb = QCheckBox(f"{cat_name}"); cb.setToolTip(cat_desc)
            cb.setChecked(cat_name in self.config.get("app_categories", [])) # Restore previous selection
            self.app_cat_checkboxes.append(cb)
            categories_layout.addWidget(cb)
        
        box.setLayout(categories_layout)
        scroll_layout.addWidget(box)
        scroll_layout.addWidget(QLabel("<small><i>Package lists for these selections are curated by Mai Bloom OS. Specific packages can be managed post-installation.</i></small>"))
        scroll_layout.addStretch()
        
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

    def create_install_summary_step(self, layout):
        layout.addWidget(self.create_styled_label("Installation Summary & Confirmation", 18, Qt.AlignCenter, True))
        self.summary_text_area = QTextEdit(); self.summary_text_area.setReadOnly(True)
        self.summary_text_area.setStyleSheet("QTextEdit { background-color: #f0f0f0; border: 1px solid #ccc; }") # Slightly styled
        layout.addWidget(self.summary_text_area)

    def update_summary_contents(self):
        if hasattr(self, 'disk_combo') and self.disk_combo and self.disk_combo.currentData():
            self.config["disk_target"] = self.disk_combo.currentData()
        else: self.config["disk_target"] = "N/A - No disk selected"

        summary = "<html><body style='font-family: sans-serif; font-size: 10pt;'>"
        summary += "<h2 style='color: #2c3e50;'>Review Your Installation Settings</h2>"
        summary += f"<p><b>Language:</b> {self.config.get('language', 'N/A')}</p>"
        summary += f"<p><b>Keyboard Layout:</b> {self.config.get('keyboard_layout', 'N/A')}</p>"
        summary += f"<p><b>Timezone:</b> {self.config.get('timezone', 'N/A (Not selected)')}</p>"
        summary += f"<p><b>Target Disk:</b> <span style='font-weight:bold;'>{self.config.get('disk_target', 'N/A')}</span></p>"
        summary += f"<p><b>Partitioning:</b> Automatic (Entire disk will be erased for KDE Desktop)</p>"
        summary += f"<p><b>Hostname:</b> {self.config.get('hostname', 'N/A')}</p>"
        summary += f"<p><b>Username:</b> {self.config.get('username', 'N/A')}</p>"
        summary += f"<p><b>Password:</b> {'Set (hidden)' if self.config.get('password') else 'Not Set'}</p>"
        summary += f"<p><b>Desktop Environment:</b> KDE Plasma (Mai Bloom OS Default)</p>"
        
        selected_categories = self.config.get("app_categories", [])
        if selected_categories:
            summary += "<p><b>Selected Application Bundles:</b></p><ul>"
            for cat in selected_categories: summary += f"<li>{cat}</li>"
            summary += "</ul>"
        else:
            summary += "<p><b>Selected Application Bundles:</b> None</p>"

        summary += "<hr><p style='color: #c0392b; font-weight: bold;'>WARNING: Clicking 'Install Mai Bloom OS' will ERASE the selected disk ({}) "
        summary = summary.format(self.config.get('disk_target', 'N/A'))
        summary += "and begin the installation. This action is IRREVERSIBLE. Ensure all important data is backed up.</p>"
        summary += "</body></html>"
        self.summary_text_area.setHtml(summary)

    def confirm_installation(self):
        # Final validation before installation starts
        try:
            self.generate_archinstall_config() # This will raise ValueError if critical configs are missing
        except ValueError as ve:
            QMessageBox.critical(self, "Configuration Incomplete", f"Cannot start installation: {ve}\nPlease go back using the 'Previous' button and complete all required fields.")
            return

        reply = QMessageBox.warning(self, "Confirm Installation",
                                    f"<b><font size='+1'>ARE YOU ABSOLUTELY SURE?</font></b><br><br>"
                                    f"The disk <b>{self.config.get('disk_target')}</b> will be completely <b>ERASED</b> and Mai Bloom OS will be installed.<br><br>"
                                    "This action is irreversible. All data on the selected disk will be lost.",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.current_step_index = self.stacked_widget.indexOf(self.progress_page)
            self.stacked_widget.setCurrentIndex(self.current_step_index)
            self.update_nav_buttons()
            self.start_actual_installation()

    def generate_archinstall_config(self):
        # --- Basic Validations ---
        if not self.config.get("disk_target") or self.config.get("disk_target") == "N/A - No disk selected": raise ValueError("Target disk not selected.")
        if not self.config.get("username") or not self.config.get("password"): raise ValueError("Username or password not set.")
        if not self.config.get("timezone") or self.config.get("timezone") in ["Select Timezone...", "Could not load timezones."]: raise ValueError("Timezone not selected.")
        if not self.config.get("keyboard_layout") or self.config.get("keyboard_layout") == "Select...": raise ValueError("Keyboard layout not selected.")
        if not self.config.get("hostname"): raise ValueError("Hostname not set.")
        if not self.config.get("language"): raise ValueError("Language not set.") # Should always have a default

        lang_map = {"English (US)": "en_US.UTF-8", "Español (España)": "es_ES.UTF-8", "Français (France)": "fr_FR.UTF-8", "Deutsch (Deutschland)": "de_DE.UTF-8"}
        sys_lang = lang_map.get(self.config.get("language"), "en_US.UTF-8")

        arch_config = {
            "archinstall-language": "English", # For archinstall's own prompts if any slip through --silent (unlikely)
            "hostname": self.config.get("hostname"),
            "locale_config": {"kb_layout": self.config.get("keyboard_layout"), "sys_enc": "UTF-8", "sys_lang": sys_lang},
            "timezone": self.config.get("timezone"),
            "!users": [{"username": self.config.get("username"), "!password": self.config.get("password"), "sudo": True}], # Using !users as per archinstall 2.8.x
            "disk_config": {"config_type": "default_layout", "device_modifications": [{"device": self.config.get("disk_target"), "wipe": True}]},
            "profile_config": {"gfx_driver": "All open-source (default)", "greeter": "sddm", "profile": {"details": ["KDE Plasma"], "main": "Desktop"}},
            "audio_config": {"audio": "pipewire"}, "bootloader": "Systemd-boot", "kernels": ["linux"],
            "swap": True, "ntp": True, "debug": False, "version": "3.0.4", # Using user's example version
            "packages": [] # Base packages, will be extended by categories
        }

        # --- USER CONFIGURABLE SECTION FOR APPLICATION CATEGORY PACKAGES ---
        selected_categories = self.config.get("app_categories", [])
        base_packages_for_install = list(arch_config.get("packages", [])) # Start with any base packages already defined

        # Define your package lists per category here for Mai Bloom OS
        # These are JUST EXAMPLES. Replace with your actual package names.
        category_to_packages_map = {
            "Education": ["libreoffice-fresh", "zotero-bin", "kstars", "kalgebra"], # Example (zotero-bin from AUR)
            "Programming & Development": ["code", "git", "python-pip", "nodejs", "npm", "jdk-openjdk", "docker"], # Example
            "Gaming": ["steam", "lutris", "wine", "gamemode", "mangohud"], # Example
            "Daily Use & Productivity": ["firefox", "thunderbird", "vlc", "gwenview", "okular", "keepassxc"], # Example
            "Graphics & Design": ["gimp", "krita", "inkscape", "blender"], # Example
            "Multimedia Production": ["audacity", "obs-studio", "kdenlive", "shotcut"] # Example
        }
        # Note: For AUR packages (like zotero-bin), archinstall might need an AUR helper configured,
        # or you'd handle AUR packages in a post-installation script.
        # Sticking to official repo packages is safer for direct archinstall 'packages' list.

        for category in selected_categories:
            base_packages_for_install.extend(category_to_packages_map.get(category, []))
        
        arch_config["packages"] = list(set(base_packages_for_install)) # Ensure unique packages
        # --- END USER CONFIGURABLE SECTION ---
        
        return arch_config

    def start_actual_installation(self):
        self.install_log_area.clear(); self.install_log_area.append("Preparing for installation...\n")
        self.progress_bar.setRange(0, 0); self.progress_bar.setValue(0)
        try:
            arch_config_dict = self.generate_archinstall_config()
            self.install_log_area.append("Archinstall configuration generated successfully.\n")
            # self.install_log_area.append(f"DEBUG CONFIG:\n{json.dumps(arch_config_dict, indent=2)}\n") # For testing
            self.prev_button.setEnabled(False); self.next_button.setEnabled(False); self.install_button.setEnabled(False)
            self.install_thread = ArchInstallThread(arch_config_dict)
            self.install_thread.log_update.connect(self.append_to_log)
            self.install_thread.installation_finished.connect(self.on_installation_finished)
            self.install_thread.start()
            self.install_log_area.append("Installation thread initiated. Please monitor progress...\n")
        except ValueError as ve:
            msg = f"Configuration Error: {ve}"
            self.install_log_area.append(f"{msg}\n"); QMessageBox.critical(self, "Configuration Error", f"Failed to prepare: {ve}\nPlease go back and correct.")
            self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
            self.current_step_index = self.stacked_widget.indexOf(self.summary_page) # Return to summary
            self.stacked_widget.setCurrentIndex(self.current_step_index)
            self.update_nav_buttons() # Re-enable summary page buttons for correction
        except Exception as e:
            msg = f"Critical error before installation: {e}"
            self.install_log_area.append(f"{msg}\n"); QMessageBox.critical(self, "Error", msg)
            self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0); self.update_nav_buttons()

    def append_to_log(self, text):
        self.install_log_area.insertPlainText(text)
        self.install_log_area.verticalScrollBar().setValue(self.install_log_area.verticalScrollBar().maximum())
        QApplication.processEvents()

    def on_installation_finished(self, success, message):
        self.progress_bar.setRange(0, 100); self.progress_bar.setValue(100 if success else 0)
        self.install_log_area.append(f"\n--- {message} ---\n")
        if success:
            QMessageBox.information(self, "Installation Complete", message)
            self.current_step_index = self.stacked_widget.indexOf(self.complete_page)
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        else:
            QMessageBox.critical(self, "Installation Failed", f"{message}\nCheck logs for details.")
            self.prev_button.setEnabled(True) # Allow going back from progress page on failure
        self.update_nav_buttons()

    def create_installation_progress_step(self, layout):
        layout.addWidget(self.create_styled_label("Installing Mai Bloom OS...", 18, Qt.AlignCenter, True))
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(False) # Indeterminate usually doesn't show percentage
        self.progress_bar.setStyleSheet("QProgressBar { min-height: 25px; }")
        layout.addWidget(self.progress_bar)
        self.install_log_area = QTextEdit(); self.install_log_area.setReadOnly(True)
        self.install_log_area.setFontFamily("Monospace"); self.install_log_area.setLineWrapMode(QTextEdit.NoWrap) # NoWrap for logs
        layout.addWidget(self.install_log_area)

    def create_installation_complete_step(self, layout):
        layout.addWidget(self.create_styled_label("Installation Successfully Completed!", 20, Qt.AlignCenter, True))
        msg = QLabel("Congratulations! Mai Bloom OS has been installed on your computer.\n\nPlease remove any installation media (like USB drives) and then click 'Restart Now' to boot into your new system.")
        msg.setWordWrap(True); msg.setAlignment(Qt.AlignCenter); layout.addWidget(msg); layout.addStretch()

    def restart_system(self):
        reply = QMessageBox.information(self, "Restart System", "The system will now attempt to restart. Please remove the installation medium.", QMessageBox.Ok | QMessageBox.Cancel)
        if reply == QMessageBox.Ok:
            print("Simulating system restart... (In a real scenario, use 'sudo reboot')")
            # For actual reboot:
            # try: subprocess.run(["sudo", "reboot"], check=True) # Sudo needed if script not run as root initially
            # except Exception as e: QMessageBox.warning(self, "Restart Failed", f"Could not reboot: {e}. Please restart manually.")
            QApplication.instance().quit()

    def closeEvent(self, event):
        if self.install_thread and self.install_thread.isRunning():
            reply = QMessageBox.question(self, 'Confirm Exit', "Installation is in progress. Exiting now may damage your system. Are you sure you want to exit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.install_thread.stop(); self.install_thread.quit(); self.install_thread.wait(3000)
                event.accept()
            else: event.ignore()
        else: event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    # It's generally better to launch the GUI, and then the GUI itself can prompt for sudo or
    # specific actions that need sudo can use 'pkexec' or 'sudo' internally if designed that way.
    # For a full system installer, running the entire GUI as root is common, but be mindful of security.
    # if os.geteuid() != 0:
    #     QMessageBox.critical(None, "Root Privileges Required", "This installer needs root privileges to run correctly. Please start it with sudo.")
    #     sys.exit(1)
    installer = MaiBloomInstaller()
    installer.show()
    sys.exit(app.exec_())

