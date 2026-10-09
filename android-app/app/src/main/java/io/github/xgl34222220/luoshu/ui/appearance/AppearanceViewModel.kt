package io.github.xgl34222220.luoshu.ui.appearance

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class AppearanceViewModel @JvmOverloads constructor(
    application: Application,
    initialSettings: AppearanceSettings = AppearanceSettings(),
) : AndroidViewModel(application) {
    private val repository = AppearanceRepository(application.applicationContext)

    val settings: StateFlow<AppearanceSettings> = repository.settings.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = initialSettings,
    )

    fun setUiStyle(value: UiStyle) = launch { repository.setUiStyle(value) }
    fun setThemeMode(value: ThemeMode) = launch { repository.setThemeMode(value) }
    fun setSeedArgb(value: Int) = launch { repository.setSeedArgb(value) }
    fun setKolorStyle(value: KolorStyle) = launch { repository.setKolorStyle(value) }
    fun setMonetEnabled(enabled: Boolean) = launch { repository.setMonetEnabled(enabled) }
    fun setAmoledBlack(enabled: Boolean) = launch { repository.setAmoledBlack(enabled) }
    fun setBlurEnabled(enabled: Boolean) = launch { repository.setBlurEnabled(enabled) }
    fun setGlassEnabled(enabled: Boolean) = launch { repository.setGlassEnabled(enabled) }
    fun setFloatingDock(enabled: Boolean) = launch { repository.setFloatingDock(enabled) }
    fun setHighRefreshRate(enabled: Boolean) = launch { repository.setHighRefreshRate(enabled) }

    internal class InitialAppearanceFactory(
        private val application: Application,
        private val settings: AppearanceSettings,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass == AppearanceViewModel::class.java)
            return AppearanceViewModel(application, settings) as T
        }
    }

    private fun launch(block: suspend () -> Unit) {
        viewModelScope.launch { block() }
    }
}

