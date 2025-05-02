#!/usr/bin/env python3
import subprocess
import os
import sys
import tempfile
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.progress import track
from rich.traceback import install

# Install rich traceback for detailed error messages
install()

console = Console()


# ------------------------ Network Manager Pre-Check ------------------------
def check_network_manager():
    """
    Check whether NetworkManager is active.
    If it is not, attempt to start it.
    """
    try:
        # Check service status; returns 0 if active.
        subprocess.check_call(['systemctl', 'is-active', '--quiet', 'NetworkManager'])
        console.print("[bold green]NetworkManager is active.[/bold green]")
    except subprocess.CalledProcessError:
        console.print("[bold yellow]NetworkManager is not active. Attempting to start it...[/bold yellow]")
        try:
            subprocess.check_call(['sudo', 'systemctl', 'start', 'NetworkManager'])
            console.print("[bold green]NetworkManager started successfully.[/bold green]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Failed to start NetworkManager: {e}[/bold red]")
            sys.exit(1)


# ------------------------ Internet Connection Functions ------------------------
def list_networks():
    try:
        output = subprocess.check_output(['nmcli', 'device', 'wifi', 'list']).decode('utf-8')
        console.print(Panel.fit(output, title="Available Networks", border_style="blue"))
    except Exception as e:
        console.print(f"[bold red]Error listing networks: {e}[/bold red]")


def connect_to_network(ssid, password):
    try:
        result = subprocess.run(
            ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            console.print(f"[bold green]Successfully connected to '{ssid}'![/bold green]")
            return True
        else:
            console.print(f"[bold red]Failed to connect to '{ssid}'. Error: {result.stderr}[/bold red]")
            return False
    except Exception as e:
        console.print(f"[bold red]Error connecting to network: {e}[/bold red]")
        return False


# ------------------------ Installer Download and Execution ------------------------
def clone_installer_repo(repo_url, destination):
    try:
        console.print("\n[bold blue]Cloning the Mai Bloom installer repository...[/bold blue]")
        
        # Simulate progress for a more engaging experience
        for _ in track(range(10), description="Preparing clone..."):
            pass
        
        subprocess.check_call(['git', 'clone', repo_url, destination])
        console.print("[bold green]Clone completed successfully.[/bold green]\n")
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error cloning the installer repository: {e}[/bold red]")
        return False


def run_installer(installer_script):
    try:
        console.print("[bold blue]Launching the Mai Bloom installation wizard...[/bold blue]")
        subprocess.check_call(['python3', installer_script])
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error while running the main installer: {e}[/bold red]")
        sys.exit(1)


# ------------------------ Main Entrypoint ------------------------
def main():
    console.print(
        Panel.fit("Welcome to the Mai Bloom OS Installer", title="Mai Bloom OS", border_style="magenta")
    )
    
    # Pre-enable and check NetworkManager
    check_network_manager()
    
    # Configure Internet Connection
    list_networks()
    ssid = Prompt.ask("Enter the SSID of the network you wish to connect to")
    password = Prompt.ask("Enter the network password", password=True)
    
    if not connect_to_network(ssid, password):
        console.print("[bold red]Network connection failed. Exiting installer.[/bold red]")
        sys.exit(1)
    
    # Download Mai Bloom Installer
    repo_url = "https://github.com/maibloom/installer"
    temp_dir = tempfile.mkdtemp(prefix="maibloom_installer_")
    if clone_installer_repo(repo_url, temp_dir):
        # Assume the main entry point is "main_installer.py"
        installer_script = os.path.join(temp_dir, 'main_installer.py')
        run_installer(installer_script)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
