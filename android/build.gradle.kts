plugins {
    // AGP の上限は Chaquopy の対応範囲で決まる（Chaquopy 17.0 は AGP 7.3〜9.2）。
    // AGP 9 は Kotlin を内蔵するので org.jetbrains.kotlin.android は付けない
    id("com.android.application") version "9.2.1" apply false
    id("com.chaquo.python") version "17.0.0" apply false
}
