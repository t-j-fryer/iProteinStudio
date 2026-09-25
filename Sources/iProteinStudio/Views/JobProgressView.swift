import SwiftUI
import StudioCore

struct JobProgressView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var model: JobDetailModel
    @State private var filter = "All output"
    @State private var follow = true
    @State private var confirmCleanup = false

    init(job: ManagedJob) { _model = StateObject(wrappedValue: JobDetailModel(job: job)) }

    private var events: [EngineProgressEvent] { model.lines.compactMap(EngineProgressEvent.init(line:)) }
    private var visibleLines: [String] {
        switch filter {
        case "Engine progress": return events.map(\.logSummary)
        case "Worker log": return model.workerLines
        default: return model.lines
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading) {
                    Text("Job progress").font(.title2.bold())
                    Text(model.job.display_name ?? model.job.workflowLabel).lineLimit(1)
                }
                Spacer()
                Text(model.job.displayStatus).font(.headline)
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text(model.job.message ?? "Waiting for a job update.").font(.callout).textSelection(.enabled)
            if let last = events.last {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(last.engine) · \(last.stageLabel)").font(.headline)
                    Text(last.explanation).font(.callout)
                    HStack {
                        if let call = last.call { Text("Call \(call)") }
                        if let elapsed = last.elapsed { Text("Elapsed \(elapsed) s") }
                        if let date = last.date { Text("Last recorded update:"); Text(date, style: .relative) }
                    }.font(.caption).foregroundStyle(.secondary)
                }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
            } else {
                Text("Detailed engine events appear here when available. Older saved jobs may provide only the ordinary logs below.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if let error = model.error {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange).textSelection(.enabled)
            }
            HStack {
                Picker("Log", selection: $filter) {
                    ForEach(["All output", "Engine progress", "Worker log"], id: \.self) { Text($0) }
                }.pickerStyle(.segmented)
                Toggle("Follow latest", isOn: $follow).toggleStyle(.checkbox)
            }
            ScrollViewReader { proxy in
                ScrollView(.vertical) {
                    VStack(alignment: .leading) {
                        Text(visibleLines.isEmpty ? "No messages recorded yet." : visibleLines.joined(separator: "\n"))
                            .font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Color.clear.frame(height: 1).id("bottom")
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(8)
                }
                .background(Color(nsColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
                .onChange(of: visibleLines) { _, _ in if follow { proxy.scrollTo("bottom", anchor: .bottom) } }
                .onChange(of: follow) { _, value in if value { proxy.scrollTo("bottom", anchor: .bottom) } }
            }
            Text("Latest 500 job-log lines. Call counts are not percentages. A quiet log or a heartbeat alone cannot establish whether the GPU is progressing.")
                .font(.caption).foregroundStyle(.secondary)
            if let report = model.recovery {
                VStack(alignment: .leading, spacing: 8) {
                    Text(report.message).font(.callout).textSelection(.enabled)
                    if report.action != "none" {
                        Button(report.action == "stop" ? "Stop job & keep results" : "Clean up job & keep results", role: .destructive) {
                            confirmCleanup = true
                        }.disabled(model.busy)
                    }
                }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
            }
            HStack {
                Button("Check & clean up…") { Task { await model.checkRecovery() } }.disabled(model.busy)
                Button("Copy support report") { copySupport() }
                    .help("Copies job status and system details without raw logs or sequences")
                Button("Copy visible log") { copy(visibleLines.joined(separator: "\n")) }
                    .help("Logs may contain sequences, structures or local file paths. Review before sharing.")
                Spacer()
                if let output = model.job.output {
                    Button("Show saved files") { NSWorkspace.shared.activateFileViewerSelecting([output]) }
                }
            }.controlSize(.small)
        }
        .padding(20).frame(minWidth: 760, idealWidth: 880, minHeight: 620, idealHeight: 740)
        .confirmationDialog("Stop this job and clean up its recorded processes?", isPresented: $confirmCleanup) {
            Button("Continue & keep saved results", role: .destructive) { Task { await model.cleanUp() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(model.recovery?.message ?? "Saved inputs, results and checkpoints will be kept. Other jobs are not selected for cleanup.")
        }
        .task {
            while !Task.isCancelled {
                await model.refresh()
                try? await Task.sleep(for: .seconds(2))
            }
        }
        .accessibilityIdentifier("job-progress-viewer")
    }

    private func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    private func copySupport() {
        let report = SupportReport.make(
            version: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "development",
            system: ProcessInfo.processInfo.operatingSystemVersionString,
            memoryBytes: ProcessInfo.processInfo.physicalMemory,
            message: model.job.message ?? "", log: model.lines)
        var details = "\nJob: \(model.job.id)\nStatus: \(model.job.displayStatus)\n"
        if let recovery = model.recovery {
            details += "Cleanup action: \(recovery.action)\nRecorded leftover processes: \(recovery.process_ids.count)\nExecution lock busy: \(recovery.execution_lock_busy)\n"
        }
        copy(report + details)
    }
}
