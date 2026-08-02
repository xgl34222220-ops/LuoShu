# LuoShu uses no reflection-based serialization framework. Keep rules are
# intentionally minimal; Android/Compose consumer rules are supplied by their
# dependencies.

# Invoked directly through app_process after Android boot. R8 must preserve the
# class name and the public static main method even though the App UI never calls it.
-keep class io.github.xgl34222220.luoshu.FontProbeCli {
    public static void main(java.lang.String[]);
}
