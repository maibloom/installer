#!/usr/bin/env python3
import subprocess
import sys
import os
import shlex # For safely quoting package names

# --- Configuration ---
# Default mount point that archinstall might use for the new system's root.
# The script will ask the user to confirm/change this.
DEFAULT_TARGET_MOUNT_POINT = "/mnt/archinstall" 

# Directory where your custom post-installation bash scripts will be stored
# (relative to this Python script's location)
POST_INSTALL_SCRIPTS_DIR = "post_install_scripts"

# List of extra packages to install for Mai Bloom after archinstall completes
EXTRA_PACKAGES = [
    "neofetch",
    "htop",
    "firefox",
    "vlc",
    # Add more core Mai Bloom packages here
    # For profile-specific packages, you'd expand this logic later
]

# List of your bash script filenames (without the directory path)
# to be run in order from the POST_INSTALL_SCRIPTS_DIR
# These scripts will be run inside the chroot of the newly installed system.
MAI_BLOOM_SCRIPTS = [
    "01_basic_setup.sh",      # Example: basic system tweaks
    "02_desktop_config.sh",   # Example: copy desktop configs
    # Add more of your script names here
]

# --- Helper function to run commands ---
def run_command(command_list, check=True, shell=False, cwd=None, env=None, capture_output=True):
    """Runs a command, prints its output, and returns the process object or raises an exception."""
    log_message = f"Executing: {' '.join(command_list)}"
    if cwd:
        log_message += f" in {cwd}"
    print(log_message)
    
    try:
        process = subprocess.run(command_list, check=check, capture_output=capture_output, text=True, shell=shell, cwd=cwd, env=env)
        if process.stdout:
            print(f"Stdout:\n{process.stdout.strip()}")
        if process.stderr:
            print(f"Stderr:\n{process.stderr.strip()}", file=sys.stderr)
        return process
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {' '.join(e.cmd)}", file=sys.stderr)
        if e.stdout:
            print(f"Stdout: {e.stdout.strip()}", file=sys.stderr)
        if e.stderr:
            print(f"Stderr: {e.stderr.strip()}", file=sys.stderr)
        raise
    except FileNotFoundError:
        print(f"Error: Command '{command_list[0]}' not found.", file=sys.stderr)
        raise

# --- Function to run commands inside chroot ---
def run_in_chroot(mount_point, command_to_run_in_chroot):
    """Runs a command string inside the chrooted environment."""
    chroot_command_list = ["arch-chroot", mount_point, "/bin/bash", "-c", command_to_run_in_chroot]
    return run_command(chroot_command_list)

# --- Main Installation Steps ---
def start_base_installation():
    """Runs the archinstall script."""
    print("="*50)
    print("STEP 1: Base Arch Linux Installation with archinstall")
    print("="*50)
    print("The 'archinstall' guided installer will now start.")
    print("Please follow its prompts to partition your disk, install the base system,")
    print("configure users, bootloader, network, etc.")
    print("\nIMPORTANT: Pay attention to where archinstall mounts your new system's root ( / ) filesystem.")
    print(f"This script will need that path for post-installation tasks. (Often /mnt or /mnt/archinstall)\n")
    
    try:
        # archinstall is interactive and handles its own TUI
        # We just call it and let it run.
        subprocess.run(["archinstall"], check=True) # Let archinstall output directly to terminal
        print("\nArchinstall process completed.")
        return True
    except subprocess.CalledProcessError:
        print("\nArchinstall process failed or was cancelled by the user.", file=sys.stderr)
        return False
    except FileNotFoundError:
        print("\nERROR: `archinstall` command not found.", file=sys.stderr)
        print("Please ensure 'archinstall' is installed on your system (e.g., `sudo pacman -S archinstall`).", file=sys.stderr)
        return False

