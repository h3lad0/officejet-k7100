#!/usr/bin/env python3
"""Adapts the HPLIP source tree for macOS and the K7100 extensions (src/k7100_ext.*).

    patch_hplip.py <hplip-source-dir>

Every edit must match exactly once, so a new HPLIP release that moved the
code fails the build instead of silently producing a different driver.
"""
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1])
hpcups = root / "prnt" / "hpcups"


def edit(path, old, new):
    text = path.read_text(encoding="latin-1")
    count = text.count(old)
    if count != 1:
        sys.exit(f"patch_hplip: {path.name}: expected 1 match, found {count}: {old!r}")
    path.write_text(text.replace(old, new), encoding="latin-1")


# APFS is case-insensitive: "utils.h" (common/) would resolve to prnt/hpcups/Utils.h.
shutil.copy(root / "common" / "utils.h", root / "common" / "hplip_common_utils.h")
for src in list(hpcups.glob("*.c*")) + list((root / "common").glob("*.c")):
    text = src.read_text(encoding="latin-1")
    if '#include "utils.h"' in text:
        src.write_text(text.replace('#include "utils.h"', '#include "hplip_common_utils.h"'), encoding="latin-1")

f = hpcups / "HPCupsFilter.cpp"
edit(f, '#include "hplip_common_utils.h"\n',
     '#include "hplip_common_utils.h"\n#include "k7100_ext.h"\n')
edit(f, "    m_argv = argv;\n",
     "    m_argv = argv;\n"
     "    {\n"
     "        cups_option_t *k7_options = NULL;\n"
     "        int k7_num = argc > 5 ? cupsParseOptions(argv[5], 0, &k7_options) : 0;\n"
     "        k7_job_start(m_ppd, k7_num, k7_options);\n"
     "        cupsFreeOptions(k7_num, k7_options);\n"
     "    }\n")
edit(f, "            cupsRasterReadPixels (cups_raster, m_pPrinterBuffer, cups_header.cupsBytesPerLine);\n",
     "            cupsRasterReadPixels (cups_raster, m_pPrinterBuffer, cups_header.cupsBytesPerLine);\n"
     "            k7_line(m_pPrinterBuffer, &cups_header);\n")
edit(f, "    m_JA.quality_attributes.media_subtype = cups_header->cupsInteger[6];\n",
     "    m_JA.quality_attributes.media_subtype = cups_header->cupsInteger[6];\n"
     "    m_JA.quality_attributes.media_type = k7_media_type(m_JA.quality_attributes.media_type);\n")
edit(f, "        m_Job.NewPage();\n",
     "        k7_page_end(&cups_header);\n        m_Job.NewPage();\n")
edit(f, "    unlink(hpPreProcessedRasterFile);\n",
     "    k7_job_end();\n    unlink(hpPreProcessedRasterFile);\n")

f = hpcups / "Pcl3Gui2.cpp"
edit(f, '#include "PrinterCommands.h"\n', '#include "PrinterCommands.h"\n#include "k7100_ext.h"\n')
edit(f, "    char            szStr[256];\n", "    char            szStr[512];\n")
edit(f, "    szStr[i++] = (char) m_pQA->media_subtype & 0xFF;\n",
     "    szStr[i++] = (char) m_pQA->media_subtype & 0xFF;\n"
     "    i += k7_vip_commands((BYTE *) szStr + i, sizeof(szStr) - i);\n")
