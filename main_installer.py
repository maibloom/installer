#!/usr/bin/env python3
import sys
import subprocess
import time
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QMessageBox
from PyQt5.QtGui import QFont

class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
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
        proceed_button.clicked.connect(self.onProceed)
        layout.addWidget(proceed_button)

        self.setLayout(layout)

    def onProceed(self):
        subprocess.Popen(["konsole", "-e", "bash", "-c", "firefox maibloom.github.io; exec bash"])
        
        time.sleep(2)

        archinstall_konsole_command = "archinstall; echo 'Archinstall process finished. You can close this terminal to continue the main script.'; exec bash"
        archinstall_process = subprocess.Popen(["konsole", "-e", "bash", "-c", archinstall_konsole_command])
        
        QMessageBox.information(self, "Archinstall Running", 
                                "Archinstall has been launched in a new terminal window.\n\n"
                                "1. Complete the Arch Linux installation using `archinstall` in that window.\n"
                                "2. After `archinstall` is done, CLOSE that `konsole` window.\n\n"
                                "This script will automatically continue with post-installation steps once that window is closed.")

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
                "echo 'Post-installation script (config.sh) finished. You can close this terminal.' && "
                "exec bash"
            )
            
            post_install_konsole_command = f"arch-chroot /mnt /bin/bash -c '{post_install_chroot_script}'"
            
            post_install_process = subprocess.Popen(["konsole", "-e", "bash", "-c", post_install_konsole_command])
            
            QMessageBox.information(self, "Post-Installation Steps", 
                                    "Post-installation configuration has been launched in a new terminal window.\n"
                                    "Please follow any instructions there. This application can now be closed "
                                    "if you wish, or wait until you close the post-install terminal.")

        else:
            error_message = (f"The archinstall terminal window was closed, but it seems it might not have completed as expected "
                             f"(konsole process return code: {return_code}).\n\n"
                             "Post-installation steps will NOT be executed. Please check the archinstall terminal for any errors.")
            print(error_message)
            QMessageBox.critical(self, "Archinstall Issue Detected", error_message)

        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = InstallerWindow()
    window.show()
    sys.exit(app.exec_())
