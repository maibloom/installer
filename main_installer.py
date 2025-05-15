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
        self.setGeometry(100, 100, 500, 220) # Slightly increased height for message

        layout = QVBoxLayout()

        message = (
            "Welcome!\n\n"
            "Your operating system will be installed using archinstall.\n"
            "The archinstall terminal will appear on the left, and Firefox with documentation "
            "will appear on the right.\n\n"
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
        screen = QApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry() # Use availableGeometry to avoid overlapping with desktop panels
            screen_width = rect.width()
            screen_height = rect.height()
            print(f"Detected screen: {screen_width}x{screen_height} (available geometry)")
        else:
            # Fallback defaults if primaryScreen isn't available
            screen_width = 1920
            screen_height = 1080
            print("Warning: Could not get primary screen geometry. Using defaults: 1920x1080.")

        # Calculate dimensions for each window (half screen width)
        win_width = screen_width // 2
        # Use a significant portion of screen height, e.g., 85%
        win_height = int(screen_height * 0.85)

        # Apply minimum sensible dimensions
        if win_height < 600: win_height = 600
        if win_width < 700: win_width = 700 # Ensure terminal/browser is wide enough

        # Define positions and titles
        # Archinstall Konsole on the left
        arch_x = 0
        arch_y = 0 # Typically 0 for top of screen
        arch_w = win_width
        arch_h = win_height
        arch_konsole_title = "Archinstall_Process_Window"

        # Firefox window on the right
        ff_x = win_width # Starts immediately after the archinstall window
        ff_y = 0
        ff_w = win_width
        ff_h = win_height
        # Standard window title substring for Firefox. This might vary if using non-standard Firefox builds.
        firefox_window_target_title = "Mozilla Firefox"
        firefox_url = "maibloom.github.io" # The URL to open

        # Launch Archinstall in its own Konsole
        arch_command = f"echo 'Starting Archinstall...'; archinstall; echo 'Archinstall process finished. This terminal will remain open.'; exec bash"
        print(f"Launching Archinstall Konsole (title: {arch_konsole_title})...")
        subprocess.Popen([
            "konsole",
            "--title", arch_konsole_title,
            "-e", "bash", "-c", arch_command
        ])
        firefox_launcher_konsole_title = "Documentation_Viewer_Launcher"
        firefox_command = (f"echo 'Opening documentation in Firefox ({firefox_url})...'; "
                           f"firefox --new-window {firefox_url}; "
                           f"echo 'Firefox launched. This terminal launcher will remain open.'; exec bash")
        print(f"Launching Firefox Konsole launcher (title: {firefox_launcher_konsole_title})...")
        subprocess.Popen([
            "konsole",
            "--title", firefox_launcher_konsole_title,
            "-e", "bash", "-c", firefox_command
        ])


        initial_wait_time = 6 # seconds
        print(f"Waiting {initial_wait_time} seconds for windows to initialize...")
        time.sleep(initial_wait_time)


        arch_geometry = f"0,{arch_x},{arch_y},{arch_w},{arch_h}"
        print(f"Attempting to move '{arch_konsole_title}' with geometry: {arch_geometry}")
        subprocess.call([
            "wmctrl", "-r", arch_konsole_title,
            "-e", arch_geometry
        ])

        print(f"Attempting to find and move '{firefox_window_target_title}'...")
        firefox_moved = False
        attempts = 0
        max_attempts = 15
        ff_geometry = f"0,{ff_x},{ff_y},{ff_w},{ff_h}"

        while not firefox_moved and attempts < max_attempts:
            try:
                win_list_output = subprocess.check_output(["wmctrl", "-l"], text=True, timeout=1)

                if firefox_window_target_title in win_list_output:
                    print(f"'{firefox_window_target_title}' window found. Attempting to move with geometry: {ff_geometry}")

                    rc = subprocess.call([
                        "wmctrl", "-r", firefox_window_target_title,
                        "-e", ff_geometry
                    ])
                    firefox_moved = True
                    print(f"Move command for '{firefox_window_target_title}' executed.") # (wmctrl exit code: {rc})
                else:
                    print(f"'{firefox_window_target_title}' window not yet found in wmctrl list (attempt {attempts+1}/{max_attempts}). Waiting...")
            except subprocess.CalledProcessError as e:
                print(f"Error running wmctrl to list windows: {e}. Retrying...")
            except subprocess.TimeoutExpired:
                print(f"Timeout running wmctrl to list windows. Retrying...")
            
            if not firefox_moved:
                time.sleep(1) # Wait 1 second before the next attempt
                attempts += 1

        if not firefox_moved:
            print(f"Warning: Could not move '{firefox_window_target_title}' after {max_attempts} attempts. "
                  f"It might not have opened as expected, or the window title is different.")
        
        print("Window placement attempts finished.")
        self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = InstallerWindow()
    window.show()
    sys.exit(app.exec_())


