#!/bin/sh
set -eu
galaxySourceDir=$(dirname "$0")
cd "$galaxySourceDir"
mkdir -p build
cp GalaxyControl.swift build/main.swift
for galaxyArch in arm64 x86_64; do
swiftc -O -target "$galaxyArch-apple-macos11" build/main.swift Background.swift AgentHost.swift NativeBridge.swift AppHelp.swift Localization.swift LocalEngine.swift CaptureHub.swift NativeCapture.swift CaptureEditor.swift ImageTools.swift DocumentTools.swift CodeTools.swift ScreenRecord.swift -framework AppKit -framework WebKit -framework ApplicationServices -framework Carbon -framework CoreGraphics -framework CoreAudio -framework CoreImage -framework PDFKit -framework ScreenCaptureKit -framework AVFoundation -framework CoreMedia -framework CoreVideo -o "build/GalaxyControl-$galaxyArch"
done
lipo -create build/GalaxyControl-arm64 build/GalaxyControl-x86_64 -output build/GalaxyControl
