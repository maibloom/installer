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

# ------------------------ Helper Functions ------------------------

def check_network_manager() -> bool:
    try:
        subprocess.check_call(['systemctl', 'is-active', '--quiet', 'NetworkManager'])
        return True
    except subprocess.CalledProcessError:
        try:
            subprocess.check_call(['sudo', 'systemctl', 'start', 'NetworkManager'])
            return True
        except subprocess.CalledProcessError:
            return False

def is_connected() -> bool:
    try:
        output = subprocess.check_output(['nmcli', 'networking', 'connectivity']).decode().strip()
        return output.lower() == 'full'
    except Exception:
        return False

def list_networks() -> str:
    try:
        return subprocess.check_output(['nmcli', 'device', 'wifi', 'list']).decode().strip()
    except Exception as e:
        return f"Error: {e}"

def connect_to_network(ssid: str, password: str) -> bool:
    try:
        res = subprocess.run(
            ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True
        )
        return res.returncode == 0
    except Exception:
        return False

def clone_repo(repo_url: str, destination: str) -> bool:
    try:
        subprocess.check_call(['git', 'clone', repo_url, destination])
        return True
    except subprocess.CalledProcessError:
        return False

def run_installer(script_path: str):
    subprocess.check_call(['python3', script_path])

# ------------------------ Screens ------------------------

class WelcomeScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # Orange "Welcome" and purple installer title
        welcome_text = (
            "[bold orange1]Welcome[/bold orange1] to the [bold purple]Mai Bloom OS Installer[/bold purple]\n"
            "A guided, simple install experience."
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
        self.net_list = Static("", id="networks")
        yield self.net_list
        self.ssid = Input(placeholder="Enter SSID", id="ssid")
        self.password = Input(placeholder="Enter Password", password=True, id="password")
        yield self.ssid
        yield self.password
        yield Button("Connect", id="connect")
        yield Button("Skip (Already Connected)", id="skip")
        self.message = Static("", id="message")
        yield self.message
        yield Footer()

    async def on_mount(self, event: events.Mount) -> None:
        # If already connected, immediately skip to cloning.
        if await asyncio.to_thread(is_connected):
            self.message.update("[bold green]Already connected. Skipping network configuration...[/bold green]")
            await asyncio.sleep(1)
            await self.app.push_screen(CloneScreen())
            return

        if not await asyncio.to_thread(check_network_manager):
            self.message.update("[bold red]NetworkManager could not be started.[/bold red]")
            return

        nets = await asyncio.to_thread(list_networks)
        self.net_list.update(f"[bold green]Available Networks:[/bold green]\n{nets}")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect":
            ssid = self.ssid.value.strip()
            password = self.password.value.strip()
            if not ssid or not password:
                self.message.update("[bold red]Please enter both SSID and password.[/bold red]")
                return
            self.message.update("Connecting...")
            if await asyncio.to_thread(connect_to_network, ssid, password):
                self.message.update("[bold green]Connected successfully![/bold green]")
                await asyncio.sleep(1)
                await self.app.push_screen(CloneScreen())
            else:
                self.message.update("[bold red]Failed to connect.[/bold red]")
        elif event.button.id == "skip":
            self.message.update("[bold green]Skipping network configuration...[/bold green]")
            await asyncio.sleep(1)
            await self.app.push_screen(CloneScreen())

class CloneScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("[bold purple]Cloning the Installer Repository[/bold purple]")
        self.progress = Static("Starting clone...", id="progress")
        yield self.progress
        yield Footer()

    async def on_mount(self, event: events.Mount) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="maibloom_")
        repo_url = "https://github.com/maibloom/installer"
        for percent in range(0, 101, 25):
            self.progress.update(f"Cloning... {percent}%")
            await asyncio.sleep(0.5)
        if await asyncio.to_thread(clone_repo, repo_url, self.temp_dir):
            self.progress.update("[bold green]Clone complete.[/bold green]")
            await asyncio.sleep(1)
            installer = os.path.join(self.temp_dir, "main_installer.py")
            self.app.exit(result=installer)
        else:
            self.progress.update("[bold red]Clone failed.[/bold red]")

# ------------------------ App ------------------------

class InstallerApp(App):
    CSS = """
    Screen {
        background: #800080;  /* Purple background */
    }
    Header, Footer {
        background: #FFA500;  /* Orange header and footer */
        color: black;
    }
    """
    async def on_exit(self) -> None:
        installer_script = self.exit_result
        if installer_script:
            try:
                run_installer(installer_script)
            except subprocess.CalledProcessError as e:
                print("Error launching installer:", e)
                sys.exit(1)

    def on_key(self, event: events.Key) -> None:
        if event.key == "q":
            self.exit()

    def compose(self) -> ComposeResult:
        yield WelcomeScreen()

if __name__ == "__main__":
    InstallerApp().run()
