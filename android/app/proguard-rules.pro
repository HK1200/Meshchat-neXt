-keep class com.chaquo.python.** { *; }
-keep class com.meshchatnext.** { *; }
# Loaded dynamically from Python via jclass("org.meshchatnext.locallink.*").
# R8 strips these in release builds (minifyEnabled) since no Java code
# references them, which silently disables LocalLink/Aware/NFC.
-keep class org.meshchatnext.** { *; }
-keepclassmembers class com.meshchatnext.MainActivity$MeshchatNextAndroidBridge {
    @android.webkit.JavascriptInterface <methods>;
}
-keep class com.hoho.android.usbserial.** { *; }
# Loaded dynamically from Python via jclass("org.able.BLE"); stripping or
# renaming breaks the bundled able BLE shim used by RNode ble:// interfaces.
-keep class org.able.** { *; }
-keep class org.json.** { *; }
-keep class org.conscrypt.** { *; }
-dontwarn com.chaquo.python.**
-dontwarn org.conscrypt.**
-dontwarn okhttp3.**
-dontwarn okio.**
-keep class okhttp3.** { *; }
-keep class okio.** { *; }
