plugins {
    id("com.android.library")
}

// LSPosed global-font module built into the main LuoShu App (io.github.xgl34222220.luoshu / .debug).
// The App depends on this library; LSPosed loads HookEntry (assets/xposed_init) from the App APK
// only inside processes the user ticked in the module scope.
android {
    namespace = "io.github.xgl34222220.luoshu.globalfont"
    compileSdk = 36

    defaultConfig {
        minSdk = 28
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        consumerProguardFiles("consumer-rules.pro")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        // The App's debug build type adds the ".debug" applicationIdSuffix; the hook side reads the
        // module preferences (XSharedPreferences) from whichever App package carries it.
        getByName("debug") {
            buildConfigField("String", "HOST_PACKAGE", "\"io.github.xgl34222220.luoshu.debug\"")
        }
        getByName("release") {
            buildConfigField("String", "HOST_PACKAGE", "\"io.github.xgl34222220.luoshu\"")
        }
    }

    // Instrumented tests open their test fonts with AssetManager.openFd, which needs them stored.
    androidResources {
        noCompress += listOf("ttf")
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
    // Instrumented coverage checks only (API 28/29/34/35 emulators); nothing here ships in the App.
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.core:core:1.13.1")
}
