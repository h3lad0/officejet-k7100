#!/usr/bin/env python3
"""Turns HPLIP's hpcups PPD for the K7100 into the macOS driver PPD: stdin -> stdout.

On top of HPLIP's page sizes it restores the options of HP's own Mac driver
(v9.7, 2008), with the printer codes taken from that driver's K7100 data:

- the full HP paper-type list with the PCL media type (ESC&l#M) and VIP media
  sub-type (ESC*o5W 0D 03) the HP driver sent for each type;
- HP's five print qualities, the real paper sources (auto, tray 1, manual feed);
- colour mode (ColorSmart/sRGB, Adobe RGB, ColorSync), ink volume, saturation,
  brightness, colour tone and C/M/Y/K adjustments, which the printer applies
  itself (hpcups sends them, see src/k7100_ext.cpp); mirror image;
- HP's print presets, ColorSync profiles per paper and cartridge set;
- maintenance commands (cleaning, ink levels) through commandtok7100.

Other changes against HPLIP: absolute filter paths (SIP protects
/usr/libexec/cups/filter), RGB instead of RGBW (hpcups' PCL3GUI2 sends only the
RGB plane; pure black pixels of an RGBW raster went to a K plane that is
dropped, so black text vanished), HP product names, A4 default, Russian UI.
"""
import argparse
import re
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--prefix", required=True)
ap.add_argument("--version", required=True)
ap.add_argument("--icon", action="store_true")
ap.add_argument("--profiles", action="store_true", help="HP ICC profiles are installed")
args = ap.parse_args()

sys.stdout.reconfigure(encoding="utf-8")
ppd = sys.stdin.read()


def sub(pattern, repl, count=0):
    global ppd
    ppd, n = re.subn(pattern, repl, ppd, count=count, flags=re.M | re.S)
    if n == 0:
        sys.exit(f"patch_ppd: not found: {pattern}")


def replace_option(name, text):
    sub(r"^\*OpenUI \*%s/.*?^\*CloseUI: \*%s\n" % (name, name), lambda m: text, count=1)


# ---------------------------------------------------------------------------
# HP data. Media: keyword, English name (HP), Russian name, PCL media type,
# VIP media sub-type, automatic two-sided printing allowed.
MEDIA = [
    ("automatic", "Automatic", "Автоматически", -1, 1041, True),
    ("plain-paper", "Plain Paper", "Обычная бумага", 0, 1, True),
    ("thick-plain-paper", "Thick Plain Paper", "Толстая обычная бумага", 0, 9, False),
    ("hp-bright-white-inkjet-paper", "HP Bright White Paper", "HP Bright White (ярко-белая)", 0, 1004, True),
    ("hp-premium-inkjet-paper", "HP Premium Paper", "HP Premium", 2, 1005, True),
    ("hp-premium-presentation-paper", "HP Premium Presentation Paper", "HP Premium для презентаций", 2, 1082, True),
    ("other-inkjet-paper", "Other Inkjet Papers", "Другая бумага для струйной печати", 2, 1007, True),
    ("hp-premium-plus-photo-paper", "HP Premium Plus Photo Paper", "HP Premium Plus Photo", 3, 1074, False),
    ("hp-premium-plus-photo-paper-glossy", "HP Premium Plus Photo & Proofing, Glossy",
     "HP Premium Plus Photo & Proofing, глянцевая", 3, 1085, False),
    ("hp-photo-satin", "HP Premium Plus Photo Satin", "HP Premium Plus Photo, сатин", 3, 1096, False),
    ("hp-premium-photo-paper", "HP Premium Photo Paper", "HP Premium Photo", 3, 1075, False),
    ("hp-advanced-photo-paper-glossy", "HP Advanced Photo Paper, Glossy", "HP Advanced Photo, глянцевая", 5, 1083, False),
    ("hp-everyday-photo-paper-semi-gloss", "HP Everyday Photo Paper, Semi-gloss",
     "HP Everyday Photo, полуглянцевая", 8, 1045, False),
    ("hp-everyday-photo-paper-matte", "HP Everyday Photo Paper, Matte", "HP Everyday Photo, матовая", 2, 1052, False),
    ("other-photo-paper", "Other Photo Papers", "Другая фотобумага", 5, 1069, False),
    ("hp-premium-inkjet-transparency-film", "HP Premium Inkjet Transparency Film",
     "Плёнка HP Premium для струйной печати", 4, 2, False),
    ("other-transparency-film", "Other Transparency Films", "Другая прозрачная плёнка", 4, 1021, False),
    ("hp-professional-brochure-paper-glossy", "HP Brochure Paper, Glossy", "HP для брошюр, глянцевая", 8, 1076, True),
    ("hp-professional-brochure-paper-matte", "HP Brochure Paper, Matte", "HP для брошюр, матовая", 2, 1077, True),
    ("hp-trifold-brochure-paper-glossy", "HP Tri-fold Brochure Paper, Glossy", "HP для буклетов, глянцевая", 2, 1054, True),
    ("hp-trifold-brochure-paper-matte", "HP Tri-fold Brochure Paper, Matte", "HP для буклетов, матовая", 2, 1089, True),
    ("other-brochure-papers", "Other Brochure Papers", "Другая бумага для брошюр", 2, 1046, True),
    ("hp-matte-greeting-cards", "HP Matte Greeting Cards", "Открытки HP, матовые", 2, 1031, False),
    ("hp-photo-greeting-card-paper", "HP Photo Greeting Cards", "Фотооткрытки HP", 5, 1032, False),
    ("hp-textured-greeting-card-paper", "HP Textured Greeting Cards", "Открытки HP, текстурированные", 2, 1040, False),
    ("other-greeting-cards", "Other Greeting Cards", "Другие открытки", 2, 1047, False),
    ("hp-labels-matte", "HP Labels, Matte", "Этикетки HP, матовые", 2, 1071, False),
    ("hp-labels-glossy", "HP Labels, Glossy", "Этикетки HP, глянцевые", 3, 1072, False),
    ("iron-on-tshirt-transfers", "HP Iron-on Transfer", "Термоперенос HP", 2, 1035, False),
    ("banner-papers", "HP Banner Paper", "Баннерная бумага HP", 0, 1030, False),
    ("other-speciality-papers", "Other Specialty Papers", "Другая специальная бумага", 2, 1039, False),
    ("hp-cd-dvd-tattoo", "HP CD/DVD Tattoo", "Наклейки HP CD/DVD", 3, 1112, False),
]

