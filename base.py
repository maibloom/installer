#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import subprocess
import socket
import shutil
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSplitter,
                           QPushButton, QMessageBox, QSpacerItem, QSizePolicy, QPlainTextEdit)
from PyQt5.QtGui import QPixmap, QFont, QFontDatabase
from PyQt5.QtCore import Qt, QTimer

# --- Configuration ---
LOGO_PATH = "logo.png"  # Path to your distro's logo file
CLONE_DIR = "/tmp/maibloom_installer_repo" # Directory for cloning the installer repo
REPO_URL = "https://github.com/maibloom/installer" # URL of the installer repository
MAIN_INSTALLER_SCRIPT = os.path.join(CLONE_DIR, "main_installer.py") # Main script in the repo
DISTRO_NAME = "Mai Bloom"
# --- End Configuration ---

class BaseInstaller(QWidget):
   def __init__(self):
       super().__init__()
       self.initUI()
       self.appendToTerminal(f"{DISTRO_NAME} Base Setup Initialized.")
       self.appendToTerminal("Press 'Start Installation' to begin the process.")

   def initUI(self):
       self.setWindowTitle(f'{DISTRO_NAME} - Base Setup with Terminal Log')
       self.setMinimumWidth(800)
       self.setMaximumWidth(1200)

       main_h_layout = QHBoxLayout(self)
       splitter = QSplitter(Qt.Horizontal)

       left_pane_widget = QWidget()
       controls_layout = QVBoxLayout(left_pane_widget)
       controls_layout.setSpacing(18)
       controls_layout.setContentsMargins(20, 20, 20, 20)

       self.logo_label = QLabel(self)
       if os.path.exists(LOGO_PATH):
           pixmap = QPixmap(LOGO_PATH)
           if not pixmap.isNull():
                self.logo_label.setPixmap(pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
           else:
                self.logo_label.setText("(Logo format invalid)")
       else:
            self.logo_label.setText("(Logo file missing)")
       self.logo_label.setAlignment(Qt.AlignCenter)
       controls_layout.addWidget(self.logo_label)

       self.welcome_label = QLabel(f"Welcome to the {DISTRO_NAME} installer!", self)
       self.welcome_label.setAlignment(Qt.AlignCenter)
       welcome_font = self.welcome_label.font()
       welcome_font.setPointSize(18)
       welcome_font.setBold(True)
       self.welcome_label.setFont(welcome_font)
       self.welcome_label.setWordWrap(True)
       controls_layout.addWidget(self.welcome_label)

       self.status_label = QLabel("Press 'Start Installation' to begin.", self)
       self.status_label.setAlignment(Qt.AlignCenter)
       status_font = self.status_label.font()
       status_font.setPointSize(13)
       self.status_label.setFont(status_font)
       self.status_label.setWordWrap(True)
       controls_layout.addWidget(self.status_label)

       controls_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

       self.start_button = QPushButton("Start Installation", self)
       button_font = self.start_button.font()
       button_font.setPointSize(11)
       self.start_button.setFont(button_font)
       self.start_button.setMinimumHeight(35)
       self.start_button.clicked.connect(self.start_installation_process)
       controls_layout.addWidget(self.start_button)

       self.retry_button = QPushButton("Retry Connection Check", self)
       self.retry_button.setFont(button_font)
       self.retry_button.setMinimumHeight(35)
       self.retry_button.clicked.connect(self.start_installation_process)
       self.retry_button.hide()
       controls_layout.addWidget(self.retry_button)

       self.close_button = QPushButton("Close", self)
       self.close_button.setFont(button_font)
       self.close_button.setMinimumHeight(35)
       self.close_button.clicked.connect(self.close)
       controls_layout.addWidget(self.close_button)

       splitter.addWidget(left_pane_widget)

       self.terminal_output = QPlainTextEdit()
       self.terminal_output.setReadOnly(True)
       terminal_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
       terminal_font.setPointSize(10)
       self.terminal_output.setFont(terminal_font)
       self.terminal_output.setLineWrapMode(QPlainTextEdit.WidgetWidth)
       splitter.addWidget(self.terminal_output)

       splitter.setSizes([350, 450])
       main_h_layout.addWidget(splitter)
       self.setLayout(main_h_layout)
       self.show()

   def appendToTerminal(self, text):
       self.terminal_output.appendPlainText(text)
       self.terminal_output.verticalScrollBar().setValue(self.terminal_output.verticalScrollBar().maximum())
       QApplication.processEvents()

   def update_status(self, message):
       print(f"Status Update: {message}")
       self.status_label.setText(message)
       self.appendToTerminal(f"[INFO] {message}")
       QApplication.processEvents()

   def check_internet(self, host="8.8.8.8", port=53, timeout=3):
       self.update_status("Checking internet connection...")
       self.appendToTerminal(f"Attempting to connect to {host}:{port} with timeout {timeout}s...")
       try:
           socket.setdefaulttimeout(timeout)
           socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
           self.update_status("Internet connection detected.")
           self.appendToTerminal("Internet connection check successful.")
           return True
       except socket.error as ex:
           print(f"Connection Error: {ex}")
           self.update_status("No internet connection found.")
           self.appendToTerminal(f"Internet connection check failed: {ex}")
           return False

   def show_network_config(self):
       self.update_status("No internet. Please configure your network (Wi-Fi).")
       self.appendToTerminal("Internet connection not found. Prompting user to configure network.")
       QMessageBox.warning(self, "Network Required",
                           "An internet connection is required to download the main installer.\n\nPlease connect to a network using the Wi-Fi settings tool that will be opened.")
       try:
           self.update_status("Attempting to open Wi-Fi settings...")
           self.appendToTerminal("Trying to launch KDE Wi-Fi settings (kcmshell6 kcm_networkmanagement wifi)...")
           command = ['kcmshell6', 'kcm_networkmanagement', 'wifi']
           process = subprocess.Popen(command)
           self.appendToTerminal(f"Launched Wi-Fi settings (PID: {process.pid}) using command: {' '.join(command)}")
           self.update_status("Wi-Fi settings opened. Please connect and then click 'Retry'.")
           self.retry_button.show()
           self.close_button.setText("Cancel Installation")
           self.start_button.hide()
       except FileNotFoundError:
            err_msg = "Error: Could not find 'kcmshell6'. Is KDE Plasma installed correctly?"
            self.update_status(err_msg)
            self.appendToTerminal(err_msg)
            QMessageBox.critical(self, "Error", f"{err_msg}\nPlease configure your network manually and restart the installer.")
            self.retry_button.hide() # Can't retry if tool is missing
            # self.start_button.show() # start_installation_process handles final button state
       except Exception as e:
           err_msg = f"Error opening Wi-Fi settings: {e}"
           self.update_status(err_msg)
           self.appendToTerminal(err_msg)
           QMessageBox.critical(self, "Error", f"An unexpected error occurred while trying to open Wi-Fi settings:\n{e}")
           self.retry_button.show()
           self.start_button.hide()

   def download_installer(self):
       self.update_status(f"Downloading main installer from {REPO_URL}...")
       self.start_button.setEnabled(False) # Disable start while this operates, even if hidden

       if os.path.exists(CLONE_DIR):
           self.update_status(f"Removing existing directory: {CLONE_DIR}")
           self.appendToTerminal(f"Attempting to remove existing clone directory: {CLONE_DIR}")
           try:
               shutil.rmtree(CLONE_DIR)
               self.appendToTerminal(f"Successfully removed {CLONE_DIR}.")
           except Exception as e:
                err_msg = f"Error removing existing directory: {e}"
                self.update_status(err_msg)
                self.appendToTerminal(err_msg)
                QMessageBox.critical(self, "Clone Error", f"Could not remove the existing installer directory at:\n{CLONE_DIR}\n\nPlease check permissions or remove it manually.\nError: {e}")
                return False # Allow start_installation_process to set buttons

       self.appendToTerminal(f"Starting download from {REPO_URL} into {CLONE_DIR}")
       git_command = ['git', 'clone', REPO_URL, CLONE_DIR]
       self.appendToTerminal(f"Executing: {' '.join(git_command)}")

       try:
           process = subprocess.Popen(git_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding='utf-8', errors='replace', bufsize=1)
           for line in iter(process.stdout.readline, ''):
               if line:
                   self.appendToTerminal(line.strip())
           process.stdout.close()
           return_code = process.wait()

           if return_code == 0:
               self.update_status("Installer downloaded successfully.")
               self.appendToTerminal("Git clone completed successfully.")
               return True
           else:
               err_msg = f"Error downloading installer (git clone failed with exit code {return_code})."
               self.update_status(err_msg)
               # Specific git errors already printed line-by-line from Popen output
               QMessageBox.critical(self, "Download Error",
                                   f"Failed to clone the repository. Exit code: {return_code}.\nCheck the terminal log for details.")
               return False
       except FileNotFoundError:
           err_msg = "Error: 'git' command not found. Is git installed?"
           self.update_status(err_msg)
           self.appendToTerminal(err_msg)
           QMessageBox.critical(self, "Error", f"{err_msg}\nPlease install git and try again.")
           return False
       except Exception as e:
           err_msg = f"An unexpected error occurred during download: {e}"
           self.update_status(err_msg)
           self.appendToTerminal(err_msg)
           QMessageBox.critical(self, "Download Error", err_msg)
           return False

   def run_main_installer(self):
       if not os.path.exists(MAIN_INSTALLER_SCRIPT):
            err_msg = f"Error: Main installer script not found at {MAIN_INSTALLER_SCRIPT}"
            self.update_status(err_msg)
            self.appendToTerminal(err_msg)
            QMessageBox.critical(self, "Error", f"The main installer script was expected at:\n{MAIN_INSTALLER_SCRIPT}\n\nBut it was not found. Does the repository contain this file?")
            return False # Indicate failure to allow button reset

       self.update_status("Launching the main installer (requires administrator privileges via kdesu)...")
       # Use kdesu for graphical privilege escalation on KDE
       command = ['/usr/lib/kf6/kdesu', 'python3', MAIN_INSTALLER_SCRIPT]

       try:
           self.appendToTerminal(f"Executing main installer with: {' '.join(command)}")
           print(f"Running command: {' '.join(command)}")
           process = subprocess.Popen(command)
           self.appendToTerminal(f"Main installer process launched using kdesu (PID: {process.pid}). This window will close shortly.")
           self.update_status("Main installer launched. This window will close shortly.")
           QTimer.singleShot(2500, self.close)
           self.close_button.setEnabled(False)
           self.retry_button.hide()
           self.start_button.hide()
           return True # Indicate success
       except FileNotFoundError:
           err_msg = "Error: 'kdesu' or 'python3' command not found."
           self.update_status(err_msg)
           self.appendToTerminal(err_msg)
           self.appendToTerminal("Please ensure KDE Development tools (providing kdesu) and Python 3 are installed and in your PATH.")
           QMessageBox.critical(self, "Error", f"{err_msg}\nPlease ensure 'kdesu' (often in kde-cli-tools or kdesu package) and 'python3' are installed and in your PATH.")
           return False
       except Exception as e:
           err_msg = f"Error launching main installer: {e}"
           self.update_status(err_msg)
           self.appendToTerminal(err_msg)
           QMessageBox.critical(self, "Error", f"An unexpected error occurred while launching the main installer:\n{e}")
           return False

   def start_installation_process(self):
       self.retry_button.hide()
       self.close_button.setText("Close")
       self.close_button.setEnabled(True)
       self.start_button.setEnabled(False) # Disable start button once pressed
       self.start_button.hide() # Hide start button, retry will be primary action if needed
       self.appendToTerminal("--- Starting Installation Process ---")

       proceed_to_run = False
       if self.check_internet():
           if self.download_installer():
               proceed_to_run = True
           else:
               self.update_status("Download failed. Please check errors and retry or close.")
               self.appendToTerminal("Download step failed. User can retry or close.")
               self.retry_button.setText("Retry Download")
               self.retry_button.show()
       else:
           self.appendToTerminal("Internet check failed. Network configuration prompted.")
           self.retry_button.setText("Retry Connection Check")
           # show_network_config will show retry_button if successful in launching,
           # or if it fails to launch kcmshell6, it will allow retry_button to be shown.
           self.show_network_config() # This method itself shows/hides buttons.

       if proceed_to_run:
           if not self.run_main_installer(): # If run_main_installer fails (e.g. kdesu not found)
                self.retry_button.setText("Retry Installation") # Or some other appropriate text
                self.retry_button.show()
                self.appendToTerminal("Failed to launch main installer. User can retry.")
       
       # Final button state management
       if not self.close_button.isEnabled(): # Main installer launched successfully and window is closing
           pass
       elif self.retry_button.isVisible():
           self.start_button.hide() # Ensure start is hidden if retry is active
           self.start_button.setEnabled(False)
       else: # No retry shown, and installer not launched (e.g. unrecoverable error before retry, or initial state)
           self.start_button.show()
           self.start_button.setEnabled(True)

# --- Main Execution ---
if __name__ == '__main__':
   app = QApplication(sys.argv)
   installer = BaseInstaller()
   sys.exit(app.exec_())

