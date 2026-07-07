plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.ayati.noveldownloader"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.ayati.noveldownloader"
        minSdk = 24
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"

        ndk {
            // 配布対象は実機スマホのみなので arm64 に絞って APK を小さくする
            abiFilters += listOf("arm64-v8a")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}

chaquopy {
    defaultConfig {
        // buildPython と同じマイナーバージョンであること（WSL の python3 は 3.12）
        version = "3.12"
        buildPython("/usr/bin/python3")
        pip {
            install("requests")
            install("beautifulsoup4")
            install("Pillow")
        }
    }
}

// リポジトリ直下の本体スクリプトと表紙用フォントをビルド時に同梱する。
// コピー先は .gitignore 済み（原本はリポジトリ直下で一元管理）。
val syncNovelDownloader by tasks.registering(Copy::class) {
    from("../../novel_downloader.py")
    into("src/main/python")
}

val syncCoverFont by tasks.registering(Copy::class) {
    from("../../font/AyatiShowaSerif-Regular.ttf")
    into("src/main/assets/fonts")
}

tasks.named("preBuild") {
    dependsOn(syncNovelDownloader, syncCoverFont)
}

// コピー先（src/main/python・src/main/assets）を入力に取るタスクへ明示依存を張る
// （Gradle 8 の implicit-dependency 検証対策）
tasks.matching {
    it.name.contains("PythonSources") || it.name.contains("Assets")
}.configureEach {
    dependsOn(syncNovelDownloader, syncCoverFont)
}
