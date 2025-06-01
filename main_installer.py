#!/usr/bin/env python3
import sys
import subprocess
import time
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QMessageBox
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QTimer

def install_pipe():
    # Launch archinstall in konsole
    archinstall_konsole_command = "archinstall; exec bash"
    archinstall_process = subprocess.Popen(
        ["konsole", "-e", "bash", "-c", archinstall_konsole_command]
    )
        
    return_code = archinstall_process.wait()

    if return_code == 0:
        print("Archinstall konsole window closed. Assuming successful completion by user. Proceeding with post-installation steps...")
        
        post_install_chroot_script = (
            "pacman -Syu --noconfirm git && "
            "echo 'Git installed/updated.' && "
            "rm -rf /installer && "
            "echo 'Removed old /installer directory if it existed.' && "
            "git clone https://github.com/maibloom/installer /installer && "
            "echo 'Cloned maibloom/installer to /installer.' && "
            "cd /installer && "
            "chmod +x config.sh && "
            "echo 'Made config.sh executable.' && "
            "./config.sh && "
            "echo 'Post-installation script (config.sh) finished. You can close this terminal.' ; "
            "exec bash"
        )

        post_install_command = f'arch-chroot /mnt /bin/bash -c "{post_install_chroot_script}"'
        # Execute with shell=True because of the complex command string
        subprocess.Popen(post_install_command, shell=True)
    else:
        print("Archinstall encountered an error. Please check the installation process.")


class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Installation Notice")
        self.setGeometry(100, 100, 500, 250)

        layout = QVBoxLayout()

        message = (
            "Welcome!\n\n"
            "Your operating system will be installed using archinstall.\n"
            "Once installation is complete, additional configurations will be applied.\n\n"
            "Please ensure you have read the documentation and are ready to proceed with archinstall "
            "in a separate terminal window."
        )
        label = QLabel(message, self)
        label.setFont(QFont("Sans Serif", 12))
        label.setWordWrap(True)
        layout.addWidget(label)

        proceed_button = QPushButton("Proceed", self)
        proceed_button.setFont(QFont("Sans Serif", 11))
        proceed_button.setStyleSheet("padding: 8px; margin-top: 20px;")
        proceed_button.clicked.connect(self.on_proceed)
        layout.addWidget(proceed_button)

        self.setLayout(layout)

    def on_proceed(self):
        # Open a separate konsole window that launches Firefox for documentation
        subprocess.Popen(
            ["konsole", "-e", "bash", "-c", "firefox https://github.com/maibloom/iso/blob/main/README.md#installation-steps-%EF%B8%8F; exec bash"]
        )
        # Optionally, use a QTimer instead of time.sleep to keep the GUI responsive.
        QTimer.singleShot(2000, install_pipe)  # 2000 ms delay before running install_pipe


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = InstallerWindow()
    window.show()
    sys.exit(app.exec_())
