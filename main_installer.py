#!/usr/bin/env python3

import urwid
import archinstall
import subprocess
import os
import sys
import shutil
import logging

def get_available_disks():
    """
    Retrieve a list of available disk devices using lsblk.
    Returns a list of disk names prefixed with '/dev/'.
    """
    try:
        # Use lsblk to list disk names (only devices, no partitions)
        result = subprocess.run(["lsblk", "-d", "-n", "-o", "NAME"], capture_output=True, text=True, check=True)
        disks = ["/dev/" + disk.strip() for disk in result.stdout.splitlines() if disk.strip() != '']
        if not disks:
            raise Exception("No disks found.")
        return disks
    except Exception as e:
        logging.error("Failed to retrieve disks: " + str(e))
        # Fallback to a default disk if listing fails
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
            {"mountpoint": "/home", "size": "70%"},  # allocate 70% for home
            {"mountpoint": "swap", "size": "10G"}    # swap partition
        ]
    }
    return partition_scheme

def run_installation(config):
    """
    Run the archinstall process with the provided configuration.
    Updates the status text on the UI with progress messages.
    """
    global status_text, loop
    try:
        installer = archinstall.Installer()
        status_text.set_text("Installation in progress...")
        loop.draw_screen()  # Force an update of the screen
        
        installer.install(config)
        status_text.set_text("Installation completed successfully!")
    except Exception as e:
        status_text.set_text("Installation failed: " + str(e))
        sys.exit(1)

def on_install_pressed(button, user_data):
    """
    Reads input fields, selected disk, and app categories,
    builds the configuration dictionary, and launches the installation.
    """
    config = {}
    # Collect installation parameters from text fields (using defaults if needed)
    config['hostname'] = hostname_edit.get_edit_text().strip() or "archlinux"
    config['locale']   = locale_edit.get_edit_text().strip() or "en_US.UTF-8"
    config['timezone'] = timezone_edit.get_edit_text().strip() or "America/New_York"
    config['user'] = {
        'name':     user_edit.get_edit_text().strip() or "yourusername",
        'password': password_edit.get_edit_text().strip() or "yourpassword",  # Secure password handling is important in production.
        'sudo': True
    }
    
    # Determine the selected disk from the radio buttons.
    selected_disk = None
    for radio in disk_radio_buttons:
        if radio.get_state():
            selected_disk = radio.get_label()
            break
    if not selected_disk:
        selected_disk = "/dev/sda"  # fallback default disk
    
    config['disk_config'] = custom_partitioning(selected_disk)
    
    # Collect app category selections from the checkboxes.
    selected_app_categories = [
        checkbox.get_label() for checkbox in app_category_checkboxes if checkbox.get_state()
    ]
    config['app_categories'] = selected_app_categories

    # Update the status widget with configuration details.
    status_text.set_text(
        "Starting installation with the following settings:\n"
        f"Hostname: {config['hostname']}\n"
        f"Locale: {config['locale']}\n"
        f"Timezone: {config['timezone']}\n"
        f"Username: {config['user']['name']}\n"
        f"Disk: {selected_disk}\n"
        f"App Categories: {', '.join(selected_app_categories) if selected_app_categories else 'None'}\n\n"
        "Note: Additional applications (e.g. various app stores) will be preinstalled by default."
    )
    loop.draw_screen()
    
    run_installation(config)

# -------------------------------
# UI Setup with Urwid
# -------------------------------

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

# Define basic text widgets for the form
welcome_text = urwid.Text("Welcome to the Arch Linux Installer", align='center')
separator = urwid.Divider()

hostname_edit = urwid.Edit(("banner", "Hostname: "), "archlinux")
locale_edit   = urwid.Edit(("banner", "Locale (e.g., en_US.UTF-8): "), "en_US.UTF-8")
timezone_edit = urwid.Edit(("banner", "Timezone (e.g., America/New_York): "), "America/New_York")
user_edit     = urwid.Edit(("banner", "Username: "), "yourusername")
password_edit = urwid.Edit(("banner", "Password: "), "", mask="*")

# Retrieve available disks and set up radio buttons for disk selection.
disks = get_available_disks()
disk_text = urwid.Text("Select Disk:")
disk_radio_buttons = []
radio_group = []
for disk in disks:
    radio_button = urwid.RadioButton(radio_group, disk, state=False)
    disk_radio_buttons.append(radio_button)

# Create a new section for selecting application categories.
app_category_text = urwid.Text("Select Application Categories (choose any that apply):")
app_category_options = ["Education", "Programming", "Gaming", "Daily Use"]
app_category_checkboxes = [urwid.CheckBox(option, state=False) for option in app_category_options]

# Inform the user about preinstalled applications.
preinstall_notice = urwid.Text(
    "Note: In addition to your selected categories, several extra applications "
    "(for example, various app stores) will be preinstalled."
)

# Create the Install button and status widget.
install_button = urwid.Button("Install", on_press=on_install_pressed)
status_text = urwid.Text("", align='left')

# Arrange all widgets into a list.
widgets = [
    welcome_text,
    separator,
    hostname_edit,
    locale_edit,
    timezone_edit,
    separator,
    user_edit,
    password_edit,
    separator,
    disk_text
]
widgets.extend(disk_radio_buttons)
widgets.append(separator)
widgets.append(app_category_text)
widgets.extend(app_category_checkboxes)
widgets.append(preinstall_notice)
widgets.append(separator)
widgets.append(urwid.AttrWrap(install_button, 'buttn', 'buttnf'))
widgets.append(separator)
widgets.append(urwid.Text("Status:"))
widgets.append(status_text)

# Build the UI layout using a Pile inside a Filler.
pile = urwid.Pile(widgets)
filler = urwid.Filler(pile, valign='top')

# Define a palette for enhanced UI colors.
palette = [
    ('banner', 'bold', ''),
    ('buttn', 'black', 'light gray'),
    ('buttnf', 'white', 'dark blue'),
]

# Create and run the main loop.
loop = urwid.MainLoop(filler, palette=palette)
loop.run()
