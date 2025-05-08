import sys
import os
from pathlib import Path
# subprocess is not directly used in this revision for root check, os.geteuid() is used.

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QCheckBox, QMessageBox, QTextEdit,
    QGroupBox, QFormLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont

# --- Archinstall Imports ---
# Core components, drawing from the style of the provided example for these items
try:
    from archinstall import Installer, ProfileConfiguration, profile_handler, User, sys_info
    from archinstall.default_profiles.minimal import MinimalProfile
    from archinstall.lib.disk.device_model import FilesystemType
    from archinstall.lib.disk.filesystem import FilesystemHandler
    # Additional imports needed for a GUI-driven (non-TUI) experience,
    # which I am "doing by myself" as requested:
    from archinstall.lib.disk.device_handler import list_block_devices, BlockDevice
    from archinstall.lib.disk.disk_layout import DiskLayoutConfiguration # To represent the chosen layout
    from archinstall.lib.disk.encryption import DiskEncryption # Programmatic encryption setup
    from archinstall.lib.disk.guided_partitioning import suggest_single_disk_layout # For GUI-based auto-partitioning
    from archinstall.lib.disk.constants import LUKS2

except ImportError as e:
    print(f"CRITICAL: Error importing archinstall modules: {e}")
    print("Please ensure archinstall is correctly installed AND the import statements in this script are correct.")
    app_temp = QApplication.instance()
    if not app_temp:
        app_temp = QApplication(sys.argv)
    QMessageBox.critical(None, "Archinstall Import Error", 
                         f"A critical error occurred while trying to import 'archinstall' modules:\n\n{e}\n\n"
                         "This might be due to 'archinstall' not being installed, an incorrect version, "
                         "or an issue with the script's import statements.\n\n"
                         "Please ensure 'archinstall' is properly installed and accessible to Python when run with sudo. "
                         "The application will now exit.")
    sys.exit(1)


# --- Configuration ---
MOUNT_POINT = Path('/mnt') 
MAI_BLOOM_PACKAGES = [
    'xorg',  # X Window System
    'sddm',  # Display Manager for Plasma
    'plasma-desktop',  # Core Plasma desktop
    'konsole', # KDE Terminal
    'dolphin', # KDE File Manager
    'kate',    # KDE Text Editor
    'ark',     # KDE Archiving tool
    'networkmanager', 
    'linux-firmware', 
    'nano', 'wget', 'git' # From example/user request
]

