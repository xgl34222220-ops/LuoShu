# Android dynamic Google Sans overlay

LuoShu v2.1.3 handles Android 12+ downloadable Google Sans named families during `post-fs-data`.

The runtime keeps signed `/data/fonts/files` font payloads untouched. It filters only Google/Product Sans named-family declarations from `/data/fonts/config/config.xml`, injects matching 400/500/700 families into the active system `fonts.xml`, and bind-mounts the generated XML views before `FontManagerService` builds its map. Switching to the default font or uninstalling removes the bind mounts and generated state.
