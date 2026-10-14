# Software Manager for Shale Linux

The app store of [Shale Linux](https://github.com/slycat555/shale-linux): apps from Flathub and
from the Arch Linux repositories, in one place. It's
[Linux Mint's Software Manager](https://github.com/linuxmint/mintinstall) (mintinstall),
changed to work with pacman instead of apt.

## What's different from Mint's

- **pacman instead of apt.** System packages come from the official Arch repositories. The
  list and the preview of every change (what gets installed or removed, download and disk
  size) come straight from pacman, without needing a password.
- **Installs keep the system consistent.** Installing a package runs `pacman -Syu --needed`,
  so the rest of the system is brought up to date in the same step. Installing on top of an
  out-of-date system is how Arch systems break, so the app never does it. The confirm dialog
  says when updates come along.
- **Safe removals.** Removing a package also removes dependencies nothing else needs. A
  package that other software still needs is refused with a plain explanation, and the base
  system and the desktop can't be removed at all.
- **Restore points.** When an install brings updates and Shale Snapshots is set up, a restore
  point is taken first, like Software Update does.
- **No password for administrators** at the computer, like Software Update. Changes run in
  a small root helper (`pacman-helper`) started through pkexec.
- **App info from AppStream.** Names, icons, descriptions, screenshots and categories for
  Arch packages come from Arch's AppStream catalogue (`archlinux-appstream-data`).
- **No Mint services.** Reviews, screenshots and Software Sources were Linux Mint's own
  (community.linuxmint.com, mintsources) and are left out.
- **Shale names and icon.** `shale-software`, `/usr/lib/shale-software`, app ID
  `org.shale.software`.

Mint's installer library ([mint-common](https://github.com/linuxmint/mintcommon)) is included
under `usr/lib/shale-software/mintcommon`, since Shale has no mint-common package.

## Building

On Shale or Arch Linux, with `base-devel` installed:

```sh
makepkg -si
```

Or install straight from the checkout with `sudo make install`.

Files are laid out as they are installed (`usr/…`); `resources/` holds the GTK interface,
compiled into `shale-software.gresource`. `tools/make-icons.py` draws the app icon and the
system-package badge from the Shale logo.

## License

GPL-2.0-or-later, like mintinstall. Copyright © Linux Mint (see `COPYRIGHT`) and the Shale
Linux contributors. Shale Linux is not affiliated with or endorsed by Linux Mint.
