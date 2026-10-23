#!/bin/bash
# Сборка драйвера HP Officejet K7100/K7103/K7108 для современных macOS (arm64 + x86_64).
#
# Оригинальный драйвер HP v9.7 (2008) содержит только PPC/i386 бинарники и не
# запускается на macOS 10.15+. Здесь фильтр растеризации пересобирается из
# открытого HP HPLIP (hpcups, язык PCL3GUI2 — тот же, что использовал HP), а PPD
# собирается из HPLIP-описания K7100 с иконкой из оригинального DMG.
set -euo pipefail

HPLIP_VER=3.26.4
JPEG_VER=9f
DRIVER_VER=1.0.0
MIN_MACOS=11.0
ARCHS="-arch arm64 -arch x86_64"

ROOT="$(cd "$(dirname "$0")" && pwd)"
SRC="$ROOT/sources"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
DMG="${HP_DMG:-$ROOT/vendor/HP_Installer_OJK7100_v9.7.dmg}"
PREFIX=/Library/Printers/HP_K7100

mkdir -p "$SRC" "$BUILD" "$DIST"

fetch() { # url file
    [ -f "$SRC/$2" ] || curl -fL --retry 3 -o "$SRC/$2" "$1"
}

# --- 1. Исходники -----------------------------------------------------------
fetch "https://downloads.sourceforge.net/project/hplip/hplip/$HPLIP_VER/hplip-$HPLIP_VER.tar.gz" "hplip-$HPLIP_VER.tar.gz"
fetch "https://www.ijg.org/files/jpegsrc.v$JPEG_VER.tar.gz" "jpegsrc.v$JPEG_VER.tar.gz"
(cd "$SRC" && shasum -a 256 -c SHA256SUMS)

