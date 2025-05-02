#!/usr/bin/env python3
import asyncio
import subprocess
import os
import sys
import tempfile

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Static, Input
from textual.screen import Screen
from textual import events

# ------------------------ Blocking Helper Functions ------------------------

def check_network_manager_blocking() -> bool:
    """Check NetworkManager status and try to start it if not running."""
    try:
        subprocess.check_call(['systemctl', 'is-active', '--quiet', 'NetworkManager'])
        return True
    except subprocess.CalledProcessError:
        try:
            subprocess.check_call(['sudo', 'systemctl', 'start', 'NetworkManager'])
            return True
        except subprocess.CalledProcessError:
            return False

def is_connected_blocking() -> bool:
    """Return True if network connectivity is already established."""
    try:
        # 'nmcli networking connectivity' returns "full" when connected.
        output = subprocess.check_output(['nmcli', 'networking', 'connectivity']).decode().strip()
        return output.lower() == 'full'
    except Exception:
        return False

def list_networks_blocking() -> str:
    """Return the output of available wireless networks."""
    try:
        output = subprocess.check_output(['nmcli', 'device', 'wifi', 'list']).decode('utf-8')
        return output
    except Exception as e:
        return f"Error listing networks: {e}"

def connect_to_network_blocking(ssid: str, password: str) -> bool:
    """Attempt to connect to a wireless network with provided credentials."""
    try:
        result = subprocess.run(
            ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def clone_installer_repo_blocking(repo_url: str, destination: str) -> bool:
    """Clone the Git repo to a destination folder."""
    try:
        subprocess.check_call(['git', 'clone', repo_url, destination])
        return True
    except subprocess.CalledProcessError:
        return False

def run_installer_blocking(installer_script: str):
    """Launch the main installer by running the script."""
    subprocess.check_call(['python3', installer_script])

# ------------------------ TUI Screens ------------------------

class WelcomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # Use orange for "Welcome" and purple for the rest
        welcome_text = (
            "[bold orange1]Welcome[/bold orange1] to the [bold purple]Mai Bloom OS Installer[/bold purple]\n"
            "An easy and guided installation experience."
        )
        yield Static(welcome_text, id="welcome")
        yield Button("Start", id="start")
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start":
            await self.app.push_screen(NetworkScreen())

class NetworkScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold purple]Network Configuration[/bold purple]")
        # Placeholder widget for network listing
        yield Static("", id="networks")
        self.ssid_input = Input(placeholder="Enter SSID", id="ssid")
        self.password_input = Input(placeholder="Enter Password", password=True, id="password")
        yield self.ssid_input
        yield self.password_input
        # Add two buttons: one to “Connect” and one to “Skip”
        yield Button("Connect", id="connect")
        yield Button("Skip (Already Connected)", id="skip")
        self.message_area = Static("", id="net_message")
        yield self.message_area
        yield Footer()

    async def on_mount(self, event: events.Mount) -> None:
        # If already connected, skip configuration.
        if await asyncio.to_thread(is_connected_blocking):
            self.message_area.update("[bold green]Network is already connected. Skipping network configuration...[/bold green]")
            await asyncio.sleep(2)
            await self.app.push_screen(CloneScreen())
            return

        nm_ok = await asyncio.to_thread(check_network_manager_blocking)
        if not nm_ok:
            self.message_area.update("[bold red]NetworkManager could not be started. Please check your system.[/bold red]")
            return

        networks_output = await asyncio.to_thread(list_networks_blocking)
        net_widget = self.query_one("#networks", Static)
        net_widget.update(f"[bold green]Available Networks:[/bold green]\n{networks_output}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect":
            ssid = self.ssid_input.value.strip()
            password = self.password_input.value.strip()
            if not ssid or not password:
                self.message_area.update("[bold red]SSID and password cannot be empty.[/bold red]")
                return

            self.message_area.update("Connecting...")
            connected = await asyncio.to_thread(connect_to_network_blocking, ssid, password)
            if connected:
                self.message_area.update("[bold green]Connected successfully![/bold green]")
                await asyncio.sleep(2)
                await self.app.push_screen(CloneScreen())
            else:
                self.message_area.update("[bold red]Failed to connect. Please recheck your credentials.[/bold red]")
        elif event.button.id == "skip":
            self.message_area.update("[bold green]Skipping network configuration...[/bold green]")
            await asyncio.sleep(1)
            await self.app.push_screen(CloneScreen())

class CloneScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold purple]Cloning the Mai Bloom Installer Repository[/bold purple]")
        self.progress_area = Static("Starting clone...", id="progress")
        yield self.progress_area
        yield Footer()

    async def on_mount(self, event: events.Mount) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="maibloom_installer_")
        repo_url = "https://github.com/maibloom/installer"

        for percent in range(0, 101, 20):
            self.progress_area.update(f"Cloning... {percent}%")
            await asyncio.sleep(0.5)

        cloned = await asyncio.to_thread(clone_installer_repo_blocking, repo_url, self.temp_dir)
        if cloned:
            self.progress_area.update("[bold green]Clone completed successfully.[/bold green]")
            self.app.temp_dir = self.temp_dir
            await asyncio.sleep(1)
            await self.app.push_screen(LaunchScreen())
        else:
            self.progress_area.update("[bold red]Error cloning the installer repository.[/bold red]")

class LaunchScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold purple]Launching the Mai Bloom Installation Wizard[/bold purple]")
        self.message_area = Static("Please wait...", id="launch_msg")
        yield self.message_area
        yield Footer()

    async def on_mount(self, event: events.Mount) -> None:
        temp_dir = getattr(self.app, "temp_dir", None)
        if not temp_dir:
            self.message_area.update("[bold red]Temporary installer directory not found.[/bold red]")
            return
        installer_script = os.path.join(temp_dir, "main_installer.py")
        self.message_area.update("Launching installer...")
        await asyncio.sleep(1)
        self.app.exit(result=installer_script)

# ------------------------ Main Textual App ------------------------

class MaiBloomInstallerApp(App):
    temp_dir: str = ""
    CSS = """
    Screen {
        background: #800080;  /* Purple background */
    }
    Header, Footer {
        background: #FFA500;  /* Orange for header/footer */
        color: black;
    }
    """

    async def on_exit(self) -> None:
        installer_script = self.exit_result
        if installer_script:
            try:
                subprocess.check_call(['python3', installer_script])
            except subprocess.CalledProcessError as e:
                print(f"Error while launching installer: {e}")
                sys.exit(1)

    def on_key(self, event: events.Key) -> None:
        if event.key == "q":
            self.exit()

    def compose(self) -> ComposeResult:
        yield WelcomeScreen()

if __name__ == "__main__":
    MaiBloomInstallerApp().run()
