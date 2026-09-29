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
        // Compile-only legacy Xposed API. The runtime classes are provided by LSPosed.
        maven(url = "https://api.xposed.info/")
    }
}

rootProject.name = "LuoShuHybrid"
include(":app")
