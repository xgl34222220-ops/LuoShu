pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // Classic XposedBridge API (compileOnly; provided by LSPosed at runtime).
        maven("https://api.xposed.info/") {
            content { includeGroup("de.robv.android.xposed") }
        }
    }
}

rootProject.name = "LuoShuGlobalFont"
include(":app")