# Quality: keyword, English, Russian, ESC*o#M value, resolution (HPLIP's choices for this model).
QUALITY = [
    ("high-speed-draft", "Fast Draft", "Быстрый черновик", -2, 300),
    ("fast-normal", "Fast Normal", "Быстрый обычный", -1, 300),
    ("normal", "Normal", "Обычное", 0, 600),
    ("best", "Best", "Наилучшее", 1, 600),
    ("highest", "Maximum dpi", "Максимальное разрешение", 2, 1200),
]

# Paper sources: keyword, English, Russian, PCL media source (ESC&l#H).
SOURCES = [
    ("Autoselect", "Automatically Select", "Автовыбор", 7),
    ("Tray1", "Tray 1", "Лоток 1", 1),
    ("ManualFeed", "Manual Feed", "Ручная подача", 2),
]

PRESETS = [  # keyword, English, Russian, media, quality, Apple quality, coating
    ("Photo_with_Paper_Auto-Detect", "Photo", "Фото", "automatic", "best", "high", "autodetect"),
    ("Photo_with_Paper_Auto-Detect_-_Fine", "Photo - Fine", "Фото — высокое качество", "automatic", "highest", "high", "autodetect"),
    ("Photo_on_Plain_Paper", "Photo on Plain Paper", "Фото на обычной бумаге", "plain-paper", "normal", "mid", "none"),
    ("Photo_on_Plain_Paper_-_Fine", "Photo on Plain Paper - Fine", "Фото на обычной бумаге — высокое качество", "plain-paper", "best", "high", "none"),
    ("Photo_on_Photo_Paper", "Photo on Photo Paper", "Фото на фотобумаге", "hp-premium-photo-paper", "best", "mid", "glossy"),
    ("Photo_on_Photo_Paper_-_Fine", "Photo on Photo Paper - Fine", "Фото на фотобумаге — высокое качество", "hp-premium-photo-paper", "highest", "high", "glossy"),
    ("Photo_on_Matte_Paper", "Photo on Matte Paper", "Фото на матовой бумаге", "hp-everyday-photo-paper-matte", "best", "mid", "matte"),
    ("Photo_on_Matte_Paper_-_Fine", "Photo on Matte Paper - Fine", "Фото на матовой бумаге — высокое качество", "hp-everyday-photo-paper-matte", "highest", "high", "matte"),
]