class WorkerThread(QThread):
    progress_updated = pyqtSignal(str)
    installation_finished = pyqtSignal(bool, str) 

    def __init__(self, config_data):
        super().__init__()
        self.config = config_data # Renamed to avoid conflict with archinstall.Config if ever used
        self._is_interrupted = False

    def run(self):
        try:
            self.progress_updated.emit("Starting installation process...")
            self.progress_updated.emit(f"Installation Target Disk: {self.config['disk'].path}")
            self.progress_updated.emit(f"Hostname: {self.config['hostname']}")
            self.progress_updated.emit(f"Username: {self.config['username']}")
            self.progress_updated.emit(f"Enable Encryption: {'Yes' if self.config['encrypt'] else 'No'}")
            self.progress_updated.emit(f"Filesystem Type: {self.config['filesystem_type'].value}")

            if not MOUNT_POINT.exists():
                MOUNT_POINT.mkdir(parents=True, exist_ok=True)
            
            self.progress_updated.emit("Suggesting disk layout based on GUI selection...")
            target_disk = self.config['disk'] # This is a BlockDevice object
            # default_fs_type is FilesystemType('ext4') from config
            disk_layout_config_obj = suggest_single_disk_layout(
                target_disk,
                default_fs_type=self.config['filesystem_type'],
                boot_type=sys_info.BOOT_MODE 
            )
            self.progress_updated.emit(f"Disk layout suggested for {sys_info.BOOT_MODE} mode.")

            disk_encryption_config_obj = None # Renamed to avoid confusion with DiskEncryption class
            if self.config['encrypt']:
                self.progress_updated.emit("Setting up disk encryption configuration...")
                if not self.config['enc_password']:
                    self.installation_finished.emit(False, "Encryption password not provided.")
                    return

                found_root_to_encrypt = False
                for dev_mod in disk_layout_config_obj.device_modifications:
                    for part_mod in dev_mod.partitions:
                        if part_mod.mountpoint == Path('/'): 
                            part_mod.encrypt = True
                            part_mod.encryption_type = LUKS2 
                            found_root_to_encrypt = True
                            self.progress_updated.emit(f"Root partition on {dev_mod.block_device.path} now marked for LUKS2 encryption.")
                
                if not found_root_to_encrypt:
                    self.installation_finished.emit(False, "Could not find a root partition in the suggested layout to mark for encryption.")
                    return

                disk_encryption_config_obj = DiskEncryption( # Creating the DiskEncryption configuration object
                    encryption_type=LUKS2,
                    encryption_password=self.config['enc_password']
                )
                self.progress_updated.emit("DiskEncryption configuration object created.")

            if self._is_interrupted: return

            self.progress_updated.emit("Initializing FilesystemHandler...")
            # FilesystemHandler is imported as per the example's style
            fs_handler = FilesystemHandler(disk_layout_config_obj, disk_encryption_config_obj)

            self.progress_updated.emit("WARNING: Filesystem operations (e.g., formatting) will now begin on the target disk!")
            try:
                # This is a destructive operation.
                fs_handler.perform_filesystem_operations(show_output=False) 
            except Exception as e:
                self.installation_finished.emit(False, f"Filesystem operations failed: {e}\n{traceback.format_exc()}")
                return

            self.progress_updated.emit("Filesystem operations completed.")
            if self._is_interrupted: return

            self.progress_updated.emit("Starting Arch Linux installation core...")
            # Installer, ProfileConfiguration, profile_handler, User are imported as per the example's style
            with Installer(
                MOUNT_POINT,
                disk_layout_config_obj,
                disk_encryption=disk_encryption_config_obj,
                kernels=['linux'] 
            ) as installation:
                if self._is_interrupted: installation.abort(); return

                self.progress_updated.emit("Mounting configured partitions...")
                installation.mount_ordered_layout()
                if self._is_interrupted: installation.abort(); return

                self.progress_updated.emit(f"Performing minimal system installation (hostname: {self.config['hostname']})...")
                installation.minimal_installation(
                    hostname=self.config['hostname'],
                )
                if self._is_interrupted: installation.abort(); return

                self.progress_updated.emit(f"Installing Mai Bloom OS specific packages: {', '.join(MAI_BLOOM_PACKAGES)}")
                installation.add_additional_packages(MAI_BLOOM_PACKAGES)
                if self._is_interrupted: installation.abort(); return

                self.progress_updated.emit("Setting up minimal profile configurations (e.g., bootloader)...")
                # MinimalProfile is imported as per the example's style
                profile_config = ProfileConfiguration(MinimalProfile()) 
                profile_handler.install_profile_config(installation, profile_config)
                if self._is_interrupted: installation.abort(); return
                
                self.progress_updated.emit(f"Creating user '{self.config['username']}'...")
                user = User(self.config['username'], self.config['password'], sudo=True)
                installation.create_users(user)
                if self._is_interrupted: installation.abort(); return
                
                if 'sddm' in MAI_BLOOM_PACKAGES:
                    self.progress_updated.emit("Enabling SDDM (Display Manager) service...")
                    try:
                        installation.enable_service('sddm') 
                    except Exception as e:
                        self.progress_updated.emit(f"Warning: Could not enable sddm service automatically: {e}. Manual enabling may be required post-installation.")

                self.progress_updated.emit("Finalizing installation setup...")

            self.progress_updated.emit("Installation process finished successfully.")
            self.installation_finished.emit(True, "Mai Bloom OS has been installed successfully!\nYou can now reboot your system.")

        except Exception as e:
            self.progress_updated.emit(f"An unexpected error occurred during installation: {e}")
            import traceback
            self.progress_updated.emit(traceback.format_exc())
            self.installation_finished.emit(False, f"Installation failed due to an unexpected error: {e}")

    def stop(self):
        self._is_interrupted = True
        self.progress_updated.emit("Cancellation request received. Attempting to stop installation gracefully...")

