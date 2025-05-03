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

    # Retrieve selected graphics driver
    for button in driver_radio_buttons:
        if button.get_state():
            user_inputs["driver"] = button.get_label()
            break

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
    # config = archinstall.Profile(user_inputs['driver'])
    # archinstall.run_installation(config)

# Define UI elements
hostname_edit = urwid.Edit("Hostname: ")
username_edit = urwid.Edit("Username: ")
password_edit = urwid.Edit("Password: ", mask="*")
disk_edit = urwid.Edit("Disk (e.g., /dev/sda): ")

# Graphics driver selection using RadioButtons
driver_group = []
driver_radio_buttons = []
for option in driver_options:
    button = urwid.RadioButton(driver_group, option)
    driver_radio_buttons.append(button)

submit_button = urwid.Button("Install", on_press=on_submit)
response = urwid.Text("")

# Arrange UI elements
pile_items = [
    hostname_edit,
    username_edit,
    password_edit,
    disk_edit,
    urwid.Text("Select Graphics Driver:")
]
pile_items.extend(driver_radio_buttons)
pile_items.extend([submit_button, response])

pile = urwid.Pile(pile_items)
fill = urwid.Filler(pile, valign='top')

# Run the application
urwid.MainLoop(fill).run()