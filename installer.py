# installer.py
import streamlit as st
import subprocess
import json
import os
from pathlib import Path

# Brand colors
PRIMARY_COLOR = "#FF3C0061"
ACCENT_COLOR = "#FFFF5F15"

# Initialize session state
if 'install_config' not in st.session_state:
    st.session_state.install_config = {
        'disk': None,
        'filesystem': 'btrfs',
        'hostname': 'mai-bloom-pc',
        'username': 'user',
        'password': '',
        'desktop': 'GNOME',
        'selected_categories': [],
        'packages': []
    }

if 'page_index' not in st.session_state:
    st.session_state.page_index = 0

st.set_page_config(
    page_title="Mai Bloom Installer",
    page_icon="🌸",
    layout="wide"
)

# Navigation handlers
def next_page(): st.session_state.page_index += 1
def prev_page(): st.session_state.page_index -= 1

# Custom native app details
NATIVE_APP = {
    "name": "Mai Bloom Center",
    "description": "Exclusive application hub for Mai Bloom",
    "script_path": "/usr/share/mai-bloom/scripts/install-native-app.sh"
}

# Required Mai Bloom packages
BASE_PACKAGES = {
    "Core": ["mai-bloom-base", "mai-bloom-theme", "mai-bloom-utils"],
    "Package Managers": ["yay", "flatpak", "snapd"]
}

# Desktop environment mappings
DESKTOP_ENVIRONMENTS = {
    "GNOME": ["gnome", "gnome-extra"],
    "KDE Plasma": ["plasma", "kde-applications"],
    "XFCE": ["xfce4", "xfce4-goodies"],
    "MATE": ["mate", "mate-extra"],
    "None (Server)": []
}

# Common software categories
SOFTWARE_CATEGORIES = {
    "Office": ["libreoffice-fresh", "thunderbird", "evince"],
    "Gaming": ["steam", "lutris", "wine", "gamemode"],
    "Development": ["code", "git", "python", "base-devel"],
    "Multimedia": ["vlc", "gimp", "kdenlive", "audacity"],
    "Utilities": ["firefox", "file-roller", "gparted", "gnome-disk-utility"]
}

# Get disk list using lsblk
def get_disks():
    try:
        cmd = "lsblk -bpd -o NAME,SIZE,MODEL -J -n -e 1,7,11,252"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        disk_data = json.loads(result.stdout)
        return disk_data['blockdevices']
    except Exception as e:
        st.error(f"Error detecting disks: {str(e)}")
        return []

# Get combined list of all Mai Bloom specific packages
def get_base_packages():
    packages = []
    for category, pkgs in BASE_PACKAGES.items():
        packages.extend(pkgs)
    return packages

# Welcome page
def welcome_page():
    st.title("Welcome to Mai Bloom")
    st.markdown("""
    ## Your Personalized Arch-Based Linux Distribution

    This installer will guide you through setting up your system.
    """)

    st.button("Get Started →", on_click=next_page)

# Disk configuration page
def disk_page():
    st.title("💾 Storage Configuration")
    st.markdown("Select the disk where Mai Bloom will be installed. The disk will be formatted.")

    disks = get_disks()

    if not disks:
        st.error("No storage devices were detected. Please ensure you have a valid drive connected.")
    else:
        disk_options = {}
        for disk in disks:
            size_gb = int(disk['size']) / (1024**3)
            size_text = f"{size_gb:.1f} GB" if size_gb < 1000 else f"{size_gb/1024:.2f} TB"
            name = (disk.get('model') or '').strip() or "Storage Device"
            disk_options[disk['name']] = f"{name} ({size_text})"

        selected_disk = st.selectbox(
            "Select installation disk",
            options=list(disk_options.keys()),
            format_func=lambda x: disk_options[x]
        )

        fs_type = st.radio(
            "Filesystem type",
            ["btrfs", "ext4"],
            horizontal=True
        )

        st.session_state.install_config.update({
            "disk": selected_disk,
            "filesystem": fs_type
        })

    col1, col2 = st.columns(2)
    col2.button("Next →", on_click=next_page, disabled=not disks)

