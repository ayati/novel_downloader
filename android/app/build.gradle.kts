plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// APK バージョンは novel_downloader のリリース版数に一致させる（版数の二重管理を回避）。
// 版数の単一ソースは本体 novel_downloader.py の __version__。
//   優先1: -PappVersion=X.Y.Z（scripts/release.sh がリリース時に渡す）
//   優先2: リポジトリ直下 novel_downloader.py の __version__（手動/開発ビルド時）
// versionCode は semver から単調増加する整数を合成（minor/patch < 100 が前提）。
val appVersion: String = run {
    val prop = (project.findProperty("appVersion") as String?)?.removePrefix("v")?.trim()
    if (!prop.isNullOrEmpty()) return@run prop
    val pyFile = rootProject.projectDir.parentFile.resolve("novel_downloader.py")
    if (pyFile.exists()) {
        Regex("""__version__\s*=\s*["']([^"']+)["']""")
            .find(pyFile.readText())?.groupValues?.get(1)?.let { return@run it }
    }
    "0.0.0"
}
val appVerParts: List<Int> =
    (appVersion.split(".") + listOf("0", "0", "0")).take(3).map { it.toIntOrNull() ?: 0 }

// リリース署名鍵。Android Developer Console に登録した鍵で署名するため、debug 鍵とは分ける。
// 鍵の場所とパスワードはリポジトリに置かず、次の優先順で解決する:
//   優先1: 環境変数  NOVEL_KEYSTORE / NOVEL_KEYSTORE_PASSWORD / NOVEL_KEY_ALIAS / NOVEL_KEY_PASSWORD
//   優先2: ~/.gradle/gradle.properties の novelStoreFile / novelStorePassword / novelKeyAlias / novelKeyPassword
// 未設定なら release 用 signingConfig を作らない（未署名で失敗させ、
// debug 鍵の APK をそのまま野良配布してしまう事故を構造的に防ぐ）。
fun signingSecret(env: String, prop: String): String? =
    (System.getenv(env) ?: project.findProperty(prop) as String?)?.trim()?.takeIf { it.isNotEmpty() }

val releaseStorePath = signingSecret("NOVEL_KEYSTORE", "novelStoreFile")
val releaseStorePassword = signingSecret("NOVEL_KEYSTORE_PASSWORD", "novelStorePassword")
val releaseKeyAlias = signingSecret("NOVEL_KEY_ALIAS", "novelKeyAlias")
val releaseKeyPassword =
    signingSecret("NOVEL_KEY_PASSWORD", "novelKeyPassword") ?: releaseStorePassword
val hasReleaseSigning =
    releaseStorePath != null && releaseStorePassword != null && releaseKeyAlias != null

android {
    namespace = "com.ayati.noveldownloader"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.ayati.noveldownloader"
        minSdk = 24
        targetSdk = 35
        versionCode = appVerParts[0] * 10000 + appVerParts[1] * 100 + appVerParts[2]
        versionName = appVersion

        ndk {
            // 配布対象は実機スマホのみなので arm64 に絞って APK を小さくする
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                // "~/..." は Gradle が展開しないので自前でホームに置換する
                storeFile =
                    file(releaseStorePath!!.replaceFirst("~", System.getProperty("user.home")))
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        getByName("release") {
            // Chaquopy の Python 側がリフレクション経由で触るクラスを削らせない
            isMinifyEnabled = false
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            }
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
