#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import subprocess
import socket
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                            QPushButton, QMessageBox, QSpacerItem, QSizePolicy)
from PyQt5.QtGui import QPixmap, QFont # Import QFont
from PyQt5.QtCore import Qt, QTimer

# --- Configuration ---
LOGO_PATH = "logo.png"  # Path to your distro's logo file
# Consider using /tmp/ or a hidden cache dir like ~/.cache/maibloom_installer
CLONE_DIR = "/tmp/maibloom_installer_repo"
REPO_URL = "https://github.com/maibloom/installer"
MAIN_INSTALLER_SCRIPT = os.path.join(CLONE_DIR, "main_installer.py") # Assuming the script is at the root of the repo
DISTRO_NAME = "Mai Bloom"
# --- End Configuration ---

class BaseInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        # Remove the QTimer to prevent automatic start
        # QTimer.singleShot(500, self.start_installation_process)

    def initUI(self):
        self.setWindowTitle(f'{DISTRO_NAME} - Base Setup')
        self.setMinimumWidth(500) # Slightly wider for bigger text
        self.setMaximumWidth(650) # Prevent excessive widening

        layout = QVBoxLayout()
        layout.setSpacing(18) # Increase spacing slightly
        layout.setContentsMargins(25, 25, 25, 25) # Increase padding

        # --- Logo ---
        self.logo_label = QLabel(self)
        if os.path.exists(LOGO_PATH):
            pixmap = QPixmap(LOGO_PATH)
            # Scale logo nicely if it's too large, keeping aspect ratio
            if not pixmap.isNull():
                 # Keep logo size reasonable
                 self.logo_label.setPixmap(pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                 self.logo_label.setText("(Logo format invalid)") # Placeholder text
        else:
             self.logo_label.setText("(Logo file missing)")
        self.logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.logo_label)

        # --- Welcome Message ---
        self.welcome_label = QLabel(f"Welcome to the {DISTRO_NAME} installer!", self)
        self.welcome_label.setAlignment(Qt.AlignCenter)
        welcome_font = self.welcome_label.font()
        welcome_font.setPointSize(18) # << Increased font size
        welcome_font.setBold(True)
        self.welcome_label.setFont(welcome_font)
        self.welcome_label.setWordWrap(True) # Ensure wrap if needed
        layout.addWidget(self.welcome_label)

        # --- Status Label ---
        self.status_label = QLabel("Press 'Start Installation' to begin.", self) # Initial message
        self.status_label.setAlignment(Qt.AlignCenter)
        status_font = self.status_label.font()
        status_font.setPointSize(13) # << Set font size for status
        self.status_label.setFont(status_font)
        self.status_label.setWordWrap(True) # Allow text wrapping
        layout.addWidget(self.status_label)

        # --- Spacer ---
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # --- Start Installation Button ---
        self.start_button = QPushButton("Start Installation", self)
        button_font = self.start_button.font()
        button_font.setPointSize(11)
        self.start_button.setFont(button_font)
        self.start_button.setMinimumHeight(35)
        self.start_button.clicked.connect(self.start_installation_process) # Connect to the process
        layout.addWidget(self.start_button)


        # --- Retry Button (Initially Hidden) ---
        self.retry_button = QPushButton("Retry Connection Check", self)
        # Make buttons slightly bigger too
        # button_font is already defined
        self.retry_button.setFont(button_font)
        self.retry_button.setMinimumHeight(35) # Taller button
        self.retry_button.clicked.connect(self.start_installation_process)
        self.retry_button.hide() # Hide until needed
        layout.addWidget(self.retry_button)

        # --- Close Button ---
        self.close_button = QPushButton("Close", self)
        self.close_button.setFont(button_font) # Use same larger font
        self.close_button.setMinimumHeight(35) # Taller button
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)


        self.setLayout(layout)
        self.show()

    def update_status(self, message):
        """Updates the status label and forces UI refresh."""
        print(f"Status Update: {message}") # Also print to console for debugging
        self.status_label.setText(message)
        QApplication.processEvents() # Force UI update

    def check_internet(self, host="8.8.8.8", port=53, timeout=3):
        """
        Checks for internet connectivity by trying to connect to Google's DNS.
        Returns True if connected, False otherwise.
        """
        self.update_status("Checking internet connection...")
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            self.update_status("Internet connection detected.")
            return True
        except socket.error as ex:
            print(f"Connection Error: {ex}")
            self.update_status("No internet connection found.")
            return False

    def show_network_config(self):
        """Shows a message and attempts to launch KDE Wi-Fi settings."""
        self.update_status("No internet connection. Please configure your network (Wi-Fi).")
        QMessageBox.warning(self, "Network Required",
                            "An internet connection is required to download the main installer.\n\nPlease connect to a network using the Wi-Fi settings tool that will be opened.")

        # Try to open KDE Wi-Fi settings specifically
        try:
            self.update_status("Attempting to open Wi-Fi settings...")
            # Command to directly open the Wi-Fi KCM module
            command = ['kcmshell6', 'kcm_networkmanagement', 'wifi'] # Keeping kcmshell6 as per original code
            process = subprocess.Popen(command)
            print(f"Launched Wi-Fi settings (PID: {process.pid}) using command: {' '.join(command)}")
            self.update_status("Wi-Fi settings opened. Please connect and then click 'Retry'.")
            self.retry_button.show() # Show the retry button
            self.close_button.setText("Cancel Installation") # Make intent clear
            self.start_button.hide() # Hide start button once process begins/needs retry

        except FileNotFoundError:
             self.update_status("Error: Could not find 'kcmshell6'. Is KDE installed correctly?")
             QMessageBox.critical(self, "Error", "Could not launch the network configuration tool ('kcmshell6' not found).\nPlease configure your network manually and restart the installer.")
             self.retry_button.hide() # Can't retry if tool is missing
             self.start_button.show() # Show start button again if tool missing error

        except Exception as e:
            # Fallback or just report error if specific command fails?
            # For now, just report the error. Could add fallback to generic network settings.
            self.update_status(f"Error opening Wi-Fi settings: {e}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred while trying to open Wi-Fi settings:\n{e}")
            self.retry_button.show() # Still allow retry even if auto-open failed
            self.start_button.hide() # Hide start button once process begins/needs retry


    def download_installer(self):
        """Clones the installer repository using git."""
        self.update_status(f"Downloading main installer from {REPO_URL}...")
        self.start_button.hide() # Hide start button during download

        if os.path.exists(CLONE_DIR):
            self.update_status(f"Removing existing directory: {CLONE_DIR}")
            try:
                import shutil
                shutil.rmtree(CLONE_DIR)
            except Exception as e:
                 self.update_status(f"Error removing existing directory: {e}")
                 QMessageBox.critical(self, "Clone Error", f"Could not remove the existing installer directory at:\n{CLONE_DIR}\n\nPlease check permissions or remove it manually.\nError: {e}")
                 self.start_button.show() # Show start button on error
                 return False

        try:
            process = subprocess.run(['git', 'clone', REPO_URL, CLONE_DIR],
                                     check=True, capture_output=True, text=True)
            print("Git Clone Output:", process.stdout)
            self.update_status("Installer downloaded successfully.")
            return True
        except FileNotFoundError:
             self.update_status("Error: 'git' command not found. Is git installed?")
             QMessageBox.critical(self, "Error", "'git' command not found. Please install git and try again.")
             self.start_button.show() # Show start button on error
             return False
        except subprocess.CalledProcessError as e:
            self.update_status(f"Error downloading installer (git clone failed).")
            print(f"Git Clone Error Output:\n{e.stderr}")
            QMessageBox.critical(self, "Download Error",
                                 f"Failed to clone the repository from:\n{REPO_URL}\n\nError: {e.stderr}\n\nPlease check the URL and your internet connection.")
            self.start_button.show() # Show start button on error
            return False
        except Exception as e:
            self.update_status(f"An unexpected error occurred during download: {e}")
            QMessageBox.critical(self, "Download Error", f"An unexpected error occurred during download:\n{e}")
            self.start_button.show() # Show start button on error
            return False

    def run_main_installer(self):
        """Runs the main installer script using sudo python."""
        if not os.path.exists(MAIN_INSTALLER_SCRIPT):
             self.update_status(f"Error: Main installer script not found at {MAIN_INSTALLER_SCRIPT}")
             QMessageBox.critical(self, "Error", f"The main installer script was expected at:\n{MAIN_INSTALLER_SCRIPT}\n\nBut it was not found after cloning. Does the repository contain this file at the root?")
             self.start_button.show() # Show start button on error
             return

        self.update_status("Launching the main installer (requires administrator privileges)...")
        command = ['sudo', 'python3', MAIN_INSTALLER_SCRIPT] # Use python3 explicitly

        try:
            print(f"Running command: {' '.join(command)}")
            process = subprocess.Popen(command)
            self.update_status("Main installer launched. This window will close shortly.")
            # Close this base installer window after launching
            QTimer.singleShot(2500, self.close) # Close after a short delay
            self.close_button.setEnabled(False) # Disable close button while timer runs
            self.retry_button.hide() # Ensure retry button is hidden
            self.start_button.hide() # Ensure start button is hidden

        except FileNotFoundError:
            self.update_status("Error: 'sudo' or 'python3' command not found.")
            QMessageBox.critical(self, "Error", "'sudo' or 'python3' command not found. Please ensure they are installed and in your PATH.")
            self.close_button.setEnabled(True) # Re-enable close button on error
            self.start_button.show() # Show start button on error
        except Exception as e:
            self.update_status(f"Error launching main installer: {e}")
            QMessageBox.critical(self, "Error", f"An unexpected error occurred while launching the main installer:\n{e}")
            self.close_button.setEnabled(True) # Re-enable close button on error
            self.start_button.show() # Show start button on error


    def start_installation_process(self):
        """Main logic flow: check internet, download, run."""
        self.retry_button.hide()
        self.close_button.setText("Close")
        self.close_button.setEnabled(True) # Ensure close button is enabled initially
        self.start_button.setEnabled(False) # Disable start button once pressed

        if self.check_internet():
            if self.download_installer():
                self.run_main_installer()
            else:
                self.update_status("Download failed. Please check errors and retry or close.")
                self.retry_button.show() # Allow retry after download failure
                self.start_button.show() # Show start button again if download failed
                self.start_button.setEnabled(True) # Re-enable start button
        else:
            self.show_network_config()
            self.start_button.show() # Show start button again if network config needed
            self.start_button.setEnabled(True) # Re-enable start button if network config needed


# --- Main Execution ---
if __name__ == '__main__':
    # Removed the check for root privileges and the associated messages
    # if os.geteuid() == 0:
    #      print("Error: Please do not run this base setup script with sudo or as root.")
    #      print("It will request administrator privileges only when needed to launch the main installer.")
    #      try:
    #          app_check = QApplication(sys.argv)
    #          QMessageBox.critical(None, "Permission Error", "Please do not run this base setup script with sudo or as root.\n\nIt will request administrator privileges later if required.")
    #      except Exception:
    #          pass
    #      sys.exit(1)

    app = QApplication(sys.argv)
    # Optional: Apply a style like Fusion for consistency if Breeze isn't default
    # app.setStyle('Fusion')
    installer = BaseInstaller()
    sys.exit(app.exec_())
