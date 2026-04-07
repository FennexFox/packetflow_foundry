#!/usr/bin/env python3
"""Shared command-string parsing helpers for retained git mutation workflows."""

from __future__ import annotations

import os
import shlex


def parse_command_argv(command: str) -> list[str] | None:
    text = str(command).strip()
    if not text:
        return None
    if os.name == "nt":
        import ctypes

        argc = ctypes.c_int()
        command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
        command_line_to_argv.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
        local_free = ctypes.windll.kernel32.LocalFree
        local_free.argtypes = [ctypes.c_void_p]
        local_free.restype = ctypes.c_void_p
        argv_ptr = command_line_to_argv(text, ctypes.byref(argc))
        if not argv_ptr:
            return None
        try:
            return [str(argv_ptr[index]) for index in range(argc.value)]
        finally:
            local_free(argv_ptr)
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return None
