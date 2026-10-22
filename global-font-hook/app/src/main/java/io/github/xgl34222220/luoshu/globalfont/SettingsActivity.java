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

/** Companion settings: switches + explanation. Plain framework views, no AndroidX. */
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

        TextView title = text(getString(R.string.app_name), 22);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        root.addView(title);
        root.addView(text(getString(activated ? R.string.status_active : R.string.status_inactive), 14));

        root.addView(toggle(R.string.toggle_enabled, ModuleConfig.KEY_ENABLED, ModuleConfig.DEFAULT_ENABLED));
        root.addView(toggle(R.string.toggle_app_fonts, ModuleConfig.KEY_APP_FONTS, ModuleConfig.DEFAULT_APP_FONTS));
        root.addView(toggle(R.string.toggle_web_fonts, ModuleConfig.KEY_WEB_FONTS, ModuleConfig.DEFAULT_WEB_FONTS));
        root.addView(toggle(R.string.toggle_web_unknown, ModuleConfig.KEY_WEB_BLOCK_UNKNOWN, ModuleConfig.DEFAULT_WEB_BLOCK_UNKNOWN));
        root.addView(toggle(R.string.toggle_verbose, ModuleConfig.KEY_VERBOSE, ModuleConfig.DEFAULT_VERBOSE));

        root.addView(text(getString(R.string.explain), 14));
        StringBuilder scope = new StringBuilder(getString(R.string.scope_title)).append('\n');
        for (String pkg : getResources().getStringArray(R.array.recommended_scope)) {
            scope.append("• ").append(pkg).append('\n');
        }
        root.addView(text(scope.toString(), 14));
        root.addView(text(getString(R.string.limits), 13));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root, new ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        setContentView(scroll);
    }

    @SuppressWarnings("deprecation")
    private SharedPreferences openPrefs() {
        try {
            // LSPosed (xposedsharedprefs) makes this readable by hooked apps; throws when the module is not active.
            SharedPreferences p = getSharedPreferences(ModuleConfig.PREFS, Context.MODE_WORLD_READABLE);
            activated = true;
            return p;
        } catch (SecurityException e) {
            activated = false;
            return getSharedPreferences(ModuleConfig.PREFS, Context.MODE_PRIVATE);
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