# ColorSync profiles of HP's driver: (media, cartridge set) -> file in Profiles/.
PROFILE_FILES = {
    "plus": "HP K7100-Prem Plus Photo(tricolor+{pen}).icc",
    "premium": "HP K7100-Premium Paper(tricolor+{pen}).icc",
}
PROFILE_MEDIA = {
    "hp-premium-plus-photo-paper": "plus", "hp-premium-plus-photo-paper-glossy": "plus",
    "hp-photo-satin": "plus", "hp-premium-photo-paper": "premium",
}
# Short keywords: a cupsICCProfile key "CS.<media>.<pens>" must fit in 40 characters.
PENS = [  # keyword, English, Russian, profile suffix
    ("K", "Tri-Color, Black", "Трёхцветный и чёрный", "black"),
    ("P", "Tri-Color, Photo", "Трёхцветный и фото", "photo"),
    ("G", "Tri-Color, Gray Photo", "Трёхцветный и серый фото", "gray"),
]

out_ru = []   # Russian translations collected while generating


def ui(name, en, ru, choices, default, kind="PickOne", order=10, section="AnySetup"):
    """choices: (keyword, English, Russian, PostScript code)."""
    lines = [f"*OpenUI *{name}/{en}: {kind}", f"*OrderDependency: {order} {section} *{name}",
             f"*Default{name}: {default}"]
    out_ru.append(f'*ru.Translation {name}/{ru}: ""')
    for kw, cen, cru, code in choices:
        lines.append(f'*{name} {kw}/{cen}: "{code}"')
        out_ru.append(f'*ru.{name} {kw}/{cru}: ""')
    lines.append(f"*CloseUI: *{name}\n")
    return "\n".join(lines)


def scale(lo=-50, hi=50, step=10):
    for v in range(lo, hi + 1, step):
        en = "0 (default)" if v == 0 else f"{v:+d}"
        ru = "0 (по умолчанию)" if v == 0 else f"{v:+d}"
        yield str(v), en, ru, ""


# ---------------------------------------------------------------------------
name = "HP Officejet K7100"
sub(r'^\*PCFileName:.*?$', '*PCFileName: "HPK7100.PPD"')
sub(r'^\*ModelName:.*?$', f'*ModelName: "{name}"')
sub(r'^\*ShortNickName:.*?$', f'*ShortNickName: "{name}"')
sub(r'^\*NickName:.*?$', f'*NickName: "{name} (hpcups {args.version})"')
sub(r'^\*FileVersion:.*?$', f'*FileVersion: "{args.version}"')
sub(r'^\*LanguageEncoding:.*?$', '*LanguageEncoding: ISOLatin1')
sub(r'^\*Product: "\(HP Officejet k7100 Printer\)"$',
    '*Product: "(Officejet K7100)"\n*Product: "(Officejet K7100 series)"\n*Product: "(HP Officejet K7100 Printer)"')
sub(r'^\*Product: "\(HP Officejet k7103 Printer\)"$', '*Product: "(HP Officejet K7103 Printer)"')
sub(r'^\*Product: "\(HP Officejet k7108 Printer\)"$', '*Product: "(HP Officejet K7108 Printer)"')
sub(r'^\*1284DeviceID:.*?$', '*1284DeviceID: "MFG:HP;MDL:Officejet K7100;DES:Officejet K7100;"')
sub(r'^\*cupsFilter: "application/vnd.cups-raster 0 hpcups"$',
    f'*cupsFilter: "application/vnd.cups-raster 0 {args.prefix}/filter/hpcups"\n'
    f'*cupsFilter: "application/vnd.cups-command 0 {args.prefix}/filter/commandtok7100"\n'
    '*cupsCommands: "Clean ReportLevels"')
sub(r'^\*cupsLanguages: "en"$', '*cupsLanguages: "en ru"')
for key in ("PageSize", "PageRegion", "ImageableArea", "PaperDimension"):
    sub(rf'^\*Default{key}: Letter$', f'*Default{key}: A4')

# HPLIP's constraints on its media/quality/source names no longer apply.
sub(r'^\*UIConstraints: [^\n]*\*(MediaType|OutputMode|InputSlot)[^\n]*\n', '')

