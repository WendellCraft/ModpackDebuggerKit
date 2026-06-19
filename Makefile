.PHONY: dev build

dev:
	PKG_CONFIG_PATH=$$HOME/.local/share/pkgconfig wails dev

build:
	PKG_CONFIG_PATH=$$HOME/.local/share/pkgconfig wails build
