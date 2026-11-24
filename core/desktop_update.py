"""Check and stage the official Windows installer from GitHub Releases."""

import hashlib
import re
import threading
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

import config

_UPDATE_LOCK = threading.Lock()


@dataclass
class UpdateInfo:
    has_update: bool
    latest_version: str
    release_notes: str
    download_url: str = ""
    file_size: int = 0
    digest: str = ""


def version_tuple(value):
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("发行版本号无效")
    return tuple(map(int, value.split(".")))


def check_update():
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest")
        response.raise_for_status()
    release = response.json()
    tag = release["tag_name"]
    version = tag.removeprefix("v")
    info = UpdateInfo(version_tuple(version) > version_tuple(config.VERSION), version, release.get("body") or "")
    if not info.has_update:
        return info
    name = f"Dayflow_{version}_x64-setup.exe"
    url = f"https://github.com/{config.GITHUB_REPO}/releases/download/{tag}/{name}"
    for asset in release.get("assets", ()):
        if asset.get("name", "").lower() != name.lower():
            continue
        candidate = asset.get("browser_download_url", "")
        # GitHub canonical names can vary in capitalization.
        if candidate.lower() != url.lower():
            continue
        info.download_url = candidate
        info.file_size = int(asset.get("size") or 0)
        digest = asset.get("digest") or ""
        if re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            info.digest = digest[7:]
        break
    return info


def stage_update():
    if not _UPDATE_LOCK.acquire(blocking=False):
        raise ValueError("更新已在下载")
    try:
        info = check_update()
        if not info.has_update or not info.digest or not 0 < info.file_size <= 500 * 1024 ** 2:
            raise ValueError("当前发行版没有可校验的 Windows 安装包")
        folder = config.APP_DATA_DIR / "updates"
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / "setup.part"
        try:
            digest = hashlib.sha256()
            size = 0
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                with client.stream("GET", info.download_url) as resp, part.open("wb") as file:
                    resp.raise_for_status()
                    actual = urlsplit(str(resp.url))
                    if actual.scheme != "https" or actual.hostname not in {
                        "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
                    }:
                        raise ValueError("安装包下载地址无效")
                    for block in resp.iter_bytes():
                        size += len(block)
                        if size > info.file_size:
                            raise ValueError("安装包大小与发行信息不一致")
                        digest.update(block)
                        file.write(block)
            if size != info.file_size or digest.hexdigest() != info.digest:
                raise ValueError("安装包校验失败")
            part.replace(folder / "setup.exe")
        finally:
            part.unlink(missing_ok=True)
        return info.digest
    finally:
        _UPDATE_LOCK.release()
