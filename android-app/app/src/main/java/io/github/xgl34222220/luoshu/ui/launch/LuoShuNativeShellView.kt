package io.github.xgl34222220.luoshu.ui.launch

import android.content.Context
import android.graphics.Typeface
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import io.github.xgl34222220.luoshu.R

/** A cheap, noninteractive preparation frame, never home or a copied splash logo. */
internal class LuoShuNativeShellView(context: Context) : LinearLayout(context) {
    init {
        orientation = VERTICAL
        setBackgroundColor(context.getColor(R.color.launch_background))
        val inset = (16 * resources.displayMetrics.density).toInt()
        setPadding(inset, inset, inset, inset)
        addView(TextView(context).apply {
            text = "洛书"
            textSize = 26f
            setTextColor(context.getColor(R.color.launch_ink))
            typeface = Typeface.create("sans-serif", Typeface.BOLD)
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        })
        addView(TextView(context).apply {
            text = "正在准备界面"
            textSize = 14f
            setTextColor(context.getColor(R.color.launch_ink))
            setPadding(0, inset, 0, 0)
        })
        ViewCompat.setOnApplyWindowInsetsListener(this) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(inset + bars.left, inset + bars.top, inset + bars.right, inset + bars.bottom)
            insets
        }
    }
}
