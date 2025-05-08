import sys
import os
from pathlib import Path
import subprocess # For checking root

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QCheckBox, QMessageBox, QTextEdit,
    QFileDialog, QGroupBox, QFormLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont

# Archinstall imports (ensure archinstall is installed)
try:
    from archinstall import Installer, ProfileConfiguration, profile_handler, User, sys_info
    from archinstall.lib.disk.device_handler import list_block_devices, BlockDevice
    from archinstall.lib.disk.device_model import FilesystemType
    from archinstall.lib.disk.disk_layout import DiskLayoutConfiguration
    from archinstall.lib.disk.encryption import DiskEncryption
    from archinstall.lib.disk.filesystem import FilesystemHandler
    from archinstall.lib.disk.guided_partitioning import suggest_single_disk_layout
    from archinstall.lib.disk.constants import LUKS2, PART_ROOT
    from archinstall.default_profiles.minimal import MinimalProfile
except ImportError as e:
    print(f"Error importing archinstall modules: {e}")
    print("Please ensure archinstall is installed and accessible in your Python environment.")
    # Show a pop-up if possible, then exit
    app_temp = QApplication.instance()
    if not app_temp:
        app_temp = QApplication(sys.argv)
    QMessageBox.critical(None, "Import Error", f"Could not import archinstall modules: {e}\n\nPlease ensure archinstall is installed.")
    sys.exit(1)


# --- Configuration ---
MOUNT_POINT = Path('/mnt') # Standard mount point for Arch Linux installation
MAI_BLOOM_PACKAGES = [
    'xorg', 'sddm', 'plasma-desktop', 'konsole', 'dolphin', 'ark', 'kate', # KDE Plasma essentials
    'networkmanager', # For network connectivity
    'linux-firmware', # Firmware for hardware
    'nano', 'wget', 'git' # User's requested utilities
]
# 'linux' kernel is added separately by archinstall's Installer class

