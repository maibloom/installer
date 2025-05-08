import sys
import os
import subprocess
import threading
import tarfile
import requests
import json # For parsing GitHub API response
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QTextEdit, QFileDialog, QLabel, QMessageBox, QProgressBar)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer

# GitHub repository details
GH_REPO_OWNER = "calamares"
GH_REPO_NAME = "calamares"
GH_API_LATEST_RELEASE_URL = f"https://api.github.com/repos/{GH_REPO_OWNER}/{GH_REPO_NAME}/releases/latest"

class DownloaderSignals(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str) # Emits downloaded file path
    error = pyqtSignal(str)
    latest_release_info = pyqtSignal(dict) # Emits {'version': str, 'download_url': str, 'src_dir_name': str}

class GitHubLatestReleaseFetcher(threading.Thread):
    def __init__(self, signals):
        super().__init__()
        self.signals = signals

    def run(self):
        try:
            response = requests.get(GH_API_LATEST_RELEASE_URL, timeout=10)
            response.raise_for_status()
            release_data = response.json()

            tag_name = release_data.get("tag_name")
            tarball_url = release_data.get("tarball_url")

            if not tag_name or not tarball_url:
                self.signals.error.emit("Could not find tag_name or tarball_url in GitHub API response.")
                return

            # Derive source directory name (e.g., calamares-3.3.14 from v3.3.14)
            # GitHub usually creates a dir like 'owner-repo-commit_hash' or 'repo-tag' from tarball
            # The tarball from 'tarball_url' typically extracts to a directory like 'calamares-calamares-<short_hash>'
            # or 'calamares-calamares-<tag_name_without_v>'
            # However, the .tar.gz available under "Assets" usually has a cleaner name like 'calamares-3.3.14.tar.gz'
            # and extracts to 'calamares-3.3.14'.
            # Let's try to find a source asset first for a cleaner name.
            assets = release_data.get("assets", [])
            source_tarball_asset_url = None
            derived_src_dir_name = f"{GH_REPO_NAME}-{tag_name.lstrip('v')}" # Default assumption

            for asset in assets:
                if asset.get("name", "").endswith(".tar.gz") and GH_REPO_NAME in asset.get("name", ""):
                    # Prefer asset like 'calamares-3.3.14.tar.gz'
                    if tag_name.lstrip('v') in asset.get("name"):
                        tarball_url = asset.get("browser_download_url")
                        # src_dir_name can be reliably derived if asset name is like 'calamares-version.tar.gz'
                        derived_src_dir_name = asset.get("name").replace(".tar.gz", "")
                        break
            # If no specific asset found, stick with the general tarball_url and its less predictable dir name,
            # or refine CALAMARES_SRC_DIR_NAME logic post-extraction.
            # For now, the derived_src_dir_name will be updated in on_download_finished after actual extraction.

            release_info = {
                "version": tag_name,
                "download_url": tarball_url,
                "default_src_dir_pattern": f"{GH_REPO_NAME}-{tag_name.lstrip('v')}" # A pattern to look for
            }
            self.signals.latest_release_info.emit(release_info)

        except requests.exceptions.Timeout:
            self.signals.error.emit("Fetching latest release timed out. Check your internet connection.")
        except requests.exceptions.RequestException as e:
            self.signals.error.emit(f"GitHub API request failed: {e}")
        except (KeyError, TypeError, json.JSONDecodeError) as e:
            self.signals.error.emit(f"Failed to parse GitHub API response: {e}")