H="$BUILD/hplip-$HPLIP_VER"
if [ ! -d "$H" ]; then
    tar xzf "$SRC/hplip-$HPLIP_VER.tar.gz" -C "$BUILD"
    # APFS нечувствительна к регистру: "utils.h" (common/) перекрывается
    # prnt/hpcups/Utils.h. Переименовываем общий заголовок.
    cp "$H/common/utils.h" "$H/common/hplip_common_utils.h"
    grep -l '#include "utils.h"' "$H"/prnt/hpcups/*.c* "$H"/common/*.c |
        xargs sed -i '' 's/#include "utils.h"/#include "hplip_common_utils.h"/'
fi

# --- 2. libjpeg (статически, universal) -------------------------------------
J="$BUILD/jpeg"
if [ ! -f "$J/lib/libjpeg.a" ]; then
    tar xzf "$SRC/jpegsrc.v$JPEG_VER.tar.gz" -C "$BUILD"
    (cd "$BUILD/jpeg-$JPEG_VER" &&
        CFLAGS="-O2 $ARCHS -mmacosx-version-min=$MIN_MACOS" \
        ./configure --disable-shared --enable-static --prefix="$J" >/dev/null &&
        make -j"$(sysctl -n hw.ncpu)" >/dev/null && make install >/dev/null &&
        cp jpegint.h "$J/include/")   # нужен для jccolor.c/jdatadbf.c из HPLIP
fi

# --- 3. hpcups --------------------------------------------------------------
O="$BUILD/obj"
mkdir -p "$O"
FLAGS=(-O2 $ARCHS -mmacosx-version-min=$MIN_MACOS
       -DAPDK_LITTLE_ENDIAN -DDISABLE_IMAGEPROCESSOR -DCONFDIR="\"$PREFIX/etc\""
       -I"$ROOT/compat" -I"$H/prnt/hpcups" -I"$H/common" -I"$H/io/hpmud" -I"$H" -I"$J/include"
       -Wno-deprecated-declarations -w)

# Список исходников берётся из Makefile.am HPLIP (D-Bus отключён: HAVE_DBUS не определён).
SOURCES=$(sed -n '/^hpcups_SOURCES/,/^$/p' "$H/Makefile.am" | tr ' \\\t' '\n\n\n' |
          grep -E '\.(c|cpp)$')

OBJS=()
for f in $SOURCES; do
    o="$O/$(echo "${f%.*}" | tr / _).o"   # с путём: common/utils.c ≠ prnt/hpcups/Utils.cpp
    OBJS+=("$o")
    [ "$o" -nt "$H/$f" ] && continue
    case "$f" in
        *.c)   clang   "${FLAGS[@]}"                -c "$H/$f" -o "$o" ;;
        *.cpp) clang++ "${FLAGS[@]}" -std=gnu++11 -c "$H/$f" -o "$o" ;;
    esac
done

STAGE="$BUILD/root"
rm -rf "$STAGE"
mkdir -p "$STAGE$PREFIX/filter" "$STAGE$PREFIX/Resources" "$STAGE/Library/Printers/PPDs/Contents/Resources"
clang++ $ARCHS -mmacosx-version-min=$MIN_MACOS -o "$STAGE$PREFIX/filter/hpcups" "${OBJS[@]}" \
    "$J/lib/libjpeg.a" -lcups -lcupsimage -lz
strip -x "$STAGE$PREFIX/filter/hpcups"
codesign --force -s - "$STAGE$PREFIX/filter/hpcups"   # ad-hoc, иначе arm64 не запустит
lipo -info "$STAGE$PREFIX/filter/hpcups"

# --- 4. Иконка из оригинального DMG HP ------------------------------------
# ICC-профили HP не переносим: они описывают цветовой тракт старого драйвера HP,
# а hpcups использует собственные таблицы цветоделения.
if [ -f "$DMG" ]; then
    MNT="$BUILD/mnt"
    mkdir -p "$MNT"
    hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$DMG" >/dev/null
    trap 'hdiutil detach -quiet "$MNT" || true' EXIT
    PKG="$MNT/HP Installer.app/Contents/Packages/HP Officejet Printer drivers-CUPS.mpkg/Contents/Packages/HP Officejet Printer drivers.pkg/Contents/Archive.pax.gz"
    ICON=./hp/cups/Officejet.driver/Contents/Resources/PrinterIcons/K7100.icns
    (cd "$BUILD" && gunzip -c "$PKG" | pax -r "$ICON")
    cp "$BUILD/$ICON" "$STAGE$PREFIX/Resources/"
    hdiutil detach -quiet "$MNT"; trap - EXIT
else
    echo "ВНИМАНИЕ: $DMG не найден — пакет будет без иконки принтера" >&2
fi

# --- 5. PPD -----------------------------------------------------------------
PPD="$STAGE/Library/Printers/PPDs/Contents/Resources/HP Officejet K7100 (hpcups).ppd"
gunzip -c "$H/ppd/hpcups/hp-officejet_k7100.ppd.gz" | python3 -I "$ROOT/tools/patch_ppd.py" \
    --prefix "$PREFIX" --version "$DRIVER_VER" \
    $( [ -f "$STAGE$PREFIX/Resources/K7100.icns" ] && echo --icon ) > "$PPD"
# В staging файлы принадлежат пользователю; владельца root выставит pkgbuild,
# поэтому замечания о правах игнорируем, а любые другие FAIL — ошибка сборки.
TESTPPD=$(cupstestppd -R "$STAGE" -W translations -W sizes "$PPD" || true)
if echo "$TESTPPD" | grep '\*\*FAIL\*\*' | grep -v "Bad permissions"; then
    exit 1
fi
gzip -9 "$PPD"

# --- 6. Пакет ---------------------------------------------------------------
cp "$H/COPYING" "$STAGE$PREFIX/COPYING-HPLIP"
cp "$ROOT/README.md" "$STAGE$PREFIX/"
PKGOUT="$DIST/HP-Officejet-K7100-macOS-$DRIVER_VER.pkg"
pkgbuild --root "$STAGE" --identifier org.local.hp.officejet.k7100 --version "$DRIVER_VER" \
    --ownership recommended --install-location / "$BUILD/component.pkg" >/dev/null
productbuild --package "$BUILD/component.pkg" "$PKGOUT" >/dev/null
rm "$BUILD/component.pkg"
echo "Готово: $PKGOUT"