# (The rest of the PyQt5 GUI classes: WelcomePage, DiskSetupPage, UserSetupPage, SummaryPage, InstallationPage, MaiBloomInstaller)
# These classes will be very similar to my previous full PyQt5 solution,
# as "Le Chat's code" only provided a very minimal single-window UI.
# I will reconstruct them here for completeness.

class WelcomePage(QWidget):
    def __init__(self, parent_installer_app): # Renamed to avoid conflict
        super().__init__()
        self.parent_app = parent_installer_app # Renamed
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Welcome to Mai Bloom OS Installer")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        intro_text = QLabel(
            "This installer will guide you through installing Mai Bloom OS, a customized Arch Linux distribution with KDE Plasma.\n\n"
            "<b>Important:</b> This installer will format the selected disk. Ensure all important data is backed up before proceeding."
        )
        intro_text.setWordWrap(True)
        intro_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(intro_text)
        
        if os.geteuid() != 0:
            warn_root = QLabel("<b>Warning: This installer must be run with root privileges (e.g., using sudo). Please restart with sudo.</b>")
            warn_root.setStyleSheet("color: red;")
            warn_root.setAlignment(Qt.AlignCenter)
            layout.addWidget(warn_root)

        next_button = QPushButton("Next")
        next_button.clicked.connect(self.parent_app.next_page)
        layout.addStretch()
        layout.addWidget(next_button, alignment=Qt.AlignRight)


