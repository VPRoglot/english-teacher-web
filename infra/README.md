# Production: сервер, деплой, бэкапы, мониторинг

Руководство по запуску сайта на одном VPS с Docker Compose. Разработка и dev-стек описаны в корневом [README.md](../README.md), здесь только production.

Что работает на сервере (`infra/docker-compose.yml` + `infra/docker-compose.prod.yml`): `nginx` (единственный сервис с открытыми портами 80 и 443), `certbot`, `web`, `api`, `worker`, `scheduler`, `postgres`, `redis`, `backup`. Образы собирает CI/CD и публикует в GHCR; на сервере ничего не собирается.

**Требования к серверу:** Linux (команды ниже для Ubuntu 24.04/Debian), Docker Engine **≥ 25** (у образа nginx `HEALTHCHECK --start-interval`), docker compose **≥ 2.24.4** (в `docker-compose.prod.yml` используются `!reset` и `!override`), `git`, `curl`, `bash`, `flock` (util-linux), домен с A-записью на IP сервера.

Во всех командах ниже `$DC` — это сокращение; задайте его один раз в сессии из корня клона репозитория (точная форма, которую использует и `infra/scripts/deploy.sh`):

```bash
export DC="docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.prod.yml"
```

## 1. Сервер

Выполняйте под `root` (или `sudo`) при первом входе.

**Пользователь `deploy` без root, вход только по ключу:**

```bash
adduser --disabled-password --gecos "" deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
# Вставьте свой публичный ключ (с рабочей машины: cat ~/.ssh/id_ed25519.pub)
echo "ssh-ed25519 AAAA... you@workstation" >> /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys

cat > /etc/ssh/sshd_config.d/10-hardening.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin no
EOF
sshd -t && systemctl reload ssh
```

Не закрывайте текущую сессию, пока в **новом** окне не получилось `ssh deploy@<сервер>`. Если на сервере в `/etc/ssh/sshd_config.d/` лежат другие файлы с теми же параметрами, первое найденное значение побеждает — проверьте `sshd -T | grep -E 'passwordauthentication|permitrootlogin'` (должно быть `no`).

**Файрвол, fail2ban, автообновления:**

```bash
apt-get update
apt-get install -y ufw fail2ban unattended-upgrades

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

systemctl enable --now fail2ban        # защита sshd включена по умолчанию
dpkg-reconfigure -plow unattended-upgrades
```

Docker сам прописывает правила iptables для опубликованных портов в обход ufw. Это безопасно, пока опубликованы только 80 и 443 (так сделано в `docker-compose.prod.yml`); не добавляйте `ports:` другим сервисам (особенно postgres и redis).

**Docker Engine из официального репозитория** (Ubuntu; для Debian замените `ubuntu` на `debian` в двух местах):

```bash
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy

docker --version            # >= 25
docker compose version      # >= 2.24.4
```

Группа `docker` фактически даёт root-доступ к хосту, поэтому ключ `deploy` храните так же бережно, как root-ключ. Дальше всё выполняется под `deploy` (заново войдите по ssh, чтобы группа применилась).

## 2. Секреты и `.env`

Склонируйте репозиторий (для `git fetch` из `deploy.sh` нужен доступ без пароля: например, read-only deploy key репозитория в `~/.ssh` пользователя `deploy` и `git clone git@github.com:<владелец>/<репозиторий>.git`):

```bash
cd ~
git clone git@github.com:<владелец>/<репозиторий>.git english-tutor
cd english-tutor
cp infra/prod.env.example .env
chmod 600 .env
```

Путь к клону (`/home/deploy/english-tutor`) — это `DEPLOY_PATH` для CD (раздел 6). Отредактируйте `.env`: каждое значение `change-me*` заменяется, backend в prod не стартует с заглушками. Комментарии в `infra/prod.env.example` описывают каждую переменную; здесь только то, что требует действий:

```bash
openssl rand -hex 32     # REVALIDATE_SECRET
openssl rand -hex 24     # POSTGRES_PASSWORD (только [0-9a-f]: не нужно экранировать в DATABASE_URL)
```

