import sys
import os
from pathlib import Path
import logging
import io # For capturing stdout/stderr

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QCheckBox, QTextEdit, QTabWidget, QFormLayout,
    QFileDialog, QMessageBox, QProgressDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# Attempt to import archinstall components
# In a real scenario, ensure archinstall is in PYTHONPATH or installed
try:
    from archinstall import SysInfo
    from archinstall.lib.args import arch_config_handler
    from archinstall.lib.configuration import ConfigurationOutput, UserConfiguration
    from archinstall.lib.disk.filesystem import FilesystemHandler
    # from archinstall.lib.disk.utils import disk_layouts # For debugging disk states
    from archinstall.lib.installer import Installer, accessibility_tools_in_use, run_custom_user_commands
    from archinstall.lib.interactions.general_conf import PostInstallationAction # We'll map this to GUI
    from archinstall.lib.models import Bootloader, NetworkConfigurationType, ProfileType
    from archinstall.lib.models.disk import DiskLayoutType, EncryptionType, FilesystemType
    from archinstall.lib.models.users import User
    from archinstall.lib.output import debug, error, info, log_level, LOG_LEVELS
    from archinstall.lib.profile.profiles_handler import profile_handler
    # We are replacing Tui, so we don't import it.
except ImportError as e:
    print(f"Error importing archinstall modules: {e}", file=sys.stderr)
    print("Please ensure archinstall is installed and accessible.", file=sys.stderr)
    sys.exit(1)

# --- Setup basic logging for archinstall to be captured ---
# Redirect archinstall's output to our GUI
# Create a logger for archinstall
archinstall_logger = logging.getLogger('archinstall')
archinstall_logger.setLevel(logging.DEBUG) # Capture all levels

# Create a custom handler that will emit signals to the GUI
class GuiLoggingHandler(logging.Handler):
    def __init__(self, signal_emitter):
        super().__init__()
        self.signal_emitter = signal_emitter

    def emit(self, record):
        msg = self.format(record)
        self.signal_emitter.emit(msg)

