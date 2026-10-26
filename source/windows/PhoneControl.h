#pragma once
#include <windows.h>
#ifdef __cplusplus
extern "C" {
#endif
#define GALAXY_PHONE_MAX_DEVICES 64
enum GalaxyPhoneOperation { GP_STATUS, GP_PAIR, GP_CONNECT, GP_START, GP_STOP, GP_KEYBOARD };
typedef struct {
 wchar_t serial[256], label[160], status[64];
 int wireless;
} GalaxyPhoneDevice;
typedef struct {
 GalaxyPhoneDevice devices[GALAXY_PHONE_MAX_DEVICES];
 int count, running, available, keyboardSdk, mouseUhid, audioMode, clipboard;
 wchar_t activeSerial[256];
} GalaxyPhoneState;
typedef struct {
 int operation, keyboardSdk, mouseUhid, audioMode, clipboard;
 wchar_t serial[256], address[256], code[7];
} GalaxyPhoneRequest;
typedef void (*GalaxyPhoneCallback)(void *context, int success, const char *error);
void GalaxyPhoneReadState(GalaxyPhoneState *);
int GalaxyPhoneSubmit(const GalaxyPhoneRequest *, GalaxyPhoneCallback, void *, const char **error);
#ifdef __cplusplus
}
#endif