- `POSTGRES_PASSWORD` и пароль в `DATABASE_URL` должны совпадать.
- `DOMAIN` — без схемы; `PUBLIC_BASE_URL` и `SITE_URL` — `https://<домен>` без завершающего `/`.
- `IMAGE_REGISTRY=ghcr.io/<владелец репозитория в нижнем регистре>`.
- `IMAGE_TAG` задайте при первом деплое (раздел 4); дальше его меняет только `deploy.sh`. Он правит `.env` через `sed -i`, а это заменяет символическую ссылку обычным файлом: держите `.env` обычным файлом в корне клона, не ссылкой.
- `S3_*` — **публичный** бакет с фото лендинга; `MEDIA_UPSTREAM` и `MEDIA_UPSTREAM_HOST` — его адрес (nginx проксирует `/media/<ключ>` туда с проверкой TLS-сертификата).
- `BACKUP_S3_*` — **другой, ПРИВАТНЫЙ** бакет с отдельным ключом доступа. `BACKUP_S3_BUCKET` обязан отличаться от `S3_BUCKET`, иначе контейнер `backup` завершится с ошибкой до дампа. Бэкапы содержат персональные данные: убедитесь в консоли хранилища, что анонимное чтение бакета бэкапов выключено. **Версионирование и блокировка объектов (object lock) в бакете бэкапов должны быть выключены**: иначе удалённые ротацией копии остаются старыми версиями объектов, и обещание «не дольше 6 месяцев» (раздел 9) не выполняется.
- `SMARTCAPTCHA_*` и `TELEGRAM_*` обязательны (см. корневой README, разделы «Заявки и уведомления»).
- Строки `SENTRY_DSN*` и `HEARTBEAT_*` необязательны: закомментируйте или оставьте пустыми, если не используете (см. раздел 8).

**Ключ шифрования бэкапов (`age`) создаётся на вашей рабочей машине, не на сервере:**

```bash
age-keygen -o age-key.txt        # на рабочей машине: https://github.com/FiloSottile/age
# выведет: Public key: age1...
```

В `.env` на сервер кладётся только публичный ключ: `BACKUP_AGE_RECIPIENT=age1...`. Файл `age-key.txt` (приватный ключ) храните вне сервера — в менеджере паролей и в офлайн-копии. **Потеряете ключ — бэкапы не расшифровать.** На сервер его копируют только на время восстановления (раздел 7) и сразу удаляют.

Проверка конфигурации (подстановки `${…:?}` в compose сообщат о недостающих переменных):

```bash
$DC config -q && echo OK
```

## 3. GHCR

Образы приватные, серверу нужен токен чтения. В GitHub: Settings → Developer settings → Personal access tokens → создайте токен с единственным правом `read:packages` (classic) и под `deploy` выполните:

```bash
echo "<PAT>" | docker login ghcr.io -u <github-логин> --password-stdin
```

Данные входа сохраняются в `~/.docker/config.json` пользователя `deploy`; именно под ним `docker compose pull` запускается из `deploy.sh`.

## 4. Первый деплой и TLS

`infra/scripts/deploy.sh <sha>` требует, чтобы в `.env` уже была ровно одна строка `IMAGE_TAG=sha-<40 hex>`: по ней он находит коммит и образы для отката. Поэтому **первый деплой делается вручную**:

1. Соберите и опубликуйте образы первого релиза. Самый простой путь — workflow `CD` (`.github/workflows/cd.yml`): после зелёного CI на `main` или запуском `workflow_dispatch` с полным sha (Actions → CD → Run workflow). Задание `images` публикует четыре образа (`english-tutor-backend`, `-frontend`, `-nginx`, `-backup`) с общим тегом `sha-<40 hex>`, даже если задание `deploy` ещё не настроено и упадёт.
2. На сервере впишите **этот же** sha в `.env` (так откат при неудаче вернёт то же состояние, а не несуществующий прежний релиз):

   ```bash
   sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=sha-<40 hex>/' .env
   ```

3. Запустите деплой. `deploy.sh` сам делает `git fetch`, `git checkout --detach <sha>`, `compose pull`, `run --rm migrate`, `up -d` и smoke-проверку; для ручного запуска отвяжите его от ssh-сессии:

   ```bash
   setsid nohup infra/scripts/deploy.sh <40 hex sha> >> deploy.log 2>&1 &
   tail -f deploy.log
   ```

   Коды выхода: `0` — релиз работает; `1` — релиз не удался, выполнен откат (или ничего не менялось); `2` — неверные аргументы или `.env`, деплой уже идёт (`.deploy.lock`) либо откат не удался (нужна ручная проверка).

   То же вручную по шагам: `git checkout --detach <sha>`, `$DC pull`, `$DC run --rm migrate`, `$DC up -d`. Сервис `migrate` вынесен в профиль и не входит в `up`: миграции запускаются только явной командой `run --rm migrate`, `up` их никогда не выполняет.

