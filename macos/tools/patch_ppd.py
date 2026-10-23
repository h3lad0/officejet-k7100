#!/usr/bin/env python3
"""Адаптирует hpcups-PPD HPLIP для K7100 под macOS: stdin -> stdout.

- путь фильтра делается абсолютным (в /usr/libexec/cups/filter писать нельзя из-за SIP);
- имена модели/Product/1284DeviceID приводятся к виду, который отдаёт принтер и
  который использовал оригинальный PPD HP, чтобы macOS сама выбирала драйвер;
- цветной режим переводится с RGBW на RGB (см. комментарий ниже);
- добавляется иконка из оригинального драйвера, A4 по умолчанию, запрет
  двусторонней печати без установленного дуплексера.
"""
import argparse
import re
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--prefix", required=True)
ap.add_argument("--version", required=True)
ap.add_argument("--icon", action="store_true")
args = ap.parse_args()

ppd = sys.stdin.read()

def sub(pattern, repl):
    global ppd
    ppd, n = re.subn(pattern, repl, ppd, flags=re.M)
    if n == 0:
        sys.exit(f"patch_ppd: не найдено: {pattern}")

name = "HP Officejet K7100"
sub(r'^\*PCFileName:.*$', '*PCFileName: "HPK7100.PPD"')
sub(r'^\*ModelName:.*$', f'*ModelName: "{name}"')
sub(r'^\*ShortNickName:.*$', f'*ShortNickName: "{name}"')
sub(r'^\*NickName:.*$', f'*NickName: "{name} (hpcups {args.version})"')
sub(r'^\*FileVersion:.*$', f'*FileVersion: "{args.version}"')
sub(r'^\*Product: "\(HP Officejet k7100 Printer\)"$',
    '*Product: "(Officejet K7100)"\n'
    '*Product: "(Officejet K7100 series)"\n'
    '*Product: "(HP Officejet K7100 Printer)"')
sub(r'^\*Product: "\(HP Officejet k7103 Printer\)"$', '*Product: "(HP Officejet K7103 Printer)"')
sub(r'^\*Product: "\(HP Officejet k7108 Printer\)"$', '*Product: "(HP Officejet K7108 Printer)"')
sub(r'^\*1284DeviceID:.*$', '*1284DeviceID: "MFG:HP;MDL:Officejet K7100;DES:Officejet K7100;"')
sub(r'^\*cupsFilter: "application/vnd.cups-raster 0 hpcups"$',
    f'*cupsFilter: "application/vnd.cups-raster 0 {args.prefix}/filter/hpcups"')
# hpcups (Pcl3Gui2) шлёт принтеру только RGB-плоскость (crd_type = eCrd_color_only),
# а из растра RGBW чисто чёрные пиксели уходят в отдельную K-плоскость, которая
# затем отбрасывается — чёрный текст пропадает. Просим у macOS обычный RGB.
sub(r'^(\*ColorModel RGB/Color: "<</cupsColorSpace) 17(/)', r'\1 1\2')
sub(r'^\*DefaultPageSize: Letter$', '*DefaultPageSize: A4')
sub(r'^\*DefaultPageRegion: Letter$', '*DefaultPageRegion: A4')
sub(r'^\*DefaultImageableArea: Letter$', '*DefaultImageableArea: A4')
sub(r'^\*DefaultPaperDimension: Letter$', '*DefaultPaperDimension: A4')

extra = []
if args.icon:
    extra.append(f'*APPrinterIconPath: "{args.prefix}/Resources/K7100.icns"')
extra += [
    '*UIConstraints: *OptionDuplex False *Duplex DuplexNoTumble',
    '*UIConstraints: *OptionDuplex False *Duplex DuplexTumble',
    '*UIConstraints: *Duplex DuplexNoTumble *OptionDuplex False',
    '*UIConstraints: *Duplex DuplexTumble *OptionDuplex False',
]
sub(r'^(\*cupsLanguages:.*)$', lambda m: m.group(1) + "\n" + "\n".join(extra))

sys.stdout.write(ppd)