class DiskSetupPage(QWidget):
    def __init__(self, parent_installer_app):
        super().__init__()
        self.parent_app = parent_installer_app
        layout = QVBoxLayout(self)

        title = QLabel("Disk Setup & Encryption")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        layout.addWidget(QLabel("Select the disk for installing Mai Bloom OS:"))
        self.disk_list_widget = QListWidget()
        self.disk_list_widget.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self.disk_list_widget)
        self.refresh_disks()

        refresh_button = QPushButton("Refresh Disk List")
        refresh_button.clicked.connect(self.refresh_disks)
        layout.addWidget(refresh_button)
        
        encryption_group = QGroupBox("Disk Encryption (Optional)")
        encryption_form_layout = QFormLayout() # Using QFormLayout for better alignment
        self.encrypt_checkbox = QCheckBox("Encrypt the system partition (LUKS2)")
        self.encrypt_checkbox.stateChanged.connect(self.toggle_encryption_fields)
        encryption_form_layout.addRow(self.encrypt_checkbox)

        self.enc_password_label = QLabel("Encryption Password:")
        self.enc_password_edit = QLineEdit()
        self.enc_password_edit.setEchoMode(QLineEdit.Password)
        encryption_form_layout.addRow(self.enc_password_label, self.enc_password_edit)
        
        self.enc_confirm_password_label = QLabel("Confirm Password:")
        self.enc_confirm_password_edit = QLineEdit()
        self.enc_confirm_password_edit.setEchoMode(QLineEdit.Password)
        encryption_form_layout.addRow(self.enc_confirm_password_label, self.enc_confirm_password_edit)
        
        encryption_group.setLayout(encryption_form_layout)
        layout.addWidget(encryption_group)
        self.toggle_encryption_fields() # Set initial visibility

        nav_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.parent_app.prev_page)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.proceed_to_next) # Renamed
        nav_layout.addWidget(back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(next_button)
        layout.addLayout(nav_layout)

    def refresh_disks(self):
        self.disk_list_widget.clear()
        try:
            # list_block_devices is imported
            devices = list_block_devices() 
            if not devices:
                self.disk_list_widget.addItem("No suitable disks found.")
                return
            for path, device_obj in devices.items(): # device_obj is a BlockDevice instance
                if not device_obj.is_optical and not device_obj.is_loop_device and device_obj.size: 
                    item_text = f"{device_obj.path} - {device_obj.device_info.model if device_obj.device_info else 'Unknown Model'} ({device_obj.size_hr})"
                    list_item = QListWidgetItem(item_text)
                    list_item.setData(Qt.UserRole, device_obj) # Store the BlockDevice object
                    self.disk_list_widget.addItem(list_item)
        except Exception as e:
            QMessageBox.warning(self, "Disk Enumeration Error", f"Could not list disks: {e}")
            self.disk_list_widget.addItem("Error listing disks.")

    def toggle_encryption_fields(self):
        is_checked = self.encrypt_checkbox.isChecked()
        self.enc_password_label.setVisible(is_checked)
        self.enc_password_edit.setVisible(is_checked)
        self.enc_confirm_password_label.setVisible(is_checked)
        self.enc_confirm_password_edit.setVisible(is_checked)

    def proceed_to_next(self): # Renamed
        selected_items = self.disk_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Disk Not Selected", "Please select a target disk for installation.")
            return
        
        # Store selected disk (BlockDevice object) in the main app's config
        self.parent_app.config_data['disk'] = selected_items[0].data(Qt.UserRole)

        self.parent_app.config_data['encrypt'] = self.encrypt_checkbox.isChecked()
        if self.parent_app.config_data['encrypt']:
            enc_pass = self.enc_password_edit.text()
            enc_confirm_pass = self.enc_confirm_password_edit.text()
            if not enc_pass:
                QMessageBox.warning(self, "Password Missing", "Encryption password cannot be empty if encryption is enabled.")
                return
            if enc_pass != enc_confirm_pass:
                QMessageBox.warning(self, "Password Mismatch", "Encryption passwords do not match.")
                return
            self.parent_app.config_data['enc_password'] = enc_pass
        else:
            self.parent_app.config_data['enc_password'] = None
        
        self.parent_app.next_page()

class UserSetupPage(QWidget):
    def __init__(self, parent_installer_app):
        super().__init__()
        self.parent_app = parent_installer_app
        layout = QVBoxLayout(self)

        title = QLabel("User and System Configuration")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        form_layout = QFormLayout()
        self.hostname_edit = QLineEdit(self.parent_app.config_data.get("hostname", "maibloom-os"))
        self.username_edit = QLineEdit(self.parent_app.config_data.get("username", "bloom"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)

        form_layout.addRow("System Hostname:", self.hostname_edit)
        form_layout.addRow("Primary Username:", self.username_edit)
        form_layout.addRow("User Password:", self.password_edit)
        form_layout.addRow("Confirm Password:", self.confirm_password_edit)
        layout.addLayout(form_layout)
        layout.addStretch()

        nav_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.parent_app.prev_page)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.proceed_to_next)
        nav_layout.addWidget(back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(next_button)
        layout.addLayout(nav_layout)

    def proceed_to_next(self):
        hostname = self.hostname_edit.text().strip()
        username = self.username_edit.text().strip() # Add validation for valid usernames if needed
        password = self.password_edit.text()
        confirm_password = self.confirm_password_edit.text()

        if not hostname:
            QMessageBox.warning(self, "Input Required", "Hostname cannot be empty.")
            return
        if not username:
            QMessageBox.warning(self, "Input Required", "Username cannot be empty.")
            return
        # Basic username validation (common constraints)
        if not username.islower() or not username.isidentifier() or any(c.isspace() for c in username):
             QMessageBox.warning(self, "Invalid Username", "Username must be all lowercase, contain no spaces, and follow typical identifier rules (e.g., no leading numbers if some systems restrict).")
             return
        if not password:
            QMessageBox.warning(self, "Input Required", "Password cannot be empty.")
            return
        if password != confirm_password:
            QMessageBox.warning(self, "Password Mismatch", "The entered passwords do not match.")
            return

        self.parent_app.config_data['hostname'] = hostname
        self.parent_app.config_data['username'] = username
        self.parent_app.config_data['password'] = password
        self.parent_app.next_page()

class SummaryPage(QWidget):
    def __init__(self, parent_installer_app):
        super().__init__()
        self.parent_app = parent_installer_app
        layout = QVBoxLayout(self)

        title = QLabel("Installation Summary & Confirmation")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        self.summary_text_display = QTextEdit() # Renamed
        self.summary_text_display.setReadOnly(True)
        layout.addWidget(self.summary_text_display)

        warning_label = QLabel(
            "<b>CRITICAL WARNING:</b> Clicking 'Install Now' will partition and format the selected disk according to the choices made, "
            "and then install Mai Bloom OS. This process is <b>IRREVERSIBLE</b> and will <b>ERASE ALL DATA</b> on the target disk."
        )
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(warning_label)
        
        nav_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.parent_app.prev_page)
        self.install_button = QPushButton("Install Now")
        self.install_button.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold; padding: 10px;") # Red button
        self.install_button.clicked.connect(self.parent_app.confirm_and_start_installation) # Renamed
        nav_layout.addWidget(back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.install_button)
        layout.addLayout(nav_layout)

    def update_summary_display(self): # Renamed
        config = self.parent_app.config_data
        disk_info = "Not Selected"
        if config.get('disk') and isinstance(config['disk'], BlockDevice):
            disk_info = f"{config['disk'].path} ({config['disk'].size_hr})"
            if config['disk'].device_info and config['disk'].device_info.model:
                disk_info += f" - {config['disk'].device_info.model}"
        
        # FilesystemType is imported
        fs_type_value = config.get('filesystem_type').value if config.get('filesystem_type') else 'N/A'


        summary_html = f"""
        <h3>Review Your Settings Carefully:</h3>
        <p><b>Installation Target Disk:</b> {disk_info}</p>
        <p><b>Filesystem for Root:</b> {fs_type_value}</p>
        <p><b>Detected Boot Mode:</b> {sys_info.BOOT_MODE}</p>
        <hr>
        <p><b>System Hostname:</b> {config.get('hostname', 'N/A')}</p>
        <p><b>Primary Username:</b> {config.get('username', 'N/A')} (will have sudo access)</p>
        <hr>
        <p><b>Encrypt System Partition:</b> {'Yes (LUKS2)' if config.get('encrypt') else 'No'}</p>
        """
        if config.get('encrypt') and not config.get('enc_password'):
            summary_html += "<p><b style='color:red;'>Warning: Encryption enabled but password seems not set. Please go back.</b></p>"
        summary_html += "<hr>"
        summary_html += f"<p><b>Core Packages for Mai Bloom OS (KDE):</b><br>{', '.join(MAI_BLOOM_PACKAGES)}</p>"
        summary_html += f"<p><b>System will be installed to:</b> {MOUNT_POINT}</p>"
        
        self.summary_text_display.setHtml(summary_html)


class InstallationPage(QWidget):
    def __init__(self, parent_installer_app):
        super().__init__()
        self.parent_app = parent_installer_app
        layout = QVBoxLayout(self)

        title = QLabel("Mai Bloom OS Installation Progress")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        self.progress_log_display = QTextEdit() # Renamed
        self.progress_log_display.setReadOnly(True)
        self.progress_log_display.setFont(QFont("Monospace", 9))
        layout.addWidget(self.progress_log_display)

        self.current_status_label = QLabel("Preparing for installation...") # Renamed
        layout.addWidget(self.current_status_label)

        self.finish_button = QPushButton("Finish & Exit")
        self.finish_button.setEnabled(False)
        self.finish_button.clicked.connect(QApplication.instance().quit)
        
        self.cancel_button = QPushButton("Cancel Installation")
        self.cancel_button.clicked.connect(self.parent_app.trigger_cancel_installation) # Renamed
        self.cancel_button.setStyleSheet("background-color: #d35400; color: white;")

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.cancel_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.finish_button)
        layout.addLayout(nav_layout)

    def log_message(self, message):
        self.progress_log_display.append(message)
    
    def update_status_text(self, message): # Renamed
        self.current_status_label.setText(message)

    def installation_phase_complete(self, success, message_text): # Renamed
        self.update_status_text(message_text)
        self.cancel_button.setEnabled(False)
        self.cancel_button.setText("Cancellation Unavailable")
        self.finish_button.setEnabled(True)
        if success:
            QMessageBox.information(self, "Installation Successful", message_text)
        else:
            QMessageBox.critical(self, "Installation Failed", message_text)