class WorkerThread(QThread):
    progress_updated = pyqtSignal(str)
    installation_finished = pyqtSignal(bool, str) # success (bool), message (str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._is_interrupted = False

    def run(self):
        try:
            self.progress_updated.emit("Starting installation process...")
            self.progress_updated.emit(f"Selected disk: {self.config['disk'].path}")
            self.progress_updated.emit(f"Hostname: {self.config['hostname']}")
            self.progress_updated.emit(f"Username: {self.config['username']}")
            self.progress_updated.emit(f"Encryption enabled: {self.config['encrypt']}")
            self.progress_updated.emit(f"Filesystem: {self.config['filesystem_type'].value}")

            if not MOUNT_POINT.exists():
                MOUNT_POINT.mkdir(parents=True, exist_ok=True)
            
            self.progress_updated.emit("Suggesting disk layout...")
            # 1. Disk Configuration
            # We assume target_disk is a BlockDevice object
            target_disk = self.config['disk']
            disk_layout_config = suggest_single_disk_layout(
                target_disk,
                default_fs_type=self.config['filesystem_type'],
                boot_type=sys_info.BOOT_MODE # 'UEFI' or 'BIOS'
            )
            self.progress_updated.emit(f"Disk layout suggested for {sys_info.BOOT_MODE} mode.")

            # 2. Disk Encryption (Optional)
            disk_encryption_obj = None
            if self.config['encrypt']:
                self.progress_updated.emit("Setting up disk encryption...")
                if not self.config['enc_password']:
                    self.installation_finished.emit(False, "Encryption password not provided.")
                    return

                # Apply encryption to the root partition(s) in the suggested layout
                found_root = False
                for dev_mod in disk_layout_config.device_modifications:
                    for part_mod in dev_mod.partitions:
                        if part_mod.mountpoint == Path('/'): # Standard root mountpoint
                            part_mod.encrypt = True
                            part_mod.encryption_type = LUKS2 # or 'luks'
                            # The password will be taken from the global disk_encryption_obj
                            found_root = True
                            self.progress_updated.emit(f"Root partition {part_mod.device_path} marked for encryption.")
                
                if not found_root:
                    self.installation_finished.emit(False, "Could not find root partition in layout to encrypt.")
                    return

                disk_encryption_obj = DiskEncryption(
                    encryption_type=LUKS2,
                    encryption_password=self.config['enc_password']
                )
                self.progress_updated.emit("DiskEncryption object created.")

            if self._is_interrupted: return

            # 3. Filesystem Operations
            self.progress_updated.emit("Initializing filesystem handler...")
            fs_handler = FilesystemHandler(disk_layout_config, disk_encryption_obj)

            self.progress_updated.emit("\nWARNING: PERFORMING FILESYSTEM OPERATIONS (FORMATTING)!")
            # In a real GUI, you'd have a log window. Here, we just emit.
            # fs_handler.perform_filesystem_operations() might print to stdout/stderr.
            # Consider capturing its output if possible or providing a callback for progress.
            # For now, we assume it logs to console where this script runs.
            try:
                fs_handler.perform_filesystem_operations(show_output=False) # show_output to archinstall's internal logging
            except Exception as e:
                self.installation_finished.emit(False, f"Filesystem operations failed: {e}")
                return

            self.progress_updated.emit("Filesystem operations completed.")
            if self._is_interrupted: return

            # 4. Installation
            self.progress_updated.emit("Starting Arch Linux installation...")
            with Installer(
                MOUNT_POINT,
                disk_layout_config,
                disk_encryption=disk_encryption_obj,
                kernels=['linux'] # Default kernel
            ) as installation:
                if self._is_interrupted: installation.abort(); return

                self.progress_updated.emit("Mounting partitions...")
                installation.mount_ordered_layout()
                if self._is_interrupted: installation.abort(); return

                self.progress_updated.emit(f"Performing minimal installation with hostname: {self.config['hostname']}")
                # Minimal installation (pacstrap base, fstab, locale, time, etc.)
                # The minimal_installation itself can take a while and does network ops.
                # It also calls _setup_hardware_specific_dependencies internally (like intel-ucode)
                installation.minimal_installation(
                    hostname=self.config['hostname'],
                    packages=['base', 'base-devel'] # Ensure these are part of minimal
                )
                if self._is_interrupted: installation.abort(); return

                self.progress_updated.emit(f"Installing Mai Bloom OS packages: {', '.join(MAI_BLOOM_PACKAGES)}")
                installation.add_additional_packages(MAI_BLOOM_PACKAGES)
                if self._is_interrupted: installation.abort(); return

                # Install a minimal profile (handles some basics like bootloader if not done yet)
                self.progress_updated.emit("Installing minimal profile configuration...")
                profile_config = ProfileConfiguration(MinimalProfile()) # MinimalProfile is very basic
                profile_handler.install_profile_config(installation, profile_config)
                if self._is_interrupted: installation.abort(); return
                
                # Bootloader should be handled by minimal_installation or profile.
                # If specific bootloader configuration is needed, it would be here.
                # For example: installation.install_bootloader() if not covered.

                self.progress_updated.emit("Creating user...")
                user = User(self.config['username'], self.config['password'], sudo=True)
                installation.create_users(user)
                if self._is_interrupted: installation.abort(); return
                
                # KDE specific configurations (e.g., enabling SDDM)
                if 'sddm' in MAI_BLOOM_PACKAGES:
                    self.progress_updated.emit("Enabling SDDM display manager...")
                    installation.enable_service('sddm') # This runs systemctl enable in chroot

                # Any other Mai Bloom OS specific post-install configurations could go here
                # by chrooting into the installation:
                # with installation. 入っ(MOUNT_POINT) as chroot:
                # chroot.run(['ln', '-sf', '/usr/share/zoneinfo/Region/City', '/etc/localtime'])
                # chroot.run(['hwclock', '--systohc'])
                # (Many of these are handled by minimal_installation or profiles though)

                self.progress_updated.emit("Finalizing installation...")
                # Unmount etc. is handled by Installer context manager exit

            self.progress_updated.emit("Installation process finished successfully.")
            self.installation_finished.emit(True, "Mai Bloom OS has been installed successfully!\nYou can now reboot your system.")

        except Exception as e:
            self.progress_updated.emit(f"An error occurred: {e}")
            import traceback
            self.progress_updated.emit(traceback.format_exc())
            self.installation_finished.emit(False, f"Installation failed: {e}")

    def stop(self):
        self._is_interrupted = True
        self.progress_updated.emit("Attempting to stop installation...")


class WelcomePage(QWidget):
    def __init__(self, parent_installer):
        super().__init__()
        self.parent_installer = parent_installer
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Welcome to Mai Bloom OS Installer")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        intro_text = QLabel(
            "This installer will guide you through installing Mai Bloom OS, a customized Arch Linux distribution with KDE Plasma.\n\n"
            "Important: This installer will format the selected disk. Make sure to back up any important data."
        )
        intro_text.setWordWrap(True)
        intro_text.setAlignment(Qt.AlignCenter)
        layout.addWidget(intro_text)
        
        if os.geteuid() != 0:
            warn_root = QLabel("<b>Warning: This installer needs to be run with root privileges (e.g., using sudo). Please restart with sudo if you haven't.</b>")
            warn_root.setStyleSheet("color: red;")
            warn_root.setAlignment(Qt.AlignCenter)
            layout.addWidget(warn_root)


        next_button = QPushButton("Next")
        next_button.clicked.connect(self.parent_installer.next_page)
        layout.addStretch()
        layout.addWidget(next_button, alignment=Qt.AlignRight)