nginx стартует сразу, пока на **self-signed** сертификате (`SERVER_NAME` берётся из `DOMAIN`), и отдаёт `/.well-known/acme-challenge/`. Браузер предупредит о сертификате — это ожидаемо. Smoke-проверка деплоя использует `curl -k`, поэтому self-signed ей не мешает.

**Выпуск сертификата Let's Encrypt.** Убедитесь, что A-запись домена указывает на сервер и порт 80 доступен снаружи. **Условия использования Let's Encrypt принимает владелец сервера** — флаг `--agree-tos` означает ваше согласие с ними:

```bash
$DC run --rm --entrypoint sh certbot -c 'certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email'
$DC exec nginx select-cert
```

(Команда в одинарных кавычках, поэтому `$DOMAIN` и `$LETSENCRYPT_EMAIL` раскрывает оболочка внутри контейнера, куда compose передаёт их из `.env`. `--entrypoint sh` нужен потому, что entrypoint сервиса `certbot` — цикл продления.)

`select-cert` подхватывает сертификат Let's Encrypt (если он читается, не просрочен и ключ соответствует) и перечитывает конфигурацию nginx; иначе остаётся на self-signed. Дальше всё автоматически:

- контейнер `certbot` каждые 12 часов выполняет `certbot renew` (продлевает только то, что подходит к сроку);
- nginx раз в 6 часов сам вызывает `select-cert` и перечитывает сертификат, поэтому новый появляется без перезапуска.

**Диагностика nginx.** Логи в формате JSON: `$DC logs nginx`. Ошибки upstream видны в поле `status` и в полях `upstream_status` / `upstream_addr` access-лога. `error_log` намеренно стоит на уровне `crit`: на ошибках upstream nginx пишет в него строку запроса и referer **без маскирования токенов**. Чтобы временно увидеть подробности, поднимите уровень в работающем контейнере и после отладки обязательно верните (пересоздание контейнера тоже возвращает `crit`):

```bash
$DC exec nginx sh -c "sed -i 's/error.log crit;/error.log warn;/' /etc/nginx/conf.d/default.conf && nginx -s reload"
$DC logs --tail 100 nginx      # error_log nginx пишет в stderr контейнера, строки видны в docker logs среди JSON access-лога
$DC exec nginx sh -c "sed -i 's/error.log warn;/error.log crit;/' /etc/nginx/conf.d/default.conf && nginx -s reload"
```

## 5. Репетитор и контент

Начальные блоки лендинга (`hero`, `about`, `services`, `reviews`, `faq`, `contacts`) уже созданы миграцией. Создайте учётную запись репетитора (одна на систему; команда спросит пароль, нужен TTY, поэтому `ssh -t` или интерактивная сессия):

```bash
$DC exec api python -m app.cli create-tutor --email you@example.com
```

Затем войдите на `https://<домен>/login` и в `/admin/site` замените заглушки: **заполните `hero.name` и блок `contacts`** — они попадают на страницу `/privacy` как имя и контакты оператора персональных данных.

## 6. CD

Workflow `.github/workflows/cd.yml`: после зелёного CI на `main` собирает и публикует четыре образа в GHCR (`sha-<commit>` и `latest`), затем по SSH запускает на сервере `infra/scripts/deploy.sh <sha>`. Скрипт работает отвязанным от SSH-сессии (`setsid nohup`), его вывод пишется в отдельный журнал `$DEPLOY_PATH/deploy-logs/<время UTC>-<sha>.log` и одновременно показывается в логе Actions; обрыв соединения деплой не прерывает (задание тогда завершится с кодом 255, а итог смотрите в журнале на сервере). Старые журналы удаляйте вручную. Автоматически деплоится только коммит, который на момент запуска остаётся вершиной `main`: CI более старого коммита, закончившийся позже, сборку и деплой пропускает (notice в логе), чтобы не откатить сервер. `workflow_dispatch` с любым sha этим не ограничен. `DEPLOY_PATH` — абсолютный путь только из символов `A-Za-z0-9._/-` (ssh передаёт его через командную строку login-шелла).

**Secrets** (GitHub → Settings → Secrets and variables → Actions; лучше как secrets окружения `production`):

