import streamlit as st
import subprocess
import os
import json

# Function to run shell commands
def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout
    else:
        st.error(result.stderr)
        return None

# Function to get disk information
def get_disk_info(disk):
    command = f"lsblk -bno NAME,SIZE,MOUNTPOINT {disk}"
    output = run_command(command)
    if output:
        lines = output.strip().split('\n')
        if len(lines) > 1:
            size = lines[1].split()[1]
            return int(size) / (1024 ** 3)  # Convert bytes to GiB
    return 0

# Function to run archinstall commands
def run_archinstall_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        st.success(result.stdout)
    else:
        st.error(result.stderr)

# Load archinstall configuration options
def load_archinstall_config():
    # Placeholder for loading actual archinstall configuration options
    # In a real scenario, this would fetch options from archinstall's API or config files
    return {
        "disks": ["/dev/sda", "/dev/nvme0n1", "/dev/mmcblk0"],
        "filesystems": ["ext4", "btrfs", "xfs", "f2fs"],
        "package_categories": {
            "Base System": ["base", "linux", "linux-firmware"],
            "Development": ["base-devel", "git"],
            "Multimedia": ["ffmpeg", "vlc", "gst-plugins-good"],
            "Utilities": ["htop", "neofetch", "curl"]
        },
        "desktop_environments": ["plasma", "gnome", "xfce4"]
    }

config = load_archinstall_config()

# Set the title of the web page
st.title("Mai Bloom Installer")

# Introduction section
st.markdown("""
    Welcome to the Mai Bloom Installer! This guided installer will help you set up Mai Bloom,
    a custom Arch Linux-based distribution, with ease. Follow the steps below to configure
    and install Mai Bloom on your system.
""")

# Step 1: Disk Partitioning
st.header("Step 1: Disk Partitioning")
st.markdown("Select the disk where Mai Bloom will be installed. The available space on the disk will be displayed.")
selected_disk = st.selectbox("Select the installation disk:", config["disks"])

if selected_disk:
    disk_size = get_disk_info(selected_disk)
    st.write(f"Available space on {selected_disk}: {disk_size:.2f} GiB")

use_swap = st.checkbox("Create a swap partition", value=True)
partition_scheme = st.radio("Choose a partitioning scheme:", ("Automatic (Recommended)", "Manual"))

if partition_scheme == "Manual":
    st.markdown("""
        **Manual Partitioning:**
        - Use a tool like `cfdisk` or `gparted` to manually partition your disk.
        - Ensure you create at least one root (`/`) partition.
    """)

# Step 2: Filesystem Selection
st.header("Step 2: Filesystem Selection")
st.markdown("Choose the filesystem for the root partition. Ext4 is recommended for most users.")
selected_filesystem = st.selectbox("Select the filesystem for the root partition:", config["filesystems"])

# Step 3: Package Selection by Category
st.header("Step 3: Package Selection")
st.markdown("Select categories of packages to install. Each category contains a set of related packages.")
selected_categories = st.multiselect("Select package categories:", config["package_categories"].keys())
selected_packages = [pkg for category in selected_categories for pkg in config["package_categories"][category]]

# Step 4: Desktop Environment Selection
st.header("Step 4: Desktop Environment Selection")
st.markdown("Choose one or more desktop environments to install. You can select multiple options.")
selected_desktops = st.multiselect("Select desktop environments:", config["desktop_environments"])

# Step 5: User Configuration
st.header("Step 5: User Configuration")
st.markdown("Set up the user account for your Mai Bloom installation.")
username = st.text_input("Enter your username:")
password = st.text_input("Enter your password:", type="password")

# Step 6: Custom Script
st.header("Step 6: Custom Script")
st.markdown("Upload a custom bash script to run additional commands during the installation process.")
uploaded_file = st.file_uploader("Upload your custom bash script", type=["sh"])

# Step 7: Installation
st.header("Step 7: Installation")
if st.button("Start Installation"):
    # Prepare the archinstall command
    command = f"archinstall --disk {selected_disk} --filesystem {selected_filesystem} --packages {','.join(selected_packages + selected_desktops)} --username {username} --!password {password}"

    if use_swap:
        command += " --swap"

    if partition_scheme == "Manual":
        command += " --manual-partitioning"

    st.markdown("**Installation in progress...**")

    # Run the archinstall command
    run_archinstall_command(command)

    # Run the custom bash script if uploaded
    if uploaded_file is not None:
        script_path = f"/tmp/{uploaded_file.name}"
        with open(script_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.markdown("**Running custom script...**")
        run_command(f"bash {script_path}")
        os.remove(script_path)

    st.success("Installation completed successfully!")

# Footer
st.markdown("""
    ---
    **Need help?** Check out the [Mai Bloom Documentation](#) or visit our [community forums](#).
""")