class Downloader(threading.Thread):
    def __init__(self, url, save_path, signals):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.signals = signals

    def run(self):
        try:
            response = requests.get(self.url, stream=True, timeout=30) # Added timeout
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            with open(self.save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress_percentage = int((downloaded_size / total_size) * 100)
                            self.signals.progress.emit(progress_percentage)
            self.signals.progress.emit(100)
            self.signals.finished.emit(self.save_path)
        except requests.exceptions.Timeout:
            self.signals.error.emit("Download timed out. Check your internet connection.")
        except requests.exceptions.RequestException as e:
            self.signals.error.emit(f"Download failed: {e}")
        except Exception as e: # Catch any other exception during download/write
            self.signals.error.emit(f"An error occurred during download: {e}")

class CalamaresDownloaderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Calamares Latest Release Downloader & Helper (Arch Linux)")
        self.setGeometry(100, 100, 800, 750)

        self.calamares_version = "Fetching..."
        self.calamares_download_url = ""
        self.calamares_src_dir_pattern = "" # Pattern for the extracted directory

        self.init_ui()

        self.download_thread = None
        self.fetch_thread = None

        self.signals = DownloaderSignals()
        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.on_download_finished)
        self.signals.error.connect(self.on_download_or_fetch_error)
        self.signals.latest_release_info.connect(self.update_release_info)

        self.download_path = ""
        self.extracted_path = ""

        self.fetch_latest_release()

    def init_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel(f"Fetching latest Calamares release info...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.info_label = QLabel(
            "This tool will download the latest Calamares source code and provide "
            "instructions to build it on Arch Linux.\n"
            "Ensure you have an internet connection and sudo privileges for installing dependencies."
        )
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.btn_download = QPushButton(f"Download Latest Calamares Source")
        self.btn_download.clicked.connect(self.start_download)
        self.btn_download.setEnabled(False) # Disabled until release info is fetched
        layout.addWidget(self.btn_download)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.instructions_label = QLabel("Build and Run Instructions (run these in your terminal):")
        layout.addWidget(self.instructions_label)

        self.instructions_text = QTextEdit()
        self.instructions_text.setReadOnly(True)
        self.instructions_text.setText("Please wait, fetching latest release information...")
        layout.addWidget(self.instructions_text)

        self.setLayout(layout)

    def fetch_latest_release(self):
        self.fetch_thread = GitHubLatestReleaseFetcher(self.signals)
        self.fetch_thread.start()

    def update_release_info(self, release_info):
        self.calamares_version = release_info["version"]
        self.calamares_download_url = release_info["download_url"]
        self.calamares_src_dir_pattern = release_info["default_src_dir_pattern"]

        self.status_label.setText(f"Latest Calamares Release: {self.calamares_version}")
        self.setWindowTitle(f"Calamares {self.calamares_version} Downloader & Helper (Arch Linux)")
        self.btn_download.setText(f"Download Calamares {self.calamares_version} Source")
        self.btn_download.setEnabled(True)
        self.instructions_text.setText(self.get_instructions()) # Update instructions with version
        QMessageBox.information(self, "Release Info Updated", f"Ready to download Calamares {self.calamares_version}.")


    def get_instructions(self, extracted_dir_name_actual=None):
        # Use actual extracted directory name if known, otherwise use pattern
        calamares_dir_name_for_display = extracted_dir_name_actual if extracted_dir_name_actual else self.calamares_src_dir_pattern
        download_filename = os.path.basename(self.calamares_download_url) if self.calamares_download_url else f"calamares-{self.calamares_version}.tar.gz"


        return f"""
        Welcome to Calamares {self.calamares_version} build helper for Arch Linux!

        The source code archive will be downloaded. Follow these steps in your terminal:

        Step 1: Ensure PyQt5 is installed
        ---------------------------------
        If you haven't installed PyQt5 yet (needed for this GUI tool):
        sudo pacman -S --needed python-pyqt5

        Step 2: Install Calamares Build Dependencies
        -------------------------------------------
        These are needed to compile Calamares. Open a terminal and run:
        sudo pacman -S --needed qt5-base qt5-svg qt5-xmlpatterns \\
            kconfig5 kcoreaddons5 ki18n5 kiconthemes5 kio5 plasma-framework5 solid5 \\
            polkit-qt5 kpmcore yaml-cpp python-yaml python-jsonschema squashfs-tools \\
            boost extra-cmake-modules cmake make ninja git

        (Note: This list is comprehensive for a Qt5 build of Calamares. `python-pyqt5` is
         also a Calamares dependency if its Python modules use PyQt bindings.)

        Step 3: Extract Calamares (if not automatically extracted)
        -----------------------------------------------------------
        The downloaded file will be '{download_filename}'.
        If extraction by this tool fails, you can do it manually:
        tar -xzf {download_filename}

        Step 4: Build Calamares
        ----------------------
        Navigate to the extracted Calamares source directory.
        The directory is typically named something like '{self.calamares_src_dir_pattern}' or '{GH_REPO_NAME}-{GH_REPO_NAME}-<some_hash>'.
        This tool will attempt to confirm the exact name after extraction.
        If this tool extracted it, the path will be confirmed. For now, assume:
        cd "{self.extracted_path if self.extracted_path else 'PATH_TO_EXTRACTED_FOLDER/' + calamares_dir_name_for_display}"
        
        mkdir build
        cd build

        Run CMake to configure the build. For a Qt5 build with KF5 dependencies installed:
        cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr

        (Optional: To disable the webview module, add: -DWITH_WEBVIEWMODULE=OFF
         Check other options with `cmake -LH ..` in the build directory.)

        After CMake finishes successfully, compile Calamares:
        make -j$(nproc)  # Uses all available CPU cores

        Step 5: Install Calamares (Optional)
        ------------------------------------
        sudo make install

        Step 6: Run Calamares
        --------------------
        If installed:
        sudo calamares

        If running from the build directory (without installing):
        sudo ./bin/calamares  (Ensure you are in the 'build' directory)

        IMPORTANT NOTES:
        * Running Calamares requires root privileges (sudo).
        * This builds the generic Calamares framework. For a custom Arch Linux installer,
          you'll need to configure Calamares modules and branding separately.
        * If CMake has issues finding Qt5/KF5, ensure all dependencies from Step 2 are installed.
          Clean the build directory (rm -rf *) and retry cmake.
        """

    def start_download(self):
        if not self.calamares_download_url:
            QMessageBox.warning(self, "Error", "Download URL not available. Cannot start download.")
            return

        save_dir = QFileDialog.getExistingDirectory(self, f"Select Directory to Save Calamares {self.calamares_version} Source")
        if not save_dir:
            QMessageBox.information(self, "Download Cancelled", "Download directory not selected.")
            return

        # Use the actual filename from the URL or a derived one
        archive_filename = os.path.basename(self.calamares_download_url)
        if not archive_filename or not archive_filename.endswith((".gz", ".zip", ".xz")): # Basic check
            archive_filename = f"calamares-{self.calamares_version}.tar.gz"


        self.download_path = os.path.join(save_dir, archive_filename)
        self.btn_download.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Downloading Calamares {self.calamares_version} to {self.download_path}...")

        self.download_thread = Downloader(self.calamares_download_url, self.download_path, self.signals)
        self.download_thread.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def on_download_or_fetch_error(self, error_message):
        QMessageBox.critical(self, "Error", error_message)
        self.status_label.setText(f"Error: {error_message}")
        # Re-enable download button only if version info was fetched successfully
        if self.calamares_version != "Fetching...":
            self.btn_download.setEnabled(True)
        else: # If fetch failed, offer to retry fetching
            self.btn_download.setText("Retry Fetching Release Info")
            self.btn_download.setEnabled(True)
            # Disconnect old slot if any, and connect to fetch_latest_release
            try:
                self.btn_download.clicked.disconnect()
            except TypeError:
                pass # No slot was connected or already disconnected
            self.btn_download.clicked.connect(self.fetch_latest_release)

        self.progress_bar.setValue(0)

    def on_download_finished(self, downloaded_file_path):
        self.status_label.setText(f"Calamares {self.calamares_version} downloaded: {downloaded_file_path}")
        QMessageBox.information(self, "Download Complete",
                                f"Calamares source downloaded successfully:\n{downloaded_file_path}")
        self.progress_bar.setValue(100)

        extract_to_dir = os.path.dirname(downloaded_file_path)
        self.status_label.setText(f"Extracting {downloaded_file_path}...")
        QApplication.processEvents()

        try:
            with tarfile.open(downloaded_file_path, "r:*") as tar: # r:* to auto-detect compression
                # Get the name of the top-level directory in the tarball
                # This is more reliable than guessing based on version string
                members = tar.getmembers()
                if not members:
                    raise tarfile.TarError("Tar archive is empty.")
                
                # Find the common top-level directory
                # GitHub tarballs usually have a single top-level directory
                # e.g. calamares-calamares-aabbcc12 or calamares-3.3.14
                top_level_dirs = set()
                for member in members:
                    if '/' in member.name:
                        top_level_dirs.add(member.name.split('/', 1)[0])
                    elif member.isdir(): # A directory at the root level
                         top_level_dirs.add(member.name)
                
                if len(top_level_dirs) == 1:
                    actual_extracted_dir_name = list(top_level_dirs)[0]
                elif self.calamares_src_dir_pattern and os.path.exists(os.path.join(extract_to_dir, self.calamares_src_dir_pattern)):
                     actual_extracted_dir_name = self.calamares_src_dir_pattern
                elif members[0].name.split('/')[0]: # Fallback to first member's root
                     actual_extracted_dir_name = members[0].name.split('/')[0]
                else: # If still unsure, use a generic name and warn user
                    actual_extracted_dir_name = f"{GH_REPO_NAME}-extracted"
                    QMessageBox.warning(self, "Extraction Info",
                                        f"Could not reliably determine the exact top-level directory name from the archive. "
                                        f"It might be something like '{members[0].name.split('/')[0]}'. "
                                        f"Please check the extraction folder: {extract_to_dir}")


                tar.extractall(path=extract_to_dir)
                self.extracted_path = os.path.join(extract_to_dir, actual_extracted_dir_name)

            if os.path.exists(self.extracted_path) and os.path.isdir(self.extracted_path):
                QMessageBox.information(self, "Extraction Complete",
                                        f"Successfully extracted to:\n{self.extracted_path}")
                self.instructions_text.setText(self.get_instructions(extracted_dir_name_actual=actual_extracted_dir_name))
                self.status_label.setText(
                    f"Calamares {self.calamares_version} extracted to {self.extracted_path}."
                )
            else:
                # This case should ideally be caught by the logic above, but as a failsafe:
                self.extracted_path = "" # Reset if not found
                raise FileNotFoundError(f"Expected extracted directory '{actual_extracted_dir_name}' not found in {extract_to_dir}. "
                                        "The tarball might have an unexpected structure. Please check the directory manually.")

        except tarfile.TarError as e:
            QMessageBox.critical(self, "Extraction Error", f"Failed to extract tarball: {e}")
            self.instructions_text.setText(self.get_instructions())
        except FileNotFoundError as e:
            QMessageBox.critical(self, "Extraction Error", str(e))
            self.instructions_text.setText(self.get_instructions())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during extraction: {e}")
            self.instructions_text.setText(self.get_instructions())
        finally:
            self.btn_download.setEnabled(True)
            # Reconnect the download button to start_download if it was changed for retrying fetch
            try:
                self.btn_download.clicked.disconnect()
            except TypeError:
                pass
            self.btn_download.clicked.connect(self.start_download)
            self.btn_download.setText(f"Download Calamares {self.calamares_version} Source")


if __name__ == '__main__':
    try:
        from PyQt5 import QtWidgets
    except ImportError:
        print("CRITICAL ERROR: PyQt5 is not installed.")
        print("This GUI application requires PyQt5 to run.")
        print("Please install it on your Arch Linux system by running:")
        print("sudo pacman -S python-pyqt5")
        sys.exit(1)

    app = QApplication(sys.argv)
    ex = CalamaresDownloaderApp()
    ex.show()
    sys.exit(app.exec_())
