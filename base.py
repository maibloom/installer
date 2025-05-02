#!/usr/bin/env python3
import urwid
import subprocess
import os
import sys
import tempfile

# ------------------------ Helper Functions ------------------------

def check_network_manager():
    try:
        subprocess.check_call(['systemctl', 'is-active', '--quiet', 'NetworkManager'])
        return True
    except subprocess.CalledProcessError:
        try:
            subprocess.check_call(['sudo', 'systemctl', 'start', 'NetworkManager'])
            return True
        except subprocess.CalledProcessError:
            return False

def is_connected():
    try:
        output = subprocess.check_output(['nmcli', 'networking', 'connectivity']).decode().strip()
        return output.lower() == 'full'
    except Exception:
        return False

def list_networks():
    try:
        return subprocess.check_output(['nmcli', 'device', 'wifi', 'list']).decode().strip()
    except Exception as e:
        return f"Network list error: {e}"

def connect_to_network(ssid, password):
    try:
        res = subprocess.run(['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
                             capture_output=True, text=True)
        return res.returncode == 0
    except Exception:
        return False

def clone_repo(repo_url, destination):
    try:
        subprocess.check_call(['git', 'clone', repo_url, destination])
        return True
    except subprocess.CalledProcessError:
        return False

def run_installer(script_path):
    subprocess.check_call(['python3', script_path])

# ------------------------ Wizard Application ------------------------

class WizardApp:
    def __init__(self):
        self.placeholder = urwid.WidgetPlaceholder(urwid.SolidFill())
        self.temp_dir = None
        self.loop = None

    def main(self):
        self.show_welcome_screen()
        palette = [
            ('welcome', 'light red', ''),
            ('title', 'light magenta', ''),
            ('button', 'black', 'dark cyan'),
            ('error', 'light red', ''),
            ('success', 'light green', ''),
            ('bg', 'white', 'dark magenta'),
        ]
        self.loop = urwid.MainLoop(self.placeholder, palette, unhandled_input=self.unhandled_input)
        self.loop.run()

    def unhandled_input(self, key):
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()

    # ------------------------ Screens ------------------------

    def show_welcome_screen(self):
        welcome_text = urwid.Text([
            ('welcome', "Welcome "),
            ("", "to the "),
            ('title', "Mai Bloom Operating System Installer\n"),
            "Press 'Enter' to start!"
            ], align="center")
        start_btn = urwid.Button("Start", on_press=self.on_welcome_start)
        btn_map = urwid.AttrMap(start_btn, 'button')
        pile = urwid.Pile([welcome_text, urwid.Divider(), btn_map])
        fill = urwid.Filler(pile, valign="middle")
        self.placeholder.original_widget = fill

    def on_welcome_start(self, button):
        self.show_network_screen()

    def show_network_screen(self):
        header = urwid.Text("Network Configuration", align="center")
        nets = list_networks()
        nets_text = urwid.Text("Available Networks:\n" + nets)
        self.ssid_edit = urwid.Edit("SSID: ")
        self.password_edit = urwid.Edit("Password: ", mask="*")
        self.msg_text = urwid.Text("")
        connect_btn = urwid.Button("Connect", on_press=self.on_connect)
        skip_btn = urwid.Button("Skip (Already Connected)", on_press=self.on_skip)
        btns = urwid.Columns([
                    urwid.AttrMap(connect_btn, 'button'),
                    urwid.AttrMap(skip_btn, 'button')
                ])
        pile = urwid.Pile([
            header, urwid.Divider(),
            nets_text, urwid.Divider(),
            self.ssid_edit, self.password_edit, urwid.Divider(),
            btns, urwid.Divider(),
            self.msg_text
        ])
        fill = urwid.Filler(pile, valign="top")
        self.placeholder.original_widget = fill

        # Auto-skip if already connected:
        if is_connected():
            self.msg_text.set_text(('success', "Already connected. Skipping network configuration..."))
            self.loop.set_alarm_in(1, lambda loop, user_data: self.show_clone_screen())
            return

        if not check_network_manager():
            self.msg_text.set_text(('error', "NetworkManager could not be started."))

    def on_connect(self, button):
        ssid = self.ssid_edit.edit_text.strip()
        password = self.password_edit.edit_text.strip()
        if not ssid or not password:
            self.msg_text.set_text(('error', "Please enter both SSID and password."))
            return
        self.msg_text.set_text("Connecting...")
        if connect_to_network(ssid, password):
            self.msg_text.set_text(('success', "Connected successfully!"))
            self.loop.set_alarm_in(1, lambda loop, user_data: self.show_clone_screen())
        else:
            self.msg_text.set_text(('error', "Failed to connect. Check credentials."))

    def on_skip(self, button):
        self.msg_text.set_text(('success', "Skipping network configuration..."))
        self.loop.set_alarm_in(1, lambda loop, user_data: self.show_clone_screen())

    def show_clone_screen(self):
        header = urwid.Text("Cloning the Installer Repository", align="center")
        self.progress_text = urwid.Text("Starting clone...")
        pile = urwid.Pile([header, urwid.Divider(), self.progress_text])
        fill = urwid.Filler(pile, valign="middle")
        self.placeholder.original_widget = fill
        self.temp_dir = tempfile.mkdtemp(prefix="maibloom_")
        repo_url = "https://github.com/maibloom/installer"
        self.clone_progress(0, repo_url)

    def clone_progress(self, percent, repo_url):
        if percent > 100:
            if clone_repo(repo_url, self.temp_dir):
                self.progress_text.set_text(('success', "Clone complete. Launching installer..."))
                self.loop.set_alarm_in(1, lambda loop, user_data: self.launch_installer())
            else:
                self.progress_text.set_text(('error', "Clone failed."))
            return
        self.progress_text.set_text(f"Cloning... {percent}%")
        self.loop.set_alarm_in(0.5, lambda loop, user_data: self.clone_progress(percent + 25, repo_url))

    def launch_installer(self):
        installer_script = os.path.join(self.temp_dir, "main_installer.py")
        # Display final message before exiting:
        final_text = urwid.Text("Launching installer...", align="center")
        self.placeholder.original_widget = urwid.Filler(final_text, valign="middle")
        try:
            run_installer(installer_script)
        except subprocess.CalledProcessError as e:
            print("Error launching installer:", e)
            sys.exit(1)
        raise urwid.ExitMainLoop()

if __name__ == '__main__':
    WizardApp().main()
