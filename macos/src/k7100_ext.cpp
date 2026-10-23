/*
 * HP Officejet K7100 extensions, see k7100_ext.h.
 *
 * Status layout ("S:" revisions 0-4 and the "Z:05" pen flags) follows HPLIP's
 * base/status.py; PCL sequences follow the PCL3GUI data of HP's Mac driver v9.7.
 *
 * SPDX-License-Identifier: MIT
 */
#include "k7100_ext.h"

#include <cups/cups.h>
#include <cups/sidechannel.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* ------------------------------------------------------------------------ */
/* Device ID status                                                         */

static int hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

/* Copies the value of "KEY:" from a device ID into buf. */
static int devid_field(const char *id, const char *key, char *buf, int size)
{
    size_t klen = strlen(key);
    for (const char *p = id; p && *p; p = strchr(p, ';') ? strchr(p, ';') + 1 : NULL) {
        while (*p == ' ') p++;
        if (!strncmp(p, key, klen) && p[klen] == ':') {
            p += klen + 1;
            int n = 0;
            while (*p && *p != ';' && n < size - 1) buf[n++] = *p++;
            buf[n] = 0;
            return n;
        }
    }
    buf[0] = 0;
    return 0;
}

static unsigned long hexnum(const char *s, int n)
{
    unsigned long v = 0;
    for (int i = 0; i < n; i++) {
        int h = hexval(s[i]);
        if (h < 0) return 0;
        v = (v << 4) | h;
    }
    return v;
}

int k7_parse_device_id(const char *device_id, k7_status *st)
{
    static const int num_pen_pos[] = {16, 16, 16, 18, 22};
    static const int pen_size[]    = {8, 8, 4, 8, 8};
    static const int status_pos[]  = {14, 14, 14, 16, 20};
    char s[256], z[256];

    memset(st, 0, sizeof(*st));
    int len = devid_field(device_id, "S", s, sizeof(s));
    if (len < 20)
        return 0;

    int rev = hexval(s[1]);
    if (rev < 0 || rev > 4)
        return 0;
    st->revision = rev;

    int top = hexval(s[2]);
    st->top_door_open = (top & 0x8) && (top & 0x1);

    int sp = status_pos[rev];
    int code = hexval(s[sp]) << 4;
    if (code != 48)
        code += hexval(s[sp + 1]);
    st->status_code = 1000 + code;

    /* Pen flags from "Z:...,05<6 hex digits per pen>". */
    char zpens[128] = "";
    if (devid_field(device_id, "Z", z, sizeof(z))) {
        for (char *f = strtok(z, ","); f; f = strtok(NULL, ","))
            if (!strncmp(f, "05", 2) && strlen(f) > 2)
                snprintf(zpens, sizeof(zpens), "%s", f + 2);
    }

    int n = hexval(s[num_pen_pos[rev]]);
    int c = num_pen_pos[rev] + 1, ps = pen_size[rev];
    for (int i = 0; i < n && i < K7_MAX_PENS && c + ps <= len; i++, c += ps) {
        unsigned long info = hexnum(s + c, ps);
        k7_pen *p = &st->pens[i];
        if (ps == 8) {
            p->kind          = ((info & 0x80000000UL) ? 1 : 0) + ((info & 0x40000000UL) ? 2 : 0);
            p->type          = (int)((info & 0x3f000000UL) >> 24);
            p->level_trigger = (int)((info & 0x70000UL) >> 16);
            p->health        = (int)((info & 0xc000UL) >> 14);
            p->level         = (int)(info & 0xff);
        } else {
            p->kind          = 3;
            p->type          = (int)((info & 0xf000) >> 12);
            p->level_trigger = (int)((info & 0x0e00) >> 9);
            p->health        = (int)((info & 0x0180) >> 7);
            p->level         = (int)(info & 0x7f);
        }
        int zf = (int)strlen(zpens) > i * 6 + 5 ? hexval(zpens[i * 6 + 5]) : -1;
        p->hp_ink = zf < 0 ? -1 : !!(zf & 0x4);
        st->num_pens = i + 1;
    }
    st->valid = 1;
    return 1;
}