class DiskSetupPage(QWidget):
    def __init__(self, parent_installer):
        super().__init__()
        self.parent_installer = parent_installer
        layout = QVBoxLayout(self)

        title = QLabel("Disk Setup")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        layout.addWidget(QLabel("Select the disk for installation:"))
        self.disk_list_widget = QListWidget()
        self.disk_list_widget.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(self.disk_list_widget)
        self.refresh_disks()

        self.refresh_button = QPushButton("Refresh Disks")
        self.refresh_button.clicked.connect(self.refresh_disks)
        layout.addWidget(self.refresh_button)
        
        # Filesystem (fixed for now as per original script)
        # fs_label = QLabel(f"Filesystem type: {self.parent_installer.config['filesystem_type'].value} (default)")
        # layout.addWidget(fs_label)

        # Encryption
        encryption_group = QGroupBox("Disk Encryption (Optional)")
        encryption_layout = QVBoxLayout()
        self.encrypt_checkbox = QCheckBox("Encrypt the system partition (LUKS)")
        self.encrypt_checkbox.stateChanged.connect(self.toggle_encryption_fields)
        encryption_layout.addWidget(self.encrypt_checkbox)

        self.enc_password_label = QLabel("Encryption Password:")
        self.enc_password_edit = QLineEdit()
        self.enc_password_edit.setEchoMode(QLineEdit.Password)
        self.enc_confirm_password_label = QLabel("Confirm Encryption Password:")
        self.enc_confirm_password_edit = QLineEdit()
        self.enc_confirm_password_edit.setEchoMode(QLineEdit.Password)
        
        encryption_layout.addWidget(self.enc_password_label)
        encryption_layout.addWidget(self.enc_password_edit)
        encryption_layout.addWidget(self.enc_confirm_password_label)
        encryption_layout.addWidget(self.enc_confirm_password_edit)
        encryption_group.setLayout(encryption_layout)
        layout.addWidget(encryption_group)
        self.toggle_encryption_fields() # Set initial state

        # Navigation
        nav_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.parent_installer.prev_page)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.proceed)
        nav_layout.addWidget(back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(next_button)
        layout.addLayout(nav_layout)

    def refresh_disks(self):
        self.disk_list_widget.clear()
        try:
            # Using list_block_devices which returns a dictionary
            # BlockDevice.all_disks() might be another option, returns List[BlockDevice]
            devices = list_block_devices() # This returns dict, values are BlockDevice objects
            for path, device in devices.items():
                if not device.is_optical and not device.is_loop_device and device.size: # Filter out CD/DVD, loop, and empty devices
                    item_text = f"{device.path} - {device.device_info.model if device.device_info else 'N/A'} ({device.size_hr})"
                    list_item = QListWidgetItem(item_text)
                    list_item.setData(Qt.UserRole, device) # Store BlockDevice object
                    self.disk_list_widget.addItem(list_item)
        except Exception as e:
            QMessageBox.warning(self, "Disk Error", f"Could not list disks: {e}")


    def toggle_encryption_fields(self):
        enable = self.encrypt_checkbox.isChecked()
        self.enc_password_label.setVisible(enable)
        self.enc_password_edit.setVisible(enable)
        self.enc_confirm_password_label.setVisible(enable)
        self.enc_confirm_password_edit.setVisible(enable)

    def proceed(self):
        selected_items = self.disk_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selection Error", "Please select a disk for installation.")
            return
        
        selected_disk_object = selected_items[0].data(Qt.UserRole)
        self.parent_installer.config['disk'] = selected_disk_object

        self.parent_installer.config['encrypt'] = self.encrypt_checkbox.isChecked()
        if self.parent_installer.config['encrypt']:
            enc_pass = self.enc_password_edit.text()
            enc_confirm_pass = self.enc_confirm_password_edit.text()
            if not enc_pass:
                QMessageBox.warning(self, "Input Error", "Encryption password cannot be empty.")
                return
            if enc_pass != enc_confirm_pass:
                QMessageBox.warning(self, "Input Error", "Encryption passwords do not match.")
                return
            self.parent_installer.config['enc_password'] = enc_pass
        else:
            self.parent_installer.config['enc_password'] = None
        
        self.parent_installer.next_page()

class UserSetupPage(QWidget):
    def __init__(self, parent_installer):
        super().__init__()
        self.parent_installer = parent_installer
        layout = QVBoxLayout(self)

        title = QLabel("User Configuration")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        form_layout = QFormLayout()
        self.hostname_edit = QLineEdit(self.parent_installer.config.get("hostname", "maibloom-os"))
        self.username_edit = QLineEdit(self.parent_installer.config.get("username", "user"))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.confirm_password_edit = QLineEdit()
        self.confirm_password_edit.setEchoMode(QLineEdit.Password)

        form_layout.addRow("Hostname:", self.hostname_edit)
        form_layout.addRow("Username:", self.username_edit)
        form_layout.addRow("Password:", self.password_edit)
        form_layout.addRow("Confirm Password:", self.confirm_password_edit)
        layout.addLayout(form_layout)

        # Navigation
        nav_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.parent_installer.prev_page)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self.proceed)
        nav_layout.addWidget(back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(next_button)
        layout.addLayout(nav_layout)

    def proceed(self):
        hostname = self.hostname_edit.text().strip()
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        confirm_password = self.confirm_password_edit.text()

        if not hostname:
            QMessageBox.warning(self, "Input Error", "Hostname cannot be empty.")
            return
        if not username:
            QMessageBox.warning(self, "Input Error", "Username cannot be empty.")
            return
        if not password:
            QMessageBox.warning(self, "Input Error", "Password cannot be empty.")
            return
        if password != confirm_password:
            QMessageBox.warning(self, "Input Error", "Passwords do not match.")
            return

        self.parent_installer.config['hostname'] = hostname
        self.parent_installer.config['username'] = username
        self.parent_installer.config['password'] = password
        self.parent_installer.next_page()


class SummaryPage(QWidget):
    def __init__(self, parent_installer):
        super().__init__()
        self.parent_installer = parent_installer
        layout = QVBoxLayout(self)

        title = QLabel("Installation Summary")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        layout.addWidget(self.summary_text)

        warning_label = QLabel(
            "<b>WARNING:</b> Clicking 'Install' will format the selected disk and install Mai Bloom OS. "
            "This process is irreversible and will erase all data on the selected disk."
        )
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("color: red;")
        layout.addWidget(warning_label)
        
        # Navigation
        nav_layout = QHBoxLayout()
        back_button = QPushButton("Back")
        back_button.clicked.connect(self.parent_installer.prev_page)
        self.install_button = QPushButton("Install")
        self.install_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.install_button.clicked.connect(self.parent_installer.start_installation_confirmed)
        nav_layout.addWidget(back_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.install_button)
        layout.addLayout(nav_layout)

    def update_summary(self):
        config = self.parent_installer.config
        summary = f"""
        <b>Installation Target:</b>
        Disk: {config['disk'].path if config['disk'] else 'Not selected'}
        Filesystem: {config['filesystem_type'].value}
        Boot Mode: {sys_info.BOOT_MODE}

        <b>System Configuration:</b>
        Hostname: {config['hostname']}
        Username: {config['username']}
        Create Sudo User: Yes

        <b>Disk Encryption:</b>
        Encrypt System: {'Yes' if config['encrypt'] else 'No'}
        Encryption Password: {'Set' if config['encrypt'] and config['enc_password'] else 'Not set'}

        <b>Packages to be installed (Core + Mai Bloom OS):</b>
        Kernel: linux
        Base: base, base-devel
        Mai Bloom OS (KDE Plasma & Utils): {', '.join(MAI_BLOOM_PACKAGES)}
        Mount Point: {MOUNT_POINT}

        Please review these settings carefully.
        """
        self.summary_text.setHtml(summary)


class InstallationPage(QWidget):
    def __init__(self, parent_installer):
        super().__init__()
        self.parent_installer = parent_installer
        layout = QVBoxLayout(self)

        title = QLabel("Installation Progress")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        layout.addWidget(title)

        self.progress_log = QTextEdit()
        self.progress_log.setReadOnly(True)
        layout.addWidget(self.progress_log)

        self.status_label = QLabel("Starting installation...")
        layout.addWidget(self.status_label)

        self.finish_button = QPushButton("Finish")
        self.finish_button.setEnabled(False)
        self.finish_button.clicked.connect(QApplication.instance().quit)
        
        self.cancel_button = QPushButton("Cancel Installation")
        self.cancel_button.clicked.connect(self.parent_installer.cancel_installation)
        self.cancel_button.setStyleSheet("background-color: #f44336; color: white;")


        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.cancel_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self.finish_button)
        layout.addLayout(nav_layout)


    def log_message(self, message):
        self.progress_log.append(message)
    
    def update_status(self, message):
        self.status_label.setText(message)

    def installation_complete(self, success, message):
        self.update_status(message)
        self.cancel_button.setEnabled(False)
        self.finish_button.setEnabled(True)
        if success:
            QMessageBox.information(self, "Installation Successful", message)
        else:
            QMessageBox.critical(self, "Installation Failed", message)


