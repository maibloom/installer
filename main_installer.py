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

# Define UI elements for each step
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

# Define steps
steps = []
current_step = [0]  # Use list for mutable integer

def next_step(button):
    if current_step[0] < len(steps) - 1:
        current_step[0] += 1
        main.original_widget = urwid.Filler(steps[current_step[0]])
    else:
        # Final step: collect inputs and proceed
        user_inputs["hostname"] = hostname_edit.edit_text.strip()
        user_inputs["username"] = username_edit.edit_text.strip()
        user_inputs["password"] = password_edit.edit_text.strip()
        user_inputs["disk"] = disk_edit.edit_text.strip()
        for btn in driver_radio_buttons:
            if btn.get_state():
                user_inputs["driver"] = btn.get_label()
                break
        summary = f"""
        Hostname: {user_inputs['hostname']}
        Username: {user_inputs['username']}
        Disk: {user_inputs['disk']}
        Graphics Driver: {user_inputs['driver']}
        """
        response.set_text(summary)
        main.original_widget = urwid.Filler(urwid.Pile([response, urwid.Button("Exit", on_press=exit_program)]))

def exit_program(button):
    raise urwid.ExitMainLoop()

# Step 1: Hostname
step1 = urwid.Pile([
    urwid.Text("Step 1: Enter Hostname"),
    hostname_edit,
    urwid.Button("Next", on_press=next_step)
])
steps.append(step1)

# Step 2: Username and Password
step2 = urwid.Pile([
    urwid.Text("Step 2: Enter Username and Password"),
    username_edit,
    password_edit,
    urwid.Button("Next", on_press=next_step)
])
steps.append(step2)

# Step 3: Disk Selection
step3 = urwid.Pile([
    urwid.Text("Step 3: Enter Disk (e.g., /dev/sda)"),
    disk_edit,
    urwid.Button("Next", on_press=next_step)
])
steps.append(step3)

# Step 4: Graphics Driver Selection
step4_items = [urwid.Text("Step 4: Select Graphics Driver")]
step4_items.extend(driver_radio_buttons)
step4_items.append(urwid.Button("Next", on_press=next_step))
step4 = urwid.Pile(step4_items)
steps.append(step4)

# Step 5: Summary (handled in next_step function)

response = urwid.Text("")

main = urwid.Padding(urwid.Filler(steps[0]), left=2, right=2)

urwid.MainLoop(main).run()