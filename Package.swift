// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "iProteinStudio",
    platforms: [.macOS(.v14)],
    dependencies: [
        // Pinned rather than tracking a moving branch: the updater installs
        // executable code and is part of the application's trust boundary.
        .package(url: "https://github.com/sparkle-project/Sparkle", exact: "2.9.2"),
    ],
    targets: [
        .executableTarget(
            name: "iProteinStudio",
            dependencies: [
                .product(name: "Sparkle", package: "Sparkle"),
            ],
            path: "Sources/iProteinStudio",
            resources: [
                .copy("Resources/pipeline"),
                .copy("Resources/web"),
                .copy("Resources/rfd3"),
                .copy("Resources/rfd3_overlay"),
                .copy("Resources/examples"),
            ],
            linkerSettings: [
                // The release bundle embeds Sparkle under Contents/Frameworks.
                // SwiftPM otherwise emits only an executable-local runpath,
                // which compiles and signs but crashes at launch under dyld.
                .unsafeFlags(["-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks"]),
            ]
        )
    ]
)