class MaiBloomInstaller(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mai Bloom OS Installer")
        self.setGeometry(100, 100, 800, 600) # x, y, width, height

        self.config = {
            "disk": None,
            "encrypt": False,
            "enc_password": None,
            "hostname": "maibloom-os",
            "username": "bloom", # Default username for Mai Bloom OS
            "password": None,
            "filesystem_type": FilesystemType('ext4'),
            # additional_packages are defined globally
        }

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.welcome_page = WelcomePage(self)
        self.disk_page = DiskSetupPage(self)
        self.user_page = UserSetupPage(self)
        self.summary_page = SummaryPage(self)
        self.install_page = InstallationPage(self)

        self.stacked_widget.addWidget(self.welcome_page)
        self.stacked_widget.addWidget(self.disk_page)
        self.stacked_widget.addWidget(self.user_page)
        self.stacked_widget.addWidget(self.summary_page)
        self.stacked_widget.addWidget(self.install_page)

        self.worker_thread = None

    def next_page(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index < self.stacked_widget.count() - 1:
            # Special handling for summary page update
            if self.stacked_widget.widget(current_index + 1) == self.summary_page:
                self.summary_page.update_summary()
            self.stacked_widget.setCurrentIndex(current_index + 1)

    def prev_page(self):
        current_index = self.stacked_widget.currentIndex()
        if current_index > 0:
            self.stacked_widget.setCurrentIndex(current_index - 1)

    def start_installation_confirmed(self):
        confirm_msg = QMessageBox.warning(
            self,
            "Confirm Installation",
            "This will erase all data on the selected disk and install Mai Bloom OS.\n"
            "Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm_msg == QMessageBox.Yes:
            self.stacked_widget.setCurrentWidget(self.install_page)
            self.run_installation()

    def run_installation(self):
        if os.geteuid() != 0:
            QMessageBox.critical(self, "Root Privileges Required", "This installer must be run as root. Please restart with sudo.")
            self.install_page.installation_complete(False, "Installation aborted: Not running as root.")
            return

        self.install_page.log_message("Preparing for installation...")
        self.install_page.cancel_button.setEnabled(True)
        self.install_page.finish_button.setEnabled(False)

        self.worker_thread = WorkerThread(self.config)
        self.worker_thread.progress_updated.connect(self.install_page.log_message)
        self.worker_thread.installation_finished.connect(self.install_page.installation_complete)
        self.worker_thread.start()

    def cancel_installation(self):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, 'Cancel Installation',
                                       "Are you sure you want to cancel the installation? This might leave the system in an inconsistent state.",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.worker_thread.stop()
                self.install_page.log_message("Installation cancellation requested by user.")
                self.install_page.cancel_button.setEnabled(False) # Prevent multiple clicks
                # Note: Stopping archinstall abruptly can be risky. WorkerThread.stop() just sets a flag.
                # Archinstall's Installer has an abort() method which is better.
                # This is a simple implementation.

    def closeEvent(self, event):
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, 'Exit Installer',
                                       "Installation is in progress. Are you sure you want to exit? This may corrupt the installation.",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.worker_thread.stop() # Attempt to stop gracefully
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def check_root():
    """Check if the script is run as root."""
    return os.geteuid() == 0

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Styling (Optional - for a slightly more modern look)
    app.setStyle("Fusion") 
    # You can experiment with QPalette for colors to match KDE Breeze if desired
    # For example:
    # palette = QPalette()
    # palette.setColor(QPalette.Window, QColor(53, 53, 53))
    # palette.setColor(QPalette.WindowText, Qt.white)
    # ... and so on for other roles
    # app.setPalette(palette)

    if not check_root():
         QMessageBox.critical(None, "Root Privileges Required", 
                                "This installer needs to be run with root privileges (e.g., using sudo).\n"
                                "The application will now exit.")
         sys.exit(1)

    installer_gui = MaiBloomInstaller()
    installer_gui.show()
    sys.exit(app.exec_())