| Секрет | Значение |
|---|---|
| `DEPLOY_HOST` | адрес сервера |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | приватный ключ, отдельный от вашего личного; публичную часть добавьте в `~deploy/.ssh/authorized_keys` |
| `DEPLOY_KNOWN_HOSTS` | строка(и) `known_hosts` сервера: `ssh-keyscan -t ed25519 <хост>` (сверьте отпечаток с консолью провайдера) |
| `DEPLOY_PATH` | абсолютный путь к клону на сервере, например `/home/deploy/english-tutor` |

**Variables:** `SENTRY_DSN_WEB` — необязательный DSN для браузерной части frontend, встраивается в образ при сборке (раздел 8).

**Environment `production`.** Задание `deploy` выполняется в окружении `production` (Settings → Environments → New environment). Настройте:

- **Required reviewers** — тогда деплой ждёт ручного подтверждения;
- **Deployment branches → Selected branches → `main`**. Без этого `workflow_dispatch` принимает любой 40-значный sha из любой ветки и может задеплоить непроверенный код.

**Правило миграций: только расширяющие.** При неудачной smoke-проверке `deploy.sh` возвращает прежние образы и прежний коммит, но **не откатывает схему БД**. Поэтому каждая миграция обязана быть совместима с кодом предыдущего релиза: столбцы и таблицы удаляются или переименовываются отдельным релизом, после того как работающий код перестал их использовать (добавили — перешли — убрали). Новые столбцы без значения по умолчанию должны быть nullable. Критерий: прежний релиз должен нормально работать на новой схеме.

**Ручной откат** на любой прежний релиз: `infra/scripts/deploy.sh <прежний sha>` (запуск и коды выхода — раздел 4). Образы четырёх сервисов (backend, frontend, nginx, backup) всегда делят один `IMAGE_TAG`, поэтому откат возвращает их вместе; смотрите `git log` или список тегов в GHCR, чтобы найти нужный sha.

## 7. Бэкапы

Контейнер `backup` (`infra/backup`, образ около 425 МБ) по расписанию `30 2 * * *` (**02:30 UTC**, 05:30 МСК) делает `pg_dump | gzip | age` и кладёт файл в бакет `BACKUP_S3_BUCKET`:

- `backups/daily/YYYY-MM-DD.sql.gz.age` — хранятся **14** новейших;
- `backups/monthly/YYYY-MM.sql.gz.age` — первая копия месяца, хранятся **6** новейших.

Только что созданная копия никогда не удаляется ротацией. Дамп снят с `--no-owner`, но **без** `--no-privileges`: в нём есть `GRANT` для роли БД, поэтому восстанавливать нужно на сервер с той же ролью (`POSTGRES_USER`).

**Проверка, что бэкапы появляются** (у `aws` свои ключи; подставьте значения из `.env`, endpoint — `BACKUP_S3_ENDPOINT_URL`):

```bash
$DC logs --tail 20 backup
$DC exec backup sh -c 'AWS_ACCESS_KEY_ID="$BACKUP_S3_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$BACKUP_S3_SECRET_KEY" AWS_DEFAULT_REGION="$BACKUP_S3_REGION" aws ${BACKUP_S3_ENDPOINT_URL:+--endpoint-url "$BACKUP_S3_ENDPOINT_URL"} s3 ls --recursive "s3://$BACKUP_S3_BUCKET/backups/"'
```

Внеплановый бэкап: `$DC exec backup backup.sh`.

### Восстановление

Восстанавливать можно **только в пустую базу** (`restore.sh` откажется, если в схеме `public` есть таблицы). На диске должно быть место примерно в **2× размера сжатого дампа** (скачанный `.age` и расшифрованный `.gz` лежат во временном каталоге контейнера).

1. Скопируйте приватный ключ с рабочей машины на сервер (временно): `scp age-key.txt deploy@<сервер>:~/age-key.txt`, затем на сервере `chmod 600 ~/age-key.txt`. Если копируете через оболочку на сервере, сначала выполните `umask 077`, чтобы файл не создался доступным другим пользователям.
2. Остановите сервисы, пишущие в базу:

   ```bash
   $DC stop api worker scheduler
   ```

3. Пересоздайте базу (переменные `POSTGRES_*` есть в окружении контейнера postgres):

   ```bash
   $DC exec postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\""'
   ```

4. Восстановите нужную копию (ключ объекта — из `s3 ls` выше):

   ```bash
   $DC run --rm -v ~/age-key.txt:/run/age-identity:ro backup \
     restore.sh backups/daily/YYYY-MM-DD.sql.gz.age /run/age-identity
   ```