# User configuration page
def user_page():
    st.title("👤 User Configuration")
    st.markdown("Set up your user account and system identity.")

    col1, col2 = st.columns(2)
    with col1:
        hostname = st.text_input(
            "Computer Name",
            st.session_state.install_config['hostname']
        )
    with col2:
        username = st.text_input(
            "Username",
            st.session_state.install_config['username']
        )

    password = st.text_input(
        "Password",
        type="password",
        value=st.session_state.install_config['password']
    )

    st.session_state.install_config.update({
        "hostname": hostname,
        "username": username,
        "password": password
    })

    col1, col2 = st.columns(2)
    col1.button("← Back", on_click=prev_page)
    col2.button("Next →", on_click=next_page)

# Desktop environment selection
def desktop_page():
    st.title("🖥️ Desktop Environment")
    st.markdown("Choose the look and feel of your Mai Bloom system.")

    de_choice = st.radio(
        "Choose your interface:",
        list(DESKTOP_ENVIRONMENTS.keys()),
        horizontal=True
    )

    st.session_state.install_config['desktop'] = de_choice

    col1, col2 = st.columns(2)
    col1.button("← Back", on_click=prev_page)
    col2.button("Next →", on_click=next_page)

# Software selection page
def packages_page():
    st.title("📦 Software Selection")

    # Native App section
    st.subheader("Mai Bloom Exclusive App")
    st.info(f"{NATIVE_APP['name']} - {NATIVE_APP['description']}")
    st.caption("This exclusive app will be installed automatically")

    st.subheader("Select software categories to install:")

    selected_categories = []

    # Create two columns for better layout
    col1, col2 = st.columns(2)

    # Split categories between columns
    categories = list(SOFTWARE_CATEGORIES.keys())
    half = len(categories) // 2 + len(categories) % 2

    # First column
    with col1:
        for category in categories[:half]:
            if st.checkbox(
                category,
                value=category in st.session_state.install_config.get('selected_categories', [])
            ):
                selected_categories.append(category)

    # Second column
    with col2:
        for category in categories[half:]:
            if st.checkbox(
                category,
                value=category in st.session_state.install_config.get('selected_categories', [])
            ):
                selected_categories.append(category)

    st.session_state.install_config['selected_categories'] = selected_categories

    # Flatten selected categories to packages
    package_list = []
    for cat in selected_categories:
        package_list.extend(SOFTWARE_CATEGORIES[cat])

    st.session_state.install_config['packages'] = package_list

    col1, col2 = st.columns(2)
    col1.button("← Back", on_click=prev_page)
    col2.button("Next →", on_click=next_page)

# Final review page
def review_page():
    st.title("🔍 Review Configuration")

    # Show summary
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("System Configuration")
        st.write(f"**Disk:** {st.session_state.install_config['disk']}")
        st.write(f"**Filesystem:** {st.session_state.install_config['filesystem']}")
        st.write(f"**Computer Name:** {st.session_state.install_config['hostname']}")
        st.write(f"**Username:** {st.session_state.install_config['username']}")

    with col2:
        st.subheader("Software Selection")
        st.write(f"**Desktop:** {st.session_state.install_config['desktop']}")
        st.write(f"**Native App:** {NATIVE_APP['name']}")
        st.write("**Categories:**")
        for cat in st.session_state.install_config.get('selected_categories', []):
            st.write(f"- {cat}")

    # Warning and install button
    st.warning("⚠️ This will erase the selected disk and install Mai Bloom.")

    col1, col2 = st.columns(2)
    col1.button("← Back", on_click=prev_page)
    if st.button("🚀 Begin Installation", type="primary"):
        st.session_state.install_in_progress = True
        install_system()

