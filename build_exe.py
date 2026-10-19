import os
import sys
import subprocess
import datetime
import shutil

def build():
    # 取得當前時間戳記，格式：YYYY/MM/DD-HH:MM
    build_time = datetime.datetime.now().strftime("%Y/%m/%d-%H:%M")
    print(f"==================================================")
    print(f"開始編譯 Teams 會議錄音與轉文字 EXE")
    print(f"版本時間戳記: {build_time}")
    print(f"==================================================")

    # 1. 自動寫入 version.py
    base_dir = os.path.dirname(os.path.abspath(__file__))
    version_file = os.path.join(base_dir, "version.py")
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(f'# 此檔案記錄軟體版本資訊（以 EXE 打包時間為準）\n')
        f.write(f'BUILD_VERSION = "{build_time}"\n')
    print(f"[1/3] 已更新 version.py: BUILD_VERSION = '{build_time}'")

    # 2. 呼叫 PyInstaller 打包
    print(f"[2/3] 正在使用 PyInstaller 封裝單一獨立 EXE...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "Teams會議錄音與轉文字",
        "--onefile",
        "recorder_gui.py"
    ]
    subprocess.run(cmd, cwd=base_dir, check=True)

    # 3. 部署複製檔案至本地及 www/meeting
    dist_exe = os.path.join(base_dir, "dist", "Teams會議錄音與轉文字.exe")
    target_exe = os.path.join(base_dir, "Teams會議錄音與轉文字.exe")

    # 若舊程式正在運行，先結束它避免鎖檔
    try:
        import time
        subprocess.run(["taskkill", "/f", "/im", "Teams會議錄音與轉文字.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception:
        pass

    shutil.copy2(dist_exe, target_exe)
    print(f"[3/3] 已更新本機 EXE: {target_exe}")

    www_meeting_dir = r"C:\Users\Joel\www\meeting"
    if os.path.exists(www_meeting_dir):
        www_exe = os.path.join(www_meeting_dir, "Teams會議錄音與轉文字.exe")
        shutil.copy2(dist_exe, www_exe)
        print(f"      已同步部署至 Windows Web 下載目錄: {www_exe}")

    wsl_meeting_dir = r"\\wsl.localhost\Ubuntu\home\joel\www\meeting"
    if os.path.exists(wsl_meeting_dir):
        wsl_exe = os.path.join(wsl_meeting_dir, "Teams會議錄音與轉文字.exe")
        try:
            shutil.copy2(dist_exe, wsl_exe)
            print(f"      已同步部署至 WSL ~/www Web 下載目錄: {wsl_exe}")
        except Exception as e:
            print(f"      部署至 WSL 失敗: {e}")

    print(f"==================================================")
    print(f"[OK] Build completed! Title version: [v{build_time}]")
    print(f"==================================================")

if __name__ == "__main__":
    build()
