# Introducing iProteinStudio

Design proposal · 2 October 2026 · no application changes

## Recommendation

Use a compact, native **Welcome window**, followed by optional guidance **inside
a sample project**. Keep a short “Discover Studio” tour in Help and on the Welcome
screen. Keep **My first protein design** visible as a separate, optional learning
experience. Installation belongs after a person chooses a scientific goal.

The introduction should answer three questions quickly:

1. What can I accomplish here?
2. What should I open or create first?
3. What will Studio preserve so I can trust and revisit the work?

It should feel like entering a capable research application. Users should not
have to identify as beginners, read a catalogue of model names, or finish a lesson
to reach their projects.

## What exists today

The source `RootView` sends a user to `SetupView` until the installer reports an
installation. The current setup opens with “Design binders against your target —
no terminal required,” then a dense explanation of sequence designers, predictors,
optional checkpoints and download requirements. The workspace already has a
project sidebar and toolbar access to Queue, Activity, Engines and AI connections.

Setup already has useful review and recovery mechanics: download-plan review,
reuse of an existing installation, partial completion, retry, cancellation and
logs. Preserve those mechanics. The proposal changes when and how people meet
them, not the reliability or permission boundary.

The separate recipe-workshop prototype has a completed first-design lesson and
authoring interfaces. They are not shipped native capabilities. Do not describe
an arbitrary graph editor, executable recipe compiler, custom-engine installer
or experimental assay database as existing functionality.

## Three explored directions

### A — Welcome window: the recommended entry

A quiet two-column window: identity and one piece of artwork on the left; clear
actions on the right. The main actions are **New project…**, **Explore a sample
project**, and **Explore Studio’s capabilities**. **Open project…** remains
immediately visible. **My first protein design** is discoverable below the main
actions, with a one-sentence description rather than a “beginner” badge.

The initial copy is:

> Protein design, on your Mac.
>
> Predict structures, design binders and compare candidates in a reproducible
> workspace.
>
> Keep every candidate connected to the methods that produced it.

Why this works: the first screen explains breadth and gives direct actions.
People with existing work can leave immediately. A researcher evaluating Studio
can inspect a sample before spending bandwidth or choosing unfamiliar engines.

The prototype's goal chooser covers structure prediction, protein binders,
nanobody redesign and ligand NISE. It then previews task-specific requirements.
Those dependency lists are explanatory, not complete install plans. A real
implementation must derive dependencies, installation state and byte totals from
the current installer and engine catalogue.

Risk: a welcome window becomes irritating if it interrupts every launch. Restore
open projects first. Show it automatically when there is no project to restore,
respect a “Show on startup” preference, and make it reopenable from Window/Help.
On returning launches, the right column can show actual recent projects. Do not
fill first launch with invented recent work.

### B — Optional introduction: explain the mental model

A three-screen introduction with Back, Continue and a persistent Skip action:

1. **The complete experiment.** Inputs → design → independent checks → candidate
   records. Explain what each stage contributes.
2. **Methods you can compare.** Show a controlled method comparison and the
   record attached to a candidate. Preserve native metrics and exact lineage.
3. **Local execution and explicit connections.** Explain local runs, reviewed
   downloads, optional alignment requests and separate AI permissions.

Why: this offers a coherent explanation to people who want one. It also provides
a reusable help resource for demonstrating the platform.

Why it should not be compulsory: slides require remembering information before
there is a task to attach it to. Their explanatory value does not justify
blocking someone who already knows what to do. Finishing the tour should not
automatically install, create a project, or start a run.

Risk: the route diagram can imply every task has exactly the same stages. Copy
must distinguish a prediction-only task from a design workflow. The diagram is
an overview, not an enforced scientific recipe.

### C — Learn in a project: the recommended teaching layer

A sample project uses the app's actual navigation vocabulary: sidebar, project
detail, route stages and a small inspector. Selecting a stage updates its
explanation. A dismissible three-part guide explains the project record, the
computational route and the exact candidate that was checked.

Why: instructions sit beside the thing they describe. A person can inspect
inputs, structures and results while learning where they belong, instead of
memorizing a generic tour of toolbar buttons. The inspector provides guidance
without covering the main content with a full-window spotlight.

