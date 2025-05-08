import sys
import subprocess
import json # For parsing lsblk output
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QStackedWidget, QMessageBox, QProgressBar, QTextEdit,
    QStyleFactory, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer

def bytes_to_human_readable(size_bytes):
    """Converts a size in bytes to a human-readable string (GiB, MiB, etc.)."""
    if size_bytes == 0:
        return "0 B"
    size_name = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB", "YiB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_name[i]}"

class MaiBloomInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mai Bloom OS Installer")
        self.setGeometry(100, 100, 750, 550)
        self.setMinimumSize(700, 500)

        QApplication.setStyle(QStyleFactory.create('Fusion'))

        self.config = {
            "language": "English (US)",
            "keyboard_layout": None,
            "timezone_region": None,
            "timezone_city": None,
            "disk_target": None, # This will store the device path like /dev/sda
            "partition_scheme": "automatic", # Hardcoded as per request
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
        self.install_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px;")
        self.restart_button = QPushButton("Restart Now")
        self.restart_button.clicked.connect(self.restart_system)

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
            (self.desktop_page, self.create_desktop_step),
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
        """Uses lsblk to find suitable disk drives for installation."""
        drives = []
        try:
            # Get non-removable, read-write block devices of type disk, including their model and size
            # lsblk -Jbo NAME,SIZE,MODEL,TYPE,RO,RM,PATH
            # Using PATH directly is better than concatenating "/dev/" + name
            result = subprocess.run(
                ["lsblk", "-Jbo", "NAME,SIZE,MODEL,TYPE,RO,RM,PATH"],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)
            for device in data.get("blockdevices", []):
                # We want actual disks, not partitions, and not read-only or removable ones typically
                # For installing *to* a USB, RM filter might need adjustment, but for internal it's fine.
                if device.get("type") == "disk" and not device.get("ro", False):
                    # Filter out loop devices if they appear as disks (sometimes snap/flatpak related)
                    if device.get("name", "").startswith("loop"):
                        continue

                    name = device.get("path", f"/dev/{device.get('name')}") # Prefer full path
                    model = device.get("model", "Unknown Model")
                    size_bytes = device.get("size", 0)
                    # Ensure size_bytes is int or float
                    try:
                        size_bytes = int(size_bytes)
                    except (ValueError, TypeError):
                        size_bytes = 0 # Or skip this device

                    size_readable = bytes_to_human_readable(size_bytes)
                    display_text = f"{name} ({model}) - {size_readable}"
                    drives.append({"path": name, "display": display_text, "size": size_bytes})
        except FileNotFoundError:
            print("lsblk command not found. Cannot detect drives.")
            QMessageBox.critical(self, "Error", "lsblk command not found. Cannot detect drives.")
            return [] # Return empty list on critical error
        except subprocess.CalledProcessError as e:
            print(f"Error running lsblk: {e}")
            QMessageBox.warning(self, "Drive Detection Error", f"Could not list drives: {e}")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing lsblk output: {e}")
            QMessageBox.warning(self, "Drive Detection Error", "Error reading drive information.")
            return []

        # Sort drives by name for consistent order
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

        # Disable Next on partition page if no drives are selectable
        if current_widget == self.partition_page:
            if hasattr(self, 'disk_combo') and self.disk_combo.count() == 0:
                self.next_button.setEnabled(False)
            else:
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
            if not self.tz_region_combo.currentText() or self.tz_region_combo.currentText() == "Select Region...":
                 QMessageBox.warning(self, "Input Error", "Please select a timezone region.")
                 return False
            if self.tz_region_combo.currentText() != "Select Region..." and \
               (not self.tz_city_combo.currentText() or self.tz_city_combo.currentText() == "Select City..."):
                 QMessageBox.warning(self, "Input Error", "Please select a timezone city.")
                 return False
            if self.tz_region_combo.currentText() != "Select Region...": # Save only if valid
                self.config["timezone_region"] = self.tz_region_combo.currentText()
                self.config["timezone_city"] = self.tz_city_combo.currentText()
            else: # Clear if not fully selected
                self.config["timezone_region"] = None
                self.config["timezone_city"] = None


        elif current_widget == self.partition_page:
            if self.disk_combo.currentIndex() == -1 or not self.disk_combo.currentData():
                QMessageBox.warning(self, "Input Error", "Please select a target disk for installation.")
                return False
            self.config["disk_target"] = self.disk_combo.currentData() # Store the device path
            self.config["partition_scheme"] = "automatic" # Explicitly set, though default

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
            if not username:
                QMessageBox.warning(self, "Input Error", "Username cannot be empty.")
                return False
            if not password:
                QMessageBox.warning(self, "Input Error", "Password cannot be empty.")
                return False
            if password != password_confirm:
                QMessageBox.warning(self, "Input Error", "Passwords do not match.")
                return False
            self.config["username"] = username
            self.config["password"] = password
        return True


    def next_step_clicked(self):
        if not self.validate_current_step():
            return

        if self.current_step_index < self.stacked_widget.count() - 1:
            next_page_widget = self.stacked_widget.widget(self.current_step_index + 1)
            if next_page_widget == self.summary_page:
                self.update_summary_contents()

            self.current_step_index += 1
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons() # Call regardless to update button states

    def prev_step_clicked(self):
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.stacked_widget.setCurrentIndex(self.current_step_index)
        self.update_nav_buttons() # Call regardless

    def create_styled_label(self, text, point_size=12, alignment=Qt.AlignLeft, is_title=False):
        label = QLabel(text)
        font = label.font()
        font.setPointSize(point_size)
        if is_title:
            font.setBold(True)
        label.setFont(font)
        label.setAlignment(alignment)
        if is_title:
            label.setStyleSheet("margin-bottom: 10px; color: #333;")
        return label

    def create_welcome_step(self, layout):
        layout.addWidget(self.create_styled_label("Welcome to Mai Bloom OS Installer!", 20, Qt.AlignCenter, True))
        intro_text = QLabel(
            "This installer will guide you through the process of installing Mai Bloom OS, "
            "a user-friendly distribution based on Arch Linux, featuring the KDE Plasma desktop environment.\n\n"
            "Please ensure you have backed up any important data before proceeding."
        )
        intro_text.setWordWrap(True)
        layout.addWidget(intro_text)
        layout.addStretch()

    def create_language_keyboard_step(self, layout):
        layout.addWidget(self.create_styled_label("Language and Keyboard Layout", 16, Qt.AlignCenter, True))
        group_box = QGroupBox("Localization Settings")
        group_layout = QVBoxLayout()
        group_layout.addWidget(QLabel("Select Installation Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English (US)", "Español (España)", "Français (France)", "Deutsch (Deutschland)"])
        self.lang_combo.setCurrentText(self.config.get("language", "English (US)"))
        group_layout.addWidget(self.lang_combo)
        group_layout.addSpacing(15)
        group_layout.addWidget(QLabel("Select Keyboard Layout:"))
        self.kb_layout_combo = QComboBox()
        self.kb_layout_combo.addItems(["Select...", "us", "uk", "es", "fr", "de"])
        self.kb_layout_combo.setCurrentText(self.config.get("keyboard_layout") if self.config.get("keyboard_layout") else "Select...")
        group_layout.addWidget(self.kb_layout_combo)
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        layout.addStretch()

    def create_timezone_step(self, layout):
        layout.addWidget(self.create_styled_label("Timezone Configuration", 16, Qt.AlignCenter, True))
        group_box = QGroupBox("Select Your Timezone")
        group_layout = QVBoxLayout()
        group_layout.addWidget(QLabel("Region:"))
        self.tz_region_combo = QComboBox()
        self.tz_region_combo.addItems(["Select Region...", "America", "Europe", "Asia", "Australia", "Africa"])
        group_layout.addWidget(self.tz_region_combo)
        group_layout.addWidget(QLabel("City/Area (based on Region):"))
        self.tz_city_combo = QComboBox()
        group_layout.addWidget(self.tz_city_combo)
        self.tz_region_combo.currentTextChanged.connect(self.update_city_combo)
        if self.config.get("timezone_region"):
            self.tz_region_combo.setCurrentText(self.config["timezone_region"])
            self.update_city_combo(self.config["timezone_region"])
            if self.config.get("timezone_city"):
                 self.tz_city_combo.setCurrentText(self.config["timezone_city"])
        else:
            self.update_city_combo(self.tz_region_combo.currentText())
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        layout.addStretch()

    def update_city_combo(self, region):
        self.tz_city_combo.clear()
        cities = {
            "America": ["New_York", "Los_Angeles", "Chicago", "Denver", "Sao_Paulo", "Mexico_City"],
            "Europe": ["London", "Paris", "Berlin", "Madrid", "Rome", "Moscow"],
            "Asia": ["Tokyo", "Shanghai", "Kolkata", "Dubai", "Hong_Kong", "Singapore"],
            "Australia": ["Sydney", "Melbourne", "Perth", "Brisbane"],
            "Africa": ["Cairo", "Johannesburg", "Nairobi", "Lagos"]
        }
        self.tz_city_combo.addItems(["Select City..."] + cities.get(region, []))
        if self.config.get("timezone_region") == region and self.config.get("timezone_city") in cities.get(region, []):
            self.tz_city_combo.setCurrentText(self.config["timezone_city"])
        else:
             self.tz_city_combo.setCurrentIndex(0)


    def create_partition_step(self, layout):
        layout.addWidget(self.create_styled_label("Disk Selection & Automatic Partitioning", 16, Qt.AlignCenter, True))

        group_box = QGroupBox("Target Disk for Installation")
        group_layout = QVBoxLayout()

        group_layout.addWidget(QLabel("Select Target Disk:"))
        self.disk_combo = QComboBox()
        # Populate dynamically
        available_drives = self.get_available_drives()
        if not available_drives:
            self.disk_combo.addItem("No suitable drives found.")
            self.disk_combo.setEnabled(False)
            # update_nav_buttons will handle Next button based on disk_combo.count()
        else:
            for drive in available_drives:
                self.disk_combo.addItem(drive["display"], userData=drive["path"]) # Store device path

        group_layout.addWidget(self.disk_combo)
        group_layout.addSpacing(15)

        warning_text = (
            "<b><font color='red'>WARNING:</font> The entire selected disk will be ERASED and automatically partitioned.</b>\n"
            "All existing data on this disk will be lost.\n\n"
            "Mai Bloom OS will set up the following partitions:\n"
            "  - EFI System Partition (for booting)\n"
            "  - Root partition (<code>/</code>) for the operating system and applications\n"
            "  - Swap partition (for virtual memory)\n\n"
            "Your <code>/home</code> directory (for user files) will be part of the root partition."
        )
        info_label = QLabel(warning_text)
        info_label.setWordWrap(True)
        group_layout.addWidget(info_label)

        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        layout.addStretch()
        # self.update_nav_buttons() # Ensure nav buttons are updated after populating combo

    def create_hostname_step(self, layout):
        layout.addWidget(self.create_styled_label("Computer Name (Hostname)", 16, Qt.AlignCenter, True))
        group_box = QGroupBox("Network Identification")
        group_layout = QVBoxLayout()
        group_layout.addWidget(QLabel("Enter a hostname for this computer (e.g., my-desktop):"))
        self.hostname_input = QLineEdit(self.config.get("hostname", "maibloom-pc"))
        group_layout.addWidget(self.hostname_input)
        info_label = QLabel("The hostname is used to identify your computer on the network.")
        info_label.setWordWrap(True)
        group_layout.addWidget(info_label)
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        layout.addStretch()

    def create_user_step(self, layout):
        layout.addWidget(self.create_styled_label("Create User Account", 16, Qt.AlignCenter, True))
        group_box = QGroupBox("Your User Details")
        group_layout = QVBoxLayout()
        group_layout.addWidget(QLabel("Your full name (optional, for display purposes):"))
        self.fullname_input = QLineEdit()
        group_layout.addWidget(self.fullname_input)
        group_layout.addWidget(QLabel("Username (e.g., john):"))
        self.username_input = QLineEdit(self.config.get("username", ""))
        group_layout.addWidget(self.username_input)
        group_layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        group_layout.addWidget(self.password_input)
        group_layout.addWidget(QLabel("Confirm Password:"))
        self.password_confirm_input = QLineEdit()
        self.password_confirm_input.setEchoMode(QLineEdit.Password)
        group_layout.addWidget(self.password_confirm_input)
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        layout.addStretch()

    def create_desktop_step(self, layout):
        layout.addWidget(self.create_styled_label("Desktop Environment", 16, Qt.AlignCenter, True))
        group_box = QGroupBox("Mai Bloom OS Experience")
        group_layout = QVBoxLayout()
        de_label = QLabel(f"Mai Bloom OS comes with <b>KDE Plasma</b> as the default desktop environment.")
        de_label.setWordWrap(True)
        group_layout.addWidget(de_label)
        kde_info = QLabel(
            "KDE Plasma offers a beautiful, customizable, and powerful desktop experience. "
            "All necessary components for KDE Plasma will be installed."
        )
        kde_info.setWordWrap(True)
        group_layout.addWidget(kde_info)
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)
        layout.addStretch()

    def create_install_summary_step(self, layout):
        layout.addWidget(self.create_styled_label("Installation Summary", 16, Qt.AlignCenter, True))
        self.summary_text_area = QTextEdit()
        self.summary_text_area.setReadOnly(True)
        layout.addWidget(self.summary_text_area)

    def update_summary_contents(self):
        # Disk target is now taken from currentData if disk_combo exists and item selected
        if hasattr(self, 'disk_combo') and self.disk_combo and self.disk_combo.currentIndex() != -1:
            self.config["disk_target"] = self.disk_combo.currentData() # Ensure it's the path
        else: # Fallback if disk_combo not ready or no selection
            self.config["disk_target"] = "N/A - No disk selected or found"


        summary = "Please review your installation settings:\n\n"
        summary += f"- Language: {self.config.get('language', 'N/A')}\n"
        summary += f"- Keyboard Layout: {self.config.get('keyboard_layout', 'N/A')}\n"
        tz_region = self.config.get('timezone_region', 'N/A')
        tz_city = self.config.get('timezone_city', 'N/A')
        if tz_region == "Select Region..." or tz_city == "Select City...":
            summary += f"- Timezone: N/A (Not fully selected)\n"
        else:
            summary += f"- Timezone: {tz_region}/{tz_city}\n"

        summary += f"- Target Disk: {self.config.get('disk_target', 'N/A')}\n"
        summary += f"- Partitioning: Automatic (Entire disk will be erased)\n" # Hardcoded
        summary += f"- Hostname: {self.config.get('hostname', 'N/A')}\n"
        summary += f"- Username: {self.config.get('username', 'N/A')}\n"
        summary += f"- Password: {'Set (hidden)' if self.config.get('password') else 'Not Set'}\n"
        summary += f"- Desktop Environment: {self.config.get('desktop_environment', 'KDE Plasma')}\n"
        if self.config.get("additional_packages"):
            summary += f"- Additional Packages: {', '.join(self.config.get('additional_packages'))}\n"
        summary += "\n<b><font color='red'>WARNING:</font> Proceeding with the installation will ERASE the selected disk "
        summary += "and install Mai Bloom OS using an automatic partitioning scheme. Ensure you have backed up important data.</b>"
        self.summary_text_area.setText(summary)


    def confirm_installation(self):
        if not self.config.get("disk_target") or "N/A" in self.config.get("disk_target"):
            QMessageBox.critical(self, "Disk Not Selected", "A target disk for installation has not been properly selected. Please go back and select a disk.")
            return

        reply = QMessageBox.warning(self, "Confirm Installation",
                                    "<b>Are you absolutely sure you want to start the installation?</b>\n\n"
                                    f"The disk <b>{self.config.get('disk_target')}</b> will be completely <b>ERASED</b>.\n"
                                    "This action cannot be undone.",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.current_step_index = self.stacked_widget.indexOf(self.progress_page)
            self.stacked_widget.setCurrentIndex(self.current_step_index)
            self.update_nav_buttons()
            self.start_actual_installation()

    def create_installation_progress_step(self, layout):
        layout.addWidget(self.create_styled_label("Installing Mai Bloom OS...", 16, Qt.AlignCenter, True))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        self.install_log_area = QTextEdit()
        self.install_log_area.setReadOnly(True)
        self.install_log_area.setFontFamily("Monospace")
        layout.addWidget(self.install_log_area)
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.simulate_progress)
        self.current_progress_value = 0

    def simulate_progress(self):
        if self.current_progress_value < 100:
            self.current_progress_value += 5
            self.progress_bar.setValue(self.current_progress_value)
            self.install_log_area.append(f"Installation task {self.current_progress_value // 5}/20 completed...")
            if self.current_progress_value == 25:
                 self.install_log_area.append(f"Formatting disk {self.config.get('disk_target')}...")
            if self.current_progress_value == 50:
                 self.install_log_area.append("Installing base system packages...")
            if self.current_progress_value == 75:
                 self.install_log_area.append("Installing KDE Plasma desktop environment...")
        else:
            self.progress_timer.stop()
            self.install_log_area.append("\nInstallation finished successfully!")
            self.current_step_index = self.stacked_widget.indexOf(self.complete_page)
            self.stacked_widget.setCurrentIndex(self.current_step_index)
            self.update_nav_buttons()

    def start_actual_installation(self):
        self.install_log_area.clear()
        self.install_log_area.append("Starting installation process...\n")
        self.install_log_area.append("Preparing `archinstall` configuration...\n")
        self.install_log_area.append(f"User configuration (for archinstall): {self.config}\n")
        self.install_log_area.append(f"Target disk: {self.config.get('disk_target')}\n")
        self.install_log_area.append("Partitioning scheme: Automatic (Full Disk Erase)\n")

        self.install_log_area.append("Simulating installation steps (backend `archinstall` calls not fully implemented).\n")
        self.install_log_area.append("In a real installer, `archinstall` commands would run here.\n")
        self.current_progress_value = 0
        self.progress_bar.setValue(0)
        self.progress_timer.start(500)

    def create_installation_complete_step(self, layout):
        layout.addWidget(self.create_styled_label("Installation Complete!", 20, Qt.AlignCenter, True))
        complete_text = QLabel(
            "Mai Bloom OS has been successfully installed on your computer.\n"
            "Please remove the installation media and click 'Restart Now' to boot into your new system."
        )
        complete_text.setWordWrap(True)
        complete_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(complete_text)
        layout.addStretch()

    def run_command(self, command_list): # Kept for potential future use, but not directly for lsblk above
        self.install_log_area.append(f"Executing: {' '.join(command_list)}\n")
        try:
            process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
            for line in iter(process.stdout.readline, ''):
                self.install_log_area.append(line.strip())
                QApplication.processEvents()
            process.stdout.close()
            return_code = process.wait()
            if return_code == 0:
                self.install_log_area.append(f"Command '{' '.join(command_list)}' successful.\n")
                return True, "Command successful"
            else:
                self.install_log_area.append(f"Command '{' '.join(command_list)}' failed with code {return_code}.\n")
                return False, f"Command failed with code {return_code}"
        except Exception as e:
            error_msg = f"Exception running command '{' '.join(command_list)}': {e}\n"
            self.install_log_area.append(error_msg)
            return False, str(e)

    def restart_system(self):
        reply = QMessageBox.information(self, "Restart System",
                                    "The system will now restart. Please remove the installation medium.",
                                    QMessageBox.Ok | QMessageBox.Cancel)
        if reply == QMessageBox.Ok:
            if hasattr(self, 'install_log_area') and self.install_log_area :
                self.install_log_area.append("Simulating system restart...")
            print("Simulating system restart...")
            QApplication.instance().quit()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    installer = MaiBloomInstaller()
    installer.show()
    sys.exit(app.exec_())