replace_option("ColorModel", ui(
    "ColorModel", "Color", "Цвет", [
        ("RGB", "Color", "Цветная", "<</cupsColorSpace 1/cupsBitsPerColor 8/cupsRowStep 0>>setpagedevice"),
        ("CMYGray", "Grayscale, High Quality", "Оттенки серого, высокое качество",
         "<</cupsColorSpace 1/cupsBitsPerColor 8/cupsRowStep 1>>setpagedevice"),
        ("KGray", "Grayscale, Black Cartridge Only", "Оттенки серого, только чёрный картридж",
         "<</cupsColorSpace 1/cupsBitsPerColor 8/cupsRowStep 2>>setpagedevice"),
    ], "RGB"))

replace_option("MediaType", ui(
    "MediaType", "Paper Type", "Тип бумаги",
    [(kw, en, ru, f"<</MediaType({kw})/cupsMediaType {max(pcl, 0)}/cupsInteger6 {vip}>>setpagedevice")
     for kw, en, ru, pcl, vip, _ in MEDIA], "plain-paper"))

replace_option("OutputMode", ui(
    "OutputMode", "Quality", "Качество",
    [(kw, en, ru, f"<</OutputType({q})/HWResolution[{r} {r}]>>setpagedevice") for kw, en, ru, q, r in QUALITY],
    "normal"))

replace_option("InputSlot", ui(
    "InputSlot", "Paper Source", "Источник бумаги",
    [(kw, en, ru, f"<</MediaPosition {pos}>>setpagedevice") for kw, en, ru, pos in SOURCES], "Tray1"))

replace_option("Duplex", ui(
    "Duplex", "Two-Sided Printing", "Двусторонняя печать", [
        ("None", "Off", "Выкл.", "<</Duplex false/Tumble false>>setpagedevice"),
        ("DuplexNoTumble", "Long-Edge Binding", "Переплёт по длинному краю", "<</Duplex true/Tumble false>>setpagedevice"),
        ("DuplexTumble", "Short-Edge Binding", "Переплёт по короткому краю", "<</Duplex true/Tumble true>>setpagedevice"),
    ], "None"))

color = "\n".join([
    "*OpenGroup: HPColorOptions/Color Options",
    ui("HPColorMode", "Color Mode", "Цветовой режим", [
        ("colorsmart", "ColorSmart/sRGB", "ColorSmart/sRGB (цвет принтера)", ""),
        ("AdobeRGB", "Adobe RGB (1998)", "Adobe RGB (1998)", ""),
        ("CS", "ColorSync (HP profiles)", "ColorSync (профили HP)", ""),
    ], "colorsmart"),
    ui("HPInkVolume", "Ink Volume", "Количество чернил", [
        ("-2", "-2 (Less)", "-2 (меньше)", ""), ("-1", "-1", "-1", ""), ("0", "0 (Default)", "0 (по умолчанию)", ""),
        ("1", "+1", "+1", ""), ("2", "+2 (More)", "+2 (больше)", "")], "0"),
    ui("HPSaturation", "Saturation", "Насыщенность", list(scale()), "0"),
    ui("HPBrightness", "Brightness", "Яркость", list(scale()), "0"),
    ui("HPColorTone", "Color Tone (Cooler/Warmer)", "Цветовой тон (холоднее/теплее)", list(scale()), "0"),
    ui("HPCyanAdjustment", "Cyan", "Голубой", list(scale()), "0"),
    ui("HPMagentaAdjustment", "Magenta", "Пурпурный", list(scale()), "0"),
    ui("HPYellowAdjustment", "Yellow", "Жёлтый", list(scale()), "0"),
    ui("HPBlackAdjustment", "Black", "Чёрный", list(scale()), "0"),
    ui("HPMirrorFlip", "Mirror Image", "Зеркальное отражение", [
        ("False", "Off", "Выкл.", "<</MirrorPrint false>>setpagedevice"),
        ("True", "On", "Вкл.", "<</MirrorPrint true>>setpagedevice")], "False", kind="Boolean"),
    "*CloseGroup: HPColorOptions\n",
])
sub(r'^(\*OpenGroup: InstallableOptions/Installable Options\n)', lambda m: color + m.group(1))
out_ru.append('*ru.Translation HPColorOptions/Параметры цвета: ""')
out_ru.append('*ru.Translation InstallableOptions/Установленные компоненты: ""')

