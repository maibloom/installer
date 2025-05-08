import sys
import subprocess
import json # For parsing lsblk output and generating archinstall config
import tempfile # For creating a temporary config file
import os # For file operations like removing temp file
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QStackedWidget, QMessageBox, QProgressBar, QTextEdit,
    QStyleFactory, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal # Added QThread, pyqtSignal

def bytes_to_human_readable(size_bytes):
    """Converts a size in bytes to a human-readable string (GiB, MiB, etc.)."""
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    i = 0
    # Ensure size_bytes is a number for comparison
    try:
        size_bytes_num = float(size_bytes)
    except (ValueError, TypeError):
        return "N/A" # Or some other error indicator

    while size_bytes_num >= 1024 and i < len(size_name) - 1:
        size_bytes_num /= 1024.0
        i += 1
    return f"{size_bytes_num:.1f} {size_name[i]}"

# --- ArchInstallThread Class ---
class ArchInstallThread(QThread):
    log_update = pyqtSignal(str) # Signal to send log lines to the GUI
    installation_finished = pyqtSignal(bool, str) # Signal for completion (success_flag, message)

    def __init__(self, config_dict, parent=None):
        super().__init__(parent)
        self.config_dict = config_dict
        self.config_file_path = None
        self._is_running = True

    def run(self):
        try:
            # Create a temporary file for the JSON configuration
            # delete=False is important because archinstall needs to read it after we close it.
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', prefix='mai_bloom_archinstall_') as tmp_file:
                json.dump(self.config_dict, tmp_file, indent=2) # indent for readability if debugging
                self.config_file_path = tmp_file.name
            self.log_update.emit(f"Archinstall configuration saved to: {self.config_file_path}\n")

            command = ["archinstall", "--config", self.config_file_path, "--silent"]
            self.log_update.emit(f"Executing command: {' '.join(command)}\n")
            self.log_update.emit("--- Installation Started (Output from archinstall) ---\n")

            # Run archinstall
            # Ensure archinstall is in PATH or provide full path if necessary
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)

            while self._is_running:
                line = process.stdout.readline()
                if line:
                    self.log_update.emit(line)
                else:
                    # Process might have finished or no more output
                    if process.poll() is not None: # Check if process has terminated
                        break # Exit loop if process terminated
                    # QThread.msleep(50) # Optional: short sleep if readline is blocking too much without output
            
            # Ensure all output is read
            for remaining_line in process.stdout:
                self.log_update.emit(remaining_line)

            process.stdout.close()
            return_code = process.wait() # Wait for process to complete fully

            self.log_update.emit("\n--- Installation Ended ---\n")

            if return_code == 0:
                self.log_update.emit("Archinstall process completed successfully.")
                self.installation_finished.emit(True, "Installation successful! Mai Bloom OS is ready.")
            else:
                self.log_update.emit(f"Archinstall process failed with exit code: {return_code}")
                self.installation_finished.emit(False, f"Installation failed (exit code: {return_code}). Please check the logs for details.")

        except FileNotFoundError:
            self.log_update.emit("\nError: 'archinstall' command not found. Please ensure it is installed and in your PATH.")
            self.installation_finished.emit(False, "'archinstall' command not found.")
        except Exception as e:
            self.log_update.emit(f"\nAn error occurred during the installation thread: {str(e)}")
            self.installation_finished.emit(False, f"An critical error occurred: {str(e)}")
        finally:
            # Clean up the temporary config file
            if self.config_file_path and os.path.exists(self.config_file_path):
                try:
                    os.remove(self.config_file_path)
                    self.log_update.emit(f"Temporary config file {self.config_file_path} removed.\n")
                except OSError as e:
                    self.log_update.emit(f"Error removing temporary config file {self.config_file_path}: {e}\n")
    
    def stop(self):
        self._is_running = False


