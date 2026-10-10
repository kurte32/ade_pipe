"""Malware scan result lookup (ADR-003).

`defender`: Microsoft Defender for Storage on-upload scanning writes a blob index tag on the
staging blob; we read it. `none`: local development only; the production guard in Settings
refuses it.
"""

from __future__ import annotations

from typing import Literal, Protocol

import structlog

from app.core.config import Settings
from app.core.storage import BlobStore

ScanResult = Literal["clean", "malicious", "pending", "error"]
DEFENDER_TAG = "Malware Scanning scan result"
log = structlog.get_logger()


class Scanner(Protocol):
    def result(self, path: str) -> ScanResult: ...


class NoScanner:
    _warned = False

    def result(self, path: str) -> ScanResult:
        if not NoScanner._warned:
            log.warning(
                "scan_disabled", reason="SCAN_MODE=none: files are promoted without scanning"
            )
            NoScanner._warned = True
        return "clean"


class DefenderScanner:
    def __init__(self, store: BlobStore) -> None:
        self._store = store

    def result(self, path: str) -> ScanResult:
        info = self._store.info("staging", path)
        if info is None:
            return "error"
        value = info.tags.get(DEFENDER_TAG)
        if value is None:
            return "pending"
        if value == "No threats found":
            return "clean"
        if value == "Malicious":
            return "malicious"
        log.error("scan_result_unexpected", value=value)
        return "error"


def get_scanner(settings: Settings, store: BlobStore) -> Scanner:
    if settings.scan_mode == "defender":
        return DefenderScanner(store)
    return NoScanner()
