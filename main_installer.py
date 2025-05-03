import urwid
import archinstall

# Define available graphics driver options
driver_options = [
    "None",
    "NVIDIA (proprietary)",
    "NVIDIA (open-source)",
    "AMD",
    "Intel"
]

# Placeholder for user inputs
user_inputs = {
    "hostname": "",
    "username": "",
    "password": "",
    "disk": "",
    "driver": driver_options[0]
}

def on_submit(button):
    # Collect user inputs
    user_inputs["hostname"] = hostname_edit.edit_text.strip()
    user_inputs["username"] = username_edit.edit_text.strip()
    user_inputs["password"] = password_edit.edit_text.strip()
    user_inputs["disk"] = disk_edit.edit_text.strip()
    user_inputs["driver"] = driver_radio.get_selected_label()

    # Display collected inputs (for demonstration purposes)
    summary = f"""
    Hostname: {user_inputs['hostname']}
    Username: {user_inputs['username']}
    Disk: {user_inputs['disk']}
    Graphics Driver: {user_inputs['driver']}
    """
    response.set_text(summary)

    # Here, you would integrate with archinstall to perform the installation
    # For example:
    # installer = archinstall.Installer()
    # installer.install(config)

# Define UI elements
hostname_edit = urwid.Edit("Hostname: ")
username_edit = urwid.Edit("Username: ")
password_edit = urwid.Edit("Password: ", mask="*")
disk_edit = urwid.Edit("Disk (e.g., /dev/sda): ")

# Graphics driver selection using RadioButtons
driver_radio = urwid.RadioButton(driver_options)

submit_button = urwid.Button("Install", on_press=on_submit)
response = urwid.Text("")

# Arrange UI elements
pile = urwid.Pile([
    hostname_edit,
    username_edit,
    password_edit,
    disk_edit,
    urwid.Text("Select Graphics Driver:"),
    driver_radio.widget,
    submit_button,
    response
])

fill = urwid.Filler(pile, valign='top')

# Run the application
urwid.MainLoop(fill).run()