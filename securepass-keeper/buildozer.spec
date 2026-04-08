[app]

title = SecurePass Keeper
package.name = securepasskeeper
package.domain = org.securepass

source.dir = .
source.include_exts = py

version = 1.0.0
requirements = python3,kivy,cryptography

orientation = portrait
fullscreen = 0

android.permissions = WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

android.api = 30
android.minapi = 21
android.ndk = 23b
android.sdk = 30

[buildozer]

log_level = 2
warn_on_root = 1