installable = "\n".join([
    ui("HPBlackCartridge", "Black Cartridge (for ink estimate)", "Чёрный картридж (для оценки чернил)", [
        ("HP94", "HP 94 (480 pages)", "HP 94 (480 страниц)", ""),
        ("HP96", "HP 96 (860 pages)", "HP 96 (860 страниц)", "")], "HP94"),
    ui("HPColorCartridge", "Tri-Color Cartridge (for ink estimate)", "Трёхцветный картридж (для оценки чернил)", [
        ("HP95", "HP 95 (260 pages)", "HP 95 (260 страниц)", ""),
        ("HP97", "HP 97 (450 pages)", "HP 97 (450 страниц)", "")], "HP95"),
    ui("HPPenConfigOptions", "Installed Cartridges", "Установленные картриджи",
       [(kw, en, ru, "") for kw, en, ru, _ in PENS], "K"),
])
sub(r'^(\*OpenUI \*OptionDuplex/)Duplexer Installed(: Boolean)', r'\1Two-Sided Printing Accessory\2')
sub(r'^(\*CloseGroup: InstallableOptions\n)', lambda m: installable + m.group(1))
out_ru += ['*ru.Translation OptionDuplex/Модуль двусторонней печати: ""',
           '*ru.OptionDuplex False/Не установлен: ""', '*ru.OptionDuplex True/Установлен: ""',
           '*ru.Translation PageSize/Размер бумаги: ""', '*ru.Translation PageRegion/Размер бумаги: ""']

extra = []
if args.icon:
    extra.append(f'*APPrinterIconPath: "{args.prefix}/Resources/K7100.icns"')

# Two-sided printing needs the accessory and a paper type HP allowed it for.
extra += [f"*UIConstraints: *OptionDuplex False *Duplex {d}\n*UIConstraints: *Duplex {d} *OptionDuplex False"
          for d in ("DuplexNoTumble", "DuplexTumble")]
for kw, _, _, _, _, duplex in MEDIA:
    if not duplex:
        extra += [f"*UIConstraints: *MediaType {kw} *Duplex {d}\n*UIConstraints: *Duplex {d} *MediaType {kw}"
                  for d in ("DuplexNoTumble", "DuplexTumble")]
# 1200 dpi colour only, as in HPLIP.
extra += [f"*UIConstraints: *ColorModel {c} *OutputMode highest\n*UIConstraints: *OutputMode highest *ColorModel {c}"
          for c in ("CMYGray", "KGray")]

for kw, en, ru, media, quality, aq, coating in PRESETS:
    extra.append(f'*APPrinterPreset {kw}/{en}: "\n\t*MediaType {media}\n\t*OutputMode {quality}\n'
                 f'\tcom.apple.print.preset.graphicsType Photo\n\tcom.apple.print.preset.quality {aq}\n'
                 f'\tcom.apple.print.preset.media-front-coating {coating}"\n*End')
    out_ru.append(f'*ru.APPrinterPreset {kw}/{ru}: ""')

if args.profiles:
    extra += ["*cupsICCQualifier1: HPColorMode", "*cupsICCQualifier2: MediaType",
              "*cupsICCQualifier3: HPPenConfigOptions"]
    for media, kind in PROFILE_MEDIA.items():
        for pen, pen_en, _, suffix in PENS:
            path = f"{args.prefix}/Profiles/" + PROFILE_FILES[kind].format(pen=suffix)
            label = PROFILE_FILES[kind].format(pen=suffix)[:-4]
            extra.append(f'*cupsICCProfile CS.{media}.{pen}/{label}: "{path}"')

SIZE_WORDS = [("Index Card", "Карточка"), ("Japanese Envelope", "японский конверт"),
              ("Envelope", "конверт"), ("American Foolscap", "Американский Foolscap"),
              ("Photo", "Фото"), ("CD DVD", "CD/DVD"), (" Borderless", " без полей"),
              (" AutoDuplex", " (двусторонняя)"), ("mm)", "mm")]
for opt in ("PageSize", "PageRegion"):
    for kw, label in re.findall(rf"^\*{opt} ([^/\s]+)/([^:]+):", ppd, flags=re.M):
        for en, ru in SIZE_WORDS:
            label = label.replace(en, ru)
        out_ru.append(f'*ru.{opt} {kw}/{label}: ""')

sub(r'^(\*cupsLanguages:.*?)$', lambda m: m.group(1) + "\n" + "\n".join(extra), count=1)
ppd = ppd.rstrip("\n") + "\n" + "\n".join(out_ru) + "\n"
sys.stdout.write(ppd)
