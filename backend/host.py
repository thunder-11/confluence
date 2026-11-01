"""Declared reference-machine metadata for reproducible measurement reports."""

import os
import platform
import sys


def host_info():
    memory = None
    try:
        if os.name == "nt":
            import ctypes

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
        "processor": platform.processor(),
        "logicalCpuCount": os.cpu_count(),
        "installedRamBytes": memory,
        "python": sys.version,
    }
