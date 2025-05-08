import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QPushButton,
    QLabel, QLineEdit, QWidget, QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt

from archinstall import Installer, ProfileConfiguration, profile_handler, User
from archinstall.default_profiles.minimal import MinimalProfile
from archinstall.lib.disk.device_model import FilesystemType
from archinstall.lib.disk.encryption_menu import DiskEncryptionMenu
from archinstall.lib.disk.filesystem import FilesystemHandler
from archinstall.lib.interactions.disk_conf import select_disk_config

class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mai Bloom OS Installer")
        self.setGeometry(100, 100, 500, 400)

        self.initUI()

    def initUI(self):
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)
        self.layout = QVBoxLayout()

        # Hostname
        self.hostnameLabel = QLabel("Hostname:")
        self.hostnameInput = QLineEdit()
        self.hostnameInput.setPlaceholderText("Enter hostname")
        self.layout.addWidget(self.hostnameLabel)
        self.layout.addWidget(self.hostnameInput)

        # Username
        self.usernameLabel = QLabel("Username:")
        self.usernameInput = QLineEdit()
        self.usernameInput.setPlaceholderText("Enter username")
        self.layout.addWidget(self.usernameLabel)
        self.layout.addWidget(self.usernameInput)

        # Password
        self.passwordLabel = QLabel("Password:")
        self.passwordInput = QLineEdit()
        self.passwordInput.setPlaceholderText("Enter password")
        self.passwordInput.setEchoMode(QLineEdit.Password)
        self.layout.addWidget(self.passwordLabel)
        self.layout.addWidget(self.passwordInput)

        # Disk Encryption
        self.encryptionCheckBox = QCheckBox("Enable Disk Encryption")
        self.layout.addWidget(self.encryptionCheckBox)

        # Install Button
        self.installButton = QPushButton("Install")
        self.installButton.clicked.connect(self.startInstallation)
        self.layout.addWidget(self.installButton)

        self.centralWidget.setLayout(self.layout)

    def startInstallation(self):
        hostname = self.hostnameInput.text()
        username = self.usernameInput.text()
        password = self.passwordInput.text()
        enable_encryption = self.encryptionCheckBox.isChecked()

        if not hostname or not username or not password:
            QMessageBox.warning(self, "Input Error", "Please fill in all fields.")
            return

        try:
            self.performInstallation(hostname, username, password, enable_encryption)
            QMessageBox.information(self, "Success", "Installation completed successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Installation failed: {str(e)}")

    def performInstallation(self, hostname, username, password, enable_encryption):
        fs_type = FilesystemType('ext4')
        disk_config = select_disk_config()

        data_store = {}
        if enable_encryption:
            disk_encryption = DiskEncryptionMenu(disk_config.device_modifications, data_store).run()
        else:
            disk_encryption = None

        fs_handler = FilesystemHandler(disk_config, disk_encryption)
        fs_handler.perform_filesystem_operations()

        mountpoint = Path('/tmp')

        with Installer(
            mountpoint,
            disk_config,
            disk_encryption=disk_encryption,
            kernels=['linux']
        ) as installation:
            installation.mount_ordered_layout()
            installation.minimal_installation(hostname=hostname)
            installation.add_additional_packages(['nano', 'wget', 'git', 'plasma', 'sddm'])

            profile_config = ProfileConfiguration(MinimalProfile())
            profile_handler.install_profile_config(installation, profile_config)

            user = User(username, password, True)
            installation.create_users(user)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = InstallerWindow()
    window.show()
    sys.exit(app.exec_())
