#!/usr/bin/env python3
import subprocess

def list_networks():
    try:
        output = subprocess.check_output(['nmcli', 'device', 'wifi', 'list']).decode('utf-8')
        print("\nAvailable Networks:\n")
        print(output)
    except Exception as e:
        print("Error listing networks:", e)

def connect_to_network(ssid, password):
    try:
        result = subprocess.run(
            ['nmcli', 'device', 'wifi', 'connect', ssid, 'password', password],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"Successfully connected to '{ssid}'!")
        else:
            print(f"Failed to connect to '{ssid}'. Error: {result.stderr}")
    except Exception as e:
        print("Error connecting:", e)

def main():
    print("Welcome to Mai Bloom OS network setup!")
    list_networks()
    ssid = input("Enter the SSID of the network you wish to connect to: ")
    password = input("Enter the network password: ")
    connect_to_network(ssid, password)

if __name__ == "__main__":
    main()
