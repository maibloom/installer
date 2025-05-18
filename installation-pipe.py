#!/usr/bin/env python3
import sys
import subprocess

def installprocess():
  archinstall_konsole_command = "archinstall; exec bash"
  archinstall_process = subprocess.Popen(["konsole", "-e", "bash", "-c", archinstall_konsole_command])
        
  return_code = archinstall_process.wait() 

  if return_code == 0:
    print("Archinstall konsole window closed. Assuming successful completion by user. Proceeding with post-installation steps...")
            
    post_install_chroot_script = (
      "pacman -Syu --noconfirm git && "
      "echo 'Git installed/updated.' && "
      "rm -rf /installer && "
      "echo 'Removed old /installer directory if it existed.' && "
      "git clone https://github.com/maibloom/installer /installer && "
      "echo 'Cloned maibloom/installer to /installer.' && "
      "cd /installer && "
      "chmod +x config.sh && "
      "echo 'Made config.sh executable.' && "
      "./config.sh && " 
      "echo 'Post-installation script (config.sh) finished. You can close this terminal.' && "
      "exec bash"
      )
            
      post_install_command = f"arch-chroot /mnt /bin/bash -c '{post_install_chroot_script}'"
            
      post_install_process = subprocess.Popen(post_install_command, shell=True)