def perform_mai_bloom_customizations(target_mount_point):
    """
    Performs post-installation tasks on the newly installed system via chroot.
    """
    print("\n" + "="*50)
    print("STEP 2: Mai Bloom OS Customizations & Extras")
    print("="*50)
    print(f"Applying customizations to the system installed at: {target_mount_point}\n")

    if not os.path.isdir(target_mount_point) or not os.path.exists(os.path.join(target_mount_point, 'bin/bash')):
        print(f"ERROR: Target mount point '{target_mount_point}' does not look like a valid Linux root filesystem.", file=sys.stderr)
        print("Please ensure archinstall completed successfully and the mount point is correct.", file=sys.stderr)
        return False

    # 1. Install extra packages defined in EXTRA_PACKAGES
    if EXTRA_PACKAGES:
        print("--- Installing extra Mai Bloom packages ---")
        package_string = " ".join(shlex.quote(pkg) for pkg in EXTRA_PACKAGES)
        try:
            run_in_chroot(target_mount_point, f"pacman -S --noconfirm --needed {package_string}")
            print("Extra packages installed successfully.\n")
        except Exception as e:
            print(f"Failed to install extra packages: {e}\n", file=sys.stderr)
            # Decide if this should be a fatal error for your installer
            # For now, we'll continue to run other scripts if any

    # 2. Run custom Mai Bloom scripts
    if MAI_BLOOM_SCRIPTS:
        print("--- Running Mai Bloom post-installation scripts ---")
        if not os.path.isdir(POST_INSTALL_SCRIPTS_DIR):
            print(f"Warning: Post-installation scripts directory '{POST_INSTALL_SCRIPTS_DIR}' not found. Skipping scripts.", file=sys.stderr)
        else:
            for script_name in MAI_BLOOM_SCRIPTS:
                host_script_path = os.path.join(POST_INSTALL_SCRIPTS_DIR, script_name)
                if not os.path.isfile(host_script_path):
                    print(f"Warning: Script '{host_script_path}' not found. Skipping.", file=sys.stderr)
                    continue

                # Define where the script will be copied inside the chroot
                chroot_tmp_script_path = os.path.join("/tmp", os.path.basename(script_name))
                
                try:
                    print(f"Preparing to run script: {script_name}")
                    # Copy script into chroot's /tmp directory
                    # The target path for cp needs to be relative to the mount point on the host
                    cp_target_path = os.path.join(target_mount_point, chroot_tmp_script_path.lstrip('/'))
                    run_command(["cp", host_script_path, cp_target_path], capture_output=False) # No need to capture output for cp

                    # Make it executable within the chroot
                    run_in_chroot(target_mount_point, f"chmod +x {chroot_tmp_script_path}")
                    
                    # Execute the script within the chroot
                    print(f"Executing '{chroot_tmp_script_path}' inside chroot...")
                    run_in_chroot(target_mount_point, chroot_tmp_script_path)
                    print(f"Script '{script_name}' executed successfully.")

                    # Clean up the script from chroot's /tmp
                    run_in_chroot(target_mount_point, f"rm -f {chroot_tmp_script_path}")
                    print(f"Cleaned up script '{chroot_tmp_script_path}' from target.")

                except Exception as e:
                    print(f"Failed to execute script '{script_name}': {e}\n", file=sys.stderr)
                    # Decide if this should be fatal
                print("-" * 20)
    else:
        print("No Mai Bloom post-installation scripts defined.\n")

    print("Mai Bloom OS customizations finished.")
    return True

# --- Main Execution Logic ---
if __name__ == "__main__":
    if os.geteuid() != 0:
        print("ERROR: This script must be run with root privileges (e.g., using `sudo python script_name.py`).")
        sys.exit(1)

    print("Welcome to the Mai Bloom OS Provisional Installer!")
    print("This script will use 'archinstall' for the base system setup,")
    print("then apply Mai Bloom specific configurations and packages.\n")

    # Get target mount point from user
    target_root = input(f"After 'archinstall' creates and mounts the new system, "
                        f"what will be its root mount point? (Press Enter for default: '{DEFAULT_TARGET_MOUNT_POINT}'): ").strip()
    if not target_root:
        target_root = DEFAULT_TARGET_MOUNT_POINT
    print(f"Will use '{target_root}' as the target system's root mount point for post-installation.\n")

    # Create post_install_scripts directory and an example script if they don't exist
    if not os.path.isdir(POST_INSTALL_SCRIPTS_DIR):
        print(f"Creating directory for post-installation scripts: '{POST_INSTALL_SCRIPTS_DIR}'")
        os.makedirs(POST_INSTALL_SCRIPTS_DIR, exist_ok=True)

    example_script_filename = "01_basic_setup.sh"
    example_script_path = os.path.join(POST_INSTALL_SCRIPTS_DIR, example_script_filename)
    if not os.path.exists(example_script_path) and example_script_filename in MAI_BLOOM_SCRIPTS :
        print(f"Creating an example post-install script: '{example_script_path}'")
        with open(example_script_path, "w") as f:
            f.write("#!/bin/bash\n\n")
            f.write("echo '--- Running Mai Bloom Basic Setup Script ---'\n")
            f.write("echo 'Hello from inside the chroot of your new Mai Bloom OS!'\n")
            f.write("date > /etc/mai_bloom_install_time.txt\n")
            f.write("# Add your custom commands here. For example:\n")
            f.write("# echo 'Setting some default configurations...'\n")
            f.write("# systemctl enable NetworkManager.service\n") # Example
            f.write("echo '--- Basic Setup Script Finished ---'\n")
        os.chmod(example_script_path, 0o755) # Make it executable
        print(f"An example script '{example_script_filename}' has been created.")
        print(f"Please edit it and add any other scripts to the '{POST_INSTALL_SCRIPTS_DIR}' directory and list them in MAI_BLOOM_SCRIPTS in this Python script.")
    print("-" * 20)


    if start_base_installation():
        print("\nBase Arch Linux system installation seems complete.")
        
        # Confirm post-install before proceeding
        proceed_post_install = input("Do you want to proceed with Mai Bloom customizations (extra packages, scripts)? (Y/n): ").strip().lower()
        if proceed_post_install == '' or proceed_post_install == 'y':
            if perform_mai_bloom_customizations(target_root):
                print("\nMAI BLOOM OS INSTALLATION COMPLETE!")
                print("You should now be able to unmount (if needed) and reboot into your new system.")
            else:
                print("\nMai Bloom OS post-installation customizations failed.", file=sys.stderr)
        else:
            print("\nSkipping Mai Bloom customizations as per user choice.")
            print("Base Arch Linux system installed. You can reboot now.")

    else:
        print("\nBase installation with archinstall did not complete. Aborting all further steps.", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)
