/* GalaxyControl portable Windows launcher. UTF-8 source; no installed runtime.
 * Build: zig cc -target x86_64-windows-gnu -municode -O2 -Wl,--subsystem,windows 
 *        GalaxyControl.c -o GalaxyControl.exe -lcomctl32 -lshell32 -luser32 -lgdi32
 * Bundled tools: <exe-dir>\\tools\\scrcpy\\{scrcpy.exe,adb.exe,scrcpy-server,...}
 * Pairing codes are supplied only through an anonymous stdin pipe.
 */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <windowsx.h>
#include <shellapi.h>
#include <shlobj.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <wctype.h>
#include "PhoneToolsPath.h"
#include "PhoneControl.h"
#include "Resource.h"
#ifdef GALAXY_EMBEDDED
extern void GalaxySetText(HWND,const wchar_t*);
extern const wchar_t* GalaxyTr(const wchar_t*);
extern void GalaxyRegisterText(HWND,const wchar_t*);
extern int GalaxyMessageBox(HWND,const wchar_t*,const wchar_t*,UINT);
extern void GalaxyCueBanner(HWND,const wchar_t*);
extern void GalaxyLocalizeWindow(HWND);
#define MessageBoxW GalaxyMessageBox
#define SetWindowTextW GalaxySetText
#else
#define GalaxyCueBanner(h,s) SendMessageW(h,EM_SETCUEBANNER,TRUE,(LPARAM)s)
#endif

#define APP_CLASS L"GalaxyControlPortable"
#define MAX_DEVICES 64
#define OUTPUT_CAP 32768
#define WM_RESULT (WM_APP + 1)
#define WM_PROGRESS (WM_APP + 2)
#define WM_TASK_FAILED (WM_APP + 3)
#define ID_USB 101
#define ID_WIFI 102
#define ID_STOP 103
#define ID_REFRESH 104
#define ID_PAIR 105
#define ID_KEYBOARD_SETTINGS 106
#define ID_HELP 107
#define ID_DEVICE 108
#define ID_ENDPOINT 109
#define ID_PAIR_ENDPOINT 110
#define ID_PAIR_CODE 111
#define ID_KEYBOARD 112
#define ID_MOUSE 113
#define ID_LOG 114
#define ID_STATUS 115
#define ID_SAMSUNG 116
#define ID_CAPTURE 117
#define ID_EDITOR 118
#define ID_TOOLS_SELECT 119
#define ID_TOOLS_RETRY 120
#define ID_TOOLS_OPEN 121
#define ID_TOOLS_MISSING 122
#define TIMER_PROCESS 1

typedef struct {
    wchar_t serial[256];
    wchar_t model[160];
    wchar_t state[64];
    int wireless;
} Device;
typedef enum { OP_REFRESH, OP_USB, OP_WIFI, OP_PAIR, OP_KEYBOARD, OP_STOP, OP_CONNECT, OP_START } Operation;
typedef struct {
    Operation op;
    wchar_t selected[256];
    wchar_t endpoint[256];
    wchar_t pairEndpoint[256];
    wchar_t code[32];
    int keyboardSdk;
    int mouseUhid;
    int audioMode, clipboard;
    GalaxyPhoneCallback callback;
    void *callbackContext;
    HANDLE runningProcess;
    DWORD runningPid;
    wchar_t runningSerial[256];
} Task;
typedef struct {
    int success;
    Operation op;
    Device devices[MAX_DEVICES];
    int count;
    wchar_t message[1200];
    wchar_t detail[OUTPUT_CAP];
    wchar_t activeSerial[256];
    wchar_t endpoint[256];
    HANDLE launchedProcess;
    DWORD launchedPid;
    GalaxyPhoneCallback callback;
    void *callbackContext;
    char error[64];
} Result;

static HINSTANCE g_instance;
static HWND g_window, g_combo, g_endpoint, g_pairEndpoint, g_code;
static HWND g_keyboard, g_mouse, g_log, g_status;
static HFONT g_font, g_titleFont;
static wchar_t g_base[32768], g_tools[32768], g_adb[32768];
static wchar_t g_scrcpy[32768], g_server[32768], g_logPath[MAX_PATH];
static wchar_t g_config[32768], g_activeSerial[256];
static int g_toolsReady;
static int g_audioMode = 0, g_clipboard = 1;
static HANDLE g_process;
static DWORD g_processId;
static Device g_devices[MAX_DEVICES];
static int g_deviceCount, g_busy, g_closing;
static int g_dpi = 96;
static int scale(int value){return MulDiv(value,g_dpi,96); }

static void copyw(wchar_t *dest, size_t count, const wchar_t *src) {
    if (!count) return;
    wcsncpy(dest, src ? src : L"", count - 1);
    dest[count - 1] = 0;
}
static void trim(wchar_t *s) {
    size_t n = wcslen(s), start = 0;
    while (start < n && iswspace(s[start])) ++start;
    if (start) memmove(s, s + start, (n - start + 1) * sizeof(wchar_t));
    n = wcslen(s);
    while (n && iswspace(s[n - 1])) s[--n] = 0;
}
static void utf8wide(const char *in, wchar_t *out, int cap) {
    if (!MultiByteToWideChar(CP_UTF8, 0, in, -1, out, cap)) {
        MultiByteToWideChar(CP_ACP, 0, in, -1, out, cap);
    }
    out[cap - 1] = 0;
}
static void setMessage(Result *r, int success, const wchar_t *s) {
    r->success = success;
    copyw(r->message, ARRAYSIZE(r->message), s);
}
static void appendDetail(Result *r, const wchar_t *s) {
    size_t n = wcslen(r->detail);
    if (n + 2 < ARRAYSIZE(r->detail)) {
        if (n) { r->detail[n++] = L'\r'; r->detail[n++] = L'\n'; }
        copyw(r->detail + n, ARRAYSIZE(r->detail) - n, s);
    }
}
static void progress(const wchar_t *s) {
    size_t bytes = (wcslen(s) + 1) * sizeof(wchar_t);
    wchar_t *message = (wchar_t *)malloc(bytes);
    if (message) {
        memcpy(message, s, bytes);
        if (!PostMessageW(g_window, WM_PROGRESS, 0, (LPARAM)message)) free(message);
    }
}
/* Windows argument quoting; no cmd.exe or shell interpretation. */
static int quoteArgument(wchar_t *dest, size_t cap, const wchar_t *arg) {
    size_t n = wcslen(dest);
    if (n + 3 >= cap) return 0;
    if (n) dest[n++] = L' ';
    dest[n++] = L'"';
    for (const wchar_t *p = arg; *p;) {
        size_t slashes = 0;
        while (*p == L'\\') { ++slashes; ++p; }
        size_t copies = slashes;
        if (*p == L'"' || !*p) copies *= 2;
        if (n + copies + 3 >= cap) return 0;
        while (copies--) dest[n++] = L'\\';
        if (*p == L'"') dest[n++] = L'\\';
        if (*p) dest[n++] = *p++;
    }
    dest[n++] = L'"'; dest[n] = 0;
    return 1;
}
static int validEndpoint(const wchar_t *s) {
    size_t n = wcslen(s);
    const wchar_t *port = wcsrchr(s, L':');
    if (n < 4 || n > 240 || !port || port == s || !port[1]) return 0;
    for (const wchar_t *p = s; *p; ++p) {
        if (!((*p >= L'0' && *p <= L'9') || (*p >= L'a' && *p <= L'z') ||
              (*p >= L'A' && *p <= L'Z') || wcschr(L".:-_[]", *p))) return 0;
    }
    unsigned long number = 0;
    for (++port; *port; ++port) {
        if (*port < L'0' || *port > L'9') return 0;
        number = number * 10 + (unsigned long)(*port - L'0');
        if (number > 65535) return 0;
    }
    return number > 0;
}
static int validCode(const wchar_t *s) {
    if (wcslen(s) != 6) return 0;
    for (int i = 0; i < 6; ++i) if (s[i] < L'0' || s[i] > L'9') return 0;
    return 1;
}

/* Executes on worker thread. Drains stdout while waiting to avoid a full-pipe
 * deadlock and never waits for EOF (an ADB daemon may retain a pipe handle). */
