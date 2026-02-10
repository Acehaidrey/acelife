from __future__ import annotations

import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass
class GoogleSheetsDownloader:
    """Lightweight downloader for public Google Sheets tabs.

    Uses the standard export endpoints (CSV or XLSX) for a sheet id + gid.
    """

    sheet_id: str

    def _export_url(self, gid: str, fmt: str) -> str:
        params = {"format": fmt, "gid": gid}
        query = urllib.parse.urlencode(params)
        return f"https://docs.google.com/spreadsheets/d/{self.sheet_id}/export?{query}"

    def download_csv(self, gid: str, out_path: str) -> str:
        url = self._export_url(gid, "csv")
        return self._download(url, out_path)

    def download_xlsx(self, gid: str, out_path: str) -> str:
        url = self._export_url(gid, "xlsx")
        return self._download(url, out_path)

    def _download(self, url: str, out_path: str) -> str:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        with open(out_path, "wb") as f:
            f.write(data)
        return out_path


def download_sheet_entry(entry: dict) -> str:
    downloader = GoogleSheetsDownloader(entry["sheet_id"])
    fmt = entry.get("format", "csv")
    out_path = entry["out"]
    if fmt == "xlsx":
        downloader.download_xlsx(entry["gid"], out_path)
    else:
        downloader.download_csv(entry["gid"], out_path)
    return out_path
