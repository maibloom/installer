import subprocess

def connect_to_network():
    print("Scanning for networks...")
    networks = subprocess.run(["nmcli", "dev", "wifi", "list"], capture_output=True, text=True)
    print(networks.stdout)

    ssid = input("Enter the SSID of the network you want to connect to: ")
    password = input("Enter the password for the network: ")

    subprocess.run(["nmcli", "dev", "wifi", "connect", ssid, "password", password])
    print("Connected to network.")

connect_to_network()
