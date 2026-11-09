# Mac power mode

The power button in the workspace toolbar is shared across Studio workflows.
The same controls appear under Mac power mode in execution settings and in
Studio Settings → Power. Status shows the current power source and reported mode.

Connect the power adapter, then choose **Enable High Power on power adapter**.
If macOS asks, authorize the change in its administrator dialog. Studio rereads
the setting before confirming it. **Use Automatic** explicitly selects Apple's
Automatic mode again. **Open Power Settings** opens Battery on notebooks or
Energy on desktops so you can review all available options.

This changes a setting for the whole Mac, including other running work. It
persists after jobs finish and after Studio quits. The shortcut changes only the
power-adapter profile; battery settings remain as configured in macOS. Studio
never enables High Power automatically when a job starts and never asks you to
give it a password directly.

High Power availability depends on the Mac. When macOS does not report support
or the current mode cannot be read, Studio offers Power Settings rather than
assuming that High Power is available. Some older systems expose limited status;
use Apple's own settings in that case. See [Apple's power-mode guidance](https://support.apple.com/101613)
for supported models and power-adapter recommendations.

High Power permits more cooling and can increase fan noise and energy use.
The effect on throughput depends on the Mac and workload; this control does not
promise a particular speedup. Release qualification and limitations are recorded
in [Lab0827](../lab_book/0827-publish-power-and-audit-github.md).