int k7_query_device_id(char *buf, int bufsize)
{
    int len = bufsize - 1;
    if (cupsSideChannelDoRequest(CUPS_SC_CMD_GET_DEVICE_ID, buf, &len, 2.0) != CUPS_SC_STATUS_OK || len <= 0)
        return 0;
    /* Some backends return the raw 2-byte IEEE 1284 length prefix. */
    if (len > 2 && (unsigned char)buf[0] < 0x20) {
        memmove(buf, buf + 2, len - 2);
        len -= 2;
    }
    buf[len] = 0;
    return len;
}

/* ------------------------------------------------------------------------ */
/* Ink estimate                                                             */

/* Capacity in full-coverage A4 pages: ISO page yield x 5 % coverage per ink. */
static double cartridge_capacity(const char *choice, double fallback)
{
    static const struct { const char *name; double pages; } yields[] = {
        {"HP94", 480}, {"HP96", 860}, {"HP95", 260}, {"HP97", 450},
    };
    for (size_t i = 0; choice && i < sizeof(yields) / sizeof(yields[0]); i++)
        if (!strcmp(choice, yields[i].name))
            return yields[i].pages * 0.05;
    return fallback;
}

static const char *marked(ppd_file_t *ppd, const char *option)
{
    ppd_choice_t *ch = ppd ? ppdFindMarkedChoice(ppd, option) : NULL;
    return ch ? ch->choice : NULL;
}

void k7_ink_capacity(ppd_file_t *ppd, k7_ink *ink)
{
    ink->capacity[K7_K] = cartridge_capacity(marked(ppd, "HPBlackCartridge"), 24.0);
    double color = cartridge_capacity(marked(ppd, "HPColorCartridge"), 13.0);
    ink->capacity[K7_C] = ink->capacity[K7_M] = ink->capacity[K7_Y] = color;
}

static void state_path(char *buf, size_t size)
{
    const char *dir = getenv("CUPS_CACHEDIR");
    const char *printer = getenv("PRINTER");
    snprintf(buf, size, "%s/HP_K7100-%s.ink", dir && *dir ? dir : "/private/var/spool/cups/cache",
             printer && *printer ? printer : "default");
}

int k7_ink_load(k7_ink *ink)
{
    char path[1024];
    state_path(path, sizeof(path));
    memset(ink->used, 0, sizeof(ink->used));
    FILE *f = fopen(path, "r");
    if (!f)
        return 0;
    int ok = fscanf(f, "%lf %lf %lf %lf", &ink->used[0], &ink->used[1], &ink->used[2], &ink->used[3]) == 4;
    fclose(f);
    return ok;
}

int k7_ink_save(const k7_ink *ink)
{
    char path[1024], tmp[1100];
    state_path(path, sizeof(path));
    snprintf(tmp, sizeof(tmp), "%s.%d", path, (int)getpid());
    FILE *f = fopen(tmp, "w");
    if (!f) {
        fprintf(stderr, "DEBUG: K7100: cannot write ink state %s\n", tmp);
        return 0;
    }
    fprintf(f, "%.6f %.6f %.6f %.6f\n", ink->used[0], ink->used[1], ink->used[2], ink->used[3]);
    fclose(f);
    return rename(tmp, path) == 0;
}

void k7_ink_reset(k7_ink *ink, int black, int color)
{
    if (black) ink->used[K7_K] = 0;
    if (color) ink->used[K7_C] = ink->used[K7_M] = ink->used[K7_Y] = 0;
}

/* ------------------------------------------------------------------------ */
/* Reporting                                                                */

static const k7_pen *find_pen(const k7_status *st, int type)
{
    for (int i = 0; st && st->valid && i < st->num_pens; i++)
        if (st->pens[i].type == type)
            return &st->pens[i];
    return NULL;
}