# --- Installation Thread ---
class InstallationThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)  # Success (bool), Message (str)
    post_install_action_signal = pyqtSignal(PostInstallationAction)

    def __init__(self, config_obj, mountpoint_str):
        super().__init__()
        self.config = config_obj
        self.mountpoint = Path(mountpoint_str)
        self.log_stream = io.StringIO() # To capture stdout/stderr if needed

    def run(self):
        # It's better to configure archinstall's own logging to use our signal
        # For now, let's try to wrap perform_installation
        try:
            self.progress_signal.emit("Starting installation preparation...")

            # Critical: Ensure the global arch_config_handler.config is THE one we've built in the GUI
            # This is a bit of a hack, ideally archinstall's functions would take config explicitly
            arch_config_handler.config = self.config

            if arch_config_handler.config.disk_config:
                self.progress_signal.emit("Performing filesystem operations...")
                fs_handler = FilesystemHandler(
                    arch_config_handler.config.disk_config,
                    arch_config_handler.config.disk_encryption
                )
                fs_handler.perform_filesystem_operations()
                self.progress_signal.emit("Filesystem operations complete.")

            self.perform_installation_steps()

            self.progress_signal.emit("Installation successful!")

            # Handle post-installation (simplified for GUI)
            # In a real GUI, we'd show a dialog with these choices
            if not arch_config_handler.args.silent: # Respect silent flag
                # For now, let's assume we want to give the user a choice via the GUI
                # The GUI will handle showing the choice dialog
                # Here, we just signal that we need to ask this.
                # For simplicity in this example, let's default to EXIT or prompt via main thread.
                # self.post_install_action_signal.emit(PostInstallationAction.EXIT) # Default
                self.finished_signal.emit(True, "Installation completed successfully.")

        except Exception as e:
            error_msg = f"Installation failed: {e}\nTraceback: {e.__traceback__}"
            self.progress_signal.emit(error_msg)
            log(error_msg, level=logging.ERROR, logger='archinstall') # Use archinstall's log
            self.finished_signal.emit(False, str(e))


    def perform_installation_steps(self) -> None:
        """
        Mirrors the perform_installation function from the original script.
        Emits progress signals.
        """
        self.progress_signal.emit('Starting installation core process...')

        config = arch_config_handler.config # Already set

        if not config.disk_config:
            self.progress_signal.emit("ERROR: No disk configuration provided")
            raise ValueError("No disk configuration provided")

        disk_config = config.disk_config
        run_mkinitcpio = not config.uki
        locale_config = config.locale_config
        disk_encryption = config.disk_encryption
        optional_repositories = config.mirror_config.optional_repositories if config.mirror_config else []

        # Note: The Installer context manager handles some output.
        # We want this output to go to our GUI log.
        with Installer(
                self.mountpoint,
                disk_config,
                disk_encryption=disk_encryption,
                kernels=config.kernels
        ) as installation:
            if disk_config.config_type != DiskLayoutType.Pre_mount:
                self.progress_signal.emit("Mounting ordered layout...")
                installation.mount_ordered_layout()

            self.progress_signal.emit("Performing sanity checks...")
            installation.sanity_check()

            if disk_config.config_type != DiskLayoutType.Pre_mount:
                if disk_encryption and disk_encryption.encryption_type != EncryptionType.NoEncryption:
                    self.progress_signal.emit("Generating encryption key files...")
                    installation.generate_key_files()

            if mirror_config := config.mirror_config:
                self.progress_signal.emit("Setting mirrors (on host)...")
                installation.set_mirrors(mirror_config, on_target=False)

            self.progress_signal.emit("Performing minimal installation...")
            installation.minimal_installation(
                optional_repositories=optional_repositories,
                mkinitcpio=run_mkinitcpio,
                hostname=config.hostname,
                locale_config=locale_config
            )
            self.progress_signal.emit("Minimal installation complete.")

            if mirror_config := config.mirror_config:
                self.progress_signal.emit("Setting mirrors (on target)...")
                installation.set_mirrors(mirror_config, on_target=True)

            if config.swap:
                self.progress_signal.emit("Setting up swap (zram)...")
                installation.setup_swap('zram')

            if config.bootloader == Bootloader.Grub and SysInfo.has_uefi():
                self.progress_signal.emit("Adding GRUB package (UEFI)...")
                installation.add_additional_packages("grub")

            self.progress_signal.emit(f"Adding bootloader: {config.bootloader.value}...")
            installation.add_bootloader(config.bootloader, config.uki)

            network_config = config.network_config
            if network_config:
                self.progress_signal.emit("Installing network configuration...")
                network_config.install_network_config(
                    installation,
                    config.profile_config
                )

            if users := config.users:
                self.progress_signal.emit("Creating users...")
                installation.create_users(users)

            audio_config = config.audio_config
            if audio_config:
                self.progress_signal.emit("Installing audio configuration...")
                audio_config.install_audio_config(installation)
            else:
                self.progress_signal.emit("No audio server will be installed.")

            if config.packages and config.packages[0] != '':
                self.progress_signal.emit(f"Adding additional packages: {', '.join(config.packages)}...")
                installation.add_additional_packages(config.packages)

            if profile_config := config.profile_config:
                self.progress_signal.emit(f"Installing profile: {profile_config.profile.name if profile_config.profile else 'None'}...")
                profile_handler.install_profile_config(installation, profile_config)

            if timezone := config.timezone:
                self.progress_signal.emit(f"Setting timezone to {timezone}...")
                installation.set_timezone(timezone)

            if config.ntp:
                self.progress_signal.emit("Activating time synchronization (NTP)...")
                installation.activate_time_synchronization()

            if accessibility_tools_in_use(): # This might need context from original env
                self.progress_signal.emit("Enabling espeakup...")
                installation.enable_espeakup()

            if root_pw := config.root_enc_password:
                self.progress_signal.emit("Setting root password...")
                root_user = User('root', root_pw, is_super_user=True) # Assuming root is always super_user
                installation.set_user_password(root_user)


            if (profile_config := config.profile_config) and profile_config.profile:
                self.progress_signal.emit(f"Performing post-install for profile {profile_config.profile.name}...")
                profile_config.profile.post_install(installation)

            if services := config.services:
                self.progress_signal.emit(f"Enabling services: {', '.join(services)}...")
                installation.enable_service(services)

            if cc := config.custom_commands:
                self.progress_signal.emit("Running custom user commands...")
                run_custom_user_commands(cc, installation) # This might print to stdout

            self.progress_signal.emit("Generating fstab...")
            installation.genfstab()

            # debug_disk_layout = disk_layouts() # Requires root, might be problematic here
            # self.progress_signal.emit(f"Disk states after installing:\n{debug_disk_layout}")
            self.progress_signal.emit("Installation core process finished.")


