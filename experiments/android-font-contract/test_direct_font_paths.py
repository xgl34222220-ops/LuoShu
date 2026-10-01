"""Execute the probe's real Java path guard without an Android emulator."""
import os,shutil,subprocess,tempfile,unittest
from pathlib import Path

class DirectFontPathTest(unittest.TestCase):
 def test_actual_java_guard_accepts_only_declared_read_targets(self):
  home=Path(os.environ.get('JAVA_HOME','/nonexistent'))/'bin'
  javac=shutil.which('javac') or (str(home/'javac') if (home/'javac').exists() else None)
  java=shutil.which('java') or (str(home/'java') if (home/'java').exists() else None)
  if not javac or not java:
   if os.environ.get('CI'):self.fail('Java guard regression requires CI JDK')
   self.skipTest('JDK unavailable; CI executes this guard')
  source=Path(__file__).parent/'app/src/main/java/io/github/xgl34222220/luoshu/fontcontract/DirectFontPaths.java'
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);main=root/'DirectFontPathsTest.java'
   main.write_text('''package io.github.xgl34222220.luoshu.fontcontract;
public class DirectFontPathsTest {
 public static void main(String[] args) {
  String[] yes={"/system/fonts/LuoShuFixed-test.ttf","/system/fonts/LuoShu-Original-test.ttc",
   "/system/fonts/NotoColorEmoji.ttf","/system/fonts/AndroidClock.ttf","/system/fonts/DroidSans.ttf",
   "/system/fonts/DroidSans-Bold.ttf","/system/fonts/RobotoStatic-Regular.ttf"};
  String[] no={"/system/fonts/Roboto-Regular.ttf","/system/etc/fonts.xml","/data/local/tmp/test.ttf",
   "/system/fonts/DroidSans.ttf.evil","/system/fonts/LuoShu/foreign.ttf","/system/fonts/LuoShu../secret", ""};
  for(String p:yes)if(!DirectFontPaths.allowed(p))throw new AssertionError("refused declared target: "+p);
  for(String p:no)if(DirectFontPaths.allowed(p))throw new AssertionError("accepted outside target: "+p);
  if(DirectFontPaths.allowed(null))throw new AssertionError("accepted null");
 }
}''')
   subprocess.run([javac,'-d',str(root),str(source),str(main)],check=True,capture_output=True)
   subprocess.run([java,'-cp',str(root),'io.github.xgl34222220.luoshu.fontcontract.DirectFontPathsTest'],check=True,capture_output=True)
if __name__=='__main__':unittest.main()