The prototype contains schematic stage descriptions, not fabricated scientific
results. Production needs a small, curated, provenance-linked example with real
inputs and saved outputs that can be inspected offline. Choose it only after
scientific review. Label sample playback persistently; never place it in the live
queue or fabricate a running progress bar.

Risk: automatically opening a project can feel like clutter. Make sample opening
an explicit action. Keep the original sample immutable; offer **Use as a starting
point…** to create a user-owned copy. Never allow editing the example to modify
its reference evidence or automatically rerun it.

## Design decisions and rationale

| Decision | Rationale and intended behavior |
|---|---|
| Separate welcome from installation | Let users understand the value before choosing large downloads. Examples and the lesson should not require inference engines. |
| Start with scientific goals | “Design a protein binder” is a decision a researcher can make. Engine selection follows when its consequences are meaningful. |
| Use ordinary macOS windows, controls and sheets | Familiar behaviors reduce learning. In implementation, use system title bars, standard buttons, file pickers, split views, inspectors and sheets. Do not draw replacement window chrome. |
| Keep visual hierarchy compact | Use system typography, semantic foreground styles and restrained spacing. A clear heading and precise supporting sentence communicate more than oversized marketing panels. |
| Let system appearance lead | Honor Light/Dark mode, accent color, Increase Contrast and Reduce Transparency. Use system materials in navigation chrome only when legibility survives; keep scientific content on stable surfaces. |
| Use system symbols for actions | SF Symbols should carry navigation and action meaning. The browser concepts use stand-in glyphs; the app should use native symbol rendering and accessibility labels. |
| Use one optional artwork | A small distinctive image gives the welcome a sense of identity. It must not compete with action labels or reappear throughout routine work. |
| Make instruction dismissible and recoverable | A user can close a tip or skip the tour without losing capabilities. Help provides Welcome, Discover Studio and My first protein design. Track dismissal locally per tip/version. |
| Keep the playful lesson separate | The tabletop teaches dependencies and evidence boundaries. Putting it in a separate learning window preserves the professional workspace's quiet tone. |
| Teach scientific interpretation alongside navigation | Explain independent checking and candidate lineage where users review results. Do not let onboarding imply a high-confidence prediction proves binding. |
| Explain external services at the point of use | “Local” must not conceal alignment queries, downloads or what an enabled external assistant can access. Show concrete service/input implications when configuring them. |
| Keep AI connection optional | AI can help choose existing routes, but no account connection or assistant permission is needed to understand the app. Offer AI after the workflow mental model is established. |
| Preserve existing recovery paths | Partial setup, interrupted runs and workspace-index failures need truthful, specific recovery. A welcome screen must not hide them or replace their states with generic success. |
| Respect experienced users | Keyboard shortcuts, Open Project and direct workflow entry remain available. No forced checklist, congratulation for clicking Next, self-assessed expertise question or “easy enough for anyone” copy. |

Native feel should come primarily from behavior and information hierarchy. The
proposed aesthetic is calm surfaces, system text, limited tint and compact
controls. The final app should use the platform's current materials through
standard APIs, with appropriate availability handling for Studio's supported
macOS versions. No custom glass shader, web-style navbar or animated backdrop is
needed to communicate sophistication.

## Artwork direction

Created **Fold and possibility**: an abstract ribbon in matte pearl and sage,
with a restrained ochre detail and three seed-like branches. Its role is to
suggest structure and exploration. It is not a protein, phylogeny, binding result
or scientific diagram. The silhouette remains readable at welcome-window size;
material texture supplies warmth without a mascot or glossy neon treatment.

Use it on the Welcome screen only, approximately 220–300 points wide, with enough
space around the primary actions. The transparent background works on both
light and dark system surfaces. Do not make the user wait for an animation or
image to load before controls become available. Omit the artwork when space is
tight, increased accessibility text makes it distracting, or visual simplicity
is preferred. It is an optional art direction, not a proposed replacement app icon.

The unmodified PNG and exact prompt are in
`lab_book/artifacts/0264-native-onboarding/`. Built-in hosted image generation was
used; no local GPU inference was run. The image has an alpha channel. This was
visual concept work, not a molecular-accuracy exercise.

