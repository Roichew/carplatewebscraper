import subprocess
import shutil
import os
import sys

APP_NAME = "CarPlateScraper"
ENTRY_FILE = "PlateScraper.py"   # 🔁 change if needed

def build():
    print("🔨 Building executable...")

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",            # no console window
        "--clean",
        "--name", APP_NAME,
        ENTRY_FILE,
    ]

    subprocess.run(cmd, check=True)

    # Move exe to project root
    exe_name = f"{APP_NAME}.exe"
    src = os.path.join("dist", exe_name)
    dst = os.path.join(os.getcwd(), exe_name)

    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"✅ EXE created: {exe_name}")
    else:
        print("❌ EXE not found!")

    # Cleanup
    for folder in ["build", "dist", "__pycache__"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)

    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)

    print("🧹 Cleanup done")

if __name__ == "__main__":
    build()
