/*
 * Fake Furuno Sensor SDK — implements the PLACEHOLDER API declared in
 * core/radar/furuno/bindings.py so the ctypes driver can be tested end to
 * end without hardware or the real SDK.  It is NOT the real Furuno API.
 *
 * Build (x64 Native Tools Command Prompt for VS):
 *     cl /LD /O2 fake_furuno_sdk.c /Fe:fake_furuno_sdk.dll
 * Then:
 *     set FURUNO_FAKE_DLL=%CD%\fake_furuno_sdk.dll
 *     python -m unittest tests.test_furuno_fake_sdk -v
 */
#include <windows.h>
#include <math.h>
#include <stdint.h>
#include <string.h>

#define API __declspec(dllexport)

typedef struct {
    uint16_t angle;
    uint16_t angle_resolution;
    float    range_m;
    uint32_t sample_count;
    uint8_t *data;
} FurunoEchoData;

typedef struct {
    int32_t target_id;
    double  bearing_deg;
    double  range_m;
    double  course_deg;
    double  speed_kts;
    int32_t state;
} FurunoTargetData;

typedef struct {
    int32_t  transmitting;
    int32_t  warming_up;
    int32_t  warmup_seconds;
    uint32_t fault_flags;
    double   operating_hours;
    double   transmit_hours;
    double   temperature_c;
    char     firmware_version[32];
    char     serial_number[32];
} FurunoStatusData;

typedef void (*EchoCb)(const FurunoEchoData *, void *);
typedef void (*TargetCb)(const FurunoTargetData *, int, void *);
typedef void (*StatusCb)(const FurunoStatusData *, void *);

static EchoCb   g_echo_cb;
static TargetCb g_target_cb;
static StatusCb g_status_cb;
static volatile LONG g_running;
static volatile LONG g_transmit;
static volatile LONG g_range_index = 7;
static HANDLE g_thread;
static const double RANGES_NM[] = {0.0625, 0.125, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24, 32, 36};

#define SPOKES 2048
#define SAMPLES 512

static DWORD WINAPI worker(LPVOID arg) {
    uint8_t buf[SAMPLES];
    uint16_t angle = 0;
    int tick = 0;
    (void)arg;
    while (g_running) {
        if (g_transmit && g_echo_cb) {
            int i;
            double range_m = RANGES_NM[g_range_index] * 1852.0;
            for (i = 0; i < 16; i++) {           /* 16 spokes per ms-ish batch */
                FurunoEchoData e;
                int s;
                for (s = 0; s < SAMPLES; s++) buf[s] = (uint8_t)((s * 7 + angle) & 0x1F);
                if (angle > 100 && angle < 140) memset(buf + 200, 240, 20);  /* a target */
                e.angle = angle; e.angle_resolution = SPOKES;
                e.range_m = (float)range_m; e.sample_count = SAMPLES; e.data = buf;
                g_echo_cb(&e, NULL);
                angle = (uint16_t)((angle + 1) % SPOKES);
            }
        }
        if (++tick % 100 == 0) {
            if (g_transmit && g_target_cb) {
                FurunoTargetData t[2] = {
                    {7, 22.5, 1500.0, 180.0, 10.0, 1},
                    {9, 300.0, 4000.0, 45.0, 6.0, 1},
                };
                g_target_cb(t, 2, NULL);
            }
        }
        Sleep(10);
    }
    return 0;
}

API int FSDK_Initialize(void) { return 0; }
API int FSDK_Terminate(void) { return 0; }

API int FSDK_Connect(const char *ip, int port) {
    (void)port;
    if (!ip || !*ip) return -1;
    g_running = 1;
    g_thread = CreateThread(NULL, 0, worker, NULL, 0, NULL);
    return g_thread ? 0 : -2;
}

API int FSDK_Disconnect(void) {
    g_running = 0;
    if (g_thread) { WaitForSingleObject(g_thread, 2000); CloseHandle(g_thread); g_thread = NULL; }
    return 0;
}

API int FSDK_SetEchoCallback(EchoCb cb, void *u)     { (void)u; g_echo_cb = cb; return 0; }
API int FSDK_SetTargetCallback(TargetCb cb, void *u) { (void)u; g_target_cb = cb; return 0; }

API int FSDK_GetStatus(FurunoStatusData *s) {
    if (!s) return -1;
    memset(s, 0, sizeof(*s));
    s->transmitting = g_transmit;
    s->operating_hours = 1234.0;
    s->transmit_hours = 567.0;
    s->temperature_c = 31.5;
    strcpy(s->firmware_version, "FAKE-1.00");
    strcpy(s->serial_number, "SN0001");
    return 0;
}

API int FSDK_SetTransmit(int on) { g_transmit = on ? 1 : 0; return 0; }
API int FSDK_SetRange(int idx) {
    if (idx < 0 || idx >= (int)(sizeof(RANGES_NM) / sizeof(RANGES_NM[0]))) return -3;
    g_range_index = idx; return 0;
}
API int FSDK_SetGain(int v, int a) { (void)v; (void)a; return 0; }
API int FSDK_SetSea(int v, int a)  { (void)v; (void)a; return 0; }
API int FSDK_SetRain(int v, int a) { (void)v; (void)a; return 0; }
API int FSDK_SetNavigationData(double lat, double lon, double hdg, double sog, double cog) {
    (void)lat; (void)lon; (void)hdg; (void)sog; (void)cog; return 0;
}
API int FSDK_AcquireTarget(double b, double r) { (void)b; (void)r; return 0; }
API int FSDK_CancelTarget(int id) { (void)id; return 0; }
API const char *FSDK_GetLastErrorText(void) { return "fake sdk error"; }
