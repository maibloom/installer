import urwid

def exit_on_q(key):
    if key in ('q', 'Q'):
        raise urwid.ExitMainLoop()

def show_or_exit(button):
    response = urwid.Text([u'You pressed: ', button.get_label()])
    done = urwid.Button(u'Ok')
    urwid.connect_signal(done, 'click', exit_on_q)
    main.original_widget = urwid.Filler(urwid.Pile([response, urwid.AttrMap(done, None, focus_map='reversed')]))

def main_menu(button):
    button_1 = urwid.Button(u'Configure Network')
    button_2 = urwid.Button(u'Start Installation')
    urwid.connect_signal(button_1, 'click', configure_network)
    urwid.connect_signal(button_2, 'click', start_installation)

    menu = urwid.Text([u'Main Menu\n', u'Please select an option:'])
    menu_buttons = urwid.GridFlow([button_1, button_2], cell_width=20, h_sep=2, v_sep=1, align='center')
    main.original_widget = urwid.Filler(urwid.Pile([menu, urwid.Divider('-'), menu_buttons]))

def configure_network(button):
    # Implement network configuration logic here
    network_interface = urwid.Edit(u'Network Interface: ')
    ip_address = urwid.Edit(u'IP Address: ')
    gateway = urwid.Edit(u'Gateway: ')
    dns_server = urwid.Edit(u'DNS Server: ')

    save_button = urwid.Button(u'Save')
    urwid.connect_signal(save_button, 'click', lambda x: show_or_exit(save_button))

    network_form = urwid.Pile([network_interface, ip_address, gateway, dns_server, urwid.Divider('-'), save_button])
    main.original_widget = urwid.Filler(urwid.Pile([urwid.Text(u'Network Configuration'), urwid.Divider('-'), network_form]))

def start_installation(button):
    # Implement installation logic here
    response = urwid.Text([u'Starting installation...'])
    done = urwid.Button(u'Ok')
    urwid.connect_signal(done, 'click', exit_on_q)
    main.original_widget = urwid.Filler(urwid.Pile([response, urwid.AttrMap(done, None, focus_map='reversed')]))

    # Run the installation bash script
    try:
        import subprocess
        subprocess.run(["bash", "install.sh"], check=True)
        response.set_text(u'Installation completed successfully!')
    except subprocess.CalledProcessError as e:
        response.set_text(f"Installation failed: {e}")

if __name__ == '__main__':
    main_button = urwid.Button(u'Main Menu')
    urwid.connect_signal(main_button, 'click', main_menu)

    main = urwid.Padding(urwid.Filler(urwid.Pile([main_button])), left=2, right=2)
    top = urwid.Overlay(main, urwid.SolidFill(u'\N{MEDIUM SHADE}'),
                        align='center', width=('relative', 60),
                        valign='middle', height=('relative', 60),
                        min_width=20, min_height=9)

    urwid.MainLoop(top, palette=[('reversed', 'standout', '')]).run()

