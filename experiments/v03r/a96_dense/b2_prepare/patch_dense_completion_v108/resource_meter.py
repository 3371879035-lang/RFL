"""Read-only Win32 process/system memory counters, no third-party runtime.

Structures follow Microsoft PROCESS_MEMORY_COUNTERS_EX and MEMORYSTATUSEX:
https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex
https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex
"""
import ctypes as C
import os
import time


class ProcessMemory(C.Structure):
    _fields_ = [('cb', C.c_uint32), ('PageFaultCount', C.c_uint32)] + [
        (name, C.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
        'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
        'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]


class SystemMemory(C.Structure):
    _fields_ = [('dwLength', C.c_uint32), ('dwMemoryLoad', C.c_uint32)] + [
        (name, C.c_uint64) for name in ('ullTotalPhys', 'ullAvailPhys', 'ullTotalPageFile',
        'ullAvailPageFile', 'ullTotalVirtual', 'ullAvailVirtual', 'ullAvailExtendedVirtual')]


kernel = C.WinDLL('kernel32', use_last_error=True)
psapi = C.WinDLL('psapi', use_last_error=True)
kernel.GetCurrentProcess.restype = C.c_void_p
psapi.GetProcessMemoryInfo.argtypes = (C.c_void_p, C.POINTER(ProcessMemory), C.c_uint32)
psapi.GetProcessMemoryInfo.restype = C.c_int
kernel.GlobalMemoryStatusEx.argtypes = (C.POINTER(SystemMemory),)
kernel.GlobalMemoryStatusEx.restype = C.c_int


def sample():
    process, system = ProcessMemory(), SystemMemory()
    process.cb, system.dwLength = C.sizeof(process), C.sizeof(system)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), C.byref(process), process.cb):
        raise C.WinError(C.get_last_error())
    if not kernel.GlobalMemoryStatusEx(C.byref(system)):
        raise C.WinError(C.get_last_error())
    return {'pid': os.getpid(), 'working_set_bytes': process.WorkingSetSize,
            'peak_working_set_bytes': process.PeakWorkingSetSize,
            'private_bytes': process.PrivateUsage, 'peak_commit_bytes': process.PeakPagefileUsage,
            'available_physical_bytes': system.ullAvailPhys, 'total_physical_bytes': system.ullTotalPhys,
            'cpu_seconds': time.process_time()}


if __name__ == '__main__':
    import json
    print(json.dumps(sample()))
