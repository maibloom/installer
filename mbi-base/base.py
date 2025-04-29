import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QMessageBox

class WelcomeApp(QWidget):
    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):
        # Set up the main window
        self.setWindowTitle('Welcome App')
        self.setGeometry(100, 100, 300, 200)

        # Create a label
        self.label = QLabel('Welcome to the PyQt5 Application!', self)
        self.label.setStyleSheet("font-size: 16px; font-weight: bold;")

        # Create a button
        self.button = QPushButton('Click Me', self)
        self.button.clicked.connect(self.on_button_click)

        # Set up the layout
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.button)
        self.setLayout(layout)

    def on_button_click(self):
        # Show a message box when the button is clicked
        QMessageBox.information(self, 'Information', 'Welcome to the PyQt5 Application!')

def main():
    app = QApplication(sys.argv)
    welcome_app = WelcomeApp()
    welcome_app.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()


