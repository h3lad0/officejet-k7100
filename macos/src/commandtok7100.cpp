/*
 * CUPS command filter for the HP Officejet K7100
 * (application/vnd.cups-command -> printer).
 *
 * Standard commands (macOS shows them in the printer's Utility tab):
 *   Clean           print-head cleaning, level 1
 *   ReportLevels    refresh cartridge status and estimated ink levels
 * Additional commands (used by the k7100 command-line tool):
 *   Clean 2|3       deeper cleaning (prime / wipe and spit)
 *   AutoAlign       automatic print-head alignment (prints and scans a page)
 *   ResetInk black|color|all   restart the ink estimate after a refill
 *
 * The PML sequences are HPLIP's (maint.py cleanType1/primeType1/
 * wipeAndSpitType1, AlignType1) for this model.
 *
 * SPDX-License-Identifier: MIT
 */
#include "k7100_ext.h"

#include <cups/cups.h>
#include <cups/ppd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

#define SEQ(s) {s, sizeof(s) - 1}

struct seq { const char *data; size_t len; };

static const seq clean_levels[3] = {
    SEQ("\x1b" "E\x1b%-12345X@PJL JOB NAME=\"clean\"\n@PJL ENTER LANGUAGE=PCL3GUI\n\x1b" "E"
        "\x1b&b19WPML \x04\x00\x06\x01\x04\x01\x05\x01\x01\x04\x04\x00\x00\x00\x64"
        "\x1b" "E@PJL EOJ\n\x1b" "E\x1b%-12345X"),
    SEQ("\x1b" "E\x1b%-12345X@PJL JOB NAME=\"clean\"\n@PJL ENTER LANGUAGE=PCL3GUI\n\x1b" "E"
        "\x1b&b19WPML \x04\x00\x06\x01\x04\x01\x05\x01\x01\x04\x04\x00\x00\x00\xc8"
        "\x1b" "E@PJL EOJ\n\x1b" "E\x1b%-12345X"),
    SEQ("\x1b" "E\x1b%-12345X@PJL JOB NAME=\"clean\"\n@PJL ENTER LANGUAGE=PCL3GUI\n\x1b" "E"
        "\x1b&b19WPML \x04\x00\x06\x01\x04\x01\x05\x01\x01\x04\x04\x00\x00\x01\x2c"
        "\x1b" "E@PJL EOJ\n\x1b" "E\x1b%-12345X"),
};

static const seq auto_align =
    SEQ("\x1b%-12345X@PJL ENTER LANGUAGE=PCL3GUI\n\x1b" "E"
        "\x1b&b17WPML \x04\x00\x04\x01\x01\x05\x02\x04\x04\x00\x00\x04\x4c"
        "\x1b" "E\x1b%-12345X");

static void send(const seq &s)
{
    fwrite(s.data, 1, s.len, stdout);
    fflush(stdout);
}

static void report(ppd_file_t *ppd, k7_ink *ink)
{
    char id[1024];
    k7_status st;
    memset(&st, 0, sizeof(st));
    if (k7_query_device_id(id, sizeof(id))) {
        fprintf(stderr, "DEBUG: K7100 device ID: %s\n", id);
        k7_parse_device_id(id, &st);
    } else {
        fputs("DEBUG: K7100: device ID not available from backend\n", stderr);
    }
    k7_report(ppd, &st, ink);
}

int main(int argc, char *argv[])
{
    if (argc < 6 || argc > 7) {
        fputs("Usage: commandtok7100 job-id user title copies options [file]\n", stderr);
        return 1;
    }

    FILE *in = argc == 7 ? fopen(argv[6], "r") : stdin;
    if (!in) {
        perror("ERROR: Unable to open command file");
        return 1;
    }

    ppd_file_t *ppd = ppdOpenFile(getenv("PPD"));
    cups_option_t *options = NULL;
    int num_options = cupsParseOptions(argv[5], 0, &options);
    if (ppd) {
        ppdMarkDefaults(ppd);
        cupsMarkOptions(ppd, num_options, options);
    }

    k7_ink ink;
    k7_ink_capacity(ppd, &ink);
    k7_ink_load(&ink);

    char line[1024];
    while (fgets(line, sizeof(line), in)) {
        line[strcspn(line, "\r\n")] = 0;
        if (!line[0] || line[0] == '#')
            continue;

        char *cmd = strtok(line, " \t"), *arg = strtok(NULL, " \t");
        fprintf(stderr, "DEBUG: K7100 command: %s %s\n", cmd, arg ? arg : "");

        if (!strcasecmp(cmd, "Clean")) {
            int level = arg ? atoi(arg) : 1;   /* "Clean all" from macOS means level 1 */
            if (level < 1 || level > 3) level = 1;
            fprintf(stderr, "INFO: Cleaning print heads (level %d)\n", level);
            send(clean_levels[level - 1]);
        } else if (!strcasecmp(cmd, "AutoAlign")) {
            fputs("INFO: Aligning print heads\n", stderr);
            send(auto_align);
        } else if (!strcasecmp(cmd, "ResetInk")) {
            int black = !arg || !strcasecmp(arg, "black") || !strcasecmp(arg, "all");
            int color = !arg || !strcasecmp(arg, "color") || !strcasecmp(arg, "all");
            k7_ink_reset(&ink, black, color);
            k7_ink_save(&ink);
            fprintf(stderr, "INFO: Ink estimate reset (%s)\n", arg ? arg : "all");
            report(ppd, &ink);
        } else if (!strcasecmp(cmd, "ReportLevels")) {
            report(ppd, &ink);
        } else {
            fprintf(stderr, "DEBUG: K7100: unsupported command %s\n", cmd);
        }
    }

    if (in != stdin) fclose(in);
    cupsFreeOptions(num_options, options);
    if (ppd) ppdClose(ppd);
    return 0;
}
