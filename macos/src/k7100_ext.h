/*
 * HP Officejet K7100 extensions for hpcups and the command filter.
 *
 *  - printer status from the IEEE 1284 device ID ("S:" and "Z:" fields),
 *    reported to CUPS as marker-* attributes and printer-state-reasons;
 *  - software ink estimate (the printer cannot report levels of refilled or
 *    third-party cartridges), kept per queue in the CUPS cache directory;
 *  - VIP colour commands (ink volume, saturation, ...) taken from the PPD,
 *    as HP's own Mac driver sent them.
 *
 * SPDX-License-Identifier: MIT
 */
#ifndef K7100_EXT_H
#define K7100_EXT_H

#include <cups/ppd.h>
#include <cups/raster.h>

#define K7_MAX_PENS 4

enum { K7_K, K7_C, K7_M, K7_Y, K7_INKS };

typedef struct {
    int kind;           /* 1 head, 2 supply, 3 cartridge */
    int type;           /* 0 none, 1 black, 2 tri-colour, 3 photo, 10 grey photo */
    int health;         /* 0 ok, 1 misinstalled, 2 incorrect, 3 failed */
    int level_trigger;  /* 0-4 sufficient, 5 may be low, 6 probably out, 7 out */
    int level;          /* firmware estimate, 0 when unknown (non-HP ink) */
    int hp_ink;         /* -1 unknown */
} k7_pen;

typedef struct {
    int    valid;
    int    revision;
    int    status_code; /* HPLIP numbering: 1000 idle, 1009 out of paper, ... */
    int    top_door_open;
    int    num_pens;
    k7_pen pens[K7_MAX_PENS];
} k7_status;

typedef struct {
    double used[K7_INKS];      /* consumed, in full-coverage A4 pages */
    double capacity[K7_INKS];  /* cartridge capacity, same unit */
} k7_ink;

/* Device ID / status */
int  k7_parse_device_id(const char *device_id, k7_status *st);
int  k7_query_device_id(char *buf, int bufsize);   /* via the backend side channel */

/* Ink estimate */
void k7_ink_capacity(ppd_file_t *ppd, k7_ink *ink);
int  k7_ink_load(k7_ink *ink);
int  k7_ink_save(const k7_ink *ink);
void k7_ink_reset(k7_ink *ink, int black, int color);

/* Report status and estimated levels to CUPS (stderr ATTR:/STATE: lines). */
void k7_report(ppd_file_t *ppd, const k7_status *st, const k7_ink *ink);

/* hpcups hooks */
void k7_job_start(ppd_file_t *ppd, int num_options, cups_option_t *options);
int  k7_media_type(int media_type);
int  k7_vip_commands(unsigned char *out, int outsize);
void k7_line(unsigned char *line, const cups_page_header2_t *h);
void k7_page_end(const cups_page_header2_t *h);
void k7_job_end(void);

#endif
