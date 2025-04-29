#!/usr/bin/env python3
"""
Arch Linux WiFi Connection Tool
A TUI application with mouse support for connecting to WiFi networks
"""

import asyncio
import subprocess
import os
import re
import sys
from typing import List, Dict, Optional, Tuple

# For a custom distro, you'll want to add these dependencies:
# - textual (pip install textual)
# - rich (pip install rich)
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Button, Static, Input, Label, DataTable, Footer, Header
from textual.reactive import reactive
from textual.binding import Binding
from rich.text import Text
from rich.console import Console
from rich.panel import Panel

# Ensure running with appropriate permissions
if os.geteuid() != 0:
    console = Console()
    console.print("[bold red]This script requires root privileges.[/bold red]")
    console.print("Please run with: [bold]sudo python wifi_connect.py[/bold]")
    sys.exit(1)

class Network:
    """Object representing a WiFi network."""
    def __init__(self, ssid: str, security: str, bssid: str, signal: int):
        self.ssid = ssid
        self.security = "Open" if not security else security
        self.bssid = bssid
        self.signal = int(signal) if signal.isdigit() else 0
        
    @property
    def signal_strength(self) -> str:
        """Convert signal strength to bars."""
        if self.signal >= 70:
            return "▮▮▮▮"
        elif self.signal >= 50:
            return "▮▮▮"
        elif self.signal >= 30:
            return "▮▮"
        else:
            return "▮"

