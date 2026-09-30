plugins { id("com.android.application") }
android {
    namespace = "io.github.xgl34222220.luoshu.fontcontract"
    compileSdk = 36
    defaultConfig {
        applicationId = "io.github.xgl34222220.luoshu.fontcontract"
        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = "experiment-only"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
