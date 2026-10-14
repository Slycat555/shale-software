# Builds Shale Software from this checkout: makepkg -si
pkgname=shale-software
pkgver=8.4.1
pkgrel=1
pkgdesc="Software Manager for Shale Linux: apps from Flathub and the Arch repositories (Linux Mint's mintinstall, for pacman)"
arch=(any)
url="https://github.com/slycat555/shale-linux"
license=(GPL-2.0-or-later)
depends=(python python-gobject python-cairo gtk3 xapp python-xapp flatpak libxmlb
         archlinux-appstream-data python-requests python-html2text python-setproctitle
         polkit pacman)
optdepends=('timeshift: restore point before updates that come with an install (Shale Snapshots)')
makedepends=(glib2)

pkgver() {
    printf '8.4.1.r%s.%s' "$(git -C "$startdir" rev-list --count HEAD)" "$(git -C "$startdir" rev-parse --short HEAD)"
}

build() {
    make -C "$startdir"
}

package() {
    make -C "$startdir" DESTDIR="$pkgdir" VERSION="$pkgver" install
}
