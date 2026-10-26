"""Own-process cancellation for isolated local workers (standard library only).

Use ``process = spawn(argv, stdout=PIPE, stderr=DEVNULL, ...)`` as a Popen.
Always call ``process.close()`` in finally; cancellation uses terminate_tree().
Windows workers are assigned to an anonymous Job Object before their first thread
is resumed. Job closure terminates its worker descendants, never another app.
"""
from __future__ import annotations
import ctypes
import os
import signal
import subprocess
import threading
from ctypes import c_uint32 as DWORD, c_int32 as LONG, c_uint64 as ULONG64
from ctypes import c_size_t as SIZE_T, c_void_p as HANDLE

class _BasicLimit(ctypes.Structure):
    _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),('LimitFlags',DWORD),('MinimumWorkingSetSize',SIZE_T),('MaximumWorkingSetSize',SIZE_T),('ActiveProcessLimit',DWORD),('Affinity',SIZE_T),('PriorityClass',DWORD),('SchedulingClass',DWORD)]
class _IOCounters(ctypes.Structure):
    _fields_=[(name,ULONG64) for name in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
class _ExtendedLimit(ctypes.Structure):
    _fields_=[('BasicLimitInformation',_BasicLimit),('IoInfo',_IOCounters),('ProcessMemoryLimit',SIZE_T),('JobMemoryLimit',SIZE_T),('PeakProcessMemoryUsed',SIZE_T),('PeakJobMemoryUsed',SIZE_T)]
class _ThreadEntry(ctypes.Structure):
    _fields_=[('dwSize',DWORD),('cntUsage',DWORD),('th32ThreadID',DWORD),('th32OwnerProcessID',DWORD),('tpBasePri',LONG),('tpDeltaPri',LONG),('dwFlags',DWORD)]

class WindowsJob:
    """An anonymous, non-inheritable Windows Job Object owned by this object."""
    def __init__(self):
        if os.name!='nt':raise OSError('Windows Job Objects require Windows')
        self._api=ctypes.WinDLL('kernel32',use_last_error=True)
        declarations={
            'CreateJobObjectW':([ctypes.c_void_p,ctypes.c_wchar_p],HANDLE),
            'SetInformationJobObject':([HANDLE,ctypes.c_int,ctypes.c_void_p,DWORD],LONG),
            'AssignProcessToJobObject':([HANDLE,HANDLE],LONG),
            'TerminateJobObject':([HANDLE,DWORD],LONG),
            'CloseHandle':([HANDLE],LONG),
            'CreateToolhelp32Snapshot':([DWORD,DWORD],HANDLE),
            'Thread32First':([HANDLE,ctypes.POINTER(_ThreadEntry)],LONG),
            'Thread32Next':([HANDLE,ctypes.POINTER(_ThreadEntry)],LONG),
            'OpenThread':([DWORD,LONG,DWORD],HANDLE),
            'ResumeThread':([HANDLE],DWORD),
        }
        for name,(args,result) in declarations.items():
            f=getattr(self._api,name);f.argtypes=args;f.restype=result
        self._lock=threading.Lock();self._handle=self._api.CreateJobObjectW(None,None)
        if not self._handle:self._raise()
        info=_ExtendedLimit();info.BasicLimitInformation.LimitFlags=0x00002000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._api.SetInformationJobObject(self._handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            error=ctypes.get_last_error();self.close();raise ctypes.WinError(error)
    @staticmethod
    def _raise():raise ctypes.WinError(ctypes.get_last_error())
    def assign(self,process):
        # Popen owns this process handle; the Job never closes that handle itself.
        if not self._api.AssignProcessToJobObject(self._handle,HANDLE(int(process._handle))):self._raise()
    def resume(self,pid):
        # CREATE_SUSPENDED leaves the initial thread stopped, while Popen closes
        # its thread handle. Enumerate only this newly created process's threads.
        snapshot=self._api.CreateToolhelp32Snapshot(0x00000004,0) # TH32CS_SNAPTHREAD
        if snapshot==HANDLE(-1).value or not snapshot:self._raise()
        resumed=False
        try:
            entry=_ThreadEntry();entry.dwSize=ctypes.sizeof(entry)
            more=self._api.Thread32First(snapshot,ctypes.byref(entry))
            while more:
                if entry.th32OwnerProcessID==pid:
                    thread=self._api.OpenThread(0x0002,False,entry.th32ThreadID) # THREAD_SUSPEND_RESUME
                    if not thread:self._raise()
                    try:
                        previous=self._api.ResumeThread(thread)
                        if previous==0xFFFFFFFF:self._raise()
                        if previous>0:resumed=True
                    finally:self._api.CloseHandle(thread)
                entry.dwSize=ctypes.sizeof(entry)
                more=self._api.Thread32Next(snapshot,ctypes.byref(entry))
        finally:self._api.CloseHandle(snapshot)
        if not resumed:raise OSError('Suspended worker initial thread was not found')
    def terminate(self):
        with self._lock:
            if self._handle and not self._api.TerminateJobObject(self._handle,1):self._raise()
    def close(self):
        with self._lock:
            if self._handle:
                handle,self._handle=self._handle,None
                self._api.CloseHandle(handle)
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

class ManagedProcess:
    def __init__(self,process,job=None):self.process,self._job=process,job;self._closed=False;self._lock=threading.Lock()
    def __getattr__(self,name):return getattr(self.process,name)
    def terminate_tree(self,timeout=5):
        with self._lock:
            if self._closed:return
            if self._job:
                self._job.terminate()
                self._job.close();self._job=None
            elif self.process.poll() is None:
                # start_new_session makes this still-live owned PID the group ID.
                # Never signal a group after its leader was reaped (PID reuse).
                try:os.killpg(self.process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            try:self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name!='nt' and self.process.poll() is None:
                    try:os.killpg(self.process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                self.process.wait(timeout=timeout)
    def close(self):
        if self.process.poll() is None:self.terminate_tree()
        with self._lock:
            if self._job:self._job.close();self._job=None
            self._closed=True
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
            if stream is not None:
                try:stream.close()
                except (OSError,ValueError):pass
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def spawn(command,**kwargs):
    """Create an isolated worker; fail closed if containment cannot be established.

    command must be an argv sequence. shell=True is intentionally unsupported.
    Caller may pass normal Popen stdin/stdout/stderr/text/encoding/cwd/env options.
    Windows creationflags are combined with CREATE_NO_WINDOW and CREATE_SUSPENDED.
    """
    if isinstance(command,(str,bytes)) or not command:raise ValueError('argv sequence required')
    if kwargs.get('shell',False):raise ValueError('shell execution is not supported')
    if os.name=='nt':
        job=WindowsJob();process=None
        try:
            kwargs['creationflags']=kwargs.get('creationflags',0)|0x08000000|0x00000004
            process=subprocess.Popen(command,**kwargs)
            job.assign(process);job.resume(process.pid)
            return ManagedProcess(process,job)
        except BaseException:
            # This exact process was created suspended by us; it has never run
            # outside the Job. Failed assignment leaves it suspended until killed.
            if process is not None:
                try:process.terminate();process.wait(timeout=5)
                except (OSError,subprocess.TimeoutExpired):pass
            job.close();raise
    if kwargs.get('start_new_session') is False:raise ValueError('isolated session is required')
    kwargs['start_new_session']=True
    return ManagedProcess(subprocess.Popen(command,**kwargs))
