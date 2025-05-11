#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import subprocess
import os
import sys
import shlex
import threading
import time

# --- Configuration (Same as your previous CLI script) ---
DEFAULT_TARGET_MOUNT_POINT = "/mnt/archinstall"
POST_INSTALL_SCRIPTS_DIR = "post_install_scripts"
EXTRA_PACKAGES = [
    "neofetch", "htop", "firefox", "vlc",
    # Add more Mai Bloom core packages
]
MAI_BLOOM_SCRIPTS = [
    "01_basic_setup.sh",
    "02_desktop_config.sh",
    # Add your script names here
]

# --- Mai Bloom Installer GUI Application ---
class MaiBloomInstallerApp:
    def __init__(self, root_tk_window):
        self.root = root_tk_window
        self.root.title("Mai Bloom OS Installer")
        self.root.geometry("750x550") # Adjusted size

        # --- Variables ---
        self.target_mount_point_var = tk.StringVar(value=DEFAULT_TARGET_MOUNT_POINT)
        self.archinstall_process = None

        # --- GUI Layout ---
        # Top instruction
        instruction_label = tk.Label(self.root, text="Welcome to the Mai Bloom OS Installer!", font=("Arial", 16))
        instruction_label.pack(pady=10)

        # Frame for Step 1: Archinstall
        step1_frame = ttk.LabelFrame(self.root, text="Step 1: Base Arch Linux Installation", padding=10)
        step1_frame.pack(padx=10, pady=10, fill="x")

        archinstall_intro_label = tk.Label(step1_frame, 
                                           text="Click below to launch 'archinstall' in a new terminal window.\n"
                                                "Follow its instructions to install the base Arch Linux system.\n"
                                                "Note the root (/) mount point it uses for the new system.",
                                           justify=tk.LEFT)
        archinstall_intro_label.pack(pady=5, anchor="w")

        self.launch_archinstall_button = ttk.Button(step1_frame, text="Launch Archinstall", command=self.launch_archinstall_thread)
        self.launch_archinstall_button.pack(pady=10)

        mount_point_frame = ttk.Frame(step1_frame)
        mount_point_frame.pack(fill="x", pady=5)
        ttk.Label(mount_point_frame, text="Target Mount Point (used by archinstall):").pack(side=tk.LEFT, padx=5)
        mount_point_entry = ttk.Entry(mount_point_frame, textvariable=self.target_mount_point_var, width=40)
        mount_point_entry.pack(side=tk.LEFT, fill="x", expand=True)


        # Frame for Step 2: Mai Bloom Customizations
        step2_frame = ttk.LabelFrame(self.root, text="Step 2: Apply Mai Bloom Customizations", padding=10)
        step2_frame.pack(padx=10, pady=10, fill="x")
        
        postinstall_intro_label = tk.Label(step2_frame, 
                                           text="After 'archinstall' is completely finished and you have exited it,\n"
                                                "verify the Target Mount Point above and click below to apply customizations.",
                                           justify=tk.LEFT)
        postinstall_intro_label.pack(pady=5, anchor="w")

        self.run_postinstall_button = ttk.Button(step2_frame, text="Run Mai Bloom Post-Install", command=self.run_postinstall_thread, state=tk.DISABLED)
        self.run_postinstall_button.pack(pady=10)

        # Log/Status Area
        log_frame = ttk.LabelFrame(self.root, text="Installer Log", padding=10)
        log_frame.pack(padx=10, pady=10, fill="both", expand=True)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, width=80, state=tk.DISABLED, wrap=tk.WORD)
        self.log_area.pack(fill="both", expand=True)

        self.add_log("Mai Bloom Installer Ready.")
        self.add_log(f"Please ensure you are running this installer with root privileges (sudo).")
        self.add_log(f"Post-install scripts will be sourced from: ./{POST_INSTALL_SCRIPTS_DIR}/")
        self.prepare_example_scripts()


    def add_log(self, message, error=False):
        self.log_area.config(state=tk.NORMAL)
        prefix = "[ERROR] " if error else "[INFO] "
        self.log_area.insert(tk.END, f"{prefix}{message}\n")
        self.log_area.see(tk.END) # Scroll to the end
        self.log_area.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def prepare_example_scripts(self):
        if not os.path.isdir(POST_INSTALL_SCRIPTS_DIR):
            self.add_log(f"Creating directory for post-installation scripts: '{POST_INSTALL_SCRIPTS_DIR}'")
            os.makedirs(POST_INSTALL_SCRIPTS_DIR, exist_ok=True)

        for script_name in MAI_BLOOM_SCRIPTS:
            example_script_path = os.path.join(POST_INSTALL_SCRIPTS_DIR, script_name)
            if not os.path.exists(example_script_path) :
                self.add_log(f"Creating an example post-install script: '{example_script_path}'")
                with open(example_script_path, "w") as f:
                    f.write("#!/bin/bash\n\n")
                    f.write(f"echo '--- Running Mai Bloom Script: {script_name} ---'\n")
                    f.write("echo 'Hello from inside the chroot of your new Mai Bloom OS!'\n")
                    f.write("# Add your custom commands for this script here.\n")
                    f.write(f"echo '--- {script_name} Finished ---'\n")
                os.chmod(example_script_path, 0o755)
                self.add_log(f"Please edit '{example_script_path}' with your desired commands.")

    def launch_archinstall_thread(self):
        self.launch_archinstall_button.config(state=tk.DISABLED)
        self.add_log("Preparing to launch archinstall...")
        threading.Thread(target=self._execute_archinstall, daemon=True).start()

    def _execute_archinstall(self):
        self.add_log("Archinstall will launch in a new terminal window.")
        self.add_log("Follow the on-screen instructions in that new terminal.")
        self.add_log(f"Key information: Target system mount point is expected to be '{self.target_mount_point_var.get()}'. "
                     "Confirm or change this in the GUI if archinstall uses a different one.")
        self.add_log("After archinstall finishes and you close its terminal, click the 'Run Mai Bloom Post-Install' button here.")

        terminal_commands_to_try = [
            ["gnome-terminal", "--", "sudo", "archinstall"],
            ["konsole", "-e", "sudo archinstall"], # Konsole -e often takes the whole command as one arg
            ["xfce4-terminal", "-e", "sudo archinstall"],
            ["xterm", "-e", "sudo archinstall"] 
        ]
        
        launched_successfully = False
        for cmd_parts in terminal_commands_to_try:
            try:
                self.add_log(f"Trying to launch with: {' '.join(cmd_parts)}")
                # For Popen, we don't want to wait. It opens in a new window.
                # `sudo` might ask for password in the new terminal if not recently entered.
                self.archinstall_process = subprocess.Popen(cmd_parts)
                self.add_log(f"Archinstall launched with '{cmd_parts[0]}'. Please complete installation in that window.")
                self.run_postinstall_button.config(state=tk.NORMAL) # Enable next step
                launched_successfully = True
                break 
            except FileNotFoundError:
                self.add_log(f"Terminal '{cmd_parts[0]}' not found. Trying next...")
            except Exception as e:
                self.add_log(f"Error launching with '{cmd_parts[0]}': {e}", error=True)
        
        if not launched_successfully:
            self.add_log("ERROR: Failed to launch archinstall. No suitable terminal found or another error occurred.", error=True)
            messagebox.showerror("Archinstall Error", "Could not launch archinstall.\nPlease ensure a common terminal (gnome-terminal, konsole, xfce4-terminal, xterm) is installed and `sudo archinstall` can be run.")
        
        self.launch_archinstall_button.config(state=tk.NORMAL) # Re-enable in case of launch failure

    def run_postinstall_thread(self):
        self.run_postinstall_button.config(state=tk.DISABLED)
        self.add_log("Starting Mai Bloom post-installation process...")
        threading.Thread(target=self._execute_postinstall_tasks, daemon=True).start()

    def _execute_postinstall_tasks(self):
        target_mp = self.target_mount_point_var.get()
        if not target_mp:
            self.add_log("ERROR: Target mount point is not specified.", error=True)
            messagebox.showerror("Configuration Error", "Target mount point for the new system is not specified.")
            self.run_postinstall_button.config(state=tk.NORMAL)
            return

        self.add_log(f"Target mount point set to: {target_mp}")

        # Call the existing logic, adapted to use GUI logging
        success = self._perform_mai_bloom_customizations_logic(target_mp)

        if success:
            self.add_log("Mai Bloom customizations completed successfully!")
            messagebox.showinfo("Installation Complete", "Mai Bloom OS base installation and customizations are complete! You can now reboot.")
        else:
            self.add_log("Mai Bloom customizations encountered errors. Please check the log.", error=True)
            messagebox.showerror("Post-Install Error", "Mai Bloom post-installation customizations failed. Please check the log for details.")
        
        self.run_postinstall_button.config(state=tk.NORMAL) # Re-enable button

    def _run_command_gui_log(self, command_list, check=True, shell=False, cwd=None, env=None):
        """Helper to run command and log to GUI's add_log."""
        log_message = f"Executing: {' '.join(command_list) if isinstance(command_list, list) else command_list}"
        if cwd: log_message += f" in {cwd}"
        self.add_log(log_message)
        
        try:
            # For commands that might produce a lot of output, use Popen and stream it
            process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=shell, cwd=cwd, env=env)
            stdout, stderr = process.communicate() # Waits for completion

            if stdout: self.add_log(f"Stdout:\n{stdout.strip()}")
            if stderr: self.add_log(f"Stderr:\n{stderr.strip()}", error=True)
            
            if check and process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command_list, output=stdout, stderr=stderr)
            return process
        except subprocess.CalledProcessError as e:
            self.add_log(f"Error running command: {' '.join(e.cmd)}", error=True)
            # No need to print stdout/stderr again if already logged
            raise
        except FileNotFoundError:
            self.add_log(f"Error: Command '{command_list[0]}' not found.", error=True)
            raise

    def _run_in_chroot_gui_log(self, mount_point, command_to_run_in_chroot):
        chroot_command_list = ["arch-chroot", mount_point, "/bin/bash", "-c", command_to_run_in_chroot]
        return self._run_command_gui_log(chroot_command_list)

    def _perform_mai_bloom_customizations_logic(self, target_mount_point):
        """Actual post-installation logic, using GUI logging."""
        self.add_log(f"Applying customizations to system at {target_mount_point}...")

        if not os.path.isdir(target_mount_point) or not os.path.exists(os.path.join(target_mount_point, 'bin/bash')):
            self.add_log(f"ERROR: Target mount point '{target_mount_point}' does not look like a valid Linux root.", error=True)
            return False

        all_tasks_successful = True

        if EXTRA_PACKAGES:
            self.add_log("--- Installing extra Mai Bloom packages ---")
            package_string = " ".join(shlex.quote(pkg) for pkg in EXTRA_PACKAGES)
            try:
                self._run_in_chroot_gui_log(target_mount_point, f"pacman -S --noconfirm --needed {package_string}")
                self.add_log("Extra packages installed successfully.")
            except Exception as e:
                self.add_log(f"Failed to install extra packages: {e}", error=True)
                all_tasks_successful = False # Mark as failed but continue with other scripts
            self.add_log("") # Newline

        if MAI_BLOOM_SCRIPTS:
            self.add_log("--- Running Mai Bloom post-installation scripts ---")
            if not os.path.isdir(POST_INSTALL_SCRIPTS_DIR):
                self.add_log(f"Warning: Scripts directory '{POST_INSTALL_SCRIPTS_DIR}' not found. Skipping scripts.", error=True)
            else:
                for script_name in MAI_BLOOM_SCRIPTS:
                    host_script_path = os.path.join(POST_INSTALL_SCRIPTS_DIR, script_name)
                    if not os.path.isfile(host_script_path):
                        self.add_log(f"Warning: Script '{host_script_path}' not found. Skipping.", error=True)
                        continue

                    chroot_tmp_script_path = os.path.join("/tmp", os.path.basename(script_name))
                    cp_target_path_on_host = os.path.join(target_mount_point, chroot_tmp_script_path.lstrip('/'))

                    try:
                        self.add_log(f"Preparing script: {script_name}")
                        self._run_command_gui_log(["cp", host_script_path, cp_target_path_on_host])
                        self._run_in_chroot_gui_log(target_mount_point, f"chmod +x {chroot_tmp_script_path}")
                        
                        self.add_log(f"Executing '{chroot_tmp_script_path}' inside chroot...")
                        self._run_in_chroot_gui_log(target_mount_point, chroot_tmp_script_path)
                        self.add_log(f"Script '{script_name}' executed successfully.")

                        self._run_in_chroot_gui_log(target_mount_point, f"rm -f {chroot_tmp_script_path}")
                        self.add_log(f"Cleaned up script '{chroot_tmp_script_path}'.")
                    except Exception as e:
                        self.add_log(f"Failed to execute script '{script_name}': {e}", error=True)
                        all_tasks_successful = False
                    self.add_log("-" * 20)
        else:
            self.add_log("No Mai Bloom post-installation scripts defined.")
        
        return all_tasks_successful

# --- Main GUI Execution ---
def main_gui():
    if os.geteuid() != 0:
        # Try to show a Tkinter error box even if main app isn't fully set up
        try:
            root_err = tk.Tk()
            root_err.withdraw() # Hide the main window
            messagebox.showerror("Permission Error", "This script must be run with root privileges (e.g., using `sudo python script_name.py`).")
        except tk.TclError: # In case Tkinter can't initialize (e.g. no DISPLAY)
            print("ERROR: This script must be run with root privileges (e.g., using `sudo python script_name.py`).", file=sys.stderr)
        sys.exit(1)
        
    main_window = tk.Tk()
    app = MaiBloomInstallerApp(main_window)
    main_window.mainloop()

if __name__ == "__main__":
    main_gui()
