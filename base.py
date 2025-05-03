#!/usr/bin/env python3
import subprocess
import os
import sys
import tempfile

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Button, Static, Input
from textual.reactive import reactive

# ------------------------ Helper Functions ------------------------

def check_network_manager():
    try:
        subprocess.check_call(['systemctl', 'is-active', '--quiet', 'NetworkManager'])
        return True
    except subprocess.CalledProcessError:
        try:
            subprocess.check_call(['sudo', 'systemctl', 'start', 'NetworkManager'])
            return True
        except subprocess.CalledProcessError:
            return False

def is_connected():
    try:
        output = subprocess.check_output(['nmcli', 'networking', 'connectivity']).decode().strip()
        return output.lower() == 'full'
    except Exception:
        return False

def list_networks():
    try:
        return subprocess.check_output(['nmcli', 'device', 'wifi', 'list']).decode().strip()
    except Exception as e:
        return f"Network list error: {e}"

def connect_to_network(ssid, password):
    try:
        res = subprocess.run(
            ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True
        )
        return res.returncode == 0
    except Exception:
        return False

def clone_repo(repo_url, destination):
    try:
        subprocess.check_call(['git', 'clone', repo_url, destination])
        return True
    except subprocess.CalledProcessError:
        return False

def run_installer(script_path):
    subprocess.check_call(['python3', script_path])


# ------------------------ Screen Classes ------------------------

class MessageScreen(Screen):
    """A simple screen to display a transient message."""
    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self.message, id="message")
        yield Footer()


class WelcomeScreen(Screen):
    """The welcome screen invites the user to begin the install process."""
    def compose(self) -> ComposeResult:
        yield Header()
        welcome_text = (
            "[bold magenta]Welcome[/bold magenta] to the [bold cyan]Mai Bloom OS Installer[/bold cyan]\n"
            "From Users, For Users"
        )
        yield Static(welcome_text, id="welcome_text")
        yield Button("Start", id="start_button")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start_button":
            # Signal the app to continue the wizard.
            self.app.handle_welcome_start()


class NetworkScreen(Screen):
    """Screen to configure network connection."""
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Network Configuration", id="network_header")
        networks = list_networks()
        yield Static(f"Available Networks:\n{networks}", id="networks_text")
        yield Input(placeholder="SSID", id="ssid_input")
        yield Input(password=True, placeholder="Password", id="password_input")
        yield Button("Connect", id="connect_button")
        yield Button("Skip (Already Connected)", id="skip_button")
        yield Static("", id="network_message")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        message_widget = self.query_one("#network_message", Static)
        if event.button.id == "connect_button":
            ssid = self.query_one("#ssid_input", Input).value.strip()
            password = self.query_one("#password_input", Input).value.strip()
            if not ssid or not password:
                message_widget.update("[red]Please enter both SSID and password.[/red]")
                return
            message_widget.update("Connecting...")
            if connect_to_network(ssid, password):
                message_widget.update("[green]Connected successfully![/green]")
                self.app.set_timer(1, self.app.show_clone_screen)
            else:
                message_widget.update("[red]Failed to connect. Check credentials.[/red]")
        elif event.button.id == "skip_button":
            message_widget.update("[green]Skipping network configuration...[/green]")
            self.app.set_timer(1, self.app.show_clone_screen)


class CloneScreen(Screen):
    """Screen to simulate cloning the installer repository."""
    progress: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Cloning the Installer Repository", id="clone_header")
        yield Static("Starting clone...", id="clone_status")
        yield Footer()

    def on_mount(self) -> None:
        # Create a temporary directory and store it in the app for later use.
        self.temp_dir = tempfile.mkdtemp(prefix="maibloom_")
        self.app.temp_dir = self.temp_dir
        self.repo_url = "https://github.com/maibloom/installer"
        self.progress = 0
        self.refresh_progress()

    def refresh_progress(self):
        clone_status = self.query_one("#clone_status", Static)
        if self.progress > 100:
            if clone_repo(self.repo_url, self.temp_dir):
                clone_status.update("[green]Clone complete. Launching installer...[/green]")
                self.app.set_timer(1, self.app.launch_installer)
            else:
                clone_status.update("[red]Clone failed.[/red]")
            return
        clone_status.update(f"Cloning... {self.progress}%")
        self.progress += 25
        self.app.set_timer(0.5, self.refresh_progress)


# ------------------------ Main App Class ------------------------

class WizardApp(App):
    """A Textual-based wizard installer app."""
    CSS_PATH = None  # Optionally, set a CSS file for styling

    def on_mount(self) -> None:
        self.temp_dir = None
        self.push_screen(WelcomeScreen())

    def handle_welcome_start(self):
        # Decide whether to configure the network or skip based on connectivity.
        if is_connected():
            self.push_screen(
                MessageScreen("Network is already connected; skipping network configuration...")
            )
            self.set_timer(1, self.show_clone_screen)
        else:
            self.push_screen(NetworkScreen())

    def show_clone_screen(self):
        self.push_screen(CloneScreen())

    def launch_installer(self):
        installer_script = (
            os.path.join(self.temp_dir, "main_installer.py") if self.temp_dir else ""
        )
        self.push_screen(MessageScreen("Launching installer..."))
        try:
            run_installer(installer_script)
        except subprocess.CalledProcessError as e:
            print(f"Error launching installer: {e}")
            sys.exit(1)
        self.exit()


if __name__ == "__main__":
    WizardApp().run()
