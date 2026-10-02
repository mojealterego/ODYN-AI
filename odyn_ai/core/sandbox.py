from __future__ import annotations
import shutil, subprocess

class SandboxRunner:
    """Real isolation boundary for high-risk local tools; unavailable means deny."""
    def __init__(self, *, backend:str="auto"):
        if backend=="auto": backend="docker" if shutil.which("docker") else ("bwrap" if shutil.which("bwrap") else "unavailable")
        self.backend=backend
    def require_available(self)->None:
        if self.backend=="unavailable": raise PermissionError("Brak dostępnego backendu izolacji dla narzędzia high_risk.")
    def build_command(self,command:list[str],*,workdir:str="/workspace",image:str="python:3.13-slim")->list[str]:
        self.require_available()
        if not command: raise ValueError("Polecenie sandbox nie może być puste.")
        if self.backend=="docker":
            return ["docker","run","--rm","--network=none","--read-only","--cap-drop=ALL","--security-opt=no-new-privileges","--pids-limit=64","--memory=256m","--cpus=1","--tmpfs","/tmp:rw,noexec,nosuid,size=64m","-v",f"{workdir}:/workspace:rw","-w","/workspace",image,*command]
        if self.backend=="bwrap":
            return ["bwrap","--die-with-parent","--unshare-all","--new-session","--ro-bind","/usr","/usr","--ro-bind","/bin","/bin","--ro-bind","/lib","/lib","--ro-bind","/lib64","/lib64","--proc","/proc","--dev","/dev","--tmpfs","/tmp","--bind",workdir,"/workspace","--chdir","/workspace","--",*command]
        raise PermissionError("Nieobsługiwany backend sandboxa.")
    def run(self,command:list[str],*,workdir:str="/workspace",image:str="python:3.13-slim",timeout:int=30)->subprocess.CompletedProcess[str]:
        return subprocess.run(self.build_command(command,workdir=workdir,image=image),cwd=workdir,capture_output=True,text=True,timeout=timeout,check=False)
