#!/usr/bin/env python3
"""
Mai Bloom Installer - Sequential Installation Workflow
"""

import asyncio
import subprocess
from typing import Optional, Tuple
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Static, Input, Label, ProgressBar, Footer, Header

# ----------------------------
# Installation Sequence Screens
# ----------------------------

class WelcomeScreen(Screen):
    """Initial welcome and confirmation screen"""
    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("\n\nMAI BLOOM INSTALLER\n", classes="title")
            yield Static("Welcome to Mai Bloom Installation\n\n", classes="subtitle")
            yield Button("Start Installation", id="begin-btn")
        yield Footer()

    @on(Button.Pressed, "#begin-btn")
    def proceed(self) -> None:
        self.app.push_screen(NetworkScreen())

class NetworkScreen(Screen):
    """WiFi configuration screen with error recovery"""
    BINDINGS = [("q", "quit", "Quit")]
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("Network Configuration", classes="screen-title")
            yield Static("Connecting to WiFi...", id="network-status")
            yield Button("Retry Connection", id="retry-btn", classes="hidden")
        yield Footer()

    def on_mount(self) -> None:
        self.attempt_connection()

    @work(exclusive=True)
    async def attempt_connection(self) -> None:
        """Try connecting with stored credentials or manual input"""
        status = self.query_one("#network-status")
        retry_btn = self.query_one("#retry-btn")
        
        try:
            status.update("Scanning networks...")
            # Implement your network connection logic here
            await asyncio.sleep(2)  # Simulated connection delay
            status.update("Connected successfully!")
            await asyncio.sleep(1)
            self.app.push_screen(DownloadScreen())
        except Exception as e:
            status.update(f"Connection failed: {str(e)}")
            retry_btn.remove_class("hidden")

    @on(Button.Pressed, "#retry-btn")
    def retry_connection(self) -> None:
        self.query_one("#retry-btn").add_class("hidden")
        self.attempt_connection()

class DownloadScreen(Screen):
    """Package download progress screen"""
    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("Downloading Components", classes="screen-title")
            yield ProgressBar(id="download-progress")
            yield Static("Preparing download...", id="download-status")
        yield Footer()

    def on_mount(self) -> None:
        self.start_download()

    @work(exclusive=True)
    async def start_download(self) -> None:
        """Simulated package download with progress"""
        progress = self.query_one("#download-progress")
        status = self.query_one("#download-status")
        
        try:
            for percent in range(0, 101, 10):
                progress.update(progress=percent)
                status.update(f"Downloading... {percent}%")
                await asyncio.sleep(0.5)
            self.app.push_screen(InstallScreen())
        except Exception as e:
            status.update(f"Download failed: {str(e)}")
            self.app.push_screen(ErrorScreen(str(e)))

class InstallScreen(Screen):
    """System installation progress screen"""
    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("System Installation", classes="screen-title")
            yield ProgressBar(id="install-progress")
            yield Static("Starting installation...", id="install-status")
        yield Footer()

    def on_mount(self) -> None:
        self.start_installation()

    @work(exclusive=True)
    async def start_installation(self) -> None:
        """Execute installation scripts"""
        progress = self.query_one("#install-progress")
        status = self.query_one("#install-status")
        
        try:
            # Execute your installation scripts here
            for step in range(1, 6):
                progress.update(progress=step*20)
                status.update(f"Installing component {step}/5")
                await asyncio.sleep(1)
            status.update("Installation complete!")
            await asyncio.sleep(1)
            self.app.push_screen(CompletionScreen())
        except Exception as e:
            self.app.push_screen(ErrorScreen(str(e)))

class CompletionScreen(Screen):
    """Final installation completion screen"""
    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("\n\nINSTALLATION COMPLETE\n", classes="title")
            yield Static("Mai Bloom is ready to use!\n\n", classes="subtitle")
            yield Button("Reboot System", id="reboot-btn")
        yield Footer()

    @on(Button.Pressed, "#reboot-btn")
    def reboot(self) -> None:
        subprocess.run(["systemctl", "reboot"])

class ErrorScreen(Screen):
    """Error display screen with recovery options"""
    def __init__(self, error_msg: str):
        super().__init__()
        self.error_msg = error_msg

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Static("Installation Error", classes="screen-title")
            yield Static(self.error_msg, id="error-message")
            with Horizontal():
                yield Button("Retry", id="retry-btn")
                yield Button("Exit", id="exit-btn")
        yield Footer()

    @on(Button.Pressed, "#retry-btn")
    def retry(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#exit-btn")
    def exit(self) -> None:
        self.app.exit()

# ----------------------------
# Main Application
# ----------------------------

class MaiBloomInstaller(App):
    """Main installer application with screen management"""
    CSS = """
    Container {
        padding: 2;
        width: 80%;
        height: 80%;
        align: center middle;
    }
    .title {
        text-align: center;
        color: $accent;
        text-style: bold;
    }
    .subtitle {
        text-align: center;
        margin: 2;
    }
    .hidden {
        display: none;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This installer requires root privileges. Use sudo.")
        sys.exit(1)
        
    MaiBloomInstaller().run()

