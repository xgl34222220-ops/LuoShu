import unittest
from framework_cycle import FrameworkCycle

class Fake:
    def __init__(self):self.calls=[];self.pid='12';self.state='running';self.now=0;self.enforcing='Enforcing';self.stale=False;self.activity='Service activity: found'
    def __call__(self,*args,**kwargs):
        self.calls.append(args);c=args[1:]
        values={('getprop','ro.kernel.qemu'):'1',('getprop','ro.build.version.sdk'):'36',('id','-u'):'0',('getenforce',):self.enforcing,('getprop','ro.zygote'):'zygote64',('readlink','/proc/self/ns/mnt'):'mnt:1',('readlink','/proc/1/ns/mnt'):'mnt:1',('getprop','init.svc.zygote'):self.state,('pidof','system_server'):self.pid,('service','check','activity'):self.activity}
        if c==('stop','zygote'):self.pid='';self.state='stopped';return b''
        if c==('start','zygote'):self.pid='12' if self.stale else '13';self.state='running';return b''
        if c[:2]==('service','check') and c[2]!='activity':return ('Service '+c[2]+': found').encode()
        if c[0]=='cat':return (self.pid+' (system_server) '+' '.join(['0']*19+['100'])).encode()
        return values[c].encode()
    def sleep(self,n):self.now+=n

class Test(unittest.TestCase):
    def setup_cycle(self,approved=True):
        f=Fake();return f,FrameworkCycle(f,approved=approved,clock=lambda:f.now,sleep=f.sleep)
    def test_no_approval_no_device_calls(self):
        f,c=self.setup_cycle(False)
        with self.assertRaises(PermissionError):c.stop()
        self.assertEqual(f.calls,[])
    def test_only_explicit_zygote_control(self):
        f,c=self.setup_cycle();c.stop();r=c.start()
        self.assertNotEqual(r['oldSystemServer'],r['newSystemServer'])
        self.assertEqual([x for x in f.calls if x[1] in ('stop','start')],[('shell','stop','zygote'),('shell','start','zygote')])
    def test_old_process_is_not_readiness(self):
        f,c=self.setup_cycle();f.stale=True;c.stop()
        with self.assertRaises(TimeoutError):c.start()
        self.assertTrue(c.stopped);self.assertEqual(f.now,120)
    def test_missing_activity_is_not_readiness(self):
        f,c=self.setup_cycle();f.activity='Service activity: not found';c.stop()
        with self.assertRaises(TimeoutError):c.start()
        self.assertTrue(c.stopped)
    def test_enforcing_required(self):
        f,c=self.setup_cycle();f.enforcing='Permissive'
        with self.assertRaises(RuntimeError):c.stop()
        self.assertFalse(any(x[1]=='stop' for x in f.calls))
    def test_unowned_start_rejected(self):
        f,c=self.setup_cycle()
        with self.assertRaises(RuntimeError):c.start()
        self.assertFalse(any(x[1]=='start' for x in f.calls))

if __name__=='__main__':unittest.main()
