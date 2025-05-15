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
        self.setGeometry(100, 100, 500, 200)

        layout = QVBoxLayout()

        message = (
            "Welcome!\n\n"
            "Your operating system will be installed using archinstall.\n"
            "The archinstall terminal and Firefox documentation will appear side-by-side.\n\n"
            "Please ensure you have read the documentation before proceeding."
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
        arch_konsole_title = "Archinstall_Process_Window"
        firefox_url = "maibloom.github.io"
        firefox_main_window_title = "Mozilla Firefox"
        
        arch_geom = "0,0,0,800,600" 
        firefox_geom = "0,800,0,800,600"

        arch_command = f"archinstall; exec bash"
        subprocess.Popen([
            "konsole",
            "--title", arch_konsole_title,
            "-e", "bash", "-c", arch_command
        ])

        firefox_launcher_konsole_title = "Firefox_Launcher_Konsole"
        firefox_launch_command = f"firefox --new-window {firefox_url}; exec bash"
        subprocess.Popen([
            "konsole",
            "--title", firefox_launcher_konsole_title,
            "-e", "bash", "-c", firefox_launch_command
        ])

        time.sleep(5) 

        subprocess.call([
            "wmctrl", "-r", arch_konsole_title,
            "-e", arch_geom
        ])
        
        time.sleep(2) 
        subprocess.call([
            "wmctrl", "-r", firefox_main_window_title,
            "-e", firefox_geom
        ])

        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = InstallerWindow()
    window.show()
    sys.exit(app.exec_())

