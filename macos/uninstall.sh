#!/bin/bash
# Удаляет драйвер HP Officejet K7100 (hpcups), установленный пакетом из dist/.
# Очереди печати, созданные с этим драйвером, нужно удалить в «Принтеры и сканеры».
set -euo pipefail
[ "$(id -u)" -eq 0 ] || exec sudo "$0" "$@"

rm -rf /Library/Printers/HP_K7100
rm -f "/Library/Printers/PPDs/Contents/Resources/HP Officejet K7100 (hpcups).ppd.gz"
rm -f /private/var/spool/cups/cache/HP_K7100-*.ink   # оценка расхода чернил
pkgutil --forget org.local.hp.officejet.k7100 2>/dev/null || true
echo "Драйвер удалён."
