#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
import archinstall
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Static, Input
from textual.reactive import reactive

# Configure logging
logging.basicConfig(
    filename='/var/log/installer.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# ------------------------ Helper Functions ------------------------

def get_default_disk():
    """
    Retrieve the first available disk device using lsblk.
    Returns a disk name prefixed with '/dev/'.
    """
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-n", "-o", "NAME"],
            capture_output=True,
            text=True,
            check=True
        )
        disks = ["/dev/" + disk.strip() for disk in result.stdout.splitlines() if disk.strip()]
        return disks[0] if disks else "/dev/sda"
    except Exception as e:
        logging.error(f"Error retrieving default disk: {e}")
        return "/dev/sda"

# ------------------------ Main Textual App ------------------------

class InstallerApp(App):
    CSS = """
    Screen {
        background: #1e1e2e;
        color: #f8f8f2;
        padding: 1 2;
    }
    Header {
        background: #282a36;
        color: #f8f8f2;
    }
    #welcome {
        text-align: center;
        padding: 2;
        color: #ff79c6;
        border: heavy #6272a4;
        margin: 1;
    }
    Input {
        border: round #6272a4;
        margin: 1;
        padding: 1;
    }
    Button {
        background: #50fa7b;
        color: #282a36;
        border: round #6272a4;
        margin: 1;
        padding: 1;
        text-style: bold;
    }
    #status_text {
        background: #ffb86c;
        color: #282a36;
        padding: 1;
        margin: 1;
        border: round #6272a4;
    }
    Footer {
        background: #282a36;
        color: #f8f8f2;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Welcome to the Arch Linux Installer", id="welcome")
        yield Input(placeholder="Hostname", id="hostname", value="archlinux")
        yield Input(placeholder="Locale (e.g., en_US.UTF-8)", id="locale", value="en_US.UTF-8")
        yield Input(placeholder="Timezone (e.g., America/New_York)", id="timezone", value="America/New_York")
        yield Input(placeholder="Username", id="username", value="user")
        yield Input(placeholder="Password", id="password", password=True)
        yield Input(placeholder="Disk (e.g., /dev/sda)", id="disk", value=get_default_disk())
        yield Input(placeholder="App Categories (comma separated)", id="app_categories", value="")
        yield Button("Install", id="install_button")
        yield Static("Status:", id="status_label")
        self.status_text = Static("", id="status_text")
        yield self.status_text
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install_button":
            hostname = self.query_one("#hostname", Input).value.strip() or "archlinux"
            locale = self.query_one("#locale", Input).value.strip() or "en_US.UTF-8"
            timezone = self.query_one("#timezone", Input).value.strip() or "America/New_York"
            username = self.query_one("#username", Input).value.strip() or "user"
            password = self.query_one("#password", Input).value.strip() or "password"
            disk = self.query_one("#disk", Input).value.strip() or get_default_disk()
            app_categories_str = self.query_one("#app_categories", Input).value.strip()
            categories = [item.strip() for item in app_categories_str.split(",") if item.strip()] if app_categories_str else []

            status_message = (
                "Starting installation with the following settings:\n"
                f"Hostname: {hostname}\n"
                f"Locale: {locale}\n"
                f"Timezone: {timezone}\n"
                f"Username: {username}\n"
                f"Disk: {disk}\n"
                f"App Categories: {', '.join(categories) if categories else 'None'}\n"
                "Note: Extra applications will be preinstalled."
            )

            self.status_text.update(status_message)
            await self.run_installation(hostname, locale, timezone, username, password, disk, categories)

    async def run_installation(self, hostname, locale, timezone, username, password, disk, categories):
        self.status_text.update("[bold magenta]Installation in progress...[/bold magenta]")
        try:
            with archinstall.Filesystem(disk, archinstall.GPT) as fs:
                fs.add_partition(size='512M', mountpoint='/boot', fs_type='fat32')
                fs.add_partition(size='20G', mountpoint='/', fs_type='ext4')
                fs.add_partition(size='100%', mountpoint='/home', fs_type='ext4')

                with archinstall.Installer(disk, mountpoint='/mnt') as installer:
                    installer.install_base_system()
                    installer.set_hostname(hostname)
                    installer.set_locale(locale)
                    installer.set_timezone(timezone)
                    installer.create_user(username, password)
                    installer.install_bootloader()

                    # Install additional packages
                    if categories:
                        installer.install_packages(categories)

            self.status_text.update("[bold green]Installation completed successfully![/bold green]")
        except Exception as e:
            logging.error(f"Installation failed: {e}")
            self.status_text.update(f"[bold red]Installation failed: {e}[/bold red]")
            self.exit()

if __name__ == "__main__":
    InstallerApp().run()