#!/usr/bin/env python3
import urwid
import archinstall  # Ensure archinstall is installed in your environment
import subprocess
import os
import sys
import shutil
import logging

# Disable all logging output.
logging.disable(logging.CRITICAL)

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
        disks = ["/dev/" + disk.strip() for disk in result.stdout.splitlines() if disk.strip() != '']
        if not disks:
            raise Exception("No disks found.")
        return disks
    except Exception as e:
        # Logging is disabled; you can handle errors here as needed.
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

def run_installation(config):
    """
    Run the archinstall process with the provided configuration.
    Updates the status text on the UI with progress messages.
    """
    global status_text, loop
    try:
        installer = archinstall.Installer()
        status_text.set_text(('info', "Installation in progress..."))
        loop.draw_screen()  # Force an update of the screen

        installer.install(config)
        status_text.set_text(('success', "Installation completed successfully!"))
    except Exception as e:
        status_text.set_text(('error', "Installation failed: " + str(e)))
        sys.exit(1)

def on_install_pressed(button, user_data):
    """
    Reads input fields, selected disk, and app categories,
    builds the configuration dictionary, and launches the installation.
    """
    config = {}
    config['hostname'] = hostname_edit.get_edit_text().strip() or "archlinux"
    config['locale']   = locale_edit.get_edit_text().strip() or "en_US.UTF-8"
    config['timezone'] = timezone_edit.get_edit_text().strip() or "America/New_York"
    config['user'] = {
        'name':     user_edit.get_edit_text().strip() or "yourusername",
        'password': password_edit.get_edit_text().strip() or "yourpassword",  # Secure handling recommended
        'sudo': True
    }
    
    # Retrieve the selected disk from radio buttons.
    selected_disk = None
    for radio in disk_radio_buttons:
        if radio.get_state():
            selected_disk = radio.get_label()
            break
    if not selected_disk:
        selected_disk = "/dev/sda"  # default fallback
    
    config['disk_config'] = custom_partitioning(selected_disk)
    
    # Gather application category selections.
    selected_app_categories = [
        checkbox.get_label() for checkbox in app_category_checkboxes if checkbox.get_state()
    ]
    config['app_categories'] = selected_app_categories

    # Update status with the selected configuration.
    status_message = (
        "Starting installation with the following settings:\n"
        f"Hostname: {config['hostname']}\n"
        f"Locale: {config['locale']}\n"
        f"Timezone: {config['timezone']}\n"
        f"Username: {config['user']['name']}\n"
        f"Disk: {selected_disk}\n"
        f"App Categories: {', '.join(selected_app_categories) if selected_app_categories else 'None'}\n\n"
        "Note: Additional applications (e.g. app stores) will be preinstalled."
    )
    status_text.set_text(('info', status_message))
    loop.draw_screen()
    run_installation(config)

# -------------------------------
# UI Setup with Urwid
# -------------------------------

# Define color palette for a more vibrant UI.
palette = [
    ('title', 'light green,bold', ''),
    ('banner', 'yellow,bold', ''),
    ('edit', 'light cyan', 'dark gray'),
    ('buttn', 'black', 'light gray'),
    ('buttnf', 'white,bold', 'dark blue'),
    ('info', 'light magenta', ''),
    ('success', 'black', 'dark green'),
    ('error', 'white,bold', 'dark red'),
]

# Title and input fields with styling.
welcome_text = urwid.Text(('title', "Welcome to the Arch Linux Installer"), align='center')
separator = urwid.Divider()

hostname_edit = urwid.AttrWrap(urwid.Edit(("banner", "Hostname: "), "archlinux"), 'edit')
locale_edit   = urwid.AttrWrap(urwid.Edit(("banner", "Locale (e.g., en_US.UTF-8): "), "en_US.UTF-8"), 'edit')
timezone_edit = urwid.AttrWrap(urwid.Edit(("banner", "Timezone (e.g., America/New_York): "), "America/New_York"), 'edit')
user_edit     = urwid.AttrWrap(urwid.Edit(("banner", "Username: "), "yourusername"), 'edit')
password_edit = urwid.AttrWrap(urwid.Edit(("banner", "Password: "), "", mask="*"), 'edit')

# Set up disk selection via radio buttons.
disks = get_available_disks()
disk_text = urwid.Text(('banner', "Select Disk:"))
disk_radio_buttons = []
radio_group = []
for disk in disks:
    radio = urwid.RadioButton(radio_group, disk, state=False)
    disk_radio_buttons.append(radio)

# Create application categories section with checkboxes.
app_category_text = urwid.Text(('banner', "Select Application Categories (choose any that apply):"))
app_category_options = ["Education", "Programming", "Gaming", "Daily Use"]
app_category_checkboxes = [urwid.CheckBox(option, state=False) for option in app_category_options]

# Notice regarding preinstalled apps.
preinstall_notice = urwid.Text(
    ('info',
    "Note: In addition to the selected categories, several extra applications "
    "(e.g. multiple app stores) will be preinstalled."
    )
)

# Create Install button.
install_button = urwid.AttrWrap(urwid.Button("Install", on_press=on_install_pressed), 'buttn', 'buttnf')
status_text = urwid.Text("", align='left')

# Arrange all widgets.
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
widgets.append(install_button)
widgets.append(separator)
widgets.append(urwid.Text(('banner', "Status:")))
widgets.append(status_text)

# Build the UI layout.
pile = urwid.Pile(widgets)
filler = urwid.Filler(pile, valign='top')

# Create and run the main loop.
loop = urwid.MainLoop(filler, palette=palette)
loop.run()
