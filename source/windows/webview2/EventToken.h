#pragma once
#include <windows.h>
// MinGW compatibility declaration for the Windows SDK event-token ABI.
// An event token is one opaque signed 64-bit value; no implementation is supplied.
// Definition verified against Microsoft win32metadata's Windows SDK EventToken.h.
typedef struct EventRegistrationToken { INT64 value; } EventRegistrationToken;
