#!/usr/bin/env python3
import subprocess

command = "ls -la"

subprocess.Popen(["konsole", "-e", "bash", "-c", f"{command}; exec bash"])