# Installation process
def install_system():
    config = st.session_state.install_config
    progress = st.progress(0)
    status = st.empty()

    try:
        status.markdown("📀 Partitioning disk...")
        progress.progress(10)

        # Prepare package lists
        base_packages = get_base_packages()
        de_packages = DESKTOP_ENVIRONMENTS[config['desktop']]
        user_packages = config['packages']

        # All packages combined
        all_packages = base_packages + de_packages + user_packages

        # Create installation command for archinstall
        install_cmd = f"""
        archinstall \\
          --disk={config['disk']} \\
          --filesystem={config['filesystem']} \\
          --hostname={config['hostname']} \\
          --user={config['username']} \\
          --password={config['password']} \\
          --packages={','.join(all_packages)}
        """

        # Execute archinstall command here in production
        # subprocess.run(install_cmd, shell=True, check=True)

        status.markdown("🖥️ Installing base system...")
        progress.progress(30)

        status.markdown("📦 Installing desktop environment...")
        progress.progress(50)

        # Execute custom script for native app installation
        status.markdown(f"🚀 Installing {NATIVE_APP['name']}...")
        progress.progress(70)

        # Command to execute the custom script
        native_app_cmd = f"""
        # Make script executable
        chmod +x /target{NATIVE_APP['script_path']}

        # Run the script in the chroot environment
        arch-chroot /target {NATIVE_APP['script_path']}
        """

        # Execute native app script here in production
        # subprocess.run(native_app_cmd, shell=True, check=True)

        status.markdown("⚙️ Configuring GRUB with Mai Bloom theme...")
        progress.progress(90)

        # GRUB configuration
        grub_cmd = """
        # Copy Mai Bloom GRUB theme
        cp -r /usr/share/mai-bloom/grub-theme /target/boot/grub/themes/mai-bloom

        # Update GRUB config to use Mai Bloom theme
        arch-chroot /target sed -i 's/^GRUB_THEME=.*/GRUB_THEME="\/boot\/grub\/themes\/mai-bloom\/theme.txt"/' /etc/default/grub

        # Update GRUB
        arch-chroot /target grub-mkconfig -o /boot/grub/grub.cfg
        """

        # Execute GRUB configuration here in production
        # subprocess.run(grub_cmd, shell=True, check=True)

        progress.progress(100)
        status.success("🎉 Installation Complete! You can now reboot into your Mai Bloom system.")

        # Show installation details
        with st.expander("Installation Details"):
            st.subheader("System Installation")
            st.code(install_cmd)

            st.subheader("Native App Installation")
            st.code(native_app_cmd)

            st.subheader("GRUB Theming")
            st.code(grub_cmd)

    except Exception as e:
        status.error(f"❌ Installation failed: {str(e)}")
        progress.empty()

        # Show error details
        with st.expander("Error Details"):
            st.code(str(e))

# Page routing
PAGES = [
    welcome_page,
    disk_page,
    user_page,
    desktop_page,
    packages_page,
    review_page
]

# Apply styling
st.markdown(f"""
<style>
[data-testid="stSidebar"] {{
    background: {PRIMARY_COLOR} !important;
}}

[data-testid="stMarkdown"] h1 {{
    color: {ACCENT_COLOR} !important;
}}

.stButton>button[data-testid="baseButton-primary"] {{
    background: {ACCENT_COLOR} !important;
    color: {PRIMARY_COLOR} !important;
    border: 2px solid {PRIMARY_COLOR} !important;
    font-weight: 600 !important;
}}

.stButton>button {{
    background: {PRIMARY_COLOR} !important;
    color: {ACCENT_COLOR} !important;
    border: 2px solid {ACCENT_COLOR} !important;
}}

.stCheckbox label p {{
    font-weight: 600 !important;
}}
</style>
""", unsafe_allow_html=True)

# Sidebar with navigation
with st.sidebar:
    st.title("Mai Bloom Installer")

    # Progress steps
    st.subheader("Installation Steps")
    steps = ["Welcome", "Disk", "User", "Desktop", "Software", "Review"]
    for i, step in enumerate(steps):
        if i == st.session_state.page_index:
            st.markdown(f"**→ {step}**")
        else:
            st.markdown(f"  {step}")

# Execute current page or show installation
if st.session_state.get('install_in_progress'):
    install_system()
else:
    PAGES[st.session_state.page_index]()

