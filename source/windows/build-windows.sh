#!/bin/sh
# Build the unified native Windows x64 GUI with Zig 0.16.
set -eu
galaxySourceDir=$(dirname "$0")
cd "$galaxySourceDir"
galaxyZigTool=${GALAXY_ZIG:-zig}
"$galaxyZigTool" cc -target x86_64-windows-gnu -DGALAXY_EMBEDDED -O2 -c GalaxyControl.c -o PhoneModule.o
"$galaxyZigTool" rc /fo GalaxyControl.res GalaxyControl.rc
"$galaxyZigTool" c++ -target x86_64-windows-gnu -std=c++17 -municode -O2 -Wno-nullability-completeness \
  CaptureTool.cpp ToolHub.cpp WindowsRecorder.cpp I18N.cpp UxShell.cpp NativeBridge.cpp SharedHost.cpp PhoneModule.o GalaxyControl.res \
  -o KIOControl.exe -Wl,--subsystem,windows \
  -ldwmapi -ladvapi32 -lgdiplus -lole32 -lcomdlg32 -lcomctl32 -lshell32 -lshlwapi -luuid -luser32 -lgdi32 -lmfuuid -lwinhttp -lws2_32