5. Удалите ключ с сервера: `shred -u ~/age-key.txt` (или `rm`).
6. Поднимите сервисы и проверьте: `$DC up -d`, затем `curl -fsS https://<домен>/api/health/ready`. Если после восстановления схема старее текущего релиза, догоните её: `$DC run --rm migrate`.

### Учебное восстановление (раз в квартал)

Проверка, что бэкап реально читается и ключ у вас на руках, — в **отдельную** базу, не трогая рабочую:

```bash
$DC exec postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE drill"'
$DC run --rm -e PGDATABASE=drill -v ~/age-key.txt:/run/age-identity:ro backup \
  restore.sh backups/daily/YYYY-MM-DD.sql.gz.age /run/age-identity
$DC exec postgres sh -c 'psql -U "$POSTGRES_USER" -d drill -c "select count(*) from users"'
$DC exec postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE drill"'
```

Затем удалите ключ с сервера. Запишите дату проверки.

## 8. Мониторинг

**Ошибки (Sentry или self-hosted GlitchTip).** Рекомендуется GlitchTip на хостинге в РФ: sentry.io хранит данные за рубежом, и подключение к нему означает трансграничную передачу данных об ошибках (152-ФЗ). В события не попадают тела запросов, локальные переменные, cookie и IP (`send_default_pii` выключен), но URL, заголовки User-Agent и тексты исключений туда уходят. Создайте два проекта (backend и frontend) и пропишите DSN в `.env`:

| Переменная | Что делает |
|---|---|
| `SENTRY_DSN` | backend (api, worker, scheduler), читается при старте контейнеров |
| `SENTRY_TRACES_SAMPLE_RATE` | доля трассируемых транзакций, 0..1 (по умолчанию 0 — только ошибки) |
| `SENTRY_DSN_WEB` | серверная часть `web` (контейнер получает её как `SENTRY_DSN`) |
| GitHub variable `SENTRY_DSN_WEB` | браузерная часть: DSN встраивается в образ frontend при сборке (`NEXT_PUBLIC_SENTRY_DSN`), поэтому после его смены нужна новая сборка (новый запуск CD) |

