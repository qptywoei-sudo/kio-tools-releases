#pragma once
#include <windows.h>
#include "Resource.h"
inline HICON GalaxyAppIcon(HINSTANCE instance,int size=0){
 return static_cast<HICON>(LoadImageW(instance,MAKEINTRESOURCEW(IDI_GALAXYCONTROL),IMAGE_ICON,size,size,LR_SHARED|(size?0:LR_DEFAULTSIZE)));
}
