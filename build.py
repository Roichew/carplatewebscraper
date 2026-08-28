import subprocess
import shutil
import os
import sys

APP_NAME = "CarPlateScraper"
ENTRY_FILE = "PlateScraper.py"   # 🔁 change if needed
OUTPUT_DIR = "bin"               # final location of the built app

def build():
    print("🔨 Building executable...")

    # PyInstaller command
    #
    # NOTE: we intentionally use --onedir (NOT --onefile).
    # --onefile packs everything into a single self-extracting exe that unpacks
    # to a temp directory at runtime. That behaviour is flagged by Windows
    # SmartScreen / Defender as untrusted and the app often refuses to open.
    # --onedir ships a plain exe next to its dependencies, which is trusted and
    # also starts faster (no unpack step).
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",            # no console window
        "--clean",
        "--noconfirm",           # overwrite previous build without prompting
        "--name", APP_NAME,
        "--collect-all", "flet",
        "--collect-all", "flet_desktop",
        ENTRY_FILE,
    ]

    subprocess.run(cmd, check=True)

    # PyInstaller --onedir output lives at dist/<APP_NAME>/ (contains the exe
    # plus an _internal folder with all dependencies). Move that whole folder
    # into ./bin so the exe and its dependencies stay together.
    src_dir = os.path.join("dist", APP_NAME)
    dst_dir = os.path.join(os.getcwd(), OUTPUT_DIR, APP_NAME)

    if os.path.exists(src_dir):
        # Clean any previous copy in the output dir first.
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
        os.makedirs(os.path.join(os.getcwd(), OUTPUT_DIR), exist_ok=True)
        shutil.move(src_dir, dst_dir)
        exe_path = os.path.join(dst_dir, f"{APP_NAME}.exe")
        print(f"✅ App created: {exe_path}")
    else:
        print("❌ Build output not found!")

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