void k7_report(ppd_file_t *ppd, const k7_status *st, const k7_ink *ink)
{
    (void)ppd;
    static const char *names[K7_INKS] = {"Black", "Cyan", "Magenta", "Yellow"};
    int level[K7_INKS];
    int low = 0, empty = 0;

    const k7_pen *black = find_pen(st, 1), *color = find_pen(st, 2);
    for (int i = 0; i < K7_INKS; i++) {
        double left = 100.0 * (1.0 - ink->used[i] / ink->capacity[i]);
        level[i] = left < 0 ? 0 : (int)(left + 0.5);
        /* Genuine HP cartridges report their own level; prefer it. */
        const k7_pen *p = i == K7_K ? black : color;
        if (p && p->hp_ink == 1 && p->level > 0 && p->level <= 100)
            level[i] = p->level;
        if (level[i] <= 10) low = 1;
        if (level[i] == 0) empty = 1;
    }

    fprintf(stderr, "ATTR: marker-colors=#000000,#00FFFF,#FF00FF,#FFFF00 "
                    "marker-names='%s','%s','%s','%s' "
                    "marker-types=ink-cartridge,ink-cartridge,ink-cartridge,ink-cartridge "
                    "marker-low-levels=10,10,10,10 marker-high-levels=100,100,100,100 "
                    "marker-levels=%d,%d,%d,%d\n",
            names[0], names[1], names[2], names[3], level[0], level[1], level[2], level[3]);

    /* Firmware flags still apply to refilled cartridges. */
    for (int i = 0; st && st->valid && i < st->num_pens; i++) {
        if (st->pens[i].level_trigger >= 7) empty = 1;
        else if (st->pens[i].level_trigger >= 5) low = 1;
    }
    int code = st && st->valid ? st->status_code : 1000;
    if (code == 1026) empty = 1;
    if (code == 1054 || (code >= 1501 && code <= 1503)) low = 1;

    fputs("STATE: -marker-supply-low-warning,marker-supply-empty-warning,door-open-warning,"
          "media-empty-warning,media-jam-warning\n", stderr);
    char add[256] = "";
    if (empty)                                strcat(add, ",marker-supply-empty-warning");
    else if (low)                             strcat(add, ",marker-supply-low-warning");
    if (st && st->top_door_open)              strcat(add, ",door-open-warning");
    if (code == 1009)                         strcat(add, ",media-empty-warning");
    if (code == 1014)                         strcat(add, ",media-jam-warning");
    if (add[0])
        fprintf(stderr, "STATE: +%s\n", add + 1);

    if (st && st->valid)
        for (int i = 0; i < st->num_pens; i++)
            fprintf(stderr, "DEBUG: K7100 pen %d: type=%d health=%d trigger=%d level=%d hp-ink=%d\n", i,
                    st->pens[i].type, st->pens[i].health, st->pens[i].level_trigger,
                    st->pens[i].level, st->pens[i].hp_ink);
}

/* ------------------------------------------------------------------------ */
/* hpcups hooks                                                             */

static ppd_file_t *g_ppd;
static double g_sum[K7_INKS];       /* per page, in 0..255 coverage units */
static double g_job[K7_INKS];       /* per job, in full A4 pages */

void k7_job_start(ppd_file_t *ppd, int num_options, cups_option_t *options)
{
    g_ppd = ppd;
    ppdMarkDefaults(ppd);
    cupsMarkOptions(ppd, num_options, options);
    memset(g_job, 0, sizeof(g_job));
    memset(g_sum, 0, sizeof(g_sum));

    char id[1024];
    k7_status st;
    k7_ink ink;
    k7_ink_capacity(ppd, &ink);
    k7_ink_load(&ink);
    if (k7_query_device_id(id, sizeof(id)))
        k7_parse_device_id(id, &st);
    else
        memset(&st, 0, sizeof(st));
    k7_report(ppd, &st, &ink);
}

/* HP sends ESC&l-1M for paper-type auto-detection; raster headers cannot carry -1. */
int k7_media_type(int media_type)
{
    const char *m = marked(g_ppd, "MediaType");
    return m && !strcmp(m, "automatic") ? -1 : media_type;
}

static int marked_int(const char *option)
{
    const char *c = marked(g_ppd, option);
    return c ? atoi(c) : 0;
}

