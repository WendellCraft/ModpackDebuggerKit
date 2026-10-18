.PHONY: dev build

# The distro ships WebKitGTK 4.1 system libraries, so the webkit2_41 build tag is
# required. Override with `make dev WAILS_TAGS=` if you have the 4.0 libraries.
WAILS_TAGS ?= webkit2_41

dev:
	PKG_CONFIG_PATH=$$HOME/.local/share/pkgconfig wails dev -tags $(WAILS_TAGS)

build:
	PKG_CONFIG_PATH=$$HOME/.local/share/pkgconfig wails build
