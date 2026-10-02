/// Orientation must never hide an existing workspace or an installation recovery.
public enum IntroductionPolicy {
    public static func shouldPresent(hasSeen: Bool, installed: Bool, hasSavedWork: Bool,
                                     installationBusy: Bool, recoveryNeeded: Bool) -> Bool {
        !hasSeen && !installed && !hasSavedWork && !installationBusy && !recoveryNeeded
    }
}
