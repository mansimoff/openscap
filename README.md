# Ansible Роль `openscap`

Сканирует сервер Rocky Linux 9/10 с помощью OpenSCAP на соответствие профилю PCI DSS,
генерирует скрипт исправления на основе первого сканирования и применяет его 
(предварительно вырезаны правила, способные лишить доступа к серверу или включить SELinux enforcing.)

## Что делает

1. Проверяет, что ОС — Rocky Linux 9 или 10 (иначе останавливается).
2. Ставит `openscap openscap-scanner openscap-utils scap-security-guide
   openscap-engine-sce libxml2`.
3. Создаёт `/openscap_data`.
4. Если ремедиация ещё не выполнялась на этом сервере (нет маркера
   `/openscap_data/.remediation_applied`) или задан
   `openscap_force_rerun: true`:
   - определяет актуальный SSG datastream-файл (`ssg-rl{N}-ds.xml` с
     fallback на `ssg-rhel{N}-ds.xml`, см. ниже "Почему два кандидата");
   - сканирует профиль `pci-dss`, сохраняет XML-результаты и HTML-отчёт;
   - генерирует bash-скрипт ремедиации (`oscap xccdf generate fix`);
   - **вырезает из него блоки правил по Rule ID** (см. список ниже) —
     фильтрация идёт по стабильному идентификатору правила, а не по
     порядковому номеру, потому что номера "N / TOTAL" отличаются между
     версиями пакета `scap-security-guide` и профилями;
   - применяет очищенный скрипт;
   - проверяет `sshd -t` и `visudo -c` после применения;
   - делает повторное сканирование "после" для сравнения;
   - пишет маркер с датой, профилем и списком исключённых правил.

## Почему два кандидата datastream-файла

`ssg-rl{N}-ds.xml` — Rocky-специфичный файл, но он несколько раз пропадал
из сборки пакета `scap-security-guide` на Rocky из-за upstream-бага
(см. [ComplianceAsCode/content#14651](https://github.com/ComplianceAsCode/content/issues/14651)).
Роль сначала ищет его, а если не находит — использует `ssg-rhel{N}-ds.xml`,
который содержит тот же набор правил (Rocky — бинарно совместимый форк
RHEL, RHEL-контент на нём валиден).

## Какие правила вырезаются и почему

| Rule ID | Что ломает, если оставить |
|---|---|
| `content_rule_sudo_require_authentication` | Комментирует `NOPASSWD`/`!authenticate` в `sudoers.d/*` — может сломать non-interactive `sudo` для автоматизации (Ansible/CI) |
| `content_rule_no_direct_root_logins` | Полностью очищает `/etc/securetty` — теряется прямой root-логин с локальной консоли/IPMI |
| `content_rule_use_pam_wheel_group_for_su` | Привязывает `su` к заведомо пустой группе — `su` перестаёт работать вообще ни для кого |
| `content_rule_selinux_state` | Переводит SELinux в `enforcing` (relabel при следующей загрузке) |
| `content_rule_grub2_enable_selinux` | Убирает `selinux=0`/`enforcing=0` из grub — работает в связке с предыдущим |

Список настраивается через `openscap_excluded_rule_ids` — при желании
можно добавить туда что-то ещё или, наоборот, сузить.

## Переменные

Все — в `defaults/main.yml`, самые важные:

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `openscap_profile` | `xccdf_org.ssgproject.content_profile_pci-dss` | Профиль сканирования |
| `openscap_apply_fixes` | `true` | Применять очищенный скрипт автоматически. `false` — только подготовить `fixes_ready_to_apply.sh`, применение — руками |
| `openscap_rescan_after_fix` | `true` | Скан "после" для отчётности |
| `openscap_force_rerun` | `false` | Прогнать весь цикл заново, игнорируя маркер |
| `openscap_excluded_rule_ids` | см. выше | Какие правила вырезать |

## Идемпотентность

Первый прогон создаёт `/openscap_data/.remediation_applied`. Повторные
прогоны роли (например, при повторном запуске `office_area` на том же
сервере) видят маркер и весь тяжёлый цикл (скан → генерация → фильтрация
→ применение) пропускают — playbook отработает за секунды, без повторного
скана и без повторного запуска remediation-скрипта. Пакеты и каталог
`/openscap_data` при этом всё равно проверяются каждый раз (это дёшево и
естественно идемпотентно через `dnf`/`file`).

Чтобы прогнать цикл заново на уже обработанном сервере:

```yaml
- hosts: myhost
  roles:
    - role: openscap
      vars:
        openscap_force_rerun: true
```

## Пример использования в `office_area.yml`

```yaml
- name: Настройка сервера после создания
  hosts: all
  become: true
  roles:
    - role: openscap
    - role: some_other_role
    - role: yet_another_role
```

## Файлы на сервере после выполнения

```
/openscap_data/
├── pcidss_results.xml              # результаты первого скана (XML)
├── pcidss_report.html              # результаты первого скана (HTML)
├── fixes_only_failed.sh            # полный сгенерированный remediation, без фильтрации
├── remove_rule_blocks.py           # скрипт фильтрации (скопирован ролью)
├── fixes_ready_to_apply.sh         # очищенный скрипт — именно он выполняется
├── excluded_rules_report.txt       # что вырезано / что не найдено
├── fixes_apply.log                 # stdout/stderr применения (если openscap_apply_fixes: true)
├── pcidss_results_after_fix.xml    # результаты скана "после" (если openscap_rescan_after_fix: true)
├── pcidss_report_after_fix.html    # результаты скана "после" (HTML)
└── .remediation_applied            # маркер идемпотентности
```