# --- MaiBloomInstaller Class ---
class MaiBloomInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mai Bloom OS Installer")
        self.setGeometry(100, 100, 750, 550)
        self.setMinimumSize(700, 500)
        self.install_thread = None # For managing the installation thread

        QApplication.setStyle(QStyleFactory.create('Fusion'))

        self.config = {
            "language": "English (US)",
            "keyboard_layout": None,
            "timezone_region": None,
            "timezone_city": None,
            "disk_target": None,
            "partition_scheme": "automatic",
            "hostname": "maibloom-pc",
            "username": None,
            "password": None,
            "desktop_environment": "KDE Plasma (Mai Bloom Default)",
            "additional_packages": []
        }

        self.main_layout = QVBoxLayout(self)
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        self.welcome_page = QWidget()
        self.lang_kb_page = QWidget()
        self.timezone_page = QWidget()
        self.partition_page = QWidget()
        self.hostname_page = QWidget()
        self.user_page = QWidget()
        self.desktop_page = QWidget()
        self.summary_page = QWidget()
        self.progress_page = QWidget()
        self.complete_page = QWidget()

        self.nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.prev_step_clicked)
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.next_step_clicked)
        self.install_button = QPushButton("Install Mai Bloom OS")
        self.install_button.clicked.connect(self.confirm_installation)
        self.install_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        self.restart_button = QPushButton("Restart Now")
        self.restart_button.clicked.connect(self.restart_system)
        self.restart_button.setStyleSheet("background-color: #007BFF; color: white; padding: 10px; font-weight: bold;")


        self.nav_layout.addWidget(self.prev_button)
        self.nav_layout.addStretch()
        self.nav_layout.addWidget(self.next_button)
        self.nav_layout.addWidget(self.install_button)
        self.nav_layout.addWidget(self.restart_button)
        self.main_layout.addLayout(self.nav_layout)

        self.steps_config_map = [
            (self.welcome_page, self.create_welcome_step),
            (self.lang_kb_page, self.create_language_keyboard_step),
            (self.timezone_page, self.create_timezone_step),
            (self.partition_page, self.create_partition_step),
            (self.hostname_page, self.create_hostname_step),
            (self.user_page, self.create_user_step),
            (self.desktop_page, self.create_desktop_step), # Confirmation for KDE
            (self.summary_page, self.create_install_summary_step),
            (self.progress_page, self.create_installation_progress_step),
            (self.complete_page, self.create_installation_complete_step)
        ]

        for page_widget, creator_function in self.steps_config_map:
            page_layout = QVBoxLayout(page_widget)
            creator_function(page_layout)
            self.stacked_widget.addWidget(page_widget)

        self.current_step_index = 0
        self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons()

    def get_available_drives(self):
        drives = []
        try:
            result = subprocess.run(
                ["lsblk", "-Jbo", "NAME,SIZE,MODEL,TYPE,RO,RM,PATH,FSTYPE,MOUNTPOINT"], # Added FSTYPE, MOUNTPOINT
                capture_output=True, text=True, check=True, timeout=5 # Added timeout
            )
            data = json.loads(result.stdout)
            active_mountpoints = ['/', '/boot', '/home', '/var', '/usr'] # Common system mountpoints
            # Try to identify the disk the current OS is running from
            # This is a heuristic and might not be foolproof
            running_os_disk_path = None
            for device_info in data.get("blockdevices", []):
                if device_info.get("mountpoint") in active_mountpoints:
                    # Find the parent disk for this partition
                    pkname = device_info.get("pkname") # Parent kernel name
                    if pkname:
                         for d in data.get("blockdevices", []):
                             if d.get("name") == pkname and d.get("type") == "disk":
                                 running_os_disk_path = d.get("path")
                                 break
                    elif device_info.get("type") == "disk": # if mountpoint is directly on disk (e.g. /)
                        running_os_disk_path = device_info.get("path")
                    if running_os_disk_path:
                        break


            for device in data.get("blockdevices", []):
                if device.get("type") == "disk" and not device.get("ro", False):
                    if device.get("name", "").startswith("loop"):
                        continue
                    
                    device_path = device.get("path", f"/dev/{device.get('name')}")
                    # Skip the disk the current OS seems to be running on
                    if device_path == running_os_disk_path:
                        # self.append_to_log(f"Skipping live OS disk: {device_path}") # For debugging if log available early
                        print(f"Debug: Skipping potential live OS disk: {device_path}")
                        continue

                    model = device.get("model", "Unknown Model")
                    size_bytes = device.get("size", 0)
                    try:
                        size_bytes = int(size_bytes)
                    except (ValueError, TypeError):
                        size_bytes = 0

                    size_readable = bytes_to_human_readable(size_bytes)
                    display_text = f"{device_path} ({model}) - {size_readable}"
                    drives.append({"path": device_path, "display": display_text, "size": size_bytes})
        except subprocess.TimeoutExpired:
            print("lsblk command timed out.")
            QMessageBox.warning(self, "Drive Detection Error", "Drive detection timed out. Please try again.")
            return []
        except FileNotFoundError:
            print("lsblk command not found.")
            QMessageBox.critical(self, "Error", "lsblk command not found. Cannot detect drives.")
            return []
        except subprocess.CalledProcessError as e:
            print(f"Error running lsblk: {e.output}") # Log output for debugging
            QMessageBox.warning(self, "Drive Detection Error", f"Could not list drives: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing lsblk output: {e}")
            QMessageBox.warning(self, "Drive Detection Error", "Error reading drive information.")
            return []
        return sorted(drives, key=lambda x: x["path"])

    def update_nav_buttons(self):
        current_widget = self.stacked_widget.widget(self.current_step_index)
        is_first_step = self.current_step_index == 0
        is_summary_step = current_widget == self.summary_page
        is_progress_step = current_widget == self.progress_page
        is_complete_step = current_widget == self.complete_page

        self.prev_button.setEnabled(not is_first_step and not is_progress_step and not is_complete_step)
        self.next_button.setVisible(not is_summary_step and not is_progress_step and not is_complete_step)
        self.install_button.setVisible(is_summary_step)
        self.restart_button.setVisible(is_complete_step)

        if is_progress_step or is_complete_step:
            self.prev_button.setVisible(False)
        
        if current_widget == self.partition_page:
            self.next_button.setEnabled(hasattr(self, 'disk_combo') and self.disk_combo.count() > 0 and self.disk_combo.currentData() is not None)
        elif not (is_progress_step or is_complete_step or is_summary_step): # For other steps
             self.next_button.setEnabled(True)


    def validate_current_step(self):
        current_widget = self.stacked_widget.widget(self.current_step_index)
        if current_widget == self.lang_kb_page:
            if not self.kb_layout_combo.currentText() or self.kb_layout_combo.currentText() == "Select...":
                QMessageBox.warning(self, "Input Error", "Please select a keyboard layout.")
                return False
            self.config["language"] = self.lang_combo.currentText()
            self.config["keyboard_layout"] = self.kb_layout_combo.currentText()
        elif current_widget == self.timezone_page:
            tz_region = self.tz_region_combo.currentText()
            tz_city = self.tz_city_combo.currentText()
            if not tz_region or tz_region == "Select Region...":
                 QMessageBox.warning(self, "Input Error", "Please select a timezone region.")
                 return False
            if not tz_city or tz_city == "Select City...":
                 QMessageBox.warning(self, "Input Error", "Please select a timezone city.")
                 return False
            self.config["timezone_region"] = tz_region
            self.config["timezone_city"] = tz_city
        elif current_widget == self.partition_page:
            if not hasattr(self, 'disk_combo') or self.disk_combo.currentIndex() == -1 or not self.disk_combo.currentData():
                QMessageBox.warning(self, "Input Error", "Please select a target disk for installation.")
                return False
            self.config["disk_target"] = self.disk_combo.currentData()
            self.config["partition_scheme"] = "automatic"
        elif current_widget == self.hostname_page:
            hostname = self.hostname_input.text().strip()
            if not hostname:
                QMessageBox.warning(self, "Input Error", "Hostname cannot be empty.")
                return False
            self.config["hostname"] = hostname
        elif current_widget == self.user_page:
            username = self.username_input.text().strip()
            password = self.password_input.text()
            password_confirm = self.password_confirm_input.text()
            if not username: QMessageBox.warning(self, "Input Error", "Username cannot be empty."); return False
            if not password: QMessageBox.warning(self, "Input Error", "Password cannot be empty."); return False
            if password != password_confirm: QMessageBox.warning(self, "Input Error", "Passwords do not match."); return False
            self.config["username"] = username
            self.config["password"] = password
        return True

    def next_step_clicked(self):
        if not self.validate_current_step():
            self.update_nav_buttons() # Ensure next button state is correct after failed validation
            return
        if self.current_step_index < self.stacked_widget.count() - 1:
            next_page_widget = self.stacked_widget.widget(self.current_step_index + 1)
            if next_page_widget == self.summary_page:
                self.update_summary_contents()
            self.current_step_index += 1
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons()

    def prev_step_clicked(self):
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons()

    def create_styled_label(self, text, point_size=12, alignment=Qt.AlignLeft, is_title=False):
        label = QLabel(text)
        font = label.font(); font.setPointSize(point_size)
        if is_title: font.setBold(True)
        label.setFont(font); label.setAlignment(alignment)
        if is_title: label.setStyleSheet("margin-bottom: 10px; color: #333;")
        return label

    def create_welcome_step(self, layout):
        layout.addWidget(self.create_styled_label("Welcome to Mai Bloom OS Installer!", 20, Qt.AlignCenter, True))
        intro = QLabel("This installer guides you through installing Mai Bloom OS, an Arch Linux-based distribution with KDE Plasma.\n\n<b>Ensure important data is backed up before proceeding.</b>")
        intro.setWordWrap(True); layout.addWidget(intro); layout.addStretch()

    def create_language_keyboard_step(self, layout):
        layout.addWidget(self.create_styled_label("Language & Keyboard", 16, Qt.AlignCenter, True))
        box = QGroupBox("Localization"); box_layout = QVBoxLayout()
        box_layout.addWidget(QLabel("Installation Language:"))
        self.lang_combo = QComboBox(); self.lang_combo.addItems(["English (US)", "Español (España)", "Français (France)", "Deutsch (Deutschland)"])
        self.lang_combo.setCurrentText(self.config.get("language", "English (US)")); box_layout.addWidget(self.lang_combo)
        box_layout.addSpacing(15); box_layout.addWidget(QLabel("Keyboard Layout:"))
        self.kb_layout_combo = QComboBox(); self.kb_layout_combo.addItems(["Select...", "us", "uk", "es", "fr", "de", "dvorak"])
        self.kb_layout_combo.setCurrentText(self.config.get("keyboard_layout") if self.config.get("keyboard_layout") else "Select...")
        box_layout.addWidget(self.kb_layout_combo); box.setLayout(box_layout); layout.addWidget(box); layout.addStretch()

    def create_timezone_step(self, layout):
        layout.addWidget(self.create_styled_label("Timezone", 16, Qt.AlignCenter, True))
        box = QGroupBox("Select Your Timezone"); box_layout = QVBoxLayout()
        box_layout.addWidget(QLabel("Region:")); self.tz_region_combo = QComboBox()
        self.tz_region_combo.addItems(["Select Region...", "America", "Europe", "Asia", "Australia", "Africa", "Etc"])
        box_layout.addWidget(self.tz_region_combo); box_layout.addWidget(QLabel("City/Area:"))
        self.tz_city_combo = QComboBox(); box_layout.addWidget(self.tz_city_combo)
        self.tz_region_combo.currentTextChanged.connect(self.update_city_combo)
        # Initial population
        current_region = self.config.get("timezone_region")
        if current_region: self.tz_region_combo.setCurrentText(current_region)
        self.update_city_combo(self.tz_region_combo.currentText()) # Populate cities based on current/default region
        current_city = self.config.get("timezone_city")
        if current_city: self.tz_city_combo.setCurrentText(current_city)

        box.setLayout(box_layout); layout.addWidget(box); layout.addStretch()

    def update_city_combo(self, region):
        self.tz_city_combo.clear()
        cities = {
            "America": ["New_York", "Los_Angeles", "Chicago", "Denver", "Toronto", "Vancouver", "Mexico_City", "Sao_Paulo", "Buenos_Aires"],
            "Europe": ["London", "Paris", "Berlin", "Madrid", "Rome", "Moscow", "Kyiv", "Amsterdam", "Stockholm", "Oslo"],
            "Asia": ["Tokyo", "Shanghai", "Kolkata", "Dubai", "Hong_Kong", "Singapore", "Seoul", "Tehran", "Baghdad", "Riyadh"],
            "Australia": ["Sydney", "Melbourne", "Perth", "Brisbane", "Auckland"],
            "Africa": ["Cairo", "Johannesburg", "Nairobi", "Lagos", "Algiers", "Casablanca"],
            "Etc": ["UTC", "GMT"]
        }
        self.tz_city_combo.addItems(["Select City..."] + cities.get(region, []))
        # Attempt to restore previous selection if applicable
        if self.config.get("timezone_region") == region and self.config.get("timezone_city") in [self.tz_city_combo.itemText(i) for i in range(self.tz_city_combo.count())]:
            self.tz_city_combo.setCurrentText(self.config["timezone_city"])
        else:
            self.tz_city_combo.setCurrentIndex(0) # Default to "Select City..."


    def create_partition_step(self, layout):
        layout.addWidget(self.create_styled_label("Disk Selection & Automatic Partitioning", 16, Qt.AlignCenter, True))
        box = QGroupBox("Target Disk for Installation"); box_layout = QVBoxLayout()
        box_layout.addWidget(QLabel("Select Target Disk:"))
        self.disk_combo = QComboBox()
        available_drives = self.get_available_drives()
        if not available_drives:
            self.disk_combo.addItem("No suitable drives found or error.")
            self.disk_combo.setEnabled(False)
        else:
            self.disk_combo.addItem("Select a disk...", None) # Placeholder item with None data
            for drive in available_drives:
                self.disk_combo.addItem(drive["display"], userData=drive["path"])
        self.disk_combo.currentIndexChanged.connect(lambda: self.update_nav_buttons()) # Update nav on selection change
        box_layout.addWidget(self.disk_combo); box_layout.addSpacing(15)
        warning_text = ("<b><font color='red'>WARNING:</font> The entire selected disk will be ERASED.</b>\n"
                        "All existing data on this disk will be lost.\n\n"
                        "Mai Bloom OS will automatically partition the disk with:\n"
                        "  - EFI System Partition (for boot, FAT32)\n"
                        "  - Root partition (<code>/</code>, ext4) for OS & apps\n"
                        "  - Home partition (<code>/home</code>, ext4) for user files\n"
                        "  - Swap partition (for virtual memory)\n")
        info_label = QLabel(warning_text); info_label.setWordWrap(True)
        box_layout.addWidget(info_label); box.setLayout(box_layout)
        layout.addWidget(box); layout.addStretch()

    def create_hostname_step(self, layout):
        layout.addWidget(self.create_styled_label("Computer Name (Hostname)", 16, Qt.AlignCenter, True))
        box = QGroupBox("Network Identification"); box_layout = QVBoxLayout()
        box_layout.addWidget(QLabel("Enter a hostname (e.g., maibloom-desktop):"))
        self.hostname_input = QLineEdit(self.config.get("hostname", "maibloom-pc"))
        box_layout.addWidget(self.hostname_input)
        info = QLabel("The hostname identifies your computer on the network."); info.setWordWrap(True)
        box_layout.addWidget(info); box.setLayout(box_layout); layout.addWidget(box); layout.addStretch()

    def create_user_step(self, layout):
        layout.addWidget(self.create_styled_label("Create User Account", 16, Qt.AlignCenter, True))
        box = QGroupBox("Your User Details"); box_layout = QVBoxLayout()
        box_layout.addWidget(QLabel("Username (e.g., bloom):"))
        self.username_input = QLineEdit(self.config.get("username", ""))
        box_layout.addWidget(self.username_input)
        box_layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit(); self.password_input.setEchoMode(QLineEdit.Password)
        box_layout.addWidget(self.password_input)
        box_layout.addWidget(QLabel("Confirm Password:"))
        self.password_confirm_input = QLineEdit(); self.password_confirm_input.setEchoMode(QLineEdit.Password)
        box_layout.addWidget(self.password_confirm_input)
        box.setLayout(box_layout); layout.addWidget(box); layout.addStretch()

    def create_desktop_step(self, layout): # Confirms KDE Plasma
        layout.addWidget(self.create_styled_label("Desktop Environment Confirmation", 16, Qt.AlignCenter, True))
        box = QGroupBox("Your Mai Bloom OS Experience"); box_layout = QVBoxLayout()
        de_label = QLabel("Mai Bloom OS is configured to install <b>KDE Plasma</b> as your desktop environment.")
        de_label.setWordWrap(True); box_layout.addWidget(de_label)
        kde_info = QLabel("This provides a powerful, customizable, and modern desktop. All necessary KDE components will be installed by default.")
        kde_info.setWordWrap(True); box_layout.addWidget(kde_info)
        box.setLayout(box_layout); layout.addWidget(box); layout.addStretch()


    def create_install_summary_step(self, layout):
        layout.addWidget(self.create_styled_label("Installation Summary", 16, Qt.AlignCenter, True))
        self.summary_text_area = QTextEdit(); self.summary_text_area.setReadOnly(True)
        layout.addWidget(self.summary_text_area)

    def update_summary_contents(self):
        if hasattr(self, 'disk_combo') and self.disk_combo and self.disk_combo.currentData():
            self.config["disk_target"] = self.disk_combo.currentData()
        else:
            self.config["disk_target"] = "N/A - No disk selected"

        summary = "<b>Please review your installation settings:</b>\n\n"
        summary += f"- <b>Language:</b> {self.config.get('language', 'N/A')}\n"
        summary += f"- <b>Keyboard Layout:</b> {self.config.get('keyboard_layout', 'N/A')}\n"
        tz_r, tz_c = self.config.get('timezone_region', 'N/A'), self.config.get('timezone_city', 'N/A')
        summary += f"- <b>Timezone:</b> {tz_r}/{tz_c}\n"
        summary += f"- <b>Target Disk:</b> {self.config.get('disk_target', 'N/A')}\n"
        summary += f"- <b>Partitioning:</b> Automatic (Entire disk will be erased and partitioned for KDE Desktop)\n"
        summary += f"- <b>Hostname:</b> {self.config.get('hostname', 'N/A')}\n"
        summary += f"- <b>Username:</b> {self.config.get('username', 'N/A')}\n"
        summary += f"- <b>Password:</b> {'Set (hidden)' if self.config.get('password') else 'Not Set'}\n"
        summary += f"- <b>Desktop Environment:</b> KDE Plasma (Default for Mai Bloom OS)\n"
        summary += "\n<b><font color='red'>WARNING:</font> Proceeding will ERASE the selected disk ({}) "
        summary = summary.format(self.config.get('disk_target', 'N/A'))
        summary += "and install Mai Bloom OS. This action cannot be undone. Ensure data is backed up.</b>"
        self.summary_text_area.setText(summary)

    def confirm_installation(self):
        if not self.config.get("disk_target") or "N/A" in str(self.config.get("disk_target")) or self.config.get("disk_target") is None:
            QMessageBox.critical(self, "Disk Not Selected", "A target disk for installation must be selected from the 'Disk Selection' step.")
            return

        reply = QMessageBox.warning(self, "Confirm Installation",
                                    f"<b>ARE YOU ABSOLUTELY SURE?</b>\n\n"
                                    f"The disk <b>{self.config.get('disk_target')}</b> will be completely <b>ERASED</b> and Mai Bloom OS will be installed.\n\n"
                                    "This action is irreversible.",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.current_step_index = self.stacked_widget.indexOf(self.progress_page)
            self.stacked_widget.setCurrentIndex(self.current_step_index)
            self.update_nav_buttons()
            self.start_actual_installation() # This now starts the thread

    # --- Archinstall JSON Generation ---
    def generate_archinstall_config(self):
        lang_map = {
            "English (US)": "en_US.UTF-8", "Español (España)": "es_ES.UTF-8",
            "Français (France)": "fr_FR.UTF-8", "Deutsch (Deutschland)": "de_DE.UTF-8",
        }
        sys_lang = lang_map.get(self.config.get("language"), "en_US.UTF-8")

        # Validate critical fields before proceeding
        if not self.config.get("disk_target") or self.config.get("disk_target") == "N/A - No disk selected":
            raise ValueError("Target disk is not selected or is invalid.")
        if not self.config.get("username") or not self.config.get("password"):
            raise ValueError("Username or password has not been set.")
        if not self.config.get("timezone_region") or self.config.get("timezone_city") or \
           self.config.get("timezone_region") == "Select Region..." or \
           self.config.get("timezone_city") == "Select City...":
            raise ValueError("Timezone is not fully selected.")
        if not self.config.get("keyboard_layout") or self.config.get("keyboard_layout") == "Select...":
            raise ValueError("Keyboard layout not selected.")


        arch_config = {
            "archinstall-language": "English",
            "hostname": self.config.get("hostname", "maibloom-pc"),
            "locale_config": {
                "kb_layout": self.config.get("keyboard_layout", "us"),
                "sys_enc": "UTF-8",
                "sys_lang": sys_lang
            },
            "timezone": f"{self.config.get('timezone_region')}/{self.config.get('timezone_city')}",
            "!users": [ # Using !users as per archinstall 2.8.x example
                {
                    "username": self.config.get("username"),
                    "!password": self.config.get("password"),
                    "sudo": True
                }
            ],
            "disk_config": { # Tells archinstall how to handle disks
                "config_type": "default_layout", # Instructs archinstall to use its default partitioning scheme for the profile
                "device_modifications": [
                    {
                        "device": self.config.get("disk_target"),
                        "wipe": True,
                        # No "partitions" array here: archinstall + profile will define them
                        # This implies ESP, /, /home, and swap for a desktop profile
                    }
                ]
            },
            "profile_config": {
                "gfx_driver": "All open-source (default)",
                "greeter": "sddm", # For KDE Plasma
                "profile": {
                    "details": ["KDE Plasma"], # Your specified DE
                    "main": "Desktop"          # Your specified profile type
                }
            },
            "audio_config": {"audio": "pipewire"},
            "bootloader": "Systemd-boot", # Ensure target system is UEFI
            "kernels": ["linux"],
            "swap": True, # Let archinstall create a swap partition/file
            "ntp": True,  # Enable time synchronization
            "packages": [], # Add any Mai Bloom OS specific packages if needed
            # "mirror_config": {} # Omitted: Let archinstall handle mirror selection
            # "network_config": {} # Omitted: Let NetworkManager from profile handle DHCP
            "debug": False, # Set to true for more verbose archinstall logs if needed during dev
            "version": "2.8.6" # From user's example JSON
        }
        return arch_config

    # --- Installation Process Handling ---
    def start_actual_installation(self):
        self.install_log_area.clear()
        self.install_log_area.append("Preparing for installation...\n")
        self.progress_bar.setRange(0, 0) # Indeterminate progress
        self.progress_bar.setValue(0) # Style purpose for indeterminate

        try:
            arch_config_dict = self.generate_archinstall_config()
            self.install_log_area.append("Archinstall configuration generated.\n")
            # self.install_log_area.append(f"DEBUG CONFIG:\n{json.dumps(arch_config_dict, indent=2)}\n") # Uncomment for debugging

            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False) # Should already be hidden
            self.install_button.setEnabled(False) # Disable during installation

            self.install_thread = ArchInstallThread(arch_config_dict)
            self.install_thread.log_update.connect(self.append_to_log)
            self.install_thread.installation_finished.connect(self.on_installation_finished)
            self.install_thread.start()
            self.install_log_area.append("Installation thread started. Please wait...\n")

        except ValueError as ve:
            error_msg = f"Configuration Error: {ve}"
            self.install_log_area.append(f"{error_msg}\n")
            QMessageBox.critical(self, "Configuration Error", f"Failed to prepare installation: {ve}\nPlease go back and review your selections.")
            self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0) # Reset
            # Enable relevant buttons for correction
            self.current_step_index = self.stacked_widget.indexOf(self.summary_page) # Go back to summary
            self.stacked_widget.setCurrentIndex(self.current_step_index)
            self.update_nav_buttons() # Re-enable summary page buttons
            return
        except Exception as e:
            error_msg = f"An critical error occurred before installation: {e}"
            self.install_log_area.append(f"{error_msg}\n")
            QMessageBox.critical(self, "Error", error_msg)
            self.progress_bar.setRange(0, 100); self.progress_bar.setValue(0)
            self.update_nav_buttons()
            return

    def append_to_log(self, text):
        self.install_log_area.insertPlainText(text) # Preserves formatting better than append sometimes
        self.install_log_area.verticalScrollBar().setValue(self.install_log_area.verticalScrollBar().maximum())
        QApplication.processEvents() # Keep UI responsive for log updates

    def on_installation_finished(self, success, message):
        self.progress_bar.setRange(0, 100) # Back to determinate
        self.progress_bar.setValue(100 if success else 0) # Show full or zero based on success
        self.install_log_area.append(f"\n--- {message} ---\n")

        if success:
            QMessageBox.information(self, "Installation Complete", message)
            self.current_step_index = self.stacked_widget.indexOf(self.complete_page)
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        else:
            QMessageBox.critical(self, "Installation Failed", f"{message}\nPlease check the installation log for details.")
            # User remains on progress page to see logs
            # Allow going back to summary to try again or change settings
            self.prev_button.setEnabled(True) # Allow going back from progress page on failure
            self.install_button.setVisible(False) # Hide install button here, it's on summary page
        
        self.update_nav_buttons() # Update nav based on new page or state


    def create_installation_progress_step(self, layout):
        layout.addWidget(self.create_styled_label("Installing Mai Bloom OS...", 16, Qt.AlignCenter, True))
        self.progress_bar = QProgressBar(); self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        self.install_log_area = QTextEdit(); self.install_log_area.setReadOnly(True)
        self.install_log_area.setFontFamily("Monospace"); self.install_log_area.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.install_log_area)
        # QTimer for simulation is removed, actual progress comes from ArchInstallThread

    def create_installation_complete_step(self, layout):
        layout.addWidget(self.create_styled_label("Installation Complete!", 20, Qt.AlignCenter, True))
        msg = QLabel("Mai Bloom OS has been successfully installed!\nRemove installation media and click 'Restart Now'.")
        msg.setWordWrap(True); msg.setAlignment(Qt.AlignCenter); layout.addWidget(msg); layout.addStretch()

    def restart_system(self):
        reply = QMessageBox.information(self, "Restart System",
                                    "The system will now attempt to restart. Please remove the installation medium.",
                                    QMessageBox.Ok | QMessageBox.Cancel)
        if reply == QMessageBox.Ok:
            print("Simulating system restart... (In a real scenario, run 'reboot')")
            # For a real reboot:
            # try:
            #     subprocess.run(["reboot"], check=True)
            # except Exception as e:
            #     QMessageBox.warning(self, "Restart Failed", f"Could not reboot automatically: {e}. Please restart manually.")
            QApplication.instance().quit()

    def closeEvent(self, event):
        # Ensure thread is stopped if application is closed prematurely
        if self.install_thread and self.install_thread.isRunning():
            reply = QMessageBox.question(self, 'Confirm Exit',
                                         "Installation is in progress. Are you sure you want to exit? This may leave your system in an inconsistent state.",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.install_thread.stop() # Signal thread to stop (if it checks the flag)
                self.install_thread.quit() # Ask Qt event loop of thread to quit
                self.install_thread.wait(5000) # Wait for thread to finish
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # For a real installer, you might need to check for root privileges here
    # if os.geteuid() != 0:
    #     QMessageBox.critical(None, "Error", "This installer must be run as root (e.g., using sudo).")
    #     sys.exit(1)
    installer = MaiBloomInstaller()
    installer.show()
    sys.exit(app.exec_())

