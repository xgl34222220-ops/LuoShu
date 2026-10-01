"""Bounded Zygote cycle for an explicitly approved disposable API36 VM.

This module is inert until called. It never edits init, policy, properties or
enters another namespace. The caller owns mount rollback before recovery start.
"""
import time

class FrameworkCycle:
    def __init__(self, adb, *, approved=False, clock=time.monotonic, sleep=time.sleep):
        self.adb=adb;self.approved=approved;self.clock=clock;self.sleep=sleep
        self.old=None;self.stopped=False

    def text(self,*args):
        return self.adb('shell',*args,timeout=10).decode().strip()

    def guard(self):
        if not self.approved:raise PermissionError('framework cycle was not approved')
        expected=[(('getprop','ro.kernel.qemu'),'1'),(('getprop','ro.build.version.sdk'),'36'),
                  (('id','-u'),'0'),(('getenforce',),'Enforcing'),(('getprop','ro.zygote'),'zygote64')]
        for command,value in expected:
            if self.text(*command)!=value:raise RuntimeError('framework precondition failed: '+str(command))
        if self.text('readlink','/proc/self/ns/mnt')!=self.text('readlink','/proc/1/ns/mnt'):
            raise RuntimeError('framework cycle requires the existing init namespace')

    def identity(self):
        pid=self.adb('shell','pidof','system_server',timeout=10,check=False).decode().strip()
        if not pid:return None
        if not pid.isdecimal():raise RuntimeError('ambiguous system_server identity')
        stat=self.text('cat','/proc/'+pid+'/stat')
        tail=stat.rsplit(')',1)[1].split()
        return (pid,tail[19])

    def wait(self,predicate,seconds,message):
        deadline=self.clock()+seconds
        while self.clock()<deadline:
            value=predicate()
            if value:return value
            self.sleep(1)
        raise TimeoutError(message)

    def stop(self):
        self.guard();self.old=self.identity()
        if not self.old:raise RuntimeError('system_server missing before cycle')
        # Mark before the command, whose transport can fail after acceptance.
        self.stopped=True
        self.adb('shell','stop','zygote',timeout=15)
        self.wait(lambda:self.text('getprop','init.svc.zygote')=='stopped' and self.identity() is None,
                  30,'zygote did not stop within the budget')

    def start(self):
        self.guard()
        if not self.stopped:raise RuntimeError('start has no owned stop attempt')
        self.adb('shell','start','zygote',timeout=15)
        def ready():
            current=self.identity()
            if not current or current==self.old:return False
            if self.text('getprop','init.svc.zygote')!='running':return False
            for service in ('activity','package','font'):
                if self.text('service','check',service)!='Service '+service+': found':return False
            return current
        current=self.wait(ready,120,'new Android framework did not become ready')
        self.stopped=False
        return {'oldSystemServer':self.old,'newSystemServer':current,'service':'zygote'}
