import subprocess
import sys
import shlex

def run_cmd(cmd):
    """Runs a command and returns its output, printing errors."""
    try:
        print(f"Running: {cmd}")
        process = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=True)
        print(process.stdout)
        return process.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print(f"Error: Command not found (is it installed on the ISO?): {cmd.split()[0]}", file=sys.stderr)
        return None

def check_connection():
    """Checks internet connectivity."""
    print("Checking internet connection...")
    return run_cmd("ping -c 1 archlinux.org") is not None

def setup_network():
    """Guides user through network setup using nmcli."""
    # Ensure NetworkManager is running (might need systemctl commands)
    # run_cmd("systemctl start NetworkManager") # Example

    while True:
        # Simplified logic - ideally use a TUI library or dialog
        choice = input("Configure [W]ired or [Wi]Fi? (or [S]kip if connected): ").lower()

        if choice == 's':
             if check_connection():
                 print("Skipping network setup.")
                 return True
             else:
                 print("Cannot skip, no connection detected.")
                 continue

        if choice == 'w':
            # Often automatic with NM, but could explicitly activate
            print("Attempting to activate wired connection...")
            # Add logic to find wired device if needed
            # run_cmd("nmcli device connect <wired_device_name>") # Example
            if check_connection():
                print("Wired connection established.")
                return True
            else:
                print("Failed to establish wired connection.")

        elif choice == 'wi':
            run_cmd("nmcli device wifi rescan")
            wifi_list_output = run_cmd("nmcli --terse --fields SSID,SECURITY device wifi list")
            if wifi_list_output:
                print("Available Wi-Fi Networks:")
                # Parse and display networks nicely
                print(wifi_list_output) # Simple display for now

            ssid = input("Enter Wi-Fi SSID: ")
            if not ssid: continue

            # Basic check if security is likely needed based on list
            password = input(f"Enter password for {ssid} (leave blank for open): ")

            connect_cmd = f"nmcli device wifi connect {shlex.quote(ssid)}"
            if password:
                connect_cmd += f" password {shlex.quote(password)}"

            run_cmd(connect_cmd)

            if check_connection():
                print("Wi-Fi connection established.")
                return True
            else:
                print("Failed to establish Wi-Fi connection.")
        else:
            print("Invalid choice.")

        retry = input("Connection failed. Try again? [Y/n]: ").lower()
        if retry == 'n':
            return False

# Main execution for file 1
if __name__ == "__main__":
    if setup_network():
        print("Network configured successfully.")
        # Proceed to stage 2 - execute the downloader script
        # Example: run_cmd("python /path/to/file2_downloader.py")
        # Make sure the path is correct within the airootfs
        downloader_script = "/usr/local/bin/mai-bloom-downloader.py" # Example path
        process = subprocess.run([sys.executable, downloader_script], check=False) # Use sys.executable for portability
        if process.returncode != 0:
            print("Failed to run the downloader script.", file=sys.stderr)
            # Maybe provide options to retry or reboot
        else:
             print("Installer download finished (or skipped).") # Or whatever downloader reports
    else:
        print("Network setup failed or was aborted. Cannot continue installation.", file=sys.stderr)
        # Offer to reboot or drop to shell
        sys.exit(1)
