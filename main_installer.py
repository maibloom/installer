#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
import archinstall

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Static, Input, Checkbox, ListView, ListItem
from textual.reactive import reactive

# Disable logging output.
logging.disable(logging.CRITICAL)


# ------------------------ Helper Functions ------------------------

def get_available_disks():
    """
    Retrieve a list of available disk devices using lsblk.
    Returns a list of disk names prefixed with '/dev/'.
    """
    try:
        result = subprocess.run(
            ["lsblk", "-d", "-n", "-o", "NAME"],
            capture_output=True,
            text=True,
            check=True
        )
        disks = ["/dev/" + disk.strip() for disk in result.stdout.splitlines() if disk.strip()]
        if not disks:
            raise Exception("No disks found.")
        return disks
    except Exception:
        return ["/dev/sda"]


def custom_partitioning(disk):
    """
    Create a simple partitioning scheme given the selected disk.
    Adjust partition sizes and mount points as required.
    """
    partition_scheme = {
        "disk": disk,
        "partitions": [
            {"mountpoint": "/", "size": "20G"},    # root partition
            {"mountpoint": "/home", "size": "70%"},  # 70% for home
            {"mountpoint": "swap", "size": "10G"}    # swap partition
        ]
    }
    return partition_scheme


# ------------------------ Main Textual App ------------------------

class InstallerApp(App):
    CSS_PATH = None
    selected_disk: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Welcome to the Arch Linux Installer", id="welcome")
        # Basic configuration inputs.
        yield Input(placeholder="Hostname", id="hostname", value="archlinux")
        yield Input(placeholder="Locale (e.g., en_US.UTF-8)", id="locale", value="en_US.UTF-8")
        yield Input(placeholder="Timezone (e.g., America/New_York)", id="timezone", value="America/New_York")
        yield Input(placeholder="Username", id="username", value="yourusername")
        yield Input(placeholder="Password", id="password", password=True)
        # Disk selection.
        yield Static("Select Disk:", id="disk_label")
        disk_list = ListView(id="disk_list")
        for disk in get_available_disks():
            disk_item = ListItem(Static(disk))
            disk_list.append(disk_item)
        yield disk_list
        # Application category checkboxes.
        yield Static("Select Application Categories (choose any that apply):", id="app_category_label")
        self.app_categories = ["Education", "Programming", "Gaming", "Daily Use"]
        for category in self.app_categories:
            cid = f"cat_{category.replace(' ', '').lower()}"
            yield Checkbox(label=category, id=cid)
        # Preinstall notice.
        yield Static(
            "Note: In addition to the selected categories, several extra applications (e.g. app stores) will be preinstalled.",
            id="preinstall_note"
        )
        # Install button.
        yield Button("Install", id="install_button")
        # Status area.
        yield Static("Status:", id="status_label")
        self.status_text = Static("", id="status_text")
        yield self.status_text
        yield Footer()

    def on_mount(self) -> None:
        # Automatically select the first disk item, if any.
        disk_list = self.query_one("#disk_list", ListView)
        if disk_list.children:
            first_item = disk_list.children[0]
            # The contained Static widget holds the disk name.
            self.selected_disk = first_item.renderable.render_str
            self.status_text.update(f"Selected disk: {self.selected_disk}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Update the selected disk based on user selection.
        selected_item = event.item
        self.selected_disk = selected_item.renderable.render_str
        self.status_text.update(f"Selected disk: {self.selected_disk}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        # When the Install button is pressed, gather configuration and start installation.
        if event.button.id == "install_button":
            hostname = self.query_one("#hostname", Input).value.strip() or "archlinux"
            locale = self.query_one("#locale", Input).value.strip() or "en_US.UTF-8"
            timezone = self.query_one("#timezone", Input).value.strip() or "America/New_York"
            username = self.query_one("#username", Input).value.strip() or "yourusername"
            password = self.query_one("#password", Input).value.strip() or "yourpassword"
            selected_disk = self.selected_disk if self.selected_disk else "/dev/sda"
            # Gather app category selections.
            selected_categories = []
            for category in self.app_categories:
                cid = f"cat_{category.replace(' ', '').lower()}"
                checkbox = self.query_one(f"#{cid}", Checkbox)
                if checkbox.value:
                    selected_categories.append(checkbox.label)
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
                "disk_config": custom_partitioning(selected_disk),
                "app_categories": selected_categories
            }
            status_message = (
                "Starting installation with the following settings:\n"
                f"Hostname: {hostname}\n"
                f"Locale: {locale}\n"
                f"Timezone: {timezone}\n"
                f"Username: {username}\n"
                f"Disk: {selected_disk}\n"
                f"App Categories: {', '.join(selected_categories) if selected_categories else 'None'}\n\n"
                "Note: Additional applications (e.g. app stores) will be preinstalled."
            )
            self.status_text.update(status_message)
            await self.run_installation(config)

    async def run_installation(self, config: dict) -> None:
        # Update status and run the installation in a background thread.
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
