"""Declared reference-machine metadata for reproducible measurement reports."""

import os
import platform
import sys


def host_info():
    memory = None
    processor = platform.processor()
    try:
        if os.name == "nt":
            import ctypes
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                processor = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()

            kib = ctypes.c_ulonglong()
            if ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(
                ctypes.byref(kib)
            ):
                memory = kib.value * 1024
        else:
            memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        pass
    return {
        "platform": platform.platform(),
        "processor": processor,
        "logicalCpuCount": os.cpu_count(),
        "installedRamBytes": memory,
        "python": sys.version,
    }


def process_memory(pid):
    """Native peak and current RSS, without a third-party monitoring service."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                ] + [
                    (name, ctypes.c_size_t)
                    for name in (
                        "PeakWorkingSetSize",
                        "WorkingSetSize",
                        "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage",
                        "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage",
                        "PagefileUsage",
                        "PeakPagefileUsage",
                    )
                ]

            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.OpenProcess.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x410, False, pid)
            if not handle:
                return {}
            try:
                counters = Counters()
                counters.cb = ctypes.sizeof(counters)
                get_info = ctypes.windll.psapi.GetProcessMemoryInfo
                get_info.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(Counters),
                    wintypes.DWORD,
                ]
                if get_info(handle, ctypes.byref(counters), counters.cb):
                    return {
                        "workingSetBytes": counters.WorkingSetSize,
                        "peakWorkingSetBytes": counters.PeakWorkingSetSize,
                    }
            finally:
                kernel.CloseHandle(handle)
        elif sys.platform.startswith("linux"):
            from pathlib import Path

            values = {
                line.split(":", 1)[0]: int(line.split()[1]) * 1024
                for line in Path(f"/proc/{pid}/status").read_text().splitlines()
                if line.startswith(("VmRSS:", "VmHWM:"))
            }
            return {
                "workingSetBytes": values.get("VmRSS"),
                "peakWorkingSetBytes": values.get("VmHWM"),
            }
    except (OSError, ValueError, AttributeError):
        pass
    return {}
