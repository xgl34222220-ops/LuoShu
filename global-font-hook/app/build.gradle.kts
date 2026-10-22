import java.util.Properties

plugins {
    id("com.android.application")
}

// The companion follows the LuoShu module version so a build can be matched to its module.
val moduleProperties = Properties().apply {
    rootProject.projectDir.parentFile.resolve("module.prop").inputStream().use { load(it) }
}
val moduleVersionCode = moduleProperties.getProperty("versionCode")?.toIntOrNull()
    ?: error("module.prop has an invalid versionCode")
val moduleVersion = moduleProperties.getProperty("version") ?: error("module.prop is missing version")

val releaseStoreFile = providers.environmentVariable("LUOSHU_KEYSTORE_FILE").orNull
val releaseStorePassword = providers.environmentVariable("LUOSHU_KEYSTORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("LUOSHU_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("LUOSHU_KEY_PASSWORD").orNull
val hasReleaseSigning = listOf(releaseStoreFile, releaseStorePassword, releaseKeyAlias, releaseKeyPassword)
    .all { !it.isNullOrBlank() }

android {
    namespace = "io.github.xgl34222220.luoshu.globalfont"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.xgl34222220.luoshu.globalfont"
        minSdk = 28
        targetSdk = 36
        versionCode = moduleVersionCode * 100 + 50
        versionName = moduleVersion.removePrefix("v") + "-globalfont"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // Instrumented tests open their test fonts with AssetManager.openFd, which needs them stored.
    androidResources {
        noCompress += listOf("ttf")
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = file(releaseStoreFile!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
            }
        }
    }

    buildTypes {
        getByName("debug") {
            // No minification: the Xposed entry is loaded by name from assets/xposed_init.
            isMinifyEnabled = false
        }
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = if (hasReleaseSigning) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    compileOnly("de.robv.android.xposed:api:82")
    testImplementation("junit:junit:4.13.2")
    // Instrumented coverage checks only (API 28/29/34/35 emulators); nothing here ships in the module APK.
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.core:core:1.13.1")
}
