"""Lumi AI updater and maintenance utility for Windows.

--update: download the latest published installer, verify its SHA-256, and run it.
No argument: detect an installed copy and offer to uninstall it. User notes are
kept unless the user explicitly confirms their deletion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import winreg
from pathlib import Path
from tkinter import Tk, messagebox

REPO = "longortovvolodja-del/Lumi-AI"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
APP_NAME = "Lumi AI"
APP_ID = "{7E7B0F9D-3B4B-4DF0-9A0B-1DCC5F0A12A4}"


def _http(url: str, *, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Lumi-AI-Updater", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _installed_program() -> tuple[Path | None, str | None]:
    roots = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, root in roots:
        try:
            with winreg.OpenKey(hive, root) as key:
                count = winreg.QueryInfoKey(key)[0]
                for index in range(count):
                    try:
                        subkey_name = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            if display_name != APP_NAME and not display_name.startswith(APP_NAME + " "):
                                continue
                            install_location = None
                            uninstall_string = None
                            try:
                                install_location = winreg.QueryValueEx(subkey, "InstallLocation")[0]
                            except OSError:
                                pass
                            try:
                                uninstall_string = winreg.QueryValueEx(subkey, "UninstallString")[0]
                            except OSError:
                                pass
                            install_dir = Path(install_location) if install_location else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "Lumi AI"
                            if not uninstall_string:
                                candidate = install_dir / "unins000.exe"
                                uninstall_string = f'"{candidate}"' if candidate.is_file() else None
                            return install_dir, uninstall_string
                    except OSError:
                        continue
        except OSError:
            continue
    default = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "Lumi AI"
    if (default / "Lumi.exe").exists():
        candidate = default / "unins000.exe"
        return default, f'"{candidate}"' if candidate.is_file() else None
    return None, None


def _root() -> Tk:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def uninstall_mode() -> int:
    root = _root()
    install_dir, uninstall_string = _installed_program()
    if install_dir is None:
        messagebox.showinfo(APP_NAME, "Установленная Lumi AI не найдена. Удалять нечего.", parent=root)
        root.destroy()
        return 0
    if not uninstall_string:
        messagebox.showerror(APP_NAME, f"Найден каталог Lumi, но штатный деинсталлятор не найден:\n{install_dir}\n\nНичего не удалено.", parent=root)
        root.destroy()
        return 2

    approved = messagebox.askyesno(
        "Удалить Lumi AI?",
        "Найдена установленная Lumi AI.\n\n"
        "Удалить программу, её файлы и ярлыки?\n"
        "Заметки и пользовательские данные пока останутся на компьютере.",
        icon="warning",
        parent=root,
    )
    if not approved:
        root.destroy()
        return 0

    # Inno Setup uninstall strings are quoted executable paths, optionally followed by args.
    import shlex
    command = shlex.split(uninstall_string, posix=False)
    if not command:
        messagebox.showerror(APP_NAME, "Не удалось прочитать команду удаления.", parent=root)
        root.destroy()
        return 2
    executable = command[0].strip('"')
    args = command[1:]
    if not any(arg.lower().startswith("/uninstall") for arg in args):
        args.append("/UNINSTALL")
    try:
        subprocess.Popen([executable, *args])
    except OSError as exc:
        messagebox.showerror(APP_NAME, f"Не удалось запустить деинсталлятор:\n{exc}", parent=root)
        root.destroy()
        return 2

    data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Lumi" / "data"
    if data_dir.exists():
        delete_data = messagebox.askyesno(
            "Удалить заметки и данные?",
            f"Удалить также локальные данные Lumi, включая заметки?\n\n{data_dir}\n\n"
            "Это действие нельзя отменить. Если сомневаешься, нажми «Нет».",
            icon="warning",
            parent=root,
        )
        if delete_data:
            messagebox.showinfo(
                APP_NAME,
                "После завершения удаления программы закройте это окно и удалите папку данных вручную, "
                "если она осталась:\n" + str(data_dir),
                parent=root,
            )
    root.destroy()
    return 0


def update_mode() -> int:
    root = _root()
    install_dir, _ = _installed_program()
    if install_dir is None:
        messagebox.showinfo(
            APP_NAME,
            "Lumi AI не найдена. Для первой установки скачай Lumi-Setup из раздела Releases GitHub.",
            parent=root,
        )
        root.destroy()
        return 0

    try:
        release = json.loads(_http(LATEST_API).decode("utf-8"))
        assets = release.get("assets", [])
        installer_asset = next((a for a in assets if a.get("name", "").startswith("Lumi-Setup-") and a.get("name", "").endswith(".exe")), None)
        checksum_asset = next((a for a in assets if a.get("name") == "SHA256SUMS.txt"), None)
        if not installer_asset or not checksum_asset:
            raise RuntimeError("В последнем релизе не найден установщик или файл SHA256SUMS.txt.")
        installer_name = installer_asset["name"]
        checksum_text = _http(checksum_asset["browser_download_url"]).decode("utf-8", errors="replace")
        expected = None
        for line in checksum_text.splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[1].lstrip("*") == installer_name:
                expected = parts[0].lower()
                break
        if not expected or len(expected) != 64:
            raise RuntimeError("Не удалось найти SHA-256 установщика.")
        with tempfile.TemporaryDirectory(prefix="lumi-update-") as temp_dir:
            installer_path = Path(temp_dir) / installer_name
            installer_path.write_bytes(_http(installer_asset["browser_download_url"], timeout=180))
            actual = hashlib.sha256(installer_path.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError("Контрольная сумма установщика не совпала. Обновление отменено.")
            messagebox.showinfo(
                APP_NAME,
                f"Найдена версия {release.get('tag_name', 'новая версия')}.\n"
                "Проверка целостности прошла успешно. Lumi закроется, затем запустится установщик обновления.",
                parent=root,
            )
            # Keep the downloaded installer after the temporary directory is removed.
            persistent_installer = Path(tempfile.gettempdir()) / installer_name
            persistent_installer.write_bytes(installer_path.read_bytes())
        root.destroy()
        subprocess.Popen([
            str(persistent_installer),
            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        ], close_fds=True)
        return 0
    except urllib.error.HTTPError as exc:
        message = (
            "Пока нет опубликованного релиза Lumi AI.\n"
            "Сначала нужно выпустить первую версию на GitHub."
            if exc.code == 404
            else f"GitHub вернул ошибку HTTP {exc.code}."
        )
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        message = f"Не удалось обновить Lumi AI:\n{exc}"
    except Exception as exc:
        message = f"Не удалось обновить Lumi AI:\n{exc}"
    messagebox.showwarning(APP_NAME, message, parent=root)
    root.destroy()
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Lumi AI updater and maintenance utility")
    parser.add_argument("--update", action="store_true", help="check for and install the latest release")
    args = parser.parse_args()
    if args.update:
        return update_mode()
    return uninstall_mode()


if __name__ == "__main__":
    raise SystemExit(main())
