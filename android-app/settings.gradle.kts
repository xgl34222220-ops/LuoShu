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
        // Legacy Xposed API 82 is compile-only and is supplied by Vector/LSPosed at runtime.
        maven("https://api.xposed.info/")
    }
}

rootProject.name = "LuoShuHybrid"
include(":app")