/* VIP commands: ESC * o 5 W <group> <id> 00 00 <signed value>. */
int k7_vip_commands(unsigned char *out, int outsize)
{
    static const struct { const char *option; unsigned char group, id; } settings[] = {
        {"HPInkVolume",         0x0b, 0x09},
        {"HPSaturation",        0x0b, 0x06},
        {"HPBrightness",        0x0b, 0x07},
        {"HPColorTone",         0x0b, 0x08},
        {"HPBlackAdjustment",   0x46, 0x10},
        {"HPCyanAdjustment",    0x46, 0x11},
        {"HPMagentaAdjustment", 0x46, 0x12},
        {"HPYellowAdjustment",  0x46, 0x13},
    };
    int n = 0;
    if (!g_ppd || outsize < 10 * (int)(sizeof(settings) / sizeof(settings[0]) + 1))
        return 0;

    /* Colour space the printer assumes for incoming RGB. */
    const char *mode = marked(g_ppd, "HPColorMode");
    unsigned char space = 0x00;                        /* sRGB, printer colour */
    if (mode && !strcmp(mode, "AdobeRGB"))  space = 0x04;
    if (mode && !strcmp(mode, "CS"))        space = 0x05; /* ColorSync already applied */
    const unsigned char cs[] = {0x1b, '*', 'o', '5', 'W', 0x0e, 0x03, 0x00, 0x00, space};
    memcpy(out + n, cs, sizeof(cs));
    n += sizeof(cs);

    for (size_t i = 0; i < sizeof(settings) / sizeof(settings[0]); i++) {
        int v = marked_int(settings[i].option);
        if (!v)
            continue;
        const unsigned char cmd[] = {0x1b, '*', 'o', '5', 'W', settings[i].group, settings[i].id,
                                     0x00, 0x00, (unsigned char)(signed char)v};
        memcpy(out + n, cmd, sizeof(cmd));
        n += sizeof(cmd);
    }
    return n;
}

/* Mirrors the line if requested and accumulates ink coverage. */
void k7_line(unsigned char *line, const cups_page_header2_t *h)
{
    unsigned bpp = h->cupsBitsPerPixel / 8, w = h->cupsWidth;
    if (bpp == 0)
        return;

    if (h->MirrorPrint) {
        for (unsigned a = 0, b = w - 1; a < b; a++, b--)
            for (unsigned k = 0; k < bpp; k++) {
                unsigned char t = line[a * bpp + k];
                line[a * bpp + k] = line[b * bpp + k];
                line[b * bpp + k] = t;
            }
    }

    if (bpp == 3 && h->cupsRowStep != 2) {
        unsigned long k = 0, c = 0, m = 0, y = 0;
        for (unsigned x = 0; x < w; x++, line += 3) {
            unsigned cc = 255 - line[0], mm = 255 - line[1], yy = 255 - line[2];
            unsigned kk = cc < mm ? (cc < yy ? cc : yy) : (mm < yy ? mm : yy);
            k += kk; c += cc - kk; m += mm - kk; y += yy - kk;
        }
        g_sum[K7_K] += k; g_sum[K7_C] += c; g_sum[K7_M] += m; g_sum[K7_Y] += y;
    } else {
        /* Grey printed with black ink only (KGray), or single-channel rasters. */
        unsigned long k = 0;
        for (unsigned x = 0; x < w; x++, line += bpp)
            k += 255 - line[0];
        g_sum[K7_K] += k;
    }
}

void k7_page_end(const cups_page_header2_t *h)
{
    /* Ink per pixel relative to Normal quality: HP lays down less in draft modes. */
    static const double quality_factor[] = {0.35, 0.6, 1.0, 1.25, 1.5}; /* OutputType -2..2 */
    int q = atoi(h->OutputType) + 2;
    double qf = (q >= 0 && q <= 4) ? quality_factor[q] : 1.0;
    double a4 = (8.2677 * h->HWResolution[0]) * (11.6929 * h->HWResolution[1]) * 255.0;
    for (int i = 0; i < K7_INKS; i++) {
        g_job[i] += g_sum[i] / a4 * qf;
        g_sum[i] = 0;
    }
}

void k7_job_end(void)
{
    k7_ink ink;
    k7_ink_capacity(g_ppd, &ink);
    k7_ink_load(&ink);
    for (int i = 0; i < K7_INKS; i++)
        ink.used[i] += g_job[i];
    k7_ink_save(&ink);
    fprintf(stderr, "DEBUG: K7100 ink used by job (A4 pages @100%%): K=%.4f C=%.4f M=%.4f Y=%.4f\n",
            g_job[0], g_job[1], g_job[2], g_job[3]);

    char id[1024];
    k7_status st;
    memset(&st, 0, sizeof(st));
    if (k7_query_device_id(id, sizeof(id)))
        k7_parse_device_id(id, &st);
    k7_report(g_ppd, &st, &ink);
}
