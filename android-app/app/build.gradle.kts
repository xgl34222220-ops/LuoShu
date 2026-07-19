import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

val moduleProperties = Properties().apply {
    val moduleProp = rootProject.projectDir.parentFile.resolve("module.prop")
    moduleProp.inputStream().use { load(it) }
}
val moduleVersion = moduleProperties.getProperty("version")
    ?: error("module.prop is missing version")
val moduleVersionCode = moduleProperties.getProperty("versionCode")?.toIntOrNull()
    ?: error("module.prop has an invalid versionCode")
val appVersionName = moduleVersion
    .removePrefix("v")
    .lowercase()
    .replace(Regex("[^0-9a-z.]+"), "-")
    .trim('-')
val releaseStoreFile = providers.environmentVariable("LUOSHU_KEYSTORE_FILE").orNull
val releaseStorePassword = providers.environmentVariable("LUOSHU_KEYSTORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("LUOSHU_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("LUOSHU_KEY_PASSWORD").orNull
val hasReleaseSigning = listOf(
    releaseStoreFile,
    releaseStorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "io.github.xgl34222220.luoshu"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.xgl34222220.luoshu"
        minSdk = 28
        targetSdk = 36
        // module.prop is the only version source shared by the module, native App and CI artifacts.
        versionCode = moduleVersionCode * 100 + 1
        versionName = appVersionName
    }

    buildFeatures {
        compose = true
        buildConfig = true
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
                enableV4Signing = true
            }
        }
    }

    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        getByName("release") {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources.excludes += setOf(
            "/META-INF/{AL2.0,LGPL2.1}",
            "/META-INF/LICENSE*",
            "/META-INF/NOTICE*"
        )
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.03.00")
    implementation(composeBom)

    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.datastore:datastore-preferences:1.2.1")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("com.materialkolor:material-kolor:2.0.0")
    implementation("dev.chrisbanes.haze:haze:1.6.10")
    implementation("dev.chrisbanes.haze:haze-materials:1.6.10")

    testImplementation("junit:junit:4.13.2")
}
