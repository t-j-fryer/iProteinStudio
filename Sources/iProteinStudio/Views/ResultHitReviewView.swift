import SwiftUI
import AppKit
import CryptoKit
import UniformTypeIdentifiers

/// A personal, retrospective selection. Never rewrites an engine's verdicts.
struct ResultHitReviewView: View {
    let items: [StudioResultItem]
    let root: URL
    var initialMetric: StudioResultMetric.Kind? = nil
    var reviewAllByDefault = false
    @StateObject private var spatial = ResultSpatialController()
    @StateObject private var model = ResultHitReviewModel()
    @State private var page = 0
    @State private var policy = ResultHitPolicy()
    @State private var selectedID: String?
    @State private var exporting = false
    @State private var exportMessage: String?
    @State private var exportError: String?

    private var settingsKey: String {
        "results.hitReview." + SHA256.hash(data: Data(root.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    var body: some View {
        let candidates = model.index.candidates
        let preferred = initialMetric ?? model.index.preferred
        let shown = model.shown
        let metrics = model.index.metrics
        let currentPage = ResultPage(count: shown.count, requested: page)
        let pageItems = Array(shown[currentPage.range])
        VStack(alignment: .leading, spacing: 0) {
            controls(candidates: candidates, shown: shown, metrics: metrics, preferred: preferred)
                .padding(12)
            ScrollView {
                ResultSpatialControls(policy: $policy.spatial, candidates: candidates, controller: spatial).padding(.horizontal, 12).padding(.bottom, 8)
            }.fixedSize(horizontal: false, vertical: true).frame(maxHeight: 310)
            if model.busy { ProgressView().controlSize(.small).padding(.horizontal, 12) }
            Divider()
            ResultPageControls(count: shown.count, page: $page)
            if shown.isEmpty {
                ContentUnavailableView("No matching designs", systemImage: "line.3.horizontal.decrease.circle",
                    description: Text(policy.validationMessage ?? "Change the score criteria or choose custom filters to review designs beyond the saved hit verdicts."))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                HSplitView {
                    List(selection: $selectedID) {
                        ForEach(pageItems) { candidate in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(candidate.name).font(.callout.weight(.medium)).lineLimit(2)
                                if let kind = policy.sortMetric ?? preferred, let score = candidate.metric(kind) {
                                    Text("\(kind.label): \(score, format: .number.precision(.fractionLength(3)))")
                                        .font(.caption).monospacedDigit()
                                }
                                Text(candidate.savedHit == true ? "Saved hit" : candidate.savedHit == false ? "Saved filters failed" : "No saved verdict")
                                    .font(.caption2).foregroundStyle(.secondary)
                            }.tag(candidate.id)
                        }
                    }.frame(minWidth: 230, idealWidth: 290, maxWidth: 380)
                    if let selected = shown.first(where: { $0.id == selectedID }) ?? pageItems.first {
                        VStack(spacing: 0) {
                            if let row = selected.spatial { ResultSpatialSummary(row: row) }
                            StudioResultGroupDetail(group: selected.group, hitsOnly: false).id(selected.id)
                        }.frame(minWidth: 400, maxWidth: .infinity)
                    }
                }
            }
        }
        .onAppear {
            if let data = UserDefaults.standard.data(forKey: settingsKey),
               let saved = try? JSONDecoder().decode(ResultHitPolicy.self, from: data) { policy = saved }
            else if reviewAllByDefault { policy.mode = .custom }
        }
        .onDisappear { spatial.cancel() }
        .onChange(of: items, initial: true) { _, _ in update() }
        .onChange(of: initialMetric) { _, _ in update() }
        .onChange(of: spatial.rows) { _, _ in update() }
        .onChange(of: policy) { old, value in
            if old.spatial != value.spatial { spatial.cancel() }
            page = 0
            update()
            if let data = try? JSONEncoder().encode(value) { UserDefaults.standard.set(data, forKey: settingsKey) }
        }
        .onChange(of: page) { _, _ in selectedID = pageItems.first?.id }
        .onChange(of: shown.map(\.id)) { _, _ in
            if !pageItems.contains(where: { $0.id == selectedID }) { selectedID = pageItems.first?.id }
        }
        .alert("CSV export failed", isPresented: Binding(get: { exportError != nil }, set: { if !$0 { exportError = nil } })) {
            Button("OK") { exportError = nil }
        } message: { Text(exportError ?? "") }
    }

    private func update() {
        model.update(items: items, policy: policy, preferred: initialMetric, spatialRows: spatial.rows)
    }

    private func controls(candidates: [ResultCandidate], shown: [ResultCandidate], metrics: [StudioResultMetric.Kind],
                          preferred: StudioResultMetric.Kind?) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Picker("Hit criteria", selection: $policy.mode) {
                    Text("Saved verdicts").tag(ResultHitPolicy.Mode.saved)
                    Text("Custom filters").tag(ResultHitPolicy.Mode.custom)
                }.frame(maxWidth: 280)
                Picker("Sort by", selection: $policy.sortMetric) {
                    Text("Default metric").tag(Optional<StudioResultMetric.Kind>.none)
                    ForEach(Array(Set(metrics + [policy.sortMetric].compactMap { $0 })).sorted { $0.label < $1.label }, id: \.self) { kind in
                        Text(kind.label).tag(Optional(kind))
                    }
                }.frame(maxWidth: 280)
                Picker("Order", selection: $policy.descending) {
                    Text("Highest first").tag(true)
                    Text("Lowest first").tag(false)
                }.frame(width: 160)
            }
            HStack {
                Text("Maximum per family")
                TextField("Unlimited", text: $policy.maxPerFamily).textFieldStyle(.roundedBorder).frame(width: 65)
                    .accessibilityLabel("Maximum selected designs per family; zero means unlimited")
                Text("0 or blank = unlimited").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text("\(shown.count) / \(candidates.count)").font(.caption).monospacedDigit()
                Button("Export Hits CSV…") { export(shown) }
                    .help("Exports all matching designs, including other pages")
                    .disabled(exporting || model.busy || shown.isEmpty || policy.validationMessage != nil)
            }
            if policy.mode == .custom {
                if !policy.rules.isEmpty {
                    ScrollView {
                        VStack(spacing: 6) {
                            ForEach($policy.rules) { $rule in
                                HStack {
                                    Picker("Metric", selection: $rule.metric) {
                                        ForEach(Array(Set(metrics + [rule.metric])).sorted { $0.label < $1.label }, id: \.self) { kind in
                                            Text(ResultAnalysis.metricLabel(kind)).tag(kind)
                                        }
                                    }.help(rule.metric.explanation)
                                    Picker("Comparison", selection: $rule.comparison) {
                                        ForEach(ResultHitPolicy.Comparison.allCases, id: \.self) { c in Text(c.rawValue).tag(c) }
                                    }.labelsHidden().accessibilityLabel("Comparison").frame(width: 65)
                                    TextField("Threshold", text: $rule.threshold).textFieldStyle(.roundedBorder).frame(width: 110)
                                        .accessibilityLabel("\(rule.metric.label) threshold")
                                    Button("Remove") { policy.rules.removeAll { $0.id == rule.id } }
                                }
                            }
                        }
                    }.frame(height: min(150, CGFloat(policy.rules.count * 36)))
                }
                HStack {
                    Button("Add metric filter") { policy.rules.append(.init(metric: preferred ?? metrics.first ?? .ipsaeMinimum)) }
                    Button("Reset to saved verdicts") { policy = ResultHitPolicy() }
                    Spacer()
                }
                Text(policy.rules.isEmpty
                     ? "No score cutoffs: all scored candidates are included. Sorting and family limits still apply."
                     : "Every rule must pass; missing scores fail. Values prefer the associated complex check when present. Stage and score-source selections above also apply.")
                    .font(.caption).foregroundStyle(.secondary)
                Text("Custom matches are a review selection. Original saved hit verdicts are unchanged.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let message = policy.validationMessage {
                Text(message).font(.caption).foregroundStyle(.red)
            }
            let missingSequences = shown.filter { $0.sequence == nil || $0.sequence?.isEmpty == true }.count
            if missingSequences > 0 {
                Text("\(missingSequences) selected design(s) lack a recorded sequence; their CSV sequence cells will be blank.")
                    .font(.caption).foregroundStyle(.orange)
            }
            if exporting { Text("Exporting CSV…").font(.caption).foregroundStyle(.secondary) }
            if let exportMessage { Text(exportMessage).font(.caption).foregroundStyle(.secondary) }
        }
    }

    private func export(_ candidates: [ResultCandidate]) {
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.commaSeparatedText]
        panel.nameFieldStringValue = root.lastPathComponent + "_hits.csv"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        exporting = true
        let mode = policy.mode.rawValue
        Task {
            let error = await Task.detached(priority: .utility) { () -> String? in
                do {
                    try ResultAnalysis.csv(candidates, mode: mode).write(to: url, atomically: true, encoding: .utf8)
                    return nil
                } catch { return error.localizedDescription }
            }.value
            exporting = false
            if let error { exportError = error }
            else { exportMessage = "Saved \(candidates.count) designs to \(url.lastPathComponent)." }
        }
    }
}
