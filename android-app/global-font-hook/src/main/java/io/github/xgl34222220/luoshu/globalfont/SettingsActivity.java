package io.github.xgl34222220.luoshu.globalfont;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

/*
 * Settings of the built-in LSPosed module (opened from 设置 → 安全与维护 or LSPosed's module
 * settings): switches + explanation. Plain framework views, no AndroidX; runs only when opened.
 */
public final class SettingsActivity extends Activity {
    private SharedPreferences prefs;
    private boolean activated;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = openPrefs();

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        root.setPadding(pad, pad, pad, pad);

        TextView title = text(getString(R.string.gfh_title), 22);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);
        root.addView(text(getString(activated || ModuleStatus.isModuleActive()
                ? R.string.gfh_status_active : R.string.gfh_status_inactive), 14));
        if (ModuleStatus.legacyCompanionInstalled(this)) {
            root.addView(text(getString(R.string.gfh_legacy_installed), 13));
        }

        root.addView(toggle(R.string.gfh_toggle_enabled, ModuleConfig.KEY_ENABLED, ModuleConfig.DEFAULT_ENABLED));
        root.addView(toggle(R.string.gfh_toggle_app_fonts, ModuleConfig.KEY_APP_FONTS, ModuleConfig.DEFAULT_APP_FONTS));
        Switch monoSwitch = toggle(R.string.gfh_toggle_mono_slot, ModuleConfig.KEY_MONO_SLOT, ModuleConfig.DEFAULT_MONO_SLOT);
        root.addView(monoSwitch);
        boolean monoOk = MonoProbe.systemMonospaceIsFixedPitch();
        monoSwitch.setEnabled(monoOk); // a proportional "monospace" slot would break alignment
        root.addView(text(getString(monoOk ? R.string.gfh_mono_slot_hint : R.string.gfh_mono_slot_unavailable), 13));
        root.addView(toggle(R.string.gfh_toggle_web_fonts, ModuleConfig.KEY_WEB_FONTS, ModuleConfig.DEFAULT_WEB_FONTS));
        root.addView(toggle(R.string.gfh_toggle_web_unknown, ModuleConfig.KEY_WEB_BLOCK_UNKNOWN, ModuleConfig.DEFAULT_WEB_BLOCK_UNKNOWN));
        root.addView(toggle(R.string.gfh_toggle_verbose, ModuleConfig.KEY_VERBOSE, ModuleConfig.DEFAULT_VERBOSE));

        root.addView(text(getString(R.string.gfh_explain), 14));
        StringBuilder scope = new StringBuilder(getString(R.string.gfh_scope_title)).append('\n');
        for (String pkg : getResources().getStringArray(R.array.gfh_recommended_scope)) {
            if (ModuleConfig.isLuoShuApp(pkg)) continue; // the App itself: only lets it show "已激活"
            scope.append("• ").append(pkg).append('\n');
        }
        root.addView(text(scope.toString(), 14));
        root.addView(text(getString(R.string.gfh_limits), 13));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(scroll);
    }

    private SharedPreferences openPrefs() {
        SharedPreferences p = worldReadablePrefs(this);
        activated = p != null;
        return p != null ? p : getSharedPreferences(ModuleConfig.PREFS, Context.MODE_PRIVATE);
    }

    /*
     * LSPosed (xposedsharedprefs) makes the module preferences readable by hooked apps. Returns null
     * when the module is not active (the framework then rejects MODE_WORLD_READABLE).
     */
    @SuppressWarnings("deprecation")
    static SharedPreferences worldReadablePrefs(Context context) {
        try {
            return context.getSharedPreferences(ModuleConfig.PREFS, Context.MODE_WORLD_READABLE);
        } catch (SecurityException e) {
            return null;
        }
    }

    private Switch toggle(int label, String key, boolean def) {
        Switch s = new Switch(this);
        s.setText(label);
        s.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        s.setChecked(prefs.getBoolean(key, def));
        s.setPadding(0, dp(10), 0, dp(10));
        s.setOnCheckedChangeListener((b, checked) -> prefs.edit().putBoolean(key, checked).apply());
        return s;
    }

    private TextView text(String s, int sp) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setPadding(0, dp(8), 0, dp(8));
        return t;
    }

    private int dp(int v) {
        return (int) (v * getResources().getDisplayMetrics().density + 0.5f);
    }
}