## Proposed first-launch sequence

1. **Welcome.** Explain the app and offer direct project entry, sample and lesson.
2. **Choose a goal, if creating work.** Route into the supported workflow. Do not
   offer unavailable science as an enabled choice.
3. **Review exact requirements.** Detect available engines and offer reuse. Show
   necessary components, verified download sizes, disk requirements and relevant
   network implications. Optional models remain optional. Do not invent elapsed
   time promises, hardware claims or universal “best” settings.
4. **Install with recoverable progress.** Retain cancellation, partial completion,
   retry and logs. Allow safe sample exploration while setup proceeds. Creating
   a plan or opening an example must not start a scientific job.
5. **Open the project at the relevant input stage.** One contextual explanation
   at a time, shown when useful. Review the normal immutable plan before any run.
6. **Introduce interpretation when results exist.** Explain hierarchy, independent
   checks and how to save the checked candidate. Avoid an up-front lecture about
   every metric.

Return visits restore projects and work, not the tour. After an update, a small
What's New item can point to relevant capabilities without replaying onboarding.
Existing installations, incomplete downloads and unavailable storage each need
their own route; none should be reset by dismissing the introduction.

## My first protein design

Keep the full name and the completed tabletop loop from the first prototype.
Introduce it with: “An optional, hands-on introduction to the design process.”
Do not describe people as novices or ask them to choose an expertise level.

Its completion should acknowledge the concept learned: a route can produce a
candidate hypothesis, which still needs independent checks and experiments. The
next actions are **Explore a sample project** and **Create a project…**, both
optional. A completion state does not authorize an engine download or GPU run.
Offer replay from Help. There is no need for streaks, points, public badges or
gamification in the ordinary scientific workspace.

## Accessibility and implementation plan

Prototype sizes and colors demonstrate intent, not replacement native controls.
Implement the chosen direction in SwiftUI/AppKit only after review. Reuse the
current installer and project routing, with an engine-independent entry surface
and a separately tracked local onboarding state. Runtime availability must remain
derived from detection, not from whether someone clicked through a tour.

Use semantic system fonts and labels, keyboard-accessible actions, standard
focus behavior, default/cancel buttons, and VoiceOver reading order. Do not
automatically move focus as installation status changes. Provide text equivalents
for essential diagrams; decorative artwork should be ignored by VoiceOver.
Honor Reduce Motion; the artwork can remain entirely static. Verify long
translations and large text before choosing a hard minimum window size.

The current storage-recovery screen retains priority when saved work cannot be
read. Welcome must not mask data-access problems. No onboarding preference can
bypass immutable plans, installation checks, MSA policy, job locking or the normal
run authorization/review path.

## Evaluation and remaining uncertainty

The interactive concepts were checked in the browser: goal selection, requirement
preview, tour progression/completion/skipping, contextual stage explanations,
guide dismissal and reopening. These are interaction checks, not a native app
implementation, a participant study or a full accessibility audit.

Compare A alone against A followed by C with bench scientists and experienced
designers. Ask each to explain what Studio does, select an appropriate starting
route, distinguish sample playback from a run, and identify which candidate was
checked. Observe wrong turns, unsolicited help needed, interpretation errors and
whether the introduction feels respectful. Ask directly about the artwork and
lesson rather than assuming “playful” is universally welcome.

Test the optional tour separately: does it improve understanding enough that
people choose to use it? If not, its content belongs in Help and contextual tips.
No invented task-time target, enjoyment rating or performance claim is assigned.

## Reference basis

- [Apple: Onboarding](https://developer.apple.com/design/human-interface-guidelines/onboarding)
  recommends a fast, optional introduction and placing explanations near the
  interface they describe. This informs the recommendation for A plus C.
- [Apple: Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos/)
  emphasizes familiar platform behavior and adaptable workspaces. This informs
  the use of native windows, standard controls and direct project access.
- [Apple: Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars)
  grounds the separation between app/window navigation and actions on content.

The concepts and the recommendation are design judgments tailored to Studio;
Apple's guidance does not establish that these prototypes improve usability.
