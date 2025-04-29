#!/usr/bin/env python3
"""
Mai Bloom Operating Installation Base Builder Tool
"""

import asyncio
import subprocess
import os
import sys
from typing import List, Optional, Tuple
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Button, Static, Input, Label, DataTable, Footer, Header
from textual.reactive import reactive
from textual.binding import Binding

class Network:
    """Represents a WiFi network with validation"""
    def __init__(self, ssid: str, security: str, bssid: str, signal: str):
        if not ssid:
            raise ValueError("SSID cannot be empty")
        self.ssid = ssid
        self.security = security if security else "Open"
        self.bssid = bssid
        self.signal = int(signal) if signal.isdigit() else 0

    @property
    def signal_strength(self) -> str:
        """Visual signal representation"""
        return "▮" * max(1, min(4, self.signal // 25))

class NetworkScanner:
    """Robust network scanner with retry logic"""
    MAX_RETRIES = 3
    RETRY_DELAY = 2

    @classmethod
    async def ensure_services(cls) -> bool:
        """Ensure required services are running"""
        for _ in range(cls.MAX_RETRIES):
            try:
                if not os.path.exists("/usr/bin/nmcli"):
                    cls.install_package("networkmanager")
                
                result = subprocess.run(
                    ["systemctl", "is-active", "NetworkManager"],
                    capture_output=True, text=True
                )
                if "inactive" in result.stdout.lower():
                    subprocess.run(["systemctl", "start", "NetworkManager"], check=True)
                return True
            except subprocess.CalledProcessError as e:
                await asyncio.sleep(cls.RETRY_DELAY)
        return False

    @staticmethod
    def install_package(pkg: str) -> None:
        """Package installation with error handling"""
        try:
            subprocess.run(
                ["pacman", "-Sy", "--noconfirm", pkg],
                check=True,
                stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(f"Failed to install {pkg}")

    @classmethod
    async def scan(cls) -> List[Network]:
        """Network scanning with retries"""
        for attempt in range(cls.MAX_RETRIES):
            try:
                subprocess.run(
                    ["nmcli", "dev", "wifi", "rescan"],
                    check=True, timeout=10
                )
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "SSID,SECURITY,BSSID,SIGNAL", "dev", "wifi", "list"],
                    capture_output=True, text=True, timeout=15
                )
                return cls.parse_results(result.stdout)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                if attempt == cls.MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(cls.RETRY_DELAY)
        return []

    @staticmethod
    def parse_results(output: str) -> List[Network]:
        """Safe results parsing"""
        networks = []
        for line in output.strip().split('\n'):
            parts = line.strip().split(':', 3)
            if len(parts) >= 4 and parts[0]:
                try:
                    networks.append(Network(*parts))
                except ValueError:
                    continue
        return sorted(networks, key=lambda x: x.signal, reverse=True)

    @classmethod
    async def connect(cls, ssid: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Connection handler with retries"""
        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])

        for attempt in range(cls.MAX_RETRIES):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    return True, "Connected successfully"
                elif "Secrets were required" in result.stderr:
                    return False, "Invalid password"
            except subprocess.TimeoutExpired:
                if attempt == cls.MAX_RETRIES - 1:
                    return False, "Connection timed out"
            await asyncio.sleep(cls.RETRY_DELAY)
        return False, "Maximum retries exceeded"

class WiFiConnector(App):
    """Main application class with enhanced state management"""
    BINDINGS = [Binding("q", "quit", "Quit")]
    CSS = """
    #main { width: 100%; height: 100%; }
    .hidden { display: none; }
    #password-container { padding: 1; border: round #666; }
    """

    status = reactive("Initializing...")
    networks = reactive([])
    selected_network = reactive(None, init=False)
    connection_attempts = reactive(0)

    def __init__(self):
        super().__init__()
        self.scanner = NetworkScanner()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            yield DataTable(id="networks-table")
            with Vertical(id="password-container", classes="hidden"):
                yield Label("", id="network-label")
                yield Input(password=True, id="password-input")
                with Horizontal():
                    yield Button("Connect", id="connect-btn")
                    yield Button("Cancel", id="cancel-btn")
            yield Static(id="status")
        yield Footer()

    async def on_mount(self) -> None:
        """Initial setup with proper error handling"""
        self.query_one("#networks-table").add_columns("SSID", "Security", "Signal", "BSSID")
        await self.initialize_services()
        await self.refresh_networks()

    @work(exclusive=True)
    async def initialize_services(self) -> None:
        """Service initialization with status updates"""
        self.status = "Checking NetworkManager..."
        if not await self.scanner.ensure_services():
            self.status = "⚠️ Failed to start NetworkManager"
            return
        self.status = "Ready"

    @work(exclusive=True)
    async def refresh_networks(self) -> None:
        """Network scanning with loading state"""
        self.status = "Scanning networks..."
        try:
            networks = await self.scanner.scan()
            table = self.query_one("#networks-table")
            table.clear()
            for net in networks:
                table.add_row(net.ssid, net.security, net.signal_strength, net.bssid, key=net.ssid)
            self.networks = networks
            self.status = f"Found {len(networks)} networks"
        except Exception as e:
            self.status = f"Scan failed: {str(e)}"

    @on(DataTable.RowSelected)
    def handle_selection(self, event: DataTable.RowSelected) -> None:
        """Handle network selection with validation"""
        if not (row := event.data_table.get_row(event.row_key)):
            return
        try:
            self.selected_network = Network(row[0], row[1], row[3], row[2])
            self.show_password_prompt()
        except ValueError:
            self.status = "Invalid network selection"

    def show_password_prompt(self) -> None:
        """Safe password prompt display"""
        if not self.selected_network:
            return
            
        container = self.query_one("#password-container")
        container.remove_class("hidden")
        self.query_one("#network-label").update(
            f"Password for {self.selected_network.ssid}:"
        )
        self.query_one("#password-input").focus()

    @on(Button.Pressed, "#connect-btn")
    async def handle_connection(self) -> None:
        """Connection handler with state validation"""
        password = self.query_one("#password-input").value
        if not self.selected_network:
            self.status = "No network selected"
            return

        self.status = f"Connecting to {self.selected_network.ssid}..."
        success, message = await self.scanner.connect(
            self.selected_network.ssid, 
            password
        )
        
        if success:
            self.status = f"Connected to {self.selected_network.ssid}!"
            self.exit()
        else:
            self.status = f"Connection failed: {message}"
            self.connection_attempts += 1
            if self.connection_attempts >= 3:
                self.status += " - Reset required"
                self.selected_network = None
                self.connection_attempts = 0

    @on(Button.Pressed, "#cancel-btn")
    def cancel_connection(self) -> None:
        """Cancel handler with state cleanup"""
        self.query_one("#password-container").add_class("hidden")
        self.selected_network = None
        self.status = "Operation cancelled"

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script requires root privileges. Use sudo.")
        sys.exit(1)
    WiFiConnector().run()
