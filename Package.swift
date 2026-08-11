// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "NanoHunterStudio",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "NanoHunterStudio",
            path: "Sources/NanoHunterStudio",
            resources: [
                .copy("Resources/pipeline"),
                .copy("Resources/web"),
                .copy("Resources/rfd3"),
            ]
        )
    ]
)
