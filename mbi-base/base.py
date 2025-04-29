import curses
import os
import subprocess

def main(stdscr):
    # Clear screen
    stdscr.clear()

    # Initialize curses settings
    curses.curs_set(1)  # Enable cursor
    stdscr.nodelay(0)   # Wait for user input

    # Display welcome message
    stdscr.addstr("Welcome to Mai Bloom Operating System Installer\n", curses.A_BOLD)
    stdscr.addstr("Please follow the instructions to configure your internet settings.\n\n")
    stdscr.refresh()

    # Internet configuration
    stdscr.addstr("Enter your network interface (e.g., eth0, wlan0): ")
    stdscr.refresh()
    network_interface = stdscr.getstr().decode('utf-8')

    stdscr.addstr("Enter your IP address: ")
    stdscr.refresh()
    ip_address = stdscr.getstr().decode('utf-8')

    stdscr.addstr("Enter your gateway: ")
    stdscr.refresh()
    gateway = stdscr.getstr().decode('utf-8')

    stdscr.addstr("Enter your DNS server: ")
    stdscr.refresh()
    dns_server = stdscr.getstr().decode('utf-8')

    # Display configuration summary
    stdscr.addstr("\nConfiguration Summary:\n", curses.A_BOLD)
    stdscr.addstr(f"Network Interface: {network_interface}\n")
    stdscr.addstr(f"IP Address: {ip_address}\n")
    stdscr.addstr(f"Gateway: {gateway}\n")
    stdscr.addstr(f"DNS Server: {dns_server}\n\n")
    stdscr.refresh()

    # Confirm configuration
    stdscr.addstr("Press 'Y' to confirm and proceed with installation, or 'N' to cancel: ")
    stdscr.refresh()
    confirm = stdscr.getch()

    if confirm == ord('Y') or confirm == ord('y'):
        stdscr.addstr("\nProceeding with installation...\n")
        stdscr.refresh()

        # Run the installation bash script
        try:
            subprocess.run(["bash", "install.sh"], check=True)
            stdscr.addstr("Installation completed successfully!\n")
        except subprocess.CalledProcessError as e:
            stdscr.addstr(f"Installation failed: {e}\n")
    else:
        stdscr.addstr("\nInstallation cancelled.\n")

    stdscr.refresh()
    stdscr.getch()

# Run the curses application
curses.wrapper(main)


