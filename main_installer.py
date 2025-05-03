#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
import archinstall  # Ensure archinstall is installed in your environment

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Static, Input
from textual.reactive import reactive

# Disable logging output.
logging.disable(logging.CRITICAL)


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
    except Exception:
        return "/dev/sda"


def custom_partitioning(disk):
    """
    Create a simple partitioning scheme given the selected disk.
    Adjust partition sizes and mount points as required.
    """
    return {
        "disk": disk,
        "partitions": [
            {"mountpoint": "/", "size": "20G"},    # root partition
            {"mountpoint": "/home", "size": "70%"},  # 70% for home
            {"mountpoint": "swap", "size": "10G"}    # swap partition
        ]
    }


# ------------------------ Main Textual App ------------------------

class InstallerApp(App):
    CSS_PATH = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Welcome to the Arch Linux Installer", id="welcome")
        # Basic configuration inputs.
        yield Input(placeholder="Hostname", id="hostname", value="archlinux")
        yield Input(placeholder="Locale (e.g., en_US.UTF-8)", id="locale", value="en_US.UTF-8")
        yield Input(placeholder="Timezone (e.g., America/New_York)", id="timezone", value="America/New_York")
        yield Input(placeholder="Username", id="username", value="yourusername")
        yield Input(placeholder="Password", id="password", password=True)
        # Disk selection input.
        yield Input(placeholder="Disk (e.g., /dev/sda)", id="disk", value=get_default_disk())
        # Application categories as a comma-separated list.
        yield Input(
            placeholder="App Categories (comma separated, e.g., Education,Programming)",
            id="app_categories",
            value=""
        )
        # Install button.
        yield Button("Install", id="install_button")
        # Status area.
        yield Static("Status:", id="status_label")
        self.status_text = Static("", id="status_text")
        yield self.status_text
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "install_button":
            # Gather data from inputs.
            hostname = self.query_one("#hostname", Input).value.strip() or "archlinux"
            locale   = self.query_one("#locale", Input).value.strip() or "en_US.UTF-8"
            timezone = self.query_one("#timezone", Input).value.strip() or "America/New_York"
            username = self.query_one("#username", Input).value.strip() or "yourusername"
            password = self.query_one("#password", Input).value.strip() or "yourpassword"
            disk     = self.query_one("#disk", Input).value.strip() or "/dev/sda"
            app_categories_str = self.query_one("#app_categories", Input).value.strip()
            categories = [item.strip() for item in app_categories_str.split(",") if item.strip()] if app_categories_str else []

            # Build the installer configuration.
            config = {
                "hostname": hostname,
                "locale": locale,
                "timezone": timezone,
                "user": {
                    "name": username,
                    "password": password,
                    "sudo": True
                },
                "disk_config": custom_partitioning(disk),
                "app_categories": categories
            }
            status_message = (
                "Starting installation with the following settings:\n"
                f"Hostname: {hostname}\n"
                f"Locale: {locale}\n"
                f"Timezone: {timezone}\n"
                f"Username: {username}\n"
                f"Disk: {disk}\n"
                f"App Categories: {', '.join(categories) if categories else 'None'}\n"
                "Note: Additional applications will be preinstalled."
            )
            self.status_text.update(status_message)
            await self.run_installation(config)

    async def run_installation(self, config: dict) -> None:
        self.status_text.update("[bold magenta]Installation in progress...[/bold magenta]")
        try:
            installer = archinstall.Installer()
            await self.run_in_thread(installer.install, config)
            self.status_text.update("[bold green]Installation completed successfully![/bold green]")
        except Exception as e:
            self.status_text.update(f"[bold red]Installation failed: {e}[/bold red]")
            self.exit()


if __name__ == "__main__":
    InstallerApp().run()