class NetworkScanner:
    """Handles WiFi network scanning using NetworkManager."""
    
    @staticmethod
    def ensure_networkmanager() -> bool:
        """Ensure NetworkManager is installed and running."""
        try:
            # Check if installed
            if subprocess.run(["which", "nmcli"], capture_output=True).returncode != 0:
                subprocess.run(["pacman", "-Sy", "--noconfirm", "networkmanager"], check=True)
                
            # Start service if not running
            if subprocess.run(["systemctl", "is-active", "NetworkManager"], 
                              capture_output=True).returncode != 0:
                subprocess.run(["systemctl", "enable", "--now", "NetworkManager"], check=True)
                
            return True
        except subprocess.SubprocessError:
            return False
    
    @staticmethod
    def scan_networks() -> List[Network]:
        """Scan for available WiFi networks."""
        networks = []
        
        # Force a rescan
        subprocess.run(["nmcli", "dev", "wifi", "rescan"], capture_output=True)
        
        # Get networks list
        output = subprocess.run(
            ["nmcli", "-t", "-f", "SSID,SECURITY,BSSID,SIGNAL", "dev", "wifi", "list"],
            capture_output=True, text=True
        ).stdout
        
        for line in output.splitlines():
            if not line.strip():
                continue
                
            parts = line.split(":")
            if len(parts) >= 4:
                ssid, security, bssid, signal = parts[0], parts[1], parts[2], parts[3]
                if ssid:  # Skip empty SSIDs
                    networks.append(Network(ssid, security, bssid, signal))
        
        # Sort by signal strength
        return sorted(networks, key=lambda n: n.signal, reverse=True)
    
    @staticmethod
    def connect_to_network(ssid: str, password: Optional[str] = None) -> Tuple[bool, str]:
        """Connect to a WiFi network."""
        cmd = ["nmcli", "dev", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return True, "Connected successfully"
        else:
            return False, result.stderr or "Unknown error"

class WiFiConnector(App):
    """Main application for WiFi connection."""
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh Networks"),
        Binding("h", "hidden_network", "Hidden Network"),
    ]
    
    CSS = """
    #main {
        width: 100%;
        height: 100%;
        background: #1a1b26;
    }
    
    Header {
        background: #414868;
        color: #c0caf5;
        text-align: center;
        padding: 1;
    }
    
    DataTable {
        width: 100%;
        height: 1fr;
    }
    
    #status {
        height: auto;
        background: #1a1b26;
        padding: 1;
        color: #7aa2f7;
    }
    
    Button {
        margin: 1 2;
    }
    
    #connect-btn {
        background: #7aa2f7;
        color: #1a1b26;
    }
    
    #refresh-btn {
        background: #9ece6a;
        color: #1a1b26;
    }
    
    .password-container {
        height: auto;
        margin: 1;
        background: #24283b;
        padding: 1;
        border: tall #414868;
    }
    
    Input {
        margin: 1 1;
    }
    
    Label {
        margin: 1 1;
    }
    """
    
    status = reactive("Scanning for networks...")
    networks: List[Network] = reactive([])
    selected_network: Optional[Network] = reactive(None)
    
    def __init__(self):
        super().__init__()
        self.scanner = NetworkScanner()
        
    def on_mount(self) -> None:
        """When app is mounted, scan for networks."""
        self.networks_table.focus()
        asyncio.create_task(self.initial_setup())
        
    async def initial_setup(self) -> None:
        """Initialize NetworkManager and perform initial scan."""
        self.status = "Ensuring NetworkManager is running..."
        
        # Run in a separate thread to avoid blocking
        success = await asyncio.to_thread(self.scanner.ensure_networkmanager)
        if not success:
            self.status = "⚠️ Failed to initialize NetworkManager"
            return
            
        await self.refresh_networks()
        
    async def refresh_networks(self) -> None:
        """Scan for networks and update the table."""
        self.status = "Scanning for networks..."
        self.networks_table.clear()
        
        try:
            # Run scan in separate thread to avoid blocking UI
            networks = await asyncio.to_thread(self.scanner.scan_networks)
            
            # Update table with results
            for network in networks:
                self.networks_table.add_row(
                    network.ssid,
                    network.security,
                    network.signal_strength,
                    network.bssid,
                    network
                )
                
            self.networks = networks
            self.status = f"Found {len(networks)} networks"
        except Exception as e:
            self.status = f"Error scanning: {str(e)}"
    
    def action_refresh(self) -> None:
        """Action to refresh networks list."""
        asyncio.create_task(self.refresh_networks())
    
    def action_hidden_network(self) -> None:
        """Show dialog for connecting to hidden network."""
        self.show_password_prompt(hidden=True)
    
    def compose(self) -> ComposeResult:
        """Create UI layout."""
        yield Header(show_clock=True)
        
        with Container(id="main"):
            yield DataTable(id="networks-table")
            
            # Password prompt (initially hidden)
            with Vertical(id="password-container", classes="password-container"):
                yield Label("Enter password:", id="network-label")
                yield Input(id="password-input", password=True)
                
                with Horizontal():
                    yield Button("Connect", id="connect-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn", variant="default")
            
            # Status bar
            yield Static(id="status")
            
            # Bottom buttons
            with Horizontal():
                yield Button("Refresh Networks", id="refresh-btn")
                yield Button("Hidden Network", id="hidden-btn")
                yield Button("Quit", id="quit-btn")
                
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the application."""
        # Set up the networks table
        table = self.query_one("#networks-table", DataTable)
        table.add_columns("SSID", "Security", "Signal", "BSSID")
        
        # Hide password container initially
        self.query_one("#password-container").display = False
        
        # Start network scanning
        asyncio.create_task(self.initial_setup())
    
    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle selection of a network row."""
        row = event.data_table.get_row_at(event.row_key)
        self.selected_network = row[-1]  # The Network object is the last column
        
        if self.selected_network.security.lower() != "open":
            self.show_password_prompt()
        else:
            asyncio.create_task(self.connect_without_password())
    
    async def connect_without_password(self) -> None:
        """Connect to an open network."""
        if not self.selected_network:
            return
            
        self.status = f"Connecting to {self.selected_network.ssid}..."
        success, message = await asyncio.to_thread(
            self.scanner.connect_to_network, 
            self.selected_network.ssid
        )
        
        self.status = message
    
    def show_password_prompt(self, hidden: bool = False) -> None:
        """Show password input dialog."""
        container = self.query_one("#password-container")
        password_input = self.query_one("#password-input", Input)
        network_label = self.query_one("#network-label", Label)
        
        password_input.value = ""
        
        if hidden:
            network_label.update("Hidden Network SSID:")
            password_input.password = False
            self.selected_network = None
        else:
            network_label.update(f"Password for {self.selected_network.ssid}:")
            password_input.password = True
        
        container.display = True
        password_input.focus()
    
    @on(Button.Pressed, "#connect-btn")
    def on_connect_pressed(self) -> None:
        """Handle the Connect button press."""
        password_input = self.query_one("#password-input", Input)
        password = password_input.value
        network_label = self.query_one("#network-label", Label)
        
        # Check if this is for a hidden network
        if self.selected_network is None:
            ssid = password  # For hidden networks, the SSID is in the first input
            self.query_one("#password-container").display = False
            self.show_password_prompt(hidden=False)
            network_label.update(f"Password for {ssid}:")
            self.selected_network = Network(ssid, "Unknown", "unknown", "0")
            return
            
        # Normal network connection
        self.query_one("#password-container").display = False
        asyncio.create_task(self.connect_with_password(password))
    
    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_pressed(self) -> None:
        """Handle the Cancel button press."""
        self.query_one("#password-container").display = False
    
    @on(Button.Pressed, "#refresh-btn")
    def on_refresh_button(self) -> None:
        """Handle refresh button press."""
        self.action_refresh()
    
    @on(Button.Pressed, "#hidden-btn")
    def on_hidden_button(self) -> None:
        """Handle hidden network button press."""
        self.action_hidden_network()
    
    @on(Button.Pressed, "#quit-btn")
    def on_quit_button(self) -> None:
        """Handle quit button press."""
        self.exit()
    
    async def connect_with_password(self, password: str) -> None:
        """Connect to a secured network with password."""
        if not self.selected_network:
            return
            
        self.status = f"Connecting to {self.selected_network.ssid}..."
        success, message = await asyncio.to_thread(
            self.scanner.connect_to_network, 
            self.selected_network.ssid,
            password
        )
        
        self.status = message

if __name__ == "__main__":
    # Initialize app
    app = WiFiConnector()
    app.run()

