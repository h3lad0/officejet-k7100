# HP Officejet K7100 / K7103 / K7108 на современных macOS и Windows

HP прекратила поддержку струйного A3+ принтера Officejet K7100 (K7103, K7108) в
2008 году. Последние официальные драйверы — для macOS 10.5 и Windows Vista.
В этом репозитории собрано всё, чтобы принтер печатал на текущих системах.

| Система | Решение | Папка |
|---|---|---|
| **macOS 11+** (Apple Silicon и Intel) — проверено на реальном принтере | Новый драйвер: фильтр `hpcups` из открытого HP HPLIP, собранный под arm64 + x86_64, и адаптированный PPD | [macos/](macos/) |
| **Windows 10 / 11** (x64, x86) — проверено на Windows 11 x64 | Оригинальный драйвер HP с подписью WHQL, установленный без устаревшего установщика HP | [windows/](windows/) |

Подробности, установка и ограничения — в README каждой папки.

## Файлы HP

Репозиторий **не содержит** программ и файлов HP. Скачайте оригинальные пакеты с
сайта поддержки HP и положите их в `vendor/` нужной папки:

- `macos/vendor/HP_Installer_OJK7100_v9.7.dmg` — нужен только для иконки принтера,
  без него драйвер для macOS тоже собирается;
- `windows/vendor/OJK7100_Full_8.exe` — источник драйвера для Windows.

Контрольные суммы версий, с которыми проверялись скрипты, лежат в `*/SHA256SUMS`.

## English summary

Drivers for the discontinued HP Officejet K7100/K7103/K7108 A3+ inkjet:

- **macOS 11+**: HP's 2008 driver is PPC/i386-only. `macos/build.sh` builds the
  open-source HPLIP `hpcups` filter as a universal binary, adapts the HPLIP PPD
  (including a fix for black text vanishing in color mode) and produces an
  installer package.
- **Windows 10/11 x64/x86**: HP's WHQL-signed Vista driver still works, but
  its installer does not. `windows/install.ps1` extracts the driver from
  HP's `OJK7100_Full_8.exe` and installs it unmodified via `pnputil`. ARM64 is
  not supported (HP's plug-ins are x64/x86 binaries only).

No HP files are redistributed; you need to supply HP's original packages yourself.

## Лицензия

Скрипты и патчи этого репозитория распространяются по лицензии MIT ([LICENSE](LICENSE)).
HPLIP и libjpeg, которые скачивает сборка, распространяются по своим лицензиям.
Драйвер HP для Windows и иконка принтера принадлежат HP Inc. и в репозиторий не входят.
HP и Officejet — товарные знаки HP Inc.; проект с HP не связан.
