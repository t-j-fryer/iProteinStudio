// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "iProteinStudio",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "iProteinStudio",
            path: "Sources/iProteinStudio",
            resources: [
                .copy("Resources/pipeline"),
                .copy("Resources/web"),
                .copy("Resources/rfd3"),
                .copy("Resources/rfd3_overlay"),
                .copy("Resources/examples"),
            ]
        )
    ]
)