class MaiBloomInstallerApp(QMainWindow): # Renamed class
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mai Bloom OS Graphical Installer")
        self.setMinimumSize(700, 550) # Adjusted size
        self.setGeometry(100, 100, 850, 650) 

        # Default configuration data
        self.config_data = {
            "disk": None, # Will be a BlockDevice object
            "encrypt": False,
            "enc_password": None,
            "hostname": "maibloom-os",
            "username": "bloom", 
            "password": None,
            "filesystem_type": FilesystemType('ext4'), # FilesystemType is imported
        }

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # Create pages
        self.welcome_page = WelcomePage(self)
        self.disk_page = DiskSetupPage(self)
        self.user_page = UserSetupPage(self)
        self.summary_page = SummaryPage(self)
        self.install_page = InstallationPage(self)

        # Add pages to stack
        self.stacked_widget.addWidget(self.welcome_page)
        self.stacked_widget.addWidget(self.disk_page)
        self.stacked_widget.addWidget(self.user_page)
        self.stacked_widget.addWidget(self.summary_page)
        self.stacked_widget.addWidget(self.install_page)

        self.installation_worker_thread = None # Renamed

    def next_page(self):
        current_idx = self.stacked_widget.currentIndex()
        if current_idx < self.stacked_widget.count() - 1:
            next_widget = self.stacked_widget.widget(current_idx + 1)
            if next_widget == self.summary_page:
                self.summary_page.update_summary_display() # Ensure summary is fresh
            self.stacked_widget.setCurrentIndex(current_idx + 1)

    def prev_page(self):
        current_idx = self.stacked_widget.currentIndex()
        if current_idx > 0:
            self.stacked_widget.setCurrentIndex(current_idx - 1)

    def confirm_and_start_installation(self): # Renamed
        reply = QMessageBox.warning(
            self,
            "Final Confirmation Before Installation",
            "You are about to start the installation process for Mai Bloom OS. "
            "This will ERASE ALL DATA on the selected disk: "
            f"{self.config_data['disk'].path if self.config_data['disk'] else 'N/A'}.\n\n"
            "This action cannot be undone. Are you absolutely sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No # Default to No
        )
        if reply == QMessageBox.Yes:
            self.stacked_widget.setCurrentWidget(self.install_page)
            self.execute_installation() # Renamed

    def execute_installation(self): # Renamed
        if os.geteuid() != 0:
            QMessageBox.critical(self, "Root Privileges Required", 
                                 "This installer must be executed with root (sudo) privileges for disk operations.")
            self.install_page.installation_phase_complete(False, "Installation aborted: Not running as root.")
            self.stacked_widget.setCurrentWidget(self.welcome_page) 
            return

        self.install_page.log_message("Preparing installation environment...")
        self.install_page.cancel_button.setEnabled(True)
        self.install_page.cancel_button.setText("Cancel Installation")
        self.install_page.finish_button.setEnabled(False)

        self.installation_worker_thread = WorkerThread(self.config_data) # Pass the config
        self.installation_worker_thread.progress_updated.connect(self.install_page.log_message)
        self.installation_worker_thread.installation_finished.connect(self.install_page.installation_phase_complete)
        self.installation_worker_thread.start()

    def trigger_cancel_installation(self): # Renamed
        if self.installation_worker_thread and self.installation_worker_thread.isRunning():
            reply = QMessageBox.question(self, 'Confirm Cancellation',
                                       "Are you sure you want to attempt to cancel the ongoing installation? "
                                       "This might leave the system in an incomplete or unstable state.",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.installation_worker_thread.stop() # Request thread to stop
                self.install_page.log_message("User requested installation cancellation.")
                self.install_page.cancel_button.setEnabled(False) 
                self.install_page.cancel_button.setText("Cancellation Initiated")
        else:
             self.install_page.log_message("No active installation process to cancel.")
             self.install_page.cancel_button.setEnabled(False)

    def closeEvent(self, event):
        if self.installation_worker_thread and self.installation_worker_thread.isRunning():
            reply = QMessageBox.question(self, 'Confirm Exit',
                                       "Mai Bloom OS installation is currently in progress. "
                                       "Exiting now may lead to a corrupted or incomplete installation.\n\n"
                                       "Are you sure you want to exit?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.installation_worker_thread.stop() # Attempt to signal thread stop
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main(): # Renamed for clarity
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # A clean, cross-platform style

    if os.geteuid() != 0:
         QMessageBox.critical(None, "Root Privileges Required", 
                                "The Mai Bloom OS Installer must be run with root (sudo) privileges.\n"
                                "Please execute the script using 'sudo python your_script_name.py'.\n\n"
                                "The application will now exit.")
         sys.exit(1)

    installer_app_window = MaiBloomInstallerApp() # Renamed
    installer_app_window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
