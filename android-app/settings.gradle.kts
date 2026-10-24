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
        // Classic XposedBridge API for :global-font-hook (compileOnly; LSPosed provides it at runtime).
        maven("https://api.xposed.info/") {
            content { includeGroup("de.robv.android.xposed") }
        }
    }
}

rootProject.name = "LuoShuHybrid"
include(":app")
// LSPosed global-font module, shipped inside the main App (isolated code, loaded only by LSPosed).
include(":global-font-hook")