static int runAdb(const wchar_t **args, int argc, const wchar_t *input,
                  DWORD timeout, wchar_t *output, size_t outputCap) {
    wchar_t command[4096] = L"";
    output[0] = 0;
    if (!quoteArgument(command, ARRAYSIZE(command), g_adb)) return -1;
    for (int i = 0; i < argc; ++i)
        if (!quoteArgument(command, ARRAYSIZE(command), args[i])) return -1;
    SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, TRUE };
    HANDLE readOut = NULL, writeOut = NULL, readIn = NULL, writeIn = NULL;
    if (!CreatePipe(&readOut, &writeOut, &sa, 0) ||
        !CreatePipe(&readIn, &writeIn, &sa, 0)) {
        copyw(output, outputCap, L"프로그램 통신을 준비하지 못했습니다.");
        if (readOut) CloseHandle(readOut);
        if (writeOut) CloseHandle(writeOut);
        if (readIn) CloseHandle(readIn);
        if (writeIn) CloseHandle(writeIn);
        return -1;
    }
    SetHandleInformation(readOut, HANDLE_FLAG_INHERIT, 0);
    SetHandleInformation(writeIn, HANDLE_FLAG_INHERIT, 0);
    STARTUPINFOW si = {0};
    PROCESS_INFORMATION pi = {0};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdInput = readIn; si.hStdOutput = writeOut; si.hStdError = writeOut;
    BOOL started = CreateProcessW(g_adb, command, NULL, NULL, TRUE,
                                 CREATE_NO_WINDOW, NULL, g_tools, &si, &pi);
    CloseHandle(readIn); CloseHandle(writeOut);
    if (!started) {
        DWORD error = GetLastError();
        swprintf(output, outputCap, L"ADB 실행 실패 (Windows 오류 %lu). tools 폴더가 함께 있는지 확인하세요.", error);
        CloseHandle(readOut); CloseHandle(writeIn); return -1;
    }
    CloseHandle(pi.hThread);
    if (input && *input) {
        char bytes[128] = {0};
        int len = WideCharToMultiByte(CP_UTF8, 0, input, -1, bytes, sizeof(bytes) - 2, NULL, NULL);
        if (len > 0) {
            bytes[len - 1] = '\n';
            DWORD written;
            WriteFile(writeIn, bytes, (DWORD)len, &written, NULL);
        }
        SecureZeroMemory(bytes, sizeof(bytes));
    }
    CloseHandle(writeIn);
    char buffer[OUTPUT_CAP] = {0}; size_t used = 0;
    ULONGLONG start = GetTickCount64();
    int timedOut = 0;
    for (;;) {
        DWORD available = 0;
        if (PeekNamedPipe(readOut, NULL, 0, NULL, &available, NULL) && available) {
            char piece[2048]; DWORD got = 0;
            if (ReadFile(readOut, piece, min(available, (DWORD)sizeof(piece)), &got, NULL) && got) {
                size_t keep = min((size_t)got, sizeof(buffer) - used - 1);
                memcpy(buffer + used, piece, keep); used += keep; buffer[used] = 0;
                continue;
            }
        }
        if (WaitForSingleObject(pi.hProcess, 25) == WAIT_OBJECT_0) {
            for (;;) {
                available = 0;
                if (!PeekNamedPipe(readOut, NULL, 0, NULL, &available, NULL) || !available) break;
                char piece[2048]; DWORD got = 0;
                if (!ReadFile(readOut, piece, min(available, (DWORD)sizeof(piece)), &got, NULL) || !got) break;
                size_t keep = min((size_t)got, sizeof(buffer) - used - 1);
                memcpy(buffer + used, piece, keep); used += keep; buffer[used] = 0;
            }
            break;
        }
        if (GetTickCount64() - start >= timeout) {
            TerminateProcess(pi.hProcess, 1); timedOut = 1;
            WaitForSingleObject(pi.hProcess, 1000); break;
        }
    }
    DWORD exitCode = 1;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    CloseHandle(pi.hProcess); CloseHandle(readOut);
    utf8wide(buffer, output, (int)outputCap);
    SecureZeroMemory(buffer, sizeof(buffer));
    if (timedOut) {
        copyw(output, outputCap, L"응답 시간이 초과되었습니다. 휴대폰의 허용 창, 케이블 또는 같은 Wi-Fi 연결을 확인하세요.");
        return -2;
    }
    return (int)exitCode;
}
static int readDevices(Result *r) {
    const wchar_t *args[] = {L"devices", L"-l"};
    wchar_t output[OUTPUT_CAP];
    int code = runAdb(args, 2, NULL, 15000, output, ARRAYSIZE(output));
    appendDetail(r, output); r->count = 0;
    if (code != 0) return 0;
    wchar_t *context = NULL;
    for (wchar_t *line = wcstok(output, L"\r\n", &context); line; line = wcstok(NULL, L"\r\n", &context)) {
        wchar_t serial[256] = L"", state[64] = L"";
        if (swscanf(line, L"%255ls %63ls", serial, state) != 2) continue;
        if (wcscmp(state, L"device") && wcscmp(state, L"unauthorized") && wcscmp(state, L"offline")) continue;
        if (!wcsncmp(serial, L"emulator-", 9)) continue;
        if (r->count >= MAX_DEVICES) break;
        Device *d = &r->devices[r->count++];
        copyw(d->serial, ARRAYSIZE(d->serial), serial);
        copyw(d->state, ARRAYSIZE(d->state), state);
        d->wireless = wcschr(serial, L':') != NULL || wcsstr(serial, L"_adb-tls") != NULL;
        wchar_t *model = wcsstr(line, L"model:");
        if (model) {
            swscanf(model + 6, L"%159ls", d->model);
            for (wchar_t *p = d->model; *p; ++p) if (*p == L'_') *p = L' ';
        } else copyw(d->model, ARRAYSIZE(d->model), L"갤럭시");
    }
    return 1;
}
static int selectDevice(Result *r, Task *t, int wireless) {
    int candidate = -1, count = 0, selected = -1;
    for (int i = 0; i < r->count; ++i) {
        Device *d = &r->devices[i];
        if (d->wireless != wireless || wcscmp(d->state, L"device")) continue;
        /* An explicitly entered endpoint outranks a previously selected device. */
        if (t->endpoint[0] && !wcscmp(t->endpoint, d->serial)) return i;
        if (t->selected[0] && !wcscmp(t->selected, d->serial)) selected = i;
        candidate = i; ++count;
    }
    if (selected >= 0) return selected;
    if (count == 1) return candidate;
    if (count > 1) setMessage(r, 0, L"연결된 휴대폰이 여러 대입니다. 위의 기기 목록에서 사용할 휴대폰을 선택하세요.");
    return -1;
}
static int discoverEndpoint(Result *r, wchar_t *endpoint, size_t cap) {
    const wchar_t *args[] = {L"mdns", L"services"};
    wchar_t output[OUTPUT_CAP];
    if (runAdb(args, 2, NULL, 10000, output, ARRAYSIZE(output)) != 0) return 0;
    appendDetail(r, output);
    wchar_t *context = NULL; int count = 0;
    for (wchar_t *line = wcstok(output, L"\r\n", &context); line; line = wcstok(NULL, L"\r\n", &context)) {
        if (!wcsstr(line, L"_adb-tls-connect._tcp")) continue;
        wchar_t name[256], type[128], address[256];
        if (swscanf(line, L"%255ls %127ls %255ls", name, type, address) == 3 && validEndpoint(address)) {
            copyw(endpoint, cap, address); ++count;
        }
    }
    if (count != 1) { endpoint[0] = 0; return 0; }
    return 1;
}
static int connectAdb(Result *r, const wchar_t *endpoint) {
    const wchar_t *args[] = {L"connect", endpoint}; wchar_t output[OUTPUT_CAP];
    int code = runAdb(args, 2, NULL, 15000, output, ARRAYSIZE(output));
    appendDetail(r, output);
    if (code || (!wcsstr(output, L"connected to") && !wcsstr(output, L"already connected"))) return 0;
    copyw(r->endpoint, ARRAYSIZE(r->endpoint), endpoint);
    return 1;
}
static int launchScrcpy(Result *r, Task *t, const wchar_t *serial) {
    wchar_t command[4096] = L"";
    const wchar_t *args[] = { L"--serial", serial, L"--window-title=Bogo Tools",
        t->keyboardSdk ? L"--keyboard=sdk" : L"--keyboard=uhid",
        t->mouseUhid ? L"--mouse=uhid" : L"--mouse=sdk", L"--shortcut-mod=lalt", L"--max-size=1920" };
    if (!quoteArgument(command, ARRAYSIZE(command), g_scrcpy)) return 0;
    for (int i = 0; i < (int)ARRAYSIZE(args); ++i)
        if (!quoteArgument(command, ARRAYSIZE(command), args[i])) return 0;
    if (t->keyboardSdk && !quoteArgument(command, ARRAYSIZE(command), L"--prefer-text")) return 0;
    if (!quoteArgument(command, ARRAYSIZE(command), t->audioMode == 2 ? L"--no-audio" : L"--audio-source=output")) return 0;
    if (t->audioMode == 1 && !quoteArgument(command, ARRAYSIZE(command), L"--audio-codec=aac")) return 0;
    if (!t->clipboard && !quoteArgument(command, ARRAYSIZE(command), L"--no-clipboard-autosync")) return 0;
    SECURITY_ATTRIBUTES sa = {sizeof(sa), NULL, TRUE};
    HANDLE log = CreateFileW(g_logPath, GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                             &sa, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    HANDLE nullInput = CreateFileW(L"NUL", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                   &sa, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (log == INVALID_HANDLE_VALUE || nullInput == INVALID_HANDLE_VALUE) {
        if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
        if (nullInput != INVALID_HANDLE_VALUE) CloseHandle(nullInput);
        setMessage(r, 0, L"실행 기록 파일을 열지 못했습니다. 이 컴퓨터의 임시 폴더 접근 권한을 확인하세요.");
        return 0;
    }
    STARTUPINFOW si = {0}; PROCESS_INFORMATION pi = {0}; si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = nullInput; si.hStdOutput = log; si.hStdError = log;
    BOOL ok = CreateProcessW(g_scrcpy, command, NULL, NULL, TRUE, CREATE_NO_WINDOW,
                            NULL, g_tools, &si, &pi);
    CloseHandle(log); CloseHandle(nullInput);
    if (!ok) {
        swprintf(r->message, ARRAYSIZE(r->message), L"휴대폰 화면 실행 실패 (Windows 오류 %lu). tools 폴더가 함께 있는지 확인하세요.", GetLastError());
        return 0;
    }
    CloseHandle(pi.hThread);
    r->launchedProcess = pi.hProcess; r->launchedPid = pi.dwProcessId;
    copyw(r->activeSerial, ARRAYSIZE(r->activeSerial), serial);
    setMessage(r, 1, t->mouseUhid ?
        L"갤럭시 화면을 여는 중입니다. 폰 커서 모드는 왼쪽 Alt 키를 눌렀다 떼면 PC로 돌아옵니다." :
        L"갤럭시 화면을 여는 중입니다. 휴대폰 입력칸을 클릭한 뒤 키보드를 입력하세요.");
    return 1;
}
static BOOL CALLBACK closeOurWindow(HWND hwnd, LPARAM pid) {
    DWORD windowPid = 0; GetWindowThreadProcessId(hwnd, &windowPid);
    if (windowPid == (DWORD)pid) PostMessageW(hwnd, WM_CLOSE, 0, 0);
    return TRUE;
}
static void stopOurProcess(HANDLE process, DWORD pid) {
    if (!process) return;
    EnumWindows(closeOurWindow, (LPARAM)pid);
    if (WaitForSingleObject(process, 1800) != WAIT_OBJECT_0) {
        TerminateProcess(process, 0); WaitForSingleObject(process, 1000);
    }
}
static DWORD WINAPI worker(LPVOID data) {
    Task *t = (Task *)data;
    Result *r = (Result *)calloc(1, sizeof(Result));
    if (!r) { PostMessageW(g_window, WM_TASK_FAILED, (WPARAM)t->callback, (LPARAM)t->callbackContext); SecureZeroMemory(t, sizeof(*t)); free(t); return 0; }
    r->op = t->op;
    r->callback = t->callback; r->callbackContext = t->callbackContext;
    if (t->op == OP_STOP) {
        stopOurProcess(t->runningProcess, t->runningPid);
        setMessage(r, 1, L"갤럭시 화면을 닫았습니다. 다시 연결하려면 USB 또는 Wi-Fi 버튼을 누르세요.");
        goto finished;
    }
    if (t->op == OP_PAIR) {
        progress(L"휴대폰과 페어링하는 중입니다. 휴대폰의 페어링 코드 창을 열어두세요.");
        const wchar_t *args[] = {L"pair", t->pairEndpoint};
        wchar_t output[OUTPUT_CAP];
        int code = runAdb(args, 2, t->code, 45000, output, ARRAYSIZE(output));
        SecureZeroMemory(t->code, sizeof(t->code)); appendDetail(r, output);
        if (!code && wcsstr(output, L"Successfully paired")) {
            setMessage(r, 1, L"페어링 완료. 'Wi-Fi 연결'을 누르세요. 자동 검색이 안 되면 연결용 주소를 입력하세요.");
            readDevices(r);
        } else setMessage(r, 0, L"페어링하지 못했습니다. 폰에서 새 페어링 창을 열고 그 창의 주소와 6자리 코드를 입력하세요.");
        goto finished;
    }
    if (t->op == OP_KEYBOARD) {
        const wchar_t *serial = t->callback ? t->selected : (t->runningSerial[0] ? t->runningSerial : t->selected);
        if (!serial[0]) {
            setMessage(r, 0, L"먼저 휴대폰을 연결한 뒤 '한글 키보드 설정'을 누르세요."); goto finished;
        }
        const wchar_t *args[] = {L"-s", serial, L"shell", L"am", L"start", L"-a", L"android.settings.HARD_KEYBOARD_SETTINGS"};
        wchar_t output[OUTPUT_CAP];
        int code = runAdb(args, 7, NULL, 15000, output, ARRAYSIZE(output)); appendDetail(r, output);
        int opened = code == 0 && !wcsstr(output, L"Error:") && !wcsstr(output, L"Exception");
        setMessage(r, opened, opened ?
            L"휴대폰에서 물리 키보드 설정을 열었습니다. scrcpy 키보드의 한국어·영어 레이아웃을 선택하세요." :
            L"키보드 설정을 열지 못했습니다. 폰 설정에서 '물리 키보드'를 검색하세요.");
        goto finished;
    }
    progress(L"연결된 휴대폰을 확인하는 중입니다…");
    if (!readDevices(r)) {
        setMessage(r, 0, L"휴대폰 목록을 읽지 못했습니다. 아래 연결 기록을 확인하세요."); goto finished;
    }
    if (t->op == OP_REFRESH) {
        setMessage(r, 1, r->count ? L"휴대폰 목록을 새로 확인했습니다." :
            L"발견된 휴대폰이 없습니다. USB 케이블과 디버깅 허용을 확인하거나 Wi-Fi 페어링을 하세요.");
        goto finished;
    }
    if (t->op == OP_CONNECT) {
        if (connectAdb(r, t->endpoint)) {
            readDevices(r); setMessage(r, 1, L"휴대폰 목록을 새로 확인했습니다.");
        } else setMessage(r, 0, L"자동으로 연결하지 못했습니다. 같은 Wi-Fi와 무선 디버깅을 확인하세요. 폰 기본 화면의 'IP 주소 및 포트'를 연결용 주소에 넣거나 새 PC에서는 먼저 페어링하세요.");
        goto finished;
    }
    if (t->op == OP_START) {
        int index = -1;
        for (int i = 0; i < r->count; ++i)
            if (!wcscmp(t->selected, r->devices[i].serial)) { index = i; break; }
        if (index < 0) { strcpy(r->error, "phoneDeviceMissing"); goto finished; }
        if (!wcscmp(r->devices[index].state, L"unauthorized")) { strcpy(r->error, "phoneUnauthorized"); goto finished; }
        if (wcscmp(r->devices[index].state, L"device")) { strcpy(r->error, "phoneDeviceMissing"); goto finished; }
        launchScrcpy(r, t, t->selected); goto finished;
    }
    if (t->op == OP_USB) {
        int index = selectDevice(r, t, 0);
        if (index >= 0) launchScrcpy(r, t, r->devices[index].serial);
        else if (!r->message[0]) {
            int unauthorized = 0;
            for (int i = 0; i < r->count; ++i)
                if (!r->devices[i].wireless && !wcscmp(r->devices[i].state, L"unauthorized")) unauthorized = 1;
            setMessage(r, 0, unauthorized ?
                L"휴대폰 잠금을 풀고 'USB 디버깅을 허용하시겠습니까?'에서 이 컴퓨터를 허용하세요. 이후 USB 연결을 다시 누르세요." :
                L"USB 휴대폰이 없습니다. 데이터 USB 케이블을 연결하고 USB 디버깅을 켜세요. 회사 PC에서 계속 안 보이면 IT 담당자에게 삼성 USB 드라이버를 요청하세요.");
        }
        goto finished;
    }
    if (t->op == OP_WIFI) {
        int index = -1;
        if (t->endpoint[0]) {
            progress(L"입력한 주소로 Wi-Fi 연결하는 중입니다…");
            if (!connectAdb(r, t->endpoint)) {
                setMessage(r, 0, L"이 주소로 연결하지 못했습니다. 폰 무선 디버깅 기본 화면의 현재 주소·포트를 확인하세요. 새 PC는 최초 페어링이 필요합니다.");
                goto finished;
            }
            readDevices(r); index = selectDevice(r, t, 1);
        } else {
            index = selectDevice(r, t, 1);
            if (index < 0 && !r->message[0]) {
                progress(L"같은 네트워크의 갤럭시를 자동 검색하는 중입니다…");
                wchar_t endpoint[256] = L"";
                if (discoverEndpoint(r, endpoint, ARRAYSIZE(endpoint)) && connectAdb(r, endpoint)) {
                    copyw(t->endpoint, ARRAYSIZE(t->endpoint), endpoint);
                    readDevices(r); index = selectDevice(r, t, 1);
                }
            }
        }
        if (index >= 0) launchScrcpy(r, t, r->devices[index].serial);
        else if (!r->message[0]) setMessage(r, 0,
            L"자동으로 연결하지 못했습니다. 같은 Wi-Fi와 무선 디버깅을 확인하세요. 폰 기본 화면의 'IP 주소 및 포트'를 연결용 주소에 넣거나 새 PC에서는 먼저 페어링하세요.");
    }
finished:
    if (!r->success && !r->error[0]) {
        const char *error = t->op == OP_PAIR ? "phonePairingFailed" :
            t->op == OP_CONNECT ? "phoneConnectFailed" : t->op == OP_START ? "phoneStartFailed" : "phoneUnavailable";
        strcpy(r->error, error);
    }
    SecureZeroMemory(t, sizeof(*t)); free(t);
    if (!PostMessageW(g_window, WM_RESULT, 0, (LPARAM)r)) {
        if (r->launchedProcess) { stopOurProcess(r->launchedProcess, r->launchedPid); CloseHandle(r->launchedProcess); }
        SecureZeroMemory(r, sizeof(*r)); free(r);
    }
    return 0;
}
static void updateControls(void) {
    int connectionIds[] = {ID_USB, ID_WIFI, ID_PAIR};
    for (int i = 0; i < (int)ARRAYSIZE(connectionIds); ++i)
        EnableWindow(GetDlgItem(g_window, connectionIds[i]), !g_busy && !g_process);
    EnableWindow(GetDlgItem(g_window, ID_STOP), !g_busy && g_process != NULL);
    EnableWindow(GetDlgItem(g_window, ID_REFRESH), !g_busy);
    EnableWindow(GetDlgItem(g_window, ID_KEYBOARD_SETTINGS), !g_busy);
    EnableWindow(g_combo, !g_busy && !g_process);
    EnableWindow(g_keyboard, !g_busy && !g_process);
    EnableWindow(g_mouse, !g_busy && !g_process);
    EnableWindow(g_endpoint, !g_busy && !g_process);
    EnableWindow(g_pairEndpoint, !g_busy && !g_process);
    EnableWindow(g_code, !g_busy && !g_process);
}
static void populateDevices(Result *r) {
    int oldIndex = (int)SendMessageW(g_combo, CB_GETCURSEL, 0, 0);
    wchar_t oldSerial[256] = L"";
    if (oldIndex >= 0 && oldIndex < g_deviceCount)
        copyw(oldSerial, ARRAYSIZE(oldSerial), g_devices[oldIndex].serial);
    SendMessageW(g_combo, CB_RESETCONTENT, 0, 0);
    g_deviceCount = r->count;
    memcpy(g_devices, r->devices, sizeof(Device) * r->count);
    int choose = 0;
    for (int i = 0; i < r->count; ++i) {
        wchar_t label[640];
        const wchar_t *state = !wcscmp(r->devices[i].state, L"device") ? L"연결됨" :
            !wcscmp(r->devices[i].state, L"unauthorized") ? L"폰에서 허용 필요" : L"응답 없음";
        swprintf(label, ARRAYSIZE(label), L"%ls · %ls · %ls (%ls)",
            r->devices[i].model, r->devices[i].wireless ? L"Wi-Fi" : L"USB", state, r->devices[i].serial);
        SendMessageW(g_combo, CB_ADDSTRING, 0, (LPARAM)label);
        if (!wcscmp(oldSerial, r->devices[i].serial) ||
            (r->activeSerial[0] && !wcscmp(r->activeSerial, r->devices[i].serial))) choose = i;
    }
    if (!r->count) SendMessageW(g_combo, CB_ADDSTRING, 0, (LPARAM)L"연결된 휴대폰 없음");
    SendMessageW(g_combo, CB_SETCURSEL, choose, 0);
}
static void beginTask(Operation op) {
    if (g_busy) return;
    if ((op == OP_USB || op == OP_WIFI || op == OP_PAIR) && g_process) return;
    Task *t = (Task *)calloc(1, sizeof(Task));
    if (!t) return;
    t->op = op;
    int index = (int)SendMessageW(g_combo, CB_GETCURSEL, 0, 0);
    if (index >= 0 && index < g_deviceCount)
        copyw(t->selected, ARRAYSIZE(t->selected), g_devices[index].serial);
    GetWindowTextW(g_endpoint, t->endpoint, ARRAYSIZE(t->endpoint)); trim(t->endpoint);
    GetWindowTextW(g_pairEndpoint, t->pairEndpoint, ARRAYSIZE(t->pairEndpoint)); trim(t->pairEndpoint);
    GetWindowTextW(g_code, t->code, ARRAYSIZE(t->code)); trim(t->code);
    t->keyboardSdk = SendMessageW(g_keyboard, CB_GETCURSEL, 0, 0) == 1;
    t->mouseUhid = SendMessageW(g_mouse, CB_GETCURSEL, 0, 0) == 1;
    t->audioMode = g_audioMode; t->clipboard = g_clipboard;
    t->runningProcess = g_process; t->runningPid = g_processId;
    copyw(t->runningSerial, ARRAYSIZE(t->runningSerial), g_activeSerial);
    if (op == OP_WIFI && t->endpoint[0] && !validEndpoint(t->endpoint)) {
        SetWindowTextW(g_status, L"연결용 주소를 '192.168.1.6:37123'처럼 IP:포트 형식으로 입력하세요."); goto rejected;
    }
    if (op == OP_PAIR && (!validEndpoint(t->pairEndpoint) || !validCode(t->code))) {
        SetWindowTextW(g_status, L"폰의 '페어링 코드로 기기 페어링' 창에 나온 주소:포트와 숫자 6자리를 입력하세요."); goto rejected;
    }
    if (op == OP_PAIR) SetWindowTextW(g_code, L"");
    WritePrivateProfileStringW(L"input", L"keyboard", t->keyboardSdk ? L"sdk" : L"uhid", g_config);
    WritePrivateProfileStringW(L"input", L"mouse", t->mouseUhid ? L"uhid" : L"sdk", g_config);
    g_busy = 1; updateControls();
    SetWindowTextW(g_status, op == OP_STOP ? L"갤럭시 화면을 닫는 중입니다…" : L"작업 중입니다…");
    HANDLE thread = CreateThread(NULL, 0, worker, t, 0, NULL);
    if (!thread) {
        g_busy = 0; updateControls(); SetWindowTextW(g_status, L"작업을 시작하지 못했습니다."); goto rejected;
    }
    CloseHandle(thread); return;
rejected:
    SecureZeroMemory(t, sizeof(*t)); free(t);
}
static HWND control(const wchar_t *cls, const wchar_t *text, DWORD style, int id,
                     int x, int y, int w, int h) {
    HWND hwnd = CreateWindowExW((!wcscmp(cls, L"EDIT") || !wcscmp(cls, WC_COMBOBOXW)) ? WS_EX_CLIENTEDGE : 0,
        cls, text, WS_CHILD | WS_VISIBLE | style,
        MulDiv(x, g_dpi, 96), MulDiv(y, g_dpi, 96), MulDiv(w, g_dpi, 96), MulDiv(h, g_dpi, 96),
        g_window, (HMENU)(INT_PTR)id, g_instance, NULL);
    SendMessageW(hwnd, WM_SETFONT, (WPARAM)g_font, TRUE);
#ifdef GALAXY_EMBEDDED
    GalaxyRegisterText(hwnd,text);
#endif
    return hwnd;
}
static void label(const wchar_t *text, int x, int y, int w, int h) {
    control(L"STATIC", text, 0, 0, x, y, w, h);
}
static int phoneToolFileExists(const wchar_t *path, void *unused) {
    (void)unused;
    /* Child process working folders and upstream tools still need a short
     * ordinary path. Report this explicitly rather than silently truncating. */
    if (wcslen(path) >= MAX_PATH) return 0;
    DWORD attributes = GetFileAttributesW(path);
    return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
}
static int usePhoneTools(const wchar_t *folder) {
    if (!GalaxyPhoneToolsComplete(folder, phoneToolFileExists, NULL)) return 0;
    if (!GalaxyJoinToolPath(g_adb, ARRAYSIZE(g_adb), folder, L"adb.exe") ||
        !GalaxyJoinToolPath(g_scrcpy, ARRAYSIZE(g_scrcpy), folder, L"scrcpy.exe") ||
        !GalaxyJoinToolPath(g_server, ARRAYSIZE(g_server), folder, L"scrcpy-server")) return 0;
    if (folder != g_tools) copyw(g_tools, ARRAYSIZE(g_tools), folder);
    SetEnvironmentVariableW(L"ADB", g_adb);
    SetEnvironmentVariableW(L"SCRCPY_SERVER_PATH", g_server);
    g_toolsReady = 1; return 1;
}
static int resolvePhoneTools(const wchar_t *root) {
    wchar_t folder[32768];
    return GalaxyFindPhoneTools(root, folder, ARRAYSIZE(folder), phoneToolFileExists, NULL) &&
           usePhoneTools(folder);
}
static void refreshMissingTools(void) {
    wchar_t missing[1024] = L"", path[32768];
    for (size_t i = 0; i < ARRAYSIZE(GalaxyPhoneToolFiles); ++i) {
        if (!GalaxyJoinToolPath(path, ARRAYSIZE(path), g_tools, GalaxyPhoneToolFiles[i]) ||
            !phoneToolFileExists(path, NULL)) {
            if (missing[0]) wcscat(missing, L", ");
            wcscat(missing, GalaxyPhoneToolFiles[i]);
        }
    }
    SetWindowTextW(GetDlgItem(g_window, ID_TOOLS_MISSING), missing);
}
static void layoutToolsRecovery(void) {
    HWND title = control(L"STATIC", L"휴대폰 연결 파일을 찾지 못했습니다.", 0, 0, 24, 24, 735, 40);
    SendMessageW(title, WM_SETFONT, (WPARAM)g_titleFont, TRUE);
    label(L"프로그램과 tools 폴더를 함께 압축 해제해 주세요. 이미지·PDF·캡처 등 다른 기능은 계속 사용할 수 있습니다.", 24, 78, 735, 100);
    label(L"찾는 폴더", 24, 184, 735, 28);
    control(L"EDIT", g_tools, ES_READONLY | ES_AUTOHSCROLL | WS_TABSTOP, 0, 24, 218, 735, 34);
    label(L"없는 파일", 24, 272, 735, 28);
    control(L"EDIT", L"", ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL | WS_TABSTOP,
            ID_TOOLS_MISSING, 24, 306, 735, 92);
    control(L"BUTTON", L"연결 도구 폴더 선택", BS_PUSHBUTTON | WS_TABSTOP, ID_TOOLS_SELECT, 24, 420, 330, 46);
    control(L"BUTTON", L"다시 확인", BS_PUSHBUTTON | WS_TABSTOP, ID_TOOLS_RETRY, 372, 420, 180, 46);
    control(L"BUTTON", L"폴더 열기", BS_PUSHBUTTON | WS_TABSTOP, ID_TOOLS_OPEN, 570, 420, 190, 46);
    if (wcslen(g_tools) + wcslen(L"\\scrcpy-server") >= MAX_PATH)
        label(L"폴더 경로가 너무 깁니다. Bogo Tools 폴더를 C:\\GalaxyControl처럼 짧은 경로로 옮긴 뒤 다시 실행하세요.", 24, 496, 735, 110);
    refreshMissingTools();
}
static void layoutUI(void);
static void restorePhonePanel(void) {
    while (GetWindow(g_window, GW_CHILD)) DestroyWindow(GetWindow(g_window, GW_CHILD));
#ifdef GALAXY_EMBEDDED
    SCROLLINFO scroll = {0}; scroll.cbSize = sizeof(scroll);
    scroll.fMask = SIF_POS; scroll.nPos = 0; SetScrollInfo(g_window, SB_VERT, &scroll, TRUE);
#endif
    layoutUI(); SetTimer(g_window, TIMER_PROCESS, 500, NULL);
#ifdef GALAXY_EMBEDDED
    GalaxyLocalizeWindow(g_window);
#endif
    PostMessageW(g_window, WM_COMMAND, ID_REFRESH, 0);
}
static void selectPhoneTools(void) {
    BROWSEINFOW info = {0}; info.hwndOwner = g_window;
#ifdef GALAXY_EMBEDDED
    info.lpszTitle = GalaxyTr(L"Windows 폴더, Bogo Tools 폴더 또는 scrcpy 폴더를 선택하세요.");
#else
    info.lpszTitle = L"Windows 폴더, Bogo Tools 폴더 또는 scrcpy 폴더를 선택하세요.";
#endif
    info.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;
    g_busy = 1;
    PIDLIST_ABSOLUTE item = SHBrowseForFolderW(&info);
    g_busy = 0;
    if (!item) return;
    wchar_t folder[MAX_PATH];
    int ready = SHGetPathFromIDListW(item, folder) && resolvePhoneTools(folder);
    CoTaskMemFree(item);
    if (ready) restorePhonePanel();
    else MessageBoxW(g_window, L"선택한 폴더에 연결 도구가 없습니다. Windows 폴더 전체를 압축 해제한 뒤 다시 선택해 주세요.",
                     L"Bogo Tools 파일 확인", MB_OK | MB_ICONINFORMATION);
}
static void launchCaptureTool(int capture) {
#ifdef GALAXY_EMBEDDED
    PostMessageW(GetParent(g_window), WM_APP + 80, capture, 0); return;
#endif
    wchar_t path[MAX_PATH]; swprintf(path, ARRAYSIZE(path), L"%ls\\GalaxyCapture.exe", g_base);
    if (GetFileAttributesW(path) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(g_window, L"같은 Windows 폴더에 GalaxyCapture.exe가 있어야 합니다. Bogo Tools 폴더 전체를 복사하세요.", L"캡처 편집기 파일 확인", MB_OK | MB_ICONERROR); return;
    }
    HINSTANCE result = ShellExecuteW(g_window, L"open", path, capture ? L"--capture" : NULL, g_base, SW_SHOWNORMAL);
    if ((INT_PTR)result <= 32) MessageBoxW(g_window, L"캡처 편집기를 열지 못했습니다.", L"GalaxyCapture", MB_OK | MB_ICONERROR);
    else if (capture) ShowWindow(g_window, SW_MINIMIZE);
}
static void layoutUI(void) {
    HWND title = control(L"STATIC", L"Bogo Tools", 0, 0, 24, 18, 240, 32);
    SendMessageW(title, WM_SETFONT, (WPARAM)g_titleFont, TRUE);
    control(L"BUTTON", L"캡처·편집", BS_PUSHBUTTON | WS_TABSTOP, ID_EDITOR, 274, 20, 106, 34);
    control(L"BUTTON", L"영역 캡처", BS_PUSHBUTTON | WS_TABSTOP, ID_CAPTURE, 388, 20, 106, 34);
    control(L"BUTTON", L"화면 끝으로 이동 · 삼성 앱", BS_PUSHBUTTON | WS_TABSTOP, ID_SAMSUNG, 505, 20, 256, 34);
    label(L"화면과 소리 · PC 마우스와 키보드로 조작합니다.", 24, 54, 740, 24);
    label(L"휴대폰", 24, 92, 72, 24);
    g_combo = control(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_VSCROLL | WS_TABSTOP,
                      ID_DEVICE, 94, 87, 533, 240);
    control(L"BUTTON", L"새로 찾기", BS_PUSHBUTTON | WS_TABSTOP, ID_REFRESH, 641, 86, 120, 31);
    control(L"BUTTON", L"USB 연결", BS_DEFPUSHBUTTON | WS_TABSTOP, ID_USB, 24, 131, 234, 44);
    control(L"BUTTON", L"Wi-Fi 연결", BS_PUSHBUTTON | WS_TABSTOP, ID_WIFI, 274, 131, 234, 44);
    control(L"BUTTON", L"화면 닫기", BS_PUSHBUTTON | WS_TABSTOP, ID_STOP, 524, 131, 237, 44);
    label(L"USB: 데이터 케이블 연결 → 폰에서 USB 디버깅 켜기 → 이 PC 허용", 24, 185, 740, 24);
    label(L"연결용 주소", 24, 222, 105, 24);
    g_endpoint = control(L"EDIT", L"", ES_AUTOHSCROLL | WS_TABSTOP, ID_ENDPOINT, 140, 216, 325, 30);
    GalaxyCueBanner(g_endpoint,L"비워두면 자동 검색 · 예: 192.168.1.6:37123");
    label(L"폰 무선 디버깅 기본 화면의 주소:포트", 479, 220, 284, 38);
    label(L"처음 Wi-Fi로 연결하는 PC에서만 페어링하세요. 두 기기는 같은 네트워크여야 합니다.", 24, 264, 740, 24);
    label(L"페어링 주소", 24, 303, 106, 24);
    g_pairEndpoint = control(L"EDIT", L"", ES_AUTOHSCROLL | WS_TABSTOP, ID_PAIR_ENDPOINT, 140, 296, 284, 30);
    GalaxyCueBanner(g_pairEndpoint,L"폰의 '페어링 코드' 팝업에 나온 주소:포트");
    label(L"코드", 439, 302, 45, 24);
    g_code = control(L"EDIT", L"", ES_PASSWORD | ES_NUMBER | ES_AUTOHSCROLL | WS_TABSTOP,
                     ID_PAIR_CODE, 488, 296, 104, 30);
    SendMessageW(g_code, EM_SETLIMITTEXT, 6, 0);
    control(L"BUTTON", L"페어링", BS_PUSHBUTTON | WS_TABSTOP, ID_PAIR, 608, 294, 153, 34);
    label(L"키보드", 24, 350, 77, 24);
    g_keyboard = control(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP,
                         ID_KEYBOARD, 104, 343, 265, 150);
    SendMessageW(g_keyboard, CB_ADDSTRING, 0, (LPARAM)L"한글 가능 · 물리 키보드 (권장)");
    SendMessageW(g_keyboard, CB_ADDSTRING, 0, (LPARAM)L"기본 키보드 · 영어 입력용");
    wchar_t keyboard[16]; GetPrivateProfileStringW(L"input", L"keyboard", L"uhid", keyboard, ARRAYSIZE(keyboard), g_config);
    SendMessageW(g_keyboard, CB_SETCURSEL, !wcscmp(keyboard, L"sdk") ? 1 : 0, 0);
    label(L"마우스", 390, 350, 78, 24);
    g_mouse = control(WC_COMBOBOXW, L"", CBS_DROPDOWNLIST | WS_TABSTOP,
                      ID_MOUSE, 469, 343, 292, 150);
    SendMessageW(g_mouse, CB_ADDSTRING, 0, (LPARAM)L"자유 이동 · 창 밖으로 나가면 PC");
    SendMessageW(g_mouse, CB_ADDSTRING, 0, (LPARAM)L"폰 커서 · 왼쪽 Alt로 PC 복귀");
    wchar_t savedMouse[16];
    GetPrivateProfileStringW(L"input", L"mouse", L"uhid", savedMouse, ARRAYSIZE(savedMouse), g_config);
    SendMessageW(g_mouse, CB_SETCURSEL, !wcscmp(savedMouse, L"sdk") ? 0 : 1, 0);
    control(L"BUTTON", L"한글 키보드 설정", BS_PUSHBUTTON | WS_TABSTOP, ID_KEYBOARD_SETTINGS, 24, 388, 190, 34);
    label(L"한글 입력: 폰의 물리 키보드에서 한국어 레이아웃을 선택하세요.", 231, 391, 530, 32);
    g_status = control(L"STATIC", L"연결을 준비했습니다. USB 또는 Wi-Fi 연결을 선택하세요.", 0,
                       ID_STATUS, 24, 444, 737, 58);
    label(L"연결 기록", 24, 511, 170, 24);
    control(L"BUTTON", L"사용 도움말", BS_PUSHBUTTON | WS_TABSTOP, ID_HELP, 641, 506, 120, 31);
    g_log = control(L"EDIT", L"", ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | WS_VSCROLL | WS_TABSTOP,
                    ID_LOG, 24, 544, 737, 126);
    SendMessageW(g_log, EM_SETLIMITTEXT, OUTPUT_CAP - 1, 0);
    label(L"복사/붙여넣기: 갤럭시 창에서 Ctrl+V · 화면 닫기로 연결 종료", 24, 682, 740, 24);
    updateControls();
}
static void readScrcpyLog(wchar_t *output, size_t cap) {
    output[0] = 0;
    HANDLE file = CreateFileW(g_logPath, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE,
                              NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    char buffer[OUTPUT_CAP]; DWORD got = 0;
    if (ReadFile(file, buffer, sizeof(buffer) - 1, &got, NULL)) {
        buffer[got] = 0; utf8wide(buffer, output, (int)cap);
    }
    CloseHandle(file);
}
static void showHelp(void) {
    MessageBoxW(g_window,
        L"USB\r\n1. 데이터 USB 케이블로 연결합니다.\r\n2. 폰 개발자 옵션에서 USB 디버깅을 켭니다.\r\n3. 폰의 허용 창에서 이 PC를 허용하고 'USB 연결'을 누릅니다.\r\n\r\n"
        L"Wi-Fi\r\n새 PC는 한 번 페어링해야 합니다. 폰의 무선 디버깅 → '페어링 코드로 기기 페어링'에서 주소와 코드를 입력하세요. 이후 'Wi-Fi 연결'을 누르면 자동 검색합니다. 안 되면 폰 무선 디버깅 기본 화면의 현재 주소:포트를 입력하세요. 회사망은 무선 연결을 막을 수 있습니다.\r\n\r\n"
        L"한글 키보드\r\n'한글 가능 · 물리 키보드'로 연결하고 '한글 키보드 설정'을 누릅니다. 폰에서 scrcpy 키보드에 한국어·영어 레이아웃을 설정하세요. 폰 입력칸을 클릭해 입력합니다. PC는 영어 입력 상태로 두고 한영 전환은 폰 키보드 설정을 따릅니다.\r\n\r\n"
        L"마우스\r\n기본은 창 밖으로 나가면 PC로 돌아옵니다. '폰 커서' 모드는 왼쪽 Alt 키를 눌렀다 떼면 돌아옵니다. 실제 폰 화면을 다른 모니터처럼 화면 가장자리로 넘나드는 기능은 scrcpy에 없습니다.\r\n\r\n"
        L"소리\r\n휴대폰 소리는 PC의 기본 출력 장치에서 재생합니다. 소리가 없으면 PC의 출력 장치·음량을 확인하고 폰 잠금을 푼 뒤 다시 연결하세요. 소리 전달은 Android 11 이상에서 지원합니다.\r\n\r\n"
        L"다른 PC\r\nBogo Tools 폴더 전체를 복사하세요. 설치·관리자 권한은 필요 없습니다. 새 PC에서는 폰에서 USB 허용 또는 Wi-Fi 페어링을 다시 해야 합니다. 기존 ADB 인증키는 유지합니다.",
        L"Bogo Tools 사용 도움말", MB_OK | MB_ICONINFORMATION);
}
static LRESULT CALLBACK windowProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {
    switch (message) {
    case WM_CREATE:
        g_window = hwnd;
        if (g_toolsReady) { layoutUI(); SetTimer(hwnd, TIMER_PROCESS, 500, NULL);
            PostMessageW(hwnd, WM_COMMAND, ID_REFRESH, 0); }
        else layoutToolsRecovery();
        return 0;
    case WM_SIZE: {
#ifdef GALAXY_EMBEDDED
        RECT r;GetClientRect(hwnd,&r);SCROLLINFO info={0};info.cbSize=sizeof(info);info.fMask=SIF_RANGE|SIF_PAGE;info.nMax=scale(724);info.nPage=r.bottom;SetScrollInfo(hwnd,SB_VERT,&info,TRUE);
#endif
        return 0;
    }
#ifdef GALAXY_EMBEDDED
    case WM_VSCROLL:case WM_MOUSEWHEEL:{SCROLLINFO info={0};info.cbSize=sizeof(info);info.fMask=SIF_ALL;GetScrollInfo(hwnd,SB_VERT,&info);int old=info.nPos;if(message==WM_MOUSEWHEEL)info.nPos-=GET_WHEEL_DELTA_WPARAM(wParam)/WHEEL_DELTA*scale(50);else switch(LOWORD(wParam)){case SB_LINEUP:info.nPos-=scale(25);break;case SB_LINEDOWN:info.nPos+=scale(25);break;case SB_PAGEUP:info.nPos-=info.nPage;break;case SB_PAGEDOWN:info.nPos+=info.nPage;break;case SB_THUMBTRACK:info.nPos=info.nTrackPos;break;}info.fMask=SIF_POS;SetScrollInfo(hwnd,SB_VERT,&info,TRUE);GetScrollInfo(hwnd,SB_VERT,&info);ScrollWindowEx(hwnd,0,old-info.nPos,NULL,NULL,NULL,NULL,SW_SCROLLCHILDREN|SW_INVALIDATE|SW_ERASE);return 0;}
#endif
    case WM_COMMAND:
        if (!g_toolsReady) {
            switch (LOWORD(wParam)) {
            case ID_TOOLS_SELECT: selectPhoneTools(); break;
            case ID_TOOLS_RETRY:
                if (usePhoneTools(g_tools) || resolvePhoneTools(g_base)) restorePhonePanel();
                else refreshMissingTools();
                break;
            case ID_TOOLS_OPEN: ShellExecuteW(hwnd, L"open", g_base, NULL, NULL, SW_SHOWNORMAL); break;
            }
            return 0;
        }
        switch (LOWORD(wParam)) {
        case ID_USB: beginTask(OP_USB); break;
        case ID_WIFI: beginTask(OP_WIFI); break;
        case ID_PAIR: beginTask(OP_PAIR); break;
        case ID_REFRESH: beginTask(OP_REFRESH); break;
        case ID_STOP: beginTask(OP_STOP); break;
        case ID_KEYBOARD_SETTINGS: beginTask(OP_KEYBOARD); break;
        case ID_HELP: showHelp(); break;
        case ID_CAPTURE: launchCaptureTool(1); break;
        case ID_EDITOR: launchCaptureTool(0); break;
        case ID_SAMSUNG:
            if (MessageBoxW(hwnd,
                L"삼성 Galaxy Connect는 호환되는 PC에서 휴대폰으로 커서를 화면 끝을 통해 이동하는 기능을 제공합니다.\r\n\r\n"
                L"필요 조건: Windows 11 64비트, Intel Wi-Fi·Bluetooth, 호환 갤럭시, 같은 삼성 계정, Wi-Fi와 Bluetooth 켜기.\r\n\r\n"
                L"이 기능은 무선 연결입니다. USB로 쓸 때는 Bogo Tools의 'USB 연결'을 이용하세요.\r\n\r\n"
                L"Microsoft Store에서 공식 삼성 앱을 여시겠습니까?", L"화면 끝으로 이동", MB_OKCANCEL | MB_ICONINFORMATION) == IDOK)
                ShellExecuteW(hwnd, L"open", L"ms-windows-store://pdp/?ProductId=9NGW9K44GQ5F", NULL, NULL, SW_SHOWNORMAL);
            break;
        } return 0;
    case WM_PROGRESS:
        SetWindowTextW(g_status, (const wchar_t *)lParam); free((void *)lParam); return 0;
    case WM_TASK_FAILED:
        g_busy = 0; updateControls();
        if (wParam) ((GalaxyPhoneCallback)wParam)((void *)lParam, 0, "phoneUnavailable");
        return 0;
    case WM_RESULT: {
        Result *r = (Result *)lParam;
        g_busy = 0;
        if (r->op == OP_STOP && g_process) {
            CloseHandle(g_process); g_process = NULL; g_processId = 0; g_activeSerial[0] = 0;
        }
        if (r->op == OP_REFRESH || r->op == OP_USB || r->op == OP_WIFI || r->op == OP_CONNECT || r->op == OP_START || (r->op == OP_PAIR && r->success))
            populateDevices(r);
        SetWindowTextW(g_status, r->message);
        if (r->detail[0]) SetWindowTextW(g_log, r->detail);
        if (r->launchedProcess) {
            g_process = r->launchedProcess; g_processId = r->launchedPid;
            copyw(g_activeSerial, ARRAYSIZE(g_activeSerial), r->activeSerial);
        }
        /* Keep the field blank after auto discovery so next launch searches the
         * current port again. Explicit endpoint entries remain user-controlled. */
        updateControls();
        if (r->callback) r->callback(r->callbackContext, r->success, r->error);
        SecureZeroMemory(r, sizeof(*r)); free(r);
        if (g_closing) PostMessageW(hwnd, WM_CLOSE, 0, 0);
        return 0;
    }
    case WM_TIMER:
        if (g_process && !g_busy && WaitForSingleObject(g_process, 0) == WAIT_OBJECT_0) {
            DWORD code = 0; GetExitCodeProcess(g_process, &code);
            CloseHandle(g_process); g_process = NULL; g_processId = 0; g_activeSerial[0] = 0;
            wchar_t output[OUTPUT_CAP]; readScrcpyLog(output, ARRAYSIZE(output));
            if (output[0]) SetWindowTextW(g_log, output);
            SetWindowTextW(g_status, code ?
                L"갤럭시 화면 실행이 끝났습니다. 아래 기록을 확인하세요. 키보드 오류라면 '기본 키보드'를 선택해 다시 연결할 수 있습니다." :
                L"갤럭시 화면을 닫았습니다. 다시 연결하려면 USB 또는 Wi-Fi 버튼을 누르세요.");
            updateControls();
        }
        return 0;
    case WM_CLOSE:
        if (g_busy) {
            g_closing = 1; SetWindowTextW(g_status, L"현재 작업을 마친 뒤 닫습니다…"); return 0;
        }
        if (g_process) { g_closing = 1; beginTask(OP_STOP); return 0; }
        DestroyWindow(hwnd); return 0;
    case WM_DESTROY:
        KillTimer(hwnd, TIMER_PROCESS);
        if (g_font) DeleteObject(g_font);
        if (g_titleFont) DeleteObject(g_titleFont);
        DeleteFileW(g_logPath);
#ifndef GALAXY_EMBEDDED
        PostQuitMessage(0);
#endif
        g_window = NULL; return 0;
    case WM_CTLCOLORSTATIC: {
        HDC dc = (HDC)wParam; SetTextColor(dc, RGB(52, 43, 38)); SetBkColor(dc, RGB(255, 250, 246));
        SetDCBrushColor(dc, RGB(255, 250, 246));
        return (LRESULT)GetStockObject(DC_BRUSH);
    }
    }
    return DefWindowProcW(hwnd, message, wParam, lParam);
}
#ifdef GALAXY_EMBEDDED
HWND OpenPhonePanel(HINSTANCE instance, HWND parent) {
    HINSTANCE previous = NULL; LPWSTR commandLine = L""; int show = SW_SHOW;
    if (g_window && IsWindow(g_window)) { ShowWindow(g_window, SW_SHOW); return g_window; }
#else
int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, LPWSTR commandLine, int show) {
#endif
    (void)previous; (void)commandLine;
    g_instance = instance;
    SetProcessDPIAware();
    HDC screen = GetDC(NULL); if (screen) { g_dpi = GetDeviceCaps(screen, LOGPIXELSY); ReleaseDC(NULL, screen); }
    #ifdef GALAXY_EMBEDDED
    RECT parentRect;GetClientRect(parent,&parentRect);int fitDpi=(parentRect.right-24)*96/790;if(fitDpi>0&&fitDpi<g_dpi)g_dpi=fitDpi;
#endif
    DWORD pathLength = GetModuleFileNameW(NULL, g_base, ARRAYSIZE(g_base));
    if (!pathLength || pathLength >= ARRAYSIZE(g_base)) g_base[0] = 0;
    wchar_t *slash = wcsrchr(g_base, L'\\'); if (slash) *slash = 0;
    GalaxyJoinToolPath(g_tools, ARRAYSIZE(g_tools), g_base, L"tools\\scrcpy");
    GalaxyJoinToolPath(g_config, ARRAYSIZE(g_config), g_base, L"KIOControl.ini");
    g_toolsReady = resolvePhoneTools(g_base);
    wchar_t temp[MAX_PATH]; GetTempPathW(ARRAYSIZE(temp), temp);
    swprintf(g_logPath, ARRAYSIZE(g_logPath), L"%lsGalaxyControl-%lu.log", temp, GetCurrentProcessId());
    INITCOMMONCONTROLSEX cc = { sizeof(cc), ICC_STANDARD_CLASSES }; InitCommonControlsEx(&cc);
    g_font = CreateFontW(-MulDiv(16, g_dpi, 96), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
        OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Malgun Gothic");
    g_titleFont = CreateFontW(-MulDiv(25, g_dpi, 96), 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET,
        OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH, L"Segoe UI");
    WNDCLASSEXW wc = {0}; wc.cbSize = sizeof(wc); wc.lpfnWndProc = windowProc;
    wc.hInstance = instance; wc.hCursor = LoadCursorW(NULL, IDC_ARROW);
    wc.hIcon = LoadIconW(GetModuleHandleW(NULL), MAKEINTRESOURCEW(IDI_GALAXYCONTROL)); wc.hIconSm = wc.hIcon;
    wc.hbrBackground = CreateSolidBrush(RGB(255, 250, 246)); wc.lpszClassName = APP_CLASS;
    RegisterClassExW(&wc);
    RECT rect = {0, 0, MulDiv(786, g_dpi, 96), MulDiv(720, g_dpi, 96)}; AdjustWindowRectEx(&rect, WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX, FALSE, 0);
    HWND hwnd = CreateWindowExW(0, APP_CLASS, L"Bogo Tools · Windows",
#ifdef GALAXY_EMBEDDED
        WS_CHILD | WS_CLIPCHILDREN | WS_VSCROLL,
#else
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
#endif
        CW_USEDEFAULT, CW_USEDEFAULT, rect.right - rect.left, rect.bottom - rect.top, 
#ifdef GALAXY_EMBEDDED
        parent,
#else
        NULL,
#endif
        NULL, instance, NULL);
    if (!hwnd) return 0;
    ShowWindow(hwnd, show); UpdateWindow(hwnd);
#ifdef GALAXY_EMBEDDED
    return hwnd;
#else
    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0) > 0) {
        if (!IsDialogMessageW(hwnd, &msg)) { TranslateMessage(&msg); DispatchMessageW(&msg); }
    }
    DeleteObject(wc.hbrBackground); return (int)msg.wParam;
#endif
}
#ifdef GALAXY_EMBEDDED
void ShutdownPhonePanel(void) { if (g_process) {stopOurProcess(g_process,g_processId);CloseHandle(g_process);g_process=NULL;} if (g_window && IsWindow(g_window)) DestroyWindow(g_window); }
int IsPhoneBusy(void) { return g_busy; }
#endif

void GalaxyPhoneReadState(GalaxyPhoneState *state) {
    if (!state) return;
    memset(state, 0, sizeof(*state));
    state->available = g_window && IsWindow(g_window) && g_toolsReady;
    state->running = g_process && WaitForSingleObject(g_process, 0) == WAIT_TIMEOUT;
    state->keyboardSdk = g_keyboard && SendMessageW(g_keyboard, CB_GETCURSEL, 0, 0) == 1;
    state->mouseUhid = g_mouse && SendMessageW(g_mouse, CB_GETCURSEL, 0, 0) == 1;
    state->audioMode = g_audioMode; state->clipboard = g_clipboard;
    if (state->running) copyw(state->activeSerial, ARRAYSIZE(state->activeSerial), g_activeSerial);
    state->count = g_deviceCount < GALAXY_PHONE_MAX_DEVICES ? g_deviceCount : GALAXY_PHONE_MAX_DEVICES;
    for (int i = 0; i < state->count; ++i) {
        GalaxyPhoneDevice *device = &state->devices[i];
        copyw(device->serial, ARRAYSIZE(device->serial), g_devices[i].serial);
        copyw(device->label, ARRAYSIZE(device->label), g_devices[i].model);
        copyw(device->status, ARRAYSIZE(device->status), g_devices[i].state);
        device->wireless = g_devices[i].wireless;
    }
}
int GalaxyPhoneSubmit(const GalaxyPhoneRequest *request, GalaxyPhoneCallback callback, void *context, const char **error) {
    if (error) *error = "invalidRequest";
    if (!request || request->operation < GP_STATUS || request->operation > GP_KEYBOARD) return 0;
    if (!g_window || !IsWindow(g_window) || !g_toolsReady) {
        if (request->operation == GP_STATUS) { if (callback) callback(context, 1, ""); return 1; }
        if (error) *error = "phoneUnavailable"; return 0;
    }
    if (request->operation == GP_STATUS && g_busy) { if (callback) callback(context, 1, ""); return 1; }
    if (g_busy) { if (error) *error = "busy"; return 0; }
    if (g_process && (request->operation == GP_START || request->operation == GP_PAIR || request->operation == GP_CONNECT)) {
        if (error) *error = "phoneAlreadyRunning"; return 0;
    }
    if (request->operation == GP_STOP && !g_process) { if (callback) callback(context, 1, ""); return 1; }
    Task *task = (Task *)calloc(1, sizeof(Task));
    if (!task) { if (error) *error = "phoneUnavailable"; return 0; }
    task->op = request->operation == GP_STATUS ? OP_REFRESH : request->operation == GP_PAIR ? OP_PAIR :
        request->operation == GP_CONNECT ? OP_CONNECT : request->operation == GP_START ? OP_START :
        request->operation == GP_STOP ? OP_STOP : OP_KEYBOARD;
    copyw(task->selected, ARRAYSIZE(task->selected), request->serial);
    copyw(task->endpoint, ARRAYSIZE(task->endpoint), request->address);
    copyw(task->pairEndpoint, ARRAYSIZE(task->pairEndpoint), request->address);
    copyw(task->code, ARRAYSIZE(task->code), request->code);
    task->keyboardSdk = request->keyboardSdk; task->mouseUhid = request->mouseUhid;
    task->audioMode = request->audioMode; task->clipboard = request->clipboard;
    task->runningProcess = g_process; task->runningPid = g_processId;
    copyw(task->runningSerial, ARRAYSIZE(task->runningSerial), g_activeSerial);
    task->callback = callback; task->callbackContext = context;
    if ((task->op == OP_PAIR && (!validEndpoint(task->pairEndpoint) || !validCode(task->code))) ||
        (task->op == OP_CONNECT && !validEndpoint(task->endpoint))) {
        SecureZeroMemory(task, sizeof(*task)); free(task); return 0;
    }
    if (task->op == OP_START) {
        SendMessageW(g_keyboard, CB_SETCURSEL, task->keyboardSdk ? 1 : 0, 0);
        SendMessageW(g_mouse, CB_SETCURSEL, task->mouseUhid ? 1 : 0, 0);
        g_audioMode = task->audioMode; g_clipboard = task->clipboard;
        WritePrivateProfileStringW(L"input", L"mouse", task->mouseUhid ? L"uhid" : L"sdk", g_config);
    }
    g_busy = 1; updateControls();
    HANDLE thread = CreateThread(NULL, 0, worker, task, 0, NULL);
    if (!thread) { g_busy = 0; updateControls(); SecureZeroMemory(task, sizeof(*task)); free(task); if (error) *error = "phoneUnavailable"; return 0; }
    CloseHandle(thread); return 1;
}