Строки `SENTRY_DSN` и `SENTRY_DSN_WEB` в `.env` закомментированы, пока не используются. Релиз событий — `IMAGE_TAG`, окружение — `prod` у всех частей (backend — `APP_ENV`, web — `SENTRY_ENVIRONMENT` и build arg `NEXT_PUBLIC_SENTRY_ENVIRONMENT`). События браузера идут через собственный туннель `/monitoring` на вашем домене, который принимает только конверты с настроенным DSN; работает и с sentry.io, и с GlitchTip. Токены приглашений и сброса пароля маскируются (`***`) в событиях. Source maps не загружаются (решение MVP), стек-трейсы браузера минифицированы — подробности в [frontend/README.md](../frontend/README.md#sentry). После изменения `.env` пересоздайте контейнеры: `$DC up -d` (простой `restart` новые значения не подхватит).

**Внешний uptime-монитор** (UptimeRobot, Better Stack, Healthchecks и т. п.), вне вашего сервера:

- `https://<домен>/api/health/ready` — готовность api (БД и Redis) и `https://<домен>/` — лендинг, интервал 1–5 минут;
- оповещение в Telegram;
- проверка срока сертификата (оповещение за 14 дней до истечения): это единственный контроль продления Let's Encrypt, `deploy.sh` сертификат не проверяет.

**Heartbeat-мониторы** подтверждают, что ночные задачи действительно срабатывают: после успешного запуска задача делает GET на свой URL, а монитор поднимает тревогу, если пинга нет. Создайте три монитора (Healthchecks.io или heartbeat-монитор GlitchTip), период 1 день, grace 2 часа, и впишите адреса (они содержат секрет) в `.env`:

| Переменная | Кто пингует | Время (UTC) |
|---|---|---|
| `HEARTBEAT_MATERIALIZE_URL` | worker, задача `lessons.materialize_series` | 01:00 |
| `HEARTBEAT_ANONYMIZE_URL` | worker, задача `leads.anonymize_stale` | 01:30 |
| `HEARTBEAT_BACKUP_URL` | контейнер `backup` | 02:30 |

Если монитор не используется, оставьте строку закомментированной (пустое значение `KEY=` тоже отключает пинг). Ошибка пинга логируется и задачу не ломает. После правки `.env`: `$DC up -d`.

## 9. Персональные данные (152-ФЗ)

**Удаление семьи по запросу родителя** (`purge-family`): семья сначала архивируется репетитором в админке (`/admin/families`), иначе команда откажет. Затем:

```bash
$DC exec api python -m app.cli purge-family <family_id>
```

Команда печатает сводку (сколько пользователей, детей, занятий, запросов и заявок будет удалено) и спрашивает подтверждение; `--yes` пропускает вопрос. Всё выполняется в одной транзакции: запросы на перенос, занятия, серии и заметки, заявки семьи с историей и пробными занятиями, приглашения, учётные записи родителей и детей; после коммита отзываются Redis-сессии. Если Redis в этот момент недоступен, команда всё равно завершается успешно (данные уже удалены) и печатает «Сессии не отозваны…»: такие сессии недействительны, потому что их пользователей больше нет. Операция необратима.

**Обезличивание заявок.** Ежедневная задача `leads.anonymize_stale` (01:30 UTC) обезличивает заявки в статусе, отличном от `converted`, если с последней смены статуса прошло не меньше 12 месяцев (подробно — корневой README, «Заявки и уведомления»). Контролируется heartbeat'ом `HEARTBEAT_ANONYMIZE_URL`.

**Срок жизни в бэкапах.** Удалённые данные остаются в зашифрованных бэкапах до 6 месяцев (ротация: 6 месячных копий). Это указано в политике конфиденциальности; при удалении по запросу сообщайте этот срок. Срок держится, только если в бакете бэкапов выключены версионирование и object lock (раздел 2) и бэкапы идут каждый день: месячная копия — первая удачная в месяце, поэтому если бэкапы не проходили в начале месяца (или весь месяц), самая старая из 6 месячных копий может оказаться старше 6 месяцев. Такой сбой виден по тревоге heartbeat-монитора `HEARTBEAT_BACKUP_URL` (раздел 8) — чините его сразу.

## 10. Чек-лист после первого деплоя

- [ ] Заявка с телефона на prod-домене проходит настоящую SmartCaptcha и создаётся в `/admin/leads`.
- [ ] Telegram-сообщение о заявке пришло.
- [ ] `curl -I https://<домен>/` показывает HSTS, CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`; оценка на SSL Labs не ниже A.
- [ ] Сертификат выпущен Let's Encrypt (не self-signed), `select-cert` выполнен.
- [ ] На следующий день пришли все три heartbeat'а (01:00, 01:30, 02:30 UTC) — cron реально срабатывает.
- [ ] Фото на лендинге загружается через `/media/…` (после загрузки в `/admin/site`): nginx проксирует его на настоящий S3 с проверкой TLS-сертификата и SNI — ответ `200`, а не `502`.
- [ ] В бакете бэкапов появился `backups/daily/…sql.gz.age`; бакет приватный, версионирование и object lock выключены.
- [ ] Тестовое событие Sentry из api и из web:
  - api (должен быть задан `SENTRY_DSN`; событие появится в проекте backend):

    ```bash
    $DC exec api python -c "import sentry_sdk; from app.core.config import get_settings; from app.core.observability import init_sentry; init_sentry(get_settings(), 'api'); sentry_sdk.capture_message('deploy check'); sentry_sdk.flush()"
    ```

  - web (браузер): откройте сайт, в консоли браузера выполните `setTimeout(() => { throw new Error('deploy check') })` — событие уйдёт через `/monitoring` в проект frontend. Серверная часть web отдельной простой проверки не имеет: убедитесь, что `SENTRY_DSN_WEB` задан, а браузерное событие дошло.
- [ ] Внешний uptime-монитор зелёный, оповещение в Telegram проверено.
- [ ] Учебное восстановление бэкапа выполнено (раздел 7).
- [ ] В `/admin/site` заполнены `hero.name` и `contacts`.

## Приложение: проверка стека без сервера

`just e2e` поднимает production-подобный стек (nginx с self-signed TLS, `tutor.test`) и прогоняет Playwright; стек остаётся доступным на `https://localhost:8443`, остановить и удалить данные — `just e2e-down`. Подробнее — корневой README, раздел «Тесты». Тесты скриптов инфраструктуры: `bash infra/nginx/test.sh`, `bash infra/backup/test.sh`, `bash infra/scripts/test-deploy.sh`.
