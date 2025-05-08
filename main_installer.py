import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox
from PyQt5.QtCore import Qt
import subprocess

class MaiBloomInstaller(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mai Bloom OS Installer")
        self.setGeometry(100, 100, 600, 400) # x, y, width, height

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.current_step = 0
        self.steps = [
            self.create_welcome_step,
            self.create_language_step,
            self.create_partition_step, # Placeholder for now
            # ... other steps
            self.create_install_summary_step
        ]

        self.setup_ui_for_current_step()

    def clear_layout(self):
        for i in reversed(range(self.layout.count())):
            widget_to_remove = self.layout.itemAt(i).widget()
            if widget_to_remove:
                widget_to_remove.setParent(None)

    def setup_ui_for_current_step(self):
        self.clear_layout()
        if self.current_step < len(self.steps):
            self.steps[self.current_step]() # Call the function to create the UI for the current step
        else:
            self.show_installation_complete()

    def next_step_clicked(self):
        # Add logic here to save choices from the current step
        # and validate before proceeding
        self.current_step += 1
        self.setup_ui_for_current_step()

    def prev_step_clicked(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.setup_ui_for_current_step()

    # --- UI Creation Methods for Each Step ---
    def create_welcome_step(self):
        welcome_label = QLabel("Welcome to Mai Bloom OS Installer!")
        welcome_label.setAlignment(Qt.AlignCenter)
        font = welcome_label.font()
        font.setPointSize(16)
        welcome_label.setFont(font)
        self.layout.addWidget(welcome_label)

        intro_text = QLabel("This installer will guide you through the process of installing Mai Bloom OS.")
        intro_text.setWordWrap(True)
        self.layout.addWidget(intro_text)

        self.layout.addStretch() # Add some space

        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_step_clicked)
        self.layout.addWidget(next_button)

    def create_language_step(self):
        title_label = QLabel("Language and Keyboard")
        title_label.setAlignment(Qt.AlignCenter)
        font = title_label.font()
        font.setPointSize(14)
        title_label.setFont(font)
        self.layout.addWidget(title_label)

        lang_label = QLabel("Select Language:")
        self.layout.addWidget(lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English", "Español", "Français", "Deutsch"]) # Populate with actual locales
        self.layout.addWidget(self.lang_combo)

        # Add keyboard layout selection here (could be another QComboBox)
        # For actual implementation, this would likely run `localectl list-keymaps`

        self.layout.addStretch()

        button_layout = QHBoxLayout()
        prev_button = QPushButton("Previous")
        prev_button.clicked.connect(self.prev_step_clicked)
        button_layout.addWidget(prev_button)

        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_step_clicked)
        button_layout.addWidget(next_button)
        self.layout.addLayout(button_layout)

    def create_partition_step(self):
        # This is where you'd implement the complex partitioning UI
        # For now, a placeholder:
        partition_label = QLabel("Disk Partitioning (Placeholder)")
        partition_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(partition_label)

        info_label = QLabel("Automatic and manual partitioning options will be available here.")
        self.layout.addWidget(info_label)
        self.layout.addStretch()

        button_layout = QHBoxLayout()
        prev_button = QPushButton("Previous")
        prev_button.clicked.connect(self.prev_step_clicked)
        button_layout.addWidget(prev_button)

        next_button = QPushButton("Next")
        next_button.clicked.connect(self.next_step_clicked)
        button_layout.addWidget(next_button)
        self.layout.addLayout(button_layout)


    def create_install_summary_step(self):
        summary_label = QLabel("Installation Summary (Placeholder)")
        summary_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(summary_label)

        # Display choices made by the user here

        self.layout.addStretch()
        install_button = QPushButton("Install Mai Bloom OS")
        install_button.clicked.connect(self.start_installation_process) # This would trigger backend commands
        self.layout.addWidget(install_button)

    def start_installation_process(self):
        # This is where you'd call your backend Python functions
        # that use `subprocess` to run Arch install commands.
        # For example:
        # self.run_command(["pacstrap", "/mnt", "base", "linux", "linux-firmware"])
        print("Starting installation... (This is where backend commands would run)")
        # After completion:
        # self.show_installation_complete()


    def show_installation_complete(self):
        self.clear_layout()
        complete_label = QLabel("Installation Complete!")
        complete_label.setAlignment(Qt.AlignCenter)
        font = complete_label.font()
        font.setPointSize(16)
        complete_label.setFont(font)
        self.layout.addWidget(complete_label)

        restart_button = QPushButton("Restart Now")
        restart_button.clicked.connect(self.restart_system)
        self.layout.addWidget(restart_button)

    def run_command(self, command_list):
        try:
            # For real use, you'd want to capture output, handle errors,
            # and potentially run in a separate thread to keep UI responsive.
            process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                print(f"Command '{' '.join(command_list)}' successful:\n{stdout}")
                return True, stdout
            else:
                print(f"Command '{' '.join(command_list)}' failed:\n{stderr}")
                return False, stderr
        except Exception as e:
            print(f"Exception running command '{' '.join(command_list)}': {e}")
            return False, str(e)

    def restart_system(self):
        print("Simulating system restart...")
        # In a real scenario: self.run_command(["reboot"])
        QApplication.instance().quit()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    installer = MaiBloomInstaller()
    installer.show()
    sys.exit(app.exec_())

