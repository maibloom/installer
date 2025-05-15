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
            "Once installation is complete, additional configurations will be applied.\n\n"
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
        subprocess.Popen([
            "konsole",
            "--geometry", "80x24+800+0",
            "-e", "bash", "-c", "firefox maibloom.github.io; exec bash"
        ])
        subprocess.Popen([
            "konsole",
            "--geometry", "80x24+0+0",
            "-e", "bash", "-c", "archinstall; exec bash"
        ])
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = InstallerWindow()
    window.show()
    sys.exit(app.exec_())
