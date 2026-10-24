// Emulator integration test for the Feature 1 nBuild replacement. Runs under app_process:
//   app_process -Djava.class.path=DIR/harness.dex /system/bin LsnfHarness DIR
// DIR holds libluoshu_nf_harness.so and the generated fonts. Prints "LSNF-HARNESS PASS" or exits 1.
import android.graphics.fonts.Font;

import java.io.File;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.io.RandomAccessFile;

public final class LsnfHarness {
    static native String probeOriginal(long artMethod);
    static native boolean install(String regular, String bold);
    static native long faceAddress(int idx);
    static native long bufferAddress(ByteBuffer buffer);
    static native long[] lastCall();
    static native int[] stats();

    private static int failures = 0;
    private static String dir;
    private static Method nBuild;
    private static boolean real;

    private static void check(boolean ok, String what) {
        System.out.println((ok ? "ok   " : "FAIL ") + what);
        if (!ok) failures++;
    }

    private static ByteBuffer map(String name) throws Exception {
        try (RandomAccessFile f = new RandomAccessFile(new File(dir, name), "r")) {
            FileChannel ch = f.getChannel();
            return ch.map(FileChannel.MapMode.READ_ONLY, 0, ch.size()).order(ByteOrder.nativeOrder());
        }
    }

    /** Builds one font and returns the native address of the bytes the framework ended up using. */
    private static long build(String name, int weight, boolean italic) throws Exception {
        if (real) {
            Font font = new Font.Builder(new File(dir, name)).setWeight(weight)
                    .setSlant(italic ? 1 : 0).build();
            check(font.getStyle().getWeight() == weight, name + ": weight " + weight + " preserved");
            check((font.getStyle().getSlant() == 1) == italic, name + ": slant preserved");
            return bufferAddress(font.getBuffer());
        }
        ByteBuffer buf = map(name);
        long ret = (long) nBuild.invoke(null, 0L, buf, new File(dir, name).getAbsolutePath(), "", weight, italic, 0);
        check(ret == 0x5151, name + ": original called");
        long[] last = lastCall();
        check(last[1] == weight, name + ": weight " + weight + " passed through");
        check((last[2] == 1) == italic, name + ": italic passed through");
        return last[0];
    }

    public static void main(String[] args) throws Exception {
        dir = args[0];
        System.load(new File(dir, "libluoshu_nf_harness.so").getAbsolutePath());
        System.out.println("sdk=" + android.os.Build.VERSION.SDK_INT);

        nBuild = Font.Builder.class.getDeclaredMethod("nBuild", long.class, ByteBuffer.class, String.class,
                String.class, int.class, boolean.class, int.class);
        nBuild.setAccessible(true);
        long artMethod = 0;
        try {
            Field f = Class.forName("java.lang.reflect.Executable").getDeclaredField("artMethod");
            f.setAccessible(true);
            artMethod = f.getLong(nBuild);
        } catch (Throwable t) {
            System.out.println("artMethod unavailable: " + t);
        }
        String mode = probeOriginal(artMethod);
        real = mode.startsWith("real:");
        System.out.println("mode=" + mode);

        check(install(new File(dir, "LuoShu-400.ttf").getPath(), new File(dir, "LuoShu-700.ttf").getPath()),
                "nBuild replaced with the Android 12+ signature");
        long regular = faceAddress(0), bold = faceAddress(1);

        long a = build("latin_body.ttf", 400, false);
        check(a == regular, "latin body font -> LuoShu regular face");
        a = build("cjk_body.ttf", 700, false);
        check(a == bold, "cjk body font w700 -> LuoShu bold face");
        a = build("latin_body.ttf", 600, true);
        check(a == bold, "w600 italic -> nearest (bold) upright face");
        a = build("pua_only.ttf", 400, false);
        check(a != regular && a != bold && a != 0, "PUA icon font kept");
        a = build("mono_post.ttf", 400, false);
        check(a != regular && a != bold && a != 0, "monospace font kept");
        a = build("color_colr.ttf", 400, false);
        check(a != regular && a != bold && a != 0, "color font kept");

        System.setProperty("luoshu.gfh.active", "1");
        a = build("latin_body.ttf", 400, false);
        check(a != regular && a != bold && a != 0, "global-font-hook marker present -> pass through");

        int[] s = stats();
        System.out.println("stats replaced=" + s[0] + " kept=" + s[1] + " yielded=" + s[2] + " ours=" + s[3]
                + " errors=" + s[4]);
        check(s[0] >= 3 && s[1] >= 3 && s[2] >= 1 && s[4] == 0, "hook counters");
        if (failures == 0) {
            System.out.println("LSNF-HARNESS PASS mode=" + (real ? "real" : "stub"));
        } else {
            System.out.println("LSNF-HARNESS FAIL " + failures);
            System.exit(1);
        }
    }
}
