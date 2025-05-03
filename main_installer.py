#!/usr/bin/env python3
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Input, Static, Checkbox, RadioButton
from textual.containers import Vertical, Horizontal
import subprocess
import sys
import archinstall

def get_available_disks():
    """
    Retrieve a list of available disk devices using lsblk.
    Returns a list of disk names prefixed with '/dev/'.
    Note: There is no fallback here. If the command fails or no disks are found,
    this function returns an empty list (or raises an error if lsblk fails).
    """
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-n", "-o", "NAME"],
            capture_output=True,
            text=True,
            check=True
        )
        disks = ["/dev/" + disk.strip() for disk in result.stdout.splitlines() if disk.strip() != '']
        return disks
    except subprocess.CalledProcessError:
        return []

def custom_partitioning(disk):
    """
    Create a simple partition scheme for the given disk.
    Adjust mount points and sizes as necessary.
    """
    return {
        "disk": disk,
        "partitions": [
            {"mountpoint": "/", "size": "20G"},
            {"mountpoint": "/home", "size": "70%"},
            {"mountpoint": "swap", "size": "10G"}
        ]
    }

def run_installation(config):
    """
    Invoke the archinstall process with our configuration.
    Returns a tuple (success_flag, message).
    """
    try:
        installer = archinstall.Installer()
        installer.install(config)
        return True, "Installation completed successfully!"
    except Exception as e:
        return False, "Installation failed: " + str(e)

class InstallerApp(App):
    CSS = """
    Screen {
        background: #1d1f21;
        color: #c5c8c6;
    }
    .title {
        text-align: center;
        background: #ffcc00;
        color: #000000;
        padding: 1 2;
        border: round #ffff00;
        margin: 1;
    }
    .label {
        color: #00ff00;
        padding: 1;
    }
    .info {
        color: #ff00ff;
        text-style: italic;
        padding: 1;
    }
    Button {
        background: #005f5f;
        border: heavy #00ffff;
        margin: 1;
    }
    Button:hover {
        background: #00ffff;
        color: black;
    }
    Input {
        border: round #00ff00;
        padding: 1;
        margin: 1;
    }
    Checkbox {
        padding: 1;
        margin: 1;
    }
    RadioButton {
        padding: 1;
        margin: 1;
    }
    Static#status {
        border: round #ff00ff;
        padding: 1;
        margin: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Welcome to the Beautiful Arch Linux Installer", classes="title")

        # Section: Installation Details
        with Vertical():
            yield Input(placeholder="Hostname", id="hostname", value="archlinux")
            yield Input(placeholder="Locale (e.g., en_US.UTF-8)", id="locale", value="en_US.UTF-8")
            yield Input(placeholder="Timezone (e.g., America/New_York)", id="timezone", value="America/New_York")
            yield Input(placeholder="Username", id="username", value="yourusername")
            yield Input(placeholder="Password", id="password", password=True)

        # Section: Disk Selection
        yield Static("Select Disk:", classes="label")
        self.disk_container = Horizontal(id="disk-container")
        disks = get_available_disks()
        self.disk_buttons = []
        if disks:
            # Do not force a default selection; let the user choose.
            for disk in disks:
                rb = RadioButton(disk, id=f"disk-{disk}")
                self.disk_buttons.append(rb)
                self.disk_container.mount(rb)
        else:
            self.disk_container.mount(Static("No disks found. Please attach a disk.", classes="error"))
        yield self.disk_container

        # Section: Application Category Selection
        yield Static("Select Application Categories:", classes="label")
        self.category_container = Horizontal(id="category-container")
        self.app_categories = []
        for cat in ["Education", "Programming", "Gaming", "Daily Use"]:
            cb = Checkbox(cat, id=f"cat-{cat}")
            self.app_categories.append(cb)
            self.category_container.mount(cb)
        yield self.category_container

        # Preinstall Notice
        yield Static(
            "Note: In addition to your selections, extra applications (e.g., app stores) will be preinstalled.",
            classes="info"
        )

        # Install Button and Status Display
        yield Button("Install", id="install-btn")
        self.status_display = Static("", id="status")
        yield self.status_display
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install-btn":
            config = self.build_config()
            if config is None:
                # build_config already set an error, so do not proceed
                return
            self.status_display.update("Starting installation...")
            self.perform_installation(config)

    def build_config(self):
        hostname = self.query_one("#hostname", Input).value.strip() or "archlinux"
        locale = self.query_one("#locale", Input).value.strip() or "en_US.UTF-8"
        timezone = self.query_one("#timezone", Input).value.strip() or "America/New_York"
        username = self.query_one("#username", Input).value.strip() or "yourusername"
        password = self.query_one("#password", Input).value.strip() or "yourpassword"

        # Determine the selected disk.
        selected_disk = None
        for rb in self.disk_buttons:
            if rb.value:
                selected_disk = rb.label
                break
        if not selected_disk:
            self.status_display.update("[error]Error: You must select a disk before installing.[/error]")
            return None

        # Gather selected application categories.
        selected_categories = [cb.label for cb in self.app_categories if cb.value]

        return {
            "hostname": hostname,
            "locale": locale,
            "timezone": timezone,
            "user": {
                "name": username,
                "password": password,
                "sudo": True
            },
            "disk_config": custom_partitioning(selected_disk),
            "app_categories": selected_categories
        }

    def perform_installation(self, config):
        success, message = run_installation(config)
        self.status_display.update(message)
        if not success:
            # Additional error handling could be added here.
            pass

if __name__ == "__main__":
    InstallerApp().run()
