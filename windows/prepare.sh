#!/bin/bash
# Готовит на macOS/Linux архив для Windows: достаёт из OJK7100_Full_8.exe только
# файлы драйвера (без 200 МБ ПО HP и старого установщика) и кладёт их рядом со
# скриптами установки. Файлы драйвера не изменяются — подпись WHQL сохраняется.
#
#   ./prepare.sh [путь/к/OJK7100_Full_8.exe]
#
# Результат: dist/HP-Officejet-K7100-Windows.zip
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
EXE="${1:-$ROOT/vendor/OJK7100_Full_8.exe}"
BUILD="$ROOT/build"
OUT="$BUILD/HP-Officejet-K7100-Windows"
DIST="$ROOT/dist"

[ -f "$EXE" ] || { echo "Не найден $EXE" >&2; exit 1; }
SEVENZIP=$(command -v 7zz || command -v 7z || true)
[ -n "$SEVENZIP" ] || { echo "Нужен 7-Zip: brew install sevenzip (или apt install 7zip)" >&2; exit 1; }

# Проверяем, что это тот самый пакет HP, для которого написан скрипт.
if ! (cd "$(dirname "$EXE")" && shasum -a 256 "$(basename "$EXE")") |
        awk '{print $1}' | grep -qxf <(awk '{print $1}' "$ROOT/SHA256SUMS"); then
    echo "ВНИМАНИЕ: контрольная сумма $EXE отличается от ожидаемой (SHA256SUMS)" >&2
fi

rm -rf "$BUILD"
mkdir -p "$BUILD/hp" "$OUT/driver" "$DIST"
"$SEVENZIP" x -y -o"$BUILD/hp" "$EXE" >/dev/null

# Всё, на что ссылаются hpoh710s.inf (x64) и hpoh710a.inf (x86): INF, каталоги
# подписи, CAB с файлами драйвера, co-installer'ы HP и файлы, которые они ищут.
FILES=(hpoh710s.inf hpoh710s.cat hpoh710s.cab
       hpoh710a.inf hpoh710a.cat hpoh710a.cab
       hpoh7103.cf_ HPZIDS40.dll hpzids01.dll HPZstub.exe autorun.inf)
for f in "${FILES[@]}"; do
    cp "$BUILD/hp/$f" "$OUT/driver/"
done

cp "$ROOT/install.ps1" "$ROOT/install.cmd" "$ROOT/uninstall.ps1" "$ROOT/README.md" "$OUT/"
# Windows-скрипты должны иметь CRLF.
for f in install.ps1 install.cmd uninstall.ps1; do
    sed -i.bak $'s/\r*$/\r/' "$OUT/$f" && rm "$OUT/$f.bak"
done

rm -f "$DIST/HP-Officejet-K7100-Windows.zip"
(cd "$BUILD" && zip -qr -X "$DIST/HP-Officejet-K7100-Windows.zip" "$(basename "$OUT")")
echo "Готово: $DIST/HP-Officejet-K7100-Windows.zip"
