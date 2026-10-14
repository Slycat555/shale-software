# Builds and installs the Shale Software Manager.
#   make                 compile the UI resources
#   make install         install under $(DESTDIR)$(PREFIX) (used by the PKGBUILD)
PREFIX ?= /usr
DESTDIR ?=
VERSION ?= $(shell git describe --tags --always 2>/dev/null || echo dev)

all: build/shale-software.gresource

build/shale-software.gresource: resources/shale-software.gresource.xml resources/*.glade
	mkdir -p build
	glib-compile-resources --sourcedir=resources --target=$@ $<

install: all
	mkdir -p $(DESTDIR)$(PREFIX)
	cd usr && find . -type f ! -path '*/__pycache__/*' -exec install -Dm644 {} $(DESTDIR)$(PREFIX)/{} \;
	chmod 755 $(DESTDIR)$(PREFIX)/bin/* \
		$(DESTDIR)$(PREFIX)/lib/shale-software/shale-software.py \
		$(DESTDIR)$(PREFIX)/lib/shale-software/update-pkgcache.py \
		$(DESTDIR)$(PREFIX)/lib/shale-software/pacman-helper
	install -Dm644 build/shale-software.gresource $(DESTDIR)$(PREFIX)/share/shale-software/shale-software.gresource
	sed -i 's/__VERSION__/$(VERSION)/' $(DESTDIR)$(PREFIX)/lib/shale-software/shale-software.py

clean:
	rm -rf build

.PHONY: all install clean
