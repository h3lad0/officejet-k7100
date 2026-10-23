# Драйвер HP Officejet K7100 / K7103 / K7108 для современных macOS

Замена официального драйвера HP *Officejet Full Feature Software v9.7* (январь 2008,
macOS 10.3.9–10.5), который на современных системах не работает.

## Почему старый драйвер не работает

В `HP_Installer_OJK7100_v9.7.dmg` фильтр печати
(`/Library/Printers/hp/cups/Officejet.driver/Contents/MacOS/Officejet`) и все библиотеки
собраны только под **PPC и i386**. 32-битный код не запускается начиная с macOS 10.15,
а Rosetta 2 на Apple Silicon i386 не поддерживает. Сам PPD из пакета пригоден, но
ссылается на этот фильтр.

## Что сделано

| Компонент | Источник |
|---|---|
| Фильтр `hpcups` (растр CUPS → PCL3GUI) | HP HPLIP 3.26.4, собран universal (arm64 + x86_64), macOS 11+ |
| PPD | HPLIP `hp-officejet_k7100.ppd`, адаптирован под macOS ([tools/patch_ppd.py](tools/patch_ppd.py)) |
| Иконка принтера | оригинальный DMG HP (`K7100.icns`) |

HPLIP — открытый драйвер самой HP; K7100/K7103/K7108 поддерживаются в нём
без бинарных плагинов, на том же языке принтера PCL3GUI, что и в старом драйвере HP.

Изменения в PPD относительно HPLIP:

- абсолютный путь к фильтру `/Library/Printers/HP_K7100/filter/hpcups`
  (в `/usr/libexec/cups/filter` писать нельзя из-за SIP);
- цветной режим запрашивает у macOS RGB вместо RGBW. В HPLIP 3.26 PCL3GUI2
  отправляет принтеру только RGB-плоскость, а из RGBW чисто чёрные пиксели
  уходят в K-плоскость, которая отбрасывается, — чёрный текст пропадал бы;
- `*Product`/`1284DeviceID`, как у оригинального PPD HP, чтобы macOS сама
  предлагала драйвер; A4 по умолчанию; иконка; запрет двусторонней печати,
  пока не отмечен «Duplexer Installed».

Не перенесено из пакета HP: HP Printer Utility, Device Manager, монитор чернил,
ПО Photosmart, ICC-профили (они описывают цветовой тракт старого драйвера, а
hpcups использует собственные таблицы цветоделения).

## Установка

```bash
sudo installer -pkg HP-Officejet-K7100-macOS-1.0.0.pkg -target /
```

Пакет не подписан сертификатом Apple Developer, поэтому двойной щелчок по нему
Gatekeeper заблокирует; используйте команду выше или «Открыть» в контекстном меню Finder.

Затем: **Системные настройки → Принтеры и сканеры → Добавить принтер** → выбрать
K7100 (USB) → в поле «Использовать» выбрать **HP Officejet K7100 (hpcups 1.0.0)**.

Добавить очередь из терминала (USB-адрес можно взять из `lpinfo -v`):

```bash
lpadmin -p K7103 -E -v "usb://HP/Officejet%20K7100?serial=..." -P "/Library/Printers/PPDs/Contents/Resources/HP Officejet K7100 (hpcups).ppd.gz"
```

Для сетевого подключения через JetDirect используйте `socket://<ip>:9100`.

Удаление: `./uninstall.sh`.

## Сборка

Нужны Xcode Command Line Tools. Для иконки принтера положите
`HP_Installer_OJK7100_v9.7.dmg` в `macos/vendor/` (или укажите путь в `HP_DMG=...`);
без него пакет соберётся без иконки. Затем:

```bash
cd macos
./build.sh
```

Скрипт скачивает исходники HPLIP и IJG libjpeg в `sources/` (контрольные суммы в
`sources/SHA256SUMS`), собирает статическую libjpeg и `hpcups`, проверяет PPD
через `cupstestppd` и кладёт пакет в `dist/`.

Адаптация HPLIP под macOS (всё в `build.sh`, исходники HPLIP не правятся по смыслу):

- `common/utils.h` переименован: на APFS без учёта регистра он перекрывался `prnt/hpcups/Utils.h`;
- имена объектных файлов включают путь (`utils.o` ≠ `Utils.o`);
- `compat/malloc.h` вместо отсутствующего в macOS заголовка;
- без D-Bus и без бинарного `libImageProcessor` (он нужен только LaserJet ZJStream).

## Что проверено

- `hpcups` запускается на arm64 и под Rosetta (x86_64), PCL у обеих архитектур
  совпадает побайтно (без учёта меток времени PJL);
- конвейер macOS `cgpdftoraster` → `hpcups` для A4, A3, Super B (13×19"), режимов
  Fast Draft/Draft/Normal/Best/Photo (1200 dpi), цвета и оттенков серого: на выходе
  PJL `ENTER LANGUAGE=PCL3GUI` с растровыми данными;
- `cupstestppd` без ошибок (остаются только предупреждения HPLIP о нестандартных
  именах размеров бумаги).

- печать на реальном HP Officejet K7100 по USB на macOS 26 (Apple Silicon):
  очередь создаётся штатно, пробная страница печатается корректно.

## Лицензии

`hpcups` — HPLIP, лицензия в `/Library/Printers/HP_K7100/COPYING-HPLIP`
(BSD/MIT/GPL по компонентам). libjpeg — Independent JPEG Group. Иконка — HP:
она не хранится в репозитории и попадает в пакет только при локальной сборке из DMG.
