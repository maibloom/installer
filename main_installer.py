#!/usr/bin/env python3
import subprocess

command = "archinstall"

subprocess.Popen(["konsole", "-e", "bash", "-c", f"{command}; exec bash"])