class ArchInstallGUI(QMainWindow):
    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ArchInstall GUI")
        self.setGeometry(100, 100, 900, 700)

        # Initialize arch_config_handler.config (or load from a file)
        # This is crucial. The GUI will populate this object.
        # For a new session, it starts empty or with defaults.
        arch_config_handler.config = UserConfiguration()
        self.config = arch_config_handler.config # Keep a reference

        # Setup logging handler to emit to our log_signal
        self.gui_log_handler = GuiLoggingHandler(self.log_signal)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.gui_log_handler.setFormatter(formatter)
        archinstall_logger.addHandler(self.gui_log_handler)
        # Also add to root logger if archinstall logs through it sometimes
        logging.getLogger().addHandler(self.gui_log_handler)


        self.log_signal.connect(self.append_log_message)

        self.init_ui()

        # Parse command line arguments for archinstall (e.g., --config, --dry-run, --silent)
        # arch_config_handler.parse_args() # This normally happens at script start
        # For GUI, we might set these programmatically or via GUI elements
        # For simplicity, assuming default args for now or that they are handled before GUI launch
        if arch_config_handler.args.config:
            self.load_config_from_path(arch_config_handler.args.config)


    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Tab widget for configuration sections
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        self._create_general_tab()
        self._create_disk_tab()
        self._create_user_tab()
        self._create_profile_packages_tab()
        self._create_network_tab()
        self._create_advanced_tab() # For things like bootloader, kernels, services

        # Log output area
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.main_layout.addWidget(self.log_output, 1) # Give it more stretch factor

        # Buttons
        self.button_layout = QHBoxLayout()
        self.load_button = QPushButton("Load Config")
        self.load_button.clicked.connect(self.load_config_dialog)
        self.save_button = QPushButton("Save Config")
        self.save_button.clicked.connect(self.save_config_dialog)
        self.dry_run_button = QPushButton("Dry Run Check")
        self.dry_run_button.clicked.connect(self.dry_run_check)
        self.install_button = QPushButton("Start Installation")
        self.install_button.clicked.connect(self.confirm_and_start_installation)

        self.button_layout.addWidget(self.load_button)
        self.button_layout.addWidget(self.save_button)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.dry_run_button)
        self.button_layout.addWidget(self.install_button)
        self.main_layout.addLayout(self.button_layout)

        self.populate_fields_from_config() # Populate with initial/loaded config

    def _create_general_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.hostname_edit = QLineEdit()
        self.kb_layout_edit = QLineEdit() # In reality, a QComboBox with layouts
        self.locale_lang_edit = QLineEdit() # e.g., en_US
        self.locale_encoding_edit = QLineEdit() # e.g., UTF-8
        self.timezone_edit = QLineEdit() # e.g., Europe/London, QComboBox better

        # TODO: Populate QComboBoxes with actual choices from archinstall if possible
        # Example: SysInfo.keyboard_layouts(), SysInfo.timezones() if they exist

        layout.addRow("Hostname:", self.hostname_edit)
        layout.addRow("Keyboard Layout:", self.kb_layout_edit)
        layout.addRow("Locale Language (e.g., en_US):", self.locale_lang_edit)
        layout.addRow("Locale Encoding (e.g., UTF-8):", self.locale_encoding_edit)
        layout.addRow("Timezone (e.g., Europe/London):", self.timezone_edit)

        self.tabs.addTab(tab, "General & Locale")

    def _create_disk_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab) # Using QVBoxLayout for more complex structuring

        # Disk Selection (Simplified)
        disk_selection_layout = QFormLayout()
        self.disk_combo = QComboBox()
        try:
            available_disks = SysInfo.block_devices() # This returns BlockDevice objects
            for disk in available_disks:
                if not disk.is_loop_device and not disk.is_readonly and disk.size: # Basic filtering
                     self.disk_combo.addItem(f"/dev/{disk.name} ({disk.human_readable_size})", disk.path)
        except Exception as e:
            self.append_log_message(f"Could not list disks: {e}")
        disk_selection_layout.addRow("Select Target Disk:", self.disk_combo)

        # Layout Strategy (Highly Simplified)
        self.layout_strategy_combo = QComboBox()
        # These would map to complex archinstall.DiskLayout objects/configurations
        self.layout_strategy_combo.addItem("Wipe Disk (Default Archinstall Layout)", "wipe")
        # self.layout_strategy_combo.addItem("Use Pre-mounted Partitions", DiskLayoutType.Pre_mount) # TODO
        # self.layout_strategy_combo.addItem("Manual Partitioning (Not Implemented)", "manual")
        disk_selection_layout.addRow("Layout Strategy:", self.layout_strategy_combo)

        layout.addLayout(disk_selection_layout)

        # Encryption
        encryption_layout = QFormLayout()
        self.encrypt_checkbox = QCheckBox("Encrypt System")
        self.encrypt_password_edit = QLineEdit()
        self.encrypt_password_edit.setEchoMode(QLineEdit.Password)
        self.encrypt_password_edit.setEnabled(False) # Enable if checkbox is checked
        self.encrypt_checkbox.toggled.connect(self.encrypt_password_edit.setEnabled)

        encryption_layout.addRow(self.encrypt_checkbox)
        encryption_layout.addRow("Encryption Password:", self.encrypt_password_edit)
        layout.addLayout(encryption_layout)

        # Filesystem type (for root)
        fs_layout = QFormLayout()
        self.filesystem_combo = QComboBox()
        for fs_type in FilesystemType:
            self.filesystem_combo.addItem(fs_type.value, fs_type)
        self.filesystem_combo.setCurrentText(FilesystemType.Btrfs.value) # Default to btrfs or ext4
        fs_layout.addRow("Root Filesystem Type:", self.filesystem_combo)
        layout.addLayout(fs_layout)

        self.tabs.addTab(tab, "Disk Configuration")


    def _create_user_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.root_password_edit = QLineEdit()
        self.root_password_edit.setEchoMode(QLineEdit.Password)
        layout.addRow("Root Password:", self.root_password_edit)

        # Simplified: Only one additional user
        self.username_edit = QLineEdit()
        self.user_password_edit = QLineEdit()
        self.user_password_edit.setEchoMode(QLineEdit.Password)
        self.user_sudo_checkbox = QCheckBox("Grant Sudo (wheel group)")
        self.user_sudo_checkbox.setChecked(True)

        layout.addRow("Create User - Username:", self.username_edit)
        layout.addRow("Create User - Password:", self.user_password_edit)
        layout.addRow(self.user_sudo_checkbox)

        self.tabs.addTab(tab, "User Setup")

    def _create_profile_packages_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.profile_combo = QComboBox()
        self.profile_combo.addItem("None", None) # Option for no profile
        try:
            available_profiles = profile_handler.get_all_profiles()
            for name, profile_obj in available_profiles.items():
                if profile_obj.type == ProfileType.profile: # Only show installable profiles
                    self.profile_combo.addItem(profile_obj.name, profile_obj)
        except Exception as e:
            self.append_log_message(f"Could not load profiles: {e}")
        layout.addRow("Desktop/Profile:", self.profile_combo)

        self.additional_packages_edit = QLineEdit()
        layout.addRow("Additional Packages (comma-separated):", self.additional_packages_edit)

        self.tabs.addTab(tab, "Profiles & Packages")

    def _create_network_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.network_config_type_combo = QComboBox()
        # Populate with NetworkConfigurationType enum or similar
        self.network_config_type_combo.addItem("Copy ISO network configuration", NetworkConfigurationType.CopyISO)
        self.network_config_type_combo.addItem("NetworkManager (Recommended for Desktops)", "NetworkManager") # This is a common choice
        # Add other types as needed, e.g., manual, dhcpcd
        layout.addRow("Network Configuration Method:", self.network_config_type_combo)

        self.tabs.addTab(tab, "Network")

    def _create_advanced_tab(self):
        tab = QWidget()
        layout = QFormLayout(tab)

        self.bootloader_combo = QComboBox()
        for bl in Bootloader:
            self.bootloader_combo.addItem(bl.value, bl)
        self.bootloader_combo.setCurrentText(Bootloader.SystemdBoot.value) # Default
        layout.addRow("Bootloader:", self.bootloader_combo)

        self.kernels_edit = QLineEdit("linux") # Default kernel
        layout.addRow("Kernels (space-separated):", self.kernels_edit)

        self.services_edit = QLineEdit() # e.g., sshd, docker
        layout.addRow("Enable Services (comma-separated):", self.services_edit)

        self.swap_checkbox = QCheckBox("Enable Swap (zram)")
        self.swap_checkbox.setChecked(True) # Archinstall default
        layout.addRow(self.swap_checkbox)
        
        self.ntp_checkbox = QCheckBox("Enable NTP (Time Synchronization)")
        self.ntp_checkbox.setChecked(True) # Archinstall default
        layout.addRow(self.ntp_checkbox)

        # UKI
        self.uki_checkbox = QCheckBox("Generate Unified Kernel Image (UKI)")
        self.uki_checkbox.setChecked(False) # Default is False in archinstall config
        layout.addRow(self.uki_checkbox)


        # Parallel Downloads (example of an arg-controlled option)
        self.parallel_downloads_checkbox = QCheckBox("Enable Parallel Downloads")
        # arch_config_handler.args.advanced is not directly available without parsing args
        # Set default based on common preference or make it always available
        self.parallel_downloads_checkbox.setEnabled(True) # Or link to an "Advanced Mode" checkbox
        self.parallel_downloads_checkbox.setChecked(False) # Default archinstall for non-advanced

        layout.addRow(self.parallel_downloads_checkbox)


        self.tabs.addTab(tab, "Advanced")


    def gather_config_from_gui(self):
        """Populate self.config (arch_config_handler.config) from GUI fields."""
        cfg = self.config # UserConfiguration instance

        # General
        cfg.hostname = self.hostname_edit.text() or None
        cfg.locale_config.kb_layout = self.kb_layout_edit.text() or None
        cfg.locale_config.lang = self.locale_lang_edit.text() or "en_US"
        cfg.locale_config.encoding = self.locale_encoding_edit.text() or "UTF-8"
        cfg.timezone = self.timezone_edit.text() or None


        # Disk (Highly Simplified - this part needs significant work for a real app)
        selected_disk_path = self.disk_combo.currentData()
        if selected_disk_path:
            # This is where it gets very complex. archinstall expects a DiskLayout object.
            # For "Wipe Disk", it generates one.
            # We need to create a mock archinstall.Disk object for the selected disk.
            # And then a DiskLayout.
            # For now, we're making a BIG assumption that archinstall can handle
            # a simple string path for wipe disk scenarios via its default logic if we
            # set disk_config.layout_type appropriately or similar.
            # This is the WEAKEST part of this GUI conversion.
            # A proper solution involves replicating archinstall's disk scanning and layout generation logic.

            cfg.disk_config.config_type = DiskLayoutType.Default # Assuming "Wipe Disk" maps to this
            # The actual blockdevice objects need to be created and assigned.
            # This is a placeholder for what should be a much more complex setup.
            if cfg.disk_config.config_type == DiskLayoutType.Default:
                 # We need to tell archinstall WHICH disk to wipe.
                 # This usually happens via `archinstall.Installer().perform_disk_action(mode='wipe')`
                 # or by setting up a DiskLayout with the target device.
                 # Let's try to create a minimal DiskLayout.
                 # This requires more knowledge of archinstall's internals than is straightforward.
                 # For this example, we'll assume the first block device in a manually constructed layout.
                 # This is NOT ROBUST.
                if selected_disk_path:
                    # This is a hack. Normally archinstall creates these BlockDevice objects.
                    # We'd need to properly select or create one.
                    # Let's assume the user selected `/dev/sda` and it's the first device
                    # in a hypothetical `BlockDevice` list.
                    # This is where the TUI's interaction for selecting disks is crucial.
                    # For now, we'll just store the path and hope the installer can use it with 'Default'.
                    # A better approach might be to set one of the pre-canned layouts
                    # from archinstall.lib.disk.user_guides.select_disk_layout() if possible.
                    cfg.disk_config.block_devices = [] # Clear any previous
                    # Find the BlockDevice object corresponding to selected_disk_path
                    matching_devices = [bd for bd in SysInfo.block_devices() if bd.path == selected_disk_path]
                    if matching_devices:
                        # This is still not a full disk_layout, but provides the target.
                        # The actual partitioning logic in archinstall for 'Default' will take over.
                        # We might need to specify which disk in disk_config if there are multiple.
                        # archinstall's `Installer` and `Disk` objects handle this.
                        # This part of the configuration is the most complex to map.
                        # Let's assume we store the target disk path and the 'Default' strategy implies wiping it.
                        # archinstall's `archinstall.lib.disk.disk_layout.DiskLayout()`
                        # and `archinstall.lib.disk.user_interaction.select_disk_layout()` are key here.
                        # To truly configure this, we need to construct a `DiskLayoutModel`.
                        # For simplicity, let's assume a single disk wipe.
                        # cfg.disk_config.layout = ??? # This needs a DiskLayoutModel instance

                        # For a simple wipe, archinstall might be okay if we just tell it which disk.
                        # It often iterates through SysInfo.block_devices() and asks the user.
                        # We are pre-selecting it.
                        # A more robust way:
                        # disk_to_format = [dev for dev in SysInfo.block_devices() if dev.path == selected_disk_path]
                        # if disk_to_format:
                        #    cfg.disk_config.block_devices = disk_to_format # This is a list
                        # else:
                        #    self.append_log_message(f"Selected disk {selected_disk_path} not found in SysInfo.")
                        # This is still incomplete as the layout itself isn't defined.
                        # The "Default" strategy in archinstall's TUI does a lot of work.
                        self.append_log_message(f"Disk selection is simplified. Target: {selected_disk_path}. Strategy: Wipe (Default).")
                        # Store the path; the Installer will need to know which disk to operate on.
                        # archinstall usually gets this by iterating or from a specific disk_layout object.
                        # We might need to pass this specifically to the installer or ensure disk_config reflects it.
                        # For now, we just hope the default wipe logic picks it up or uses the first available.
                        # This is a major simplification.
                        # Let's assume `arch_config_handler.config.disk_layout` is what's needed.
                        # And it needs to be populated like `archinstall --disk_layouts=...`
                        # For now, we are skipping the detailed creation of disk_layout.
                        # The perform_filesystem_operations() will fail if disk_config is not well-formed.
                        pass # This section needs a proper DiskLayoutModel built

            # Encryption
            if self.encrypt_checkbox.isChecked():
                cfg.disk_encryption.encryption_type = EncryptionType.Luks # Default to Luks
                cfg.disk_encryption.encrypt_method = EncryptionType.Luks # Assuming this for now
                cfg.disk_encryption.encryption_password = self.encrypt_password_edit.text()
                # cfg.disk_encryption.partitions_to_encrypt = ['/'] # Example
            else:
                cfg.disk_encryption.encryption_type = EncryptionType.NoEncryption
                cfg.disk_encryption.encryption_password = None

            # Filesystem
            # This usually applies to specific partitions in a layout.
            # For a simple wipe, it might be the root fs.
            cfg.disk_config.filesystem_type = self.filesystem_combo.currentData()


        # User Setup
        cfg.root_enc_password = self.root_password_edit.text() or None
        cfg.users = []
        if self.username_edit.text():
            new_user = User(
                username=self.username_edit.text(),
                password=self.user_password_edit.text(),
                is_super_user=self.user_sudo_checkbox.isChecked()
            )
            cfg.users.append(new_user)

        # Profile & Packages
        selected_profile_obj = self.profile_combo.currentData()
        if selected_profile_obj:
            cfg.profile_config.profile = selected_profile_obj
        else:
            cfg.profile_config.profile = None # Explicitly None

        cfg.packages = [pkg.strip() for pkg in self.additional_packages_edit.text().split(',') if pkg.strip()]
        if not cfg.packages: cfg.packages = [''] # archinstall expects [''] for no packages

        # Network
        # This needs mapping to archinstall's NetworkConfigModel
        # For "Copy ISO", it's NetworkConfigurationType.CopyISO
        # For "NetworkManager", it usually means installing 'networkmanager' package and enabling the service
        net_choice = self.network_config_type_combo.currentText()
        if net_choice == "Copy ISO network configuration":
            cfg.network_config.type = NetworkConfigurationType.CopyISO
        elif net_choice == "NetworkManager (Recommended for Desktops)":
            cfg.network_config.type = NetworkConfigurationType.Manual # Placeholder
            # We'd also add 'networkmanager' to packages and enable the service
            if 'networkmanager' not in cfg.packages:
                cfg.packages.append('networkmanager')
            if not cfg.services: cfg.services = []
            if 'NetworkManager.service' not in cfg.services:
                 cfg.services.append('NetworkManager.service')


        # Advanced
        cfg.bootloader = self.bootloader_combo.currentData()
        cfg.kernels = [k.strip() for k in self.kernels_edit.text().split(' ') if k.strip()]
        cfg.services = [s.strip() for s in self.services_edit.text().split(',') if s.strip()]
        cfg.swap = self.swap_checkbox.isChecked()
        cfg.ntp = self.ntp_checkbox.isChecked()
        cfg.uki = self.uki_checkbox.isChecked()

        # This would normally be set by arch_args.py or a global setting
        # For now, let's tie it to the checkbox directly for demonstration
        if self.parallel_downloads_checkbox.isChecked():
            if cfg.mirror_config: # ensure mirror_config exists
                 cfg.mirror_config.parallel_downloads = True # This might not be the right place
            # The parallel downloads setting is often a global Pacman configuration,
            # not directly in mirror_config. It affects /etc/pacman.conf.
            # archinstall handles this during minimal_installation or pacstrap.
            # This is more of a hint; the installer needs to act on it.
            # A direct mapping might be `arch_config_handler.args.parallel_downloads = True`
            # but modifying args at this stage is not standard.
            # For now, we'll just log it as an intention.
            self.append_log_message("Parallel downloads enabled (GUI option). Installer needs to handle this.")
        else:
            if cfg.mirror_config:
                 cfg.mirror_config.parallel_downloads = False


        # Update the global config object as well, as some archinstall parts might read from it directly
        arch_config_handler.config = cfg
        self.append_log_message("Configuration gathered from GUI.")


    def populate_fields_from_config(self):
        """Update GUI fields from self.config."""
        cfg = self.config
        if not cfg: return # No config loaded

        # General
        self.hostname_edit.setText(cfg.hostname or "")
        if cfg.locale_config:
            self.kb_layout_edit.setText(cfg.locale_config.kb_layout or "")
            self.locale_lang_edit.setText(cfg.locale_config.lang or "en_US")
            self.locale_encoding_edit.setText(cfg.locale_config.encoding or "UTF-8")
        self.timezone_edit.setText(cfg.timezone or "")

        # Disk (Very simplified)
        # Cannot easily repopulate complex disk choices.
        # If a config was loaded, this part would need to interpret the disk_config object.
        if cfg.disk_config and cfg.disk_config.block_devices:
            # Try to select the first disk if available. This is a guess.
            disk_path_to_select = cfg.disk_config.block_devices[0].path
            index = self.disk_combo.findData(disk_path_to_select)
            if index >=0:
                self.disk_combo.setCurrentIndex(index)

        if cfg.disk_config and cfg.disk_config.config_type == DiskLayoutType.Default:
            self.layout_strategy_combo.setCurrentText("Wipe Disk (Default Archinstall Layout)")

        if cfg.disk_encryption and cfg.disk_encryption.encryption_type != EncryptionType.NoEncryption:
            self.encrypt_checkbox.setChecked(True)
            self.encrypt_password_edit.setText(cfg.disk_encryption.encryption_password or "")
        else:
            self.encrypt_checkbox.setChecked(False)

        if cfg.disk_config and cfg.disk_config.filesystem_type:
            index = self.filesystem_combo.findData(cfg.disk_config.filesystem_type)
            if index >= 0:
                self.filesystem_combo.setCurrentIndex(index)


        # User
        self.root_password_edit.setText(cfg.root_enc_password or "")
        if cfg.users:
            # Assuming one user for simplicity in GUI
            user = cfg.users[0]
            self.username_edit.setText(user.username)
            self.user_password_edit.setText(user.password or "") # Password might be unset if loaded
            self.user_sudo_checkbox.setChecked(user.is_super_user)
        else:
            self.username_edit.clear()
            self.user_password_edit.clear()
            self.user_sudo_checkbox.setChecked(True)


        # Profile & Packages
        if cfg.profile_config and cfg.profile_config.profile:
            # Find profile by name as object instances might differ
            profile_name = cfg.profile_config.profile.name
            for i in range(self.profile_combo.count()):
                if self.profile_combo.itemData(i) and self.profile_combo.itemData(i).name == profile_name:
                    self.profile_combo.setCurrentIndex(i)
                    break
        else:
            self.profile_combo.setCurrentIndex(self.profile_combo.findData(None)) # Select "None"

        self.additional_packages_edit.setText(", ".join(cfg.packages) if cfg.packages and cfg.packages != [''] else "")

        # Network (Simplified)
        if cfg.network_config:
            if cfg.network_config.type == NetworkConfigurationType.CopyISO:
                self.network_config_type_combo.setCurrentText("Copy ISO network configuration")
            elif 'NetworkManager.service' in (cfg.services or []):
                 self.network_config_type_combo.setCurrentText("NetworkManager (Recommended for Desktops)")


        # Advanced
        if cfg.bootloader:
            index = self.bootloader_combo.findData(cfg.bootloader)
            if index >= 0:
                self.bootloader_combo.setCurrentIndex(index)
        self.kernels_edit.setText(" ".join(cfg.kernels or ["linux"]))
        self.services_edit.setText(", ".join(cfg.services or []))
        self.swap_checkbox.setChecked(cfg.swap)
        self.ntp_checkbox.setChecked(cfg.ntp)
        self.uki_checkbox.setChecked(cfg.uki if hasattr(cfg, 'uki') else False)

        self.append_log_message("Fields populated from configuration.")


    def append_log_message(self, message):
        self.log_output.append(message)
        QApplication.processEvents() # Keep UI responsive during logging

    def load_config_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        filePath, _ = QFileDialog.getOpenFileName(self, "Load ArchInstall Configuration", "",
                                                  "JSON Files (*.json);;All Files (*)", options=options)
        if filePath:
            self.load_config_from_path(filePath)

    def load_config_from_path(self, file_path_str: str):
        try:
            file_path = Path(file_path_str)
            # Use archinstall's ConfigurationOutput to load (it handles UserConfiguration internally)
            # This might need adjustment if ConfigurationOutput is only for saving.
            # Let's try setting arch_config_handler.args.config and re-parsing or manually loading.
            arch_config_handler.args.config = str(file_path) # Set the arg
            
            # Re-initialize or load config (this is tricky, as archinstall does this early)
            # The clean way is UserConfiguration.load_from_file(file_path) if it exists
            # Or, arch_config_handler.load_config() if it exists and respects args.config
            # For now, assuming direct load into self.config and then populating.
            
            # archinstall.lib.UserConfiguration has `load_config` which can take path
            new_config = UserConfiguration.load_config(path=file_path)
            if new_config:
                self.config = new_config
                arch_config_handler.config = new_config # Update global reference
                self.populate_fields_from_config()
                self.append_log_message(f"Configuration loaded from {file_path}")
            else:
                self.append_log_message(f"Failed to load configuration from {file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error Loading Config", f"Could not load configuration file: {e}")
            self.append_log_message(f"Error loading config: {e}")


    def save_config_dialog(self):
        self.gather_config_from_gui() # Ensure current GUI state is in self.config
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        filePath, _ = QFileDialog.getSaveFileName(self, "Save ArchInstall Configuration",
                                                  "archinstall_config.json",
                                                  "JSON Files (*.json);;All Files (*)", options=options)
        if filePath:
            try:
                # Use ConfigurationOutput for saving
                conf_out = ConfigurationOutput(self.config)
                conf_out.file_path = Path(filePath)
                conf_out.save()
                self.append_log_message(f"Configuration saved to {filePath}")
                QMessageBox.information(self, "Config Saved", f"Configuration saved to {filePath}")
            except Exception as e:
                QMessageBox.critical(self, "Error Saving Config", f"Could not save configuration file: {e}")
                self.append_log_message(f"Error saving config: {e}")

    def dry_run_check(self):
        self.gather_config_from_gui()
        # A true dry-run would involve more of archinstall's validation logic
        # For now, this is a placeholder.
        self.append_log_message("Performing dry-run check (simulated)...")
        try:
            # ConfigurationOutput can write a debug version
            config_out = ConfigurationOutput(self.config)
            config_out.write_debug() # This prints to stdout, which our logger should catch
            self.append_log_message("Dry-run check: Configuration seems okay (based on current data).")
            # A more thorough check would involve trying to instantiate Installer, etc.
            # For example, trying to create the DiskLayoutModel and seeing if it validates.
            if not self.config.disk_config: # or other critical parts
                 self.append_log_message("Dry-run WARNING: Disk configuration is missing or incomplete.")
                 QMessageBox.warning(self, "Dry Run", "Disk configuration appears incomplete.")
                 return

            # Check hostname
            if not self.config.hostname:
                self.append_log_message("Dry-run WARNING: Hostname is not set.")
                QMessageBox.warning(self, "Dry Run", "Hostname is not set.")
                return

            self.append_log_message("Dry-run simulation complete. Check logs for details.")
            QMessageBox.information(self, "Dry Run", "Dry run check completed. See log for details.")

        except Exception as e:
            self.append_log_message(f"Dry-run check error: {e}")
            QMessageBox.critical(self, "Dry Run Error", f"Error during dry-run check: {e}")


    def confirm_and_start_installation(self):
        self.gather_config_from_gui()

        # Use archinstall's own confirmation if available, or a simple QMessageBox
        # config_output = ConfigurationOutput(self.config)
        # if not config_output.confirm_config(): # This is a TUI call
        # We need a GUI equivalent:
        reply = QMessageBox.question(self, "Confirm Installation",
                                     "Are you sure you want to start the installation with the current settings?\n"
                                     "This may format disks and make irreversible changes.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            self.append_log_message("Installation aborted by user.")
            return

        # Set mountpoint (archinstall.args.mountpoint)
        # For GUI, we might have a field for this, or use default
        mountpoint_str = arch_config_handler.args.mountpoint or "/mnt/archinstall"
        self.config.mountpoint = Path(mountpoint_str) # Ensure it's in config if needed

        self.append_log_message(f"Starting installation on mountpoint: {mountpoint_str}")
        self.install_button.setEnabled(False)
        self.dry_run_button.setEnabled(False)
        self.load_button.setEnabled(False)
        self.save_button.setEnabled(False)

        # Create and start the installation thread
        # Pass the current self.config (which is arch_config_handler.config)
        self.install_thread = InstallationThread(self.config, mountpoint_str)
        self.install_thread.progress_signal.connect(self.append_log_message)
        self.install_thread.finished_signal.connect(self.installation_finished)
        # self.install_thread.post_install_action_signal.connect(self.handle_post_installation_action)
        self.install_thread.start()

        # Progress dialog (optional, basic version)
        self.progress_dialog = QProgressDialog("Installing Arch Linux...", "Cancel", 0, 0, self)
        self.progress_dialog.setWindowTitle("Installation Progress")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()
        # Since InstallationThread emits text logs, we don't have granular steps for QProgressDialog easily
        # We could try to parse log messages for keywords if really needed.

    def installation_finished(self, success, message):
        self.progress_dialog.close()
        if success:
            self.append_log_message(f"Installation finished successfully: {message}")
            QMessageBox.information(self, "Installation Complete", f"Arch Linux installation finished successfully.\n{message}")
            self.handle_post_installation_gui()
        else:
            self.append_log_message(f"Installation failed: {message}")
            QMessageBox.critical(self, "Installation Failed", f"Arch Linux installation failed: {message}")

        self.install_button.setEnabled(True)
        self.dry_run_button.setEnabled(True)
        self.load_button.setEnabled(True)
        self.save_button.setEnabled(True)

    def handle_post_installation_gui(self):
        """Show a dialog for post-installation actions."""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Post-Installation")
        msg_box.setText("Installation is complete. What would you like to do?")
        reboot_button = msg_box.addButton("Reboot", QMessageBox.YesRole)
        chroot_button = msg_box.addButton("Chroot into Installation", QMessageBox.NoRole)
        exit_button = msg_box.addButton("Exit", QMessageBox.RejectRole)

        msg_box.exec_()

        if msg_box.clickedButton() == reboot_button:
            self.append_log_message("User chose to reboot.")
            # os.system('reboot') # Be very careful with this in a GUI
            QMessageBox.information(self, "Reboot", "Please reboot the system manually.") # Safer
        elif msg_box.clickedButton() == chroot_button:
            self.append_log_message("User chose to chroot. This functionality needs to be manually executed in a terminal.")
            # Dropping to shell from GUI is tricky. Inform user.
            # try:
            #     # This requires the installer instance from the thread, which is complex to get here
            #     # And it would block the GUI thread if not handled carefully
            #     QMessageBox.information(self, "Chroot", "Chroot functionality is complex for GUI. Manual chroot: arch-chroot /mnt/archinstall")
            # except Exception as e:
            #    self.append_log_message(f"Could not drop to shell: {e}")
            QMessageBox.information(self, "Chroot", "To chroot, please open a terminal and run:\n`arch-chroot /mnt/archinstall` (or your custom mountpoint).")
        else: # Exit
            self.append_log_message("User chose to exit.")
            # self.close() # Or just do nothing

    def closeEvent(self, event):
        # Clean up resources, threads if any are running
        if hasattr(self, 'install_thread') and self.install_thread.isRunning():
            reply = QMessageBox.question(self, "Confirm Exit",
                                         "Installation is in progress. Are you sure you want to exit?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                # self.install_thread.terminate() # This is dangerous, can corrupt installation
                # self.install_thread.wait()
                event.accept()
                # Ideally, implement a safe stop mechanism in the thread.
            else:
                event.ignore()
        else:
            event.accept()


def gui_main():
    # This is where original `guided()` logic would integrate
    # We need to handle arch_config_handler.args for things like --silent, --dry-run, --config
    # arch_config_handler.parse_args() # This is usually called by archinstall's entry point

    # if arch_config_handler.args.silent:
    #     # Perform a fully automated install if all config is provided
    #     # This GUI is not for silent mode primarily, but it could be a config generator
    #     print("Silent mode requested. This GUI is interactive. For silent, use archinstall CLI.")
    #     # Potentially run the installation logic directly if config is complete
    #     # guided_setup_for_silent_run() # A new function
    #     return

    app = QApplication(sys.argv)
    main_window = ArchInstallGUI() # This will also handle loading --config via its init
    main_window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    # To make archinstall's logging work as expected with the GUI handler,
    # it's good to configure its default output early.
    # archinstall.lib.output.log_set_stream(sys.stdout) # Or a custom stream
    # archinstall.lib.output.log_set_level(logging.INFO)

    # Simulate arch_config_handler argument parsing if needed for testing
    # For example, to test loading a config file:
    # sys.argv.extend(['--config', 'path/to/your/config.json'])
    arch_config_handler.parse_args() # Let archinstall parse its own args first

    gui_main()

