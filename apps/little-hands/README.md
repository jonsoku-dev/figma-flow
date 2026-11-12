# 작은손 커피공방 운영 배포

이 디렉터리의 기존 Django 5.2 서비스와 PostgreSQL 17을 위한 단일 호스트 패키지다. Gunicorn은 호스트 loopback에서만 받으며 호스트의 nginx가 HTTPS를 종료한다. 사용자 계정, 예약, 결제, 외부 메시지를 자동 생성하거나 발송하지 않는다. Compose 실행은 공개 배포 승인을 대신하지 않는다.

`ARCHITECTURE.md`가 데이터·권한 계약을 소유한다. Python과 PostgreSQL 이미지는 다중 플랫폼 digest로 고정했고 `requirements.lock`은 전체 Python 의존성과 PyPI SHA256을 고정한다. 버전 갱신 시 `requirements.txt`와 lock을 함께 검토하고 새 이미지에서 검사한다. 운영 환경은 Docker Compose v2, Linux 컨테이너 및 호스트 nginx를 전제로 한다. Docker 소켓 접근자는 모든 비밀과 DB를 읽을 수 있는 관리자다.

## 1. 비밀과 설정

이 디렉터리에서 실행한다. 운영 비밀은 체크아웃 밖의 전용 디렉터리에 둔다. 비밀값을 CLI 인수나 저장소 파일에 입력하지 않는다. 아래는 최초 설치용이며 기존 비밀을 덮어쓰지 않는다.

```sh
export LH_SECRETS_DIR="$HOME/.config/littlehands-production/secrets"
python3 - <<'PY'
import os, secrets
from pathlib import Path
root = Path(os.environ['LH_SECRETS_DIR'])
root.mkdir(parents=True, exist_ok=True, mode=0o700)
for name in ('django_secret', 'postgres_password', 'owner_password', 'runtime_password'):
    with (root / name).open('x') as f:
        os.chmod(f.name, 0o600)
        f.write(secrets.token_urlsafe(64) + '\n')
PY
```

파일 비밀은 Compose가 bind mount한다. Linux에서 앱 UID 10001은 Django/runtime 비밀과 migration owner 비밀을 읽어야 하며, 고정한 PostgreSQL 이미지의 UID 999는 DB 초기화 비밀을 읽어야 한다. ACL을 지원하는 전용 호스트의 예시는 다음과 같다. 호스트의 같은 UID도 비밀을 읽을 수 있으므로 신뢰하는 전용 서비스 계정에만 해당 UID를 할당한다.

```sh
setfacl -m u:10001:r-- "$LH_SECRETS_DIR/django_secret" "$LH_SECRETS_DIR/runtime_password" "$LH_SECRETS_DIR/owner_password"
setfacl -m u:999:r-- "$LH_SECRETS_DIR/postgres_password" "$LH_SECRETS_DIR/runtime_password" "$LH_SECRETS_DIR/owner_password"
```

비밀을 world-readable로 바꾸지 않는다. Docker Desktop과 실제 Linux의 파일 권한 동작은 다르므로 대상 호스트에서 확인한다. 암호 파일 변경은 기존 DB role 암호를 변경하지 않는다. DB 암호 회전은 점검 시간에 역할 암호와 파일을 함께 교체하고 앱을 재생성한다.

```sh
export LH_ALLOWED_HOSTS='workshop.example.invalid'
export LH_SITE_URL='https://workshop.example.invalid'
export LH_HTTP_PORT=8870
```

위 도메인은 문서용이다. 소유한 실도메인으로 두 값을 교체한다. 쉼표로 구분한 정확한 호스트만 허용한다. `LH_ENV=production`은 HTTPS, secure cookie, CSRF, HSTS를 강제한다. HSTS는 하위 도메인·preload까지 설정되므로 같은 도메인의 다른 서비스도 HTTPS 준비가 필요하다. 운영 비밀과 DB 백업을 build context에 복사하지 않는다. `.dockerignore`와 Dockerfile의 명시적 COPY가 `.env`, `.venv`, 캡처, private 자료와 디자인 증거를 제외한다.

## 2. 최초 시작과 마이그레이션

다른 프로젝트와 충돌하지 않는 Compose 프로젝트 이름을 유지한다. `config --quiet`는 설정 값만 검사한다. 전체 `config` 출력은 환경을 표시할 수 있다.

```sh
docker compose config --quiet
docker compose build web
docker compose up -d db
docker compose run --rm migrate
docker compose exec -T db psql -U postgres -d littlehands -v ON_ERROR_STOP=1 < deploy/grants.sql
docker compose run --rm web python manage.py check --deploy --fail-level WARNING
docker compose up -d web
docker compose ps
```

초기화 SQL은 **빈 DB 볼륨에서 한 번** 실행한다. 기존 볼륨에 새 role을 적용하는 방법으로 재시작을 사용하지 않는다. 마이그레이션은 단일 운영자·배포 작업이 실행한다. 웹 시작 시 자동 migrate하지 않는다. `littlehands_owner`만 스키마 DDL을 수행하며 웹은 소유권·역할 멤버십·CREATE·TRUNCATE 없이 실행한다. `grants.sql`은 매번 migrate 다음에 실행한다. 새 테이블에는 기본 runtime 권한을 주지 않으므로 누락 시 서비스가 실패하는 쪽으로 동작한다. 감사·멱등 journal에는 SELECT/INSERT만 남기고 UPDATE/DELETE/TRUNCATE를 회수하며 기존 DB trigger도 유지한다. `django_migrations`는 웹에 노출하지 않는다.

정적 파일은 이미지 빌드 중 WhiteNoise manifest로 수집하며 앱이 직접 서빙한다. 빌드에 실제 비밀이나 DB가 필요하지 않다. 파일 저장소나 고객 업로드는 이 앱의 현재 범위가 아니다. 컨테이너 파일시스템은 읽기 전용이며 임시 파일만 `/tmp`에 쓴다. Gunicorn access log는 개인정보 URL 기록을 줄이기 위해 켜지 않는다. 호스트 proxy 로그도 보존 기간·접근 권한과 URL 개인정보 처리를 운영자가 정한다.

새 버전은 백업 후 점검 시간에 `docker compose stop web`, build, migrate, grants, deploy check, `up -d web` 순서로 적용한다. 실패 시 새 코드를 시작하지 않는다. migration은 역호환을 보장하지 않으므로 이전 이미지 재시작만으로 DB rollback을 가정하지 않는다. 이 단일 호스트 패키지는 무중단 배포나 고가용성을 제공하지 않는다.

## 3. 운영자 생성

기본 관리자나 고정 암호는 없다. 전용 운영자는 Django shell에서 직접 입력하여 만든다. 다음 명령은 터미널을 연결하고 이어지는 Python 코드는 해당 REPL에서 실행한다. 각 단계의 예외가 없음을 확인한다.

```sh
docker compose run --rm web python manage.py shell -i python
```

```python
from getpass import getpass
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
User = get_user_model()
username = input('운영자 ID: ').strip()
password = getpass('새 암호: ')
assert username and password == getpass('새 암호 확인: ')
user = User(username=username, is_staff=True)
validate_password(password, user)
with transaction.atomic():
    user.set_password(password)
    user.save(force_insert=True)
    group, _ = Group.objects.get_or_create(name='공방 운영자')
    group.permissions.add(Permission.objects.get(codename='manage_operations', content_type__app_label='booking'))
    user.groups.add(group)

exit()
```

필요한 경우에만 `docker compose run --rm web python manage.py createsuperuser`로 별도의 비상 관리자를 대화형 생성한다. 일반 운영 계정을 superuser로 만들지 않는다. staging seed는 production에서 실행하지 않는다.

## 4. HTTPS와 도메인 인계

`deploy/nginx.conf.example`은 호스트 nginx `http` 블록에 넣는 예제다. 도메인·인증서 경로·포트를 실제 값으로 맞춘다. 도메인 소유권, DNS A/AAAA, 인증서 발급·자동 갱신, 방화벽의 80/443, nginx 설정 검사와 reload는 승인된 대상 호스트에서 운영자가 수행한다. 인증서가 설치되기 전 이 예제를 활성화하지 않는다. HTTP 예제는 ACME challenge 경로를 제공하지 않으므로 DNS challenge나 별도 승인된 발급 절차를 사용한다.

nginx는 Host와 X-Forwarded-Proto/IP를 덮어쓴다. loopback 앱 포트를 외부에 열거나 추가 proxy를 연결하지 않는다. `LH_TRUST_PROXY=1` 때문에 이 신뢰 경계가 필수다. 공유 호스트의 로컬 사용자·컨테이너도 신뢰할 수 있어야 한다. DB에는 호스트 포트가 없다. 실제 HTTPS origin에서 `/health/`, 로그인/로그아웃, 예약/취소, 운영자 권한, static 파일, cookie 및 CSRF를 확인한 뒤 트래픽을 허용한다. healthcheck는 내부 HTTP+신뢰 헤더로 DB까지 검사할 뿐 TLS나 실도메인 인수를 증명하지 않는다.

## 5. 백업과 복구

백업은 회원·예약 개인정보를 포함한다. 체크아웃 밖의 접근 제한·암호화 저장소를 준비하고 운영 보존 기간/RPO/RTO에 맞춰 예약·관측한다. 실행 예시는 외부 저장소 업로드를 수행하지 않는다. `pg_dump`의 custom 형식은 DB 전체의 일관된 snapshot을 남긴다. 비밀 파일·이미지 digest·코드 버전은 별도로 암호화 보관한다.

```sh
umask 077
export LH_BACKUP_DIR="$HOME/.local/share/littlehands-backups"
mkdir -p "$LH_BACKUP_DIR"
backup_file="$LH_BACKUP_DIR/$(date -u +%Y%m%dT%H%M%SZ).dump"
if docker compose exec -T db pg_dump -U postgres -d littlehands --format=custom > "$backup_file.partial"; then
  mv "$backup_file.partial" "$backup_file"
else
  rm -f "$backup_file.partial"
  false
fi
```

정기 복구 리허설은 운영 DB를 덮어쓰지 않는 별도 DB로 한다. 아래 `littlehands_restore_check`가 이미 존재하면 중단하고 원인을 확인한다. 복구는 실패 즉시 종료한다. 스키마 소유자는 기존 role을 재사용하고 권한은 재적용한다.

```sh
docker compose exec -T db createdb -U postgres -O littlehands_owner littlehands_restore_check
docker compose exec -T db pg_restore -U postgres -d littlehands_restore_check --exit-on-error < "$backup_file"
docker compose exec -T db psql -U postgres -d littlehands_restore_check -v ON_ERROR_STOP=1 < deploy/grants.sql
docker compose run --rm -e LH_DB_NAME=littlehands_restore_check web python manage.py check --database default
docker compose exec -T db psql -U postgres -d littlehands_restore_check -v ON_ERROR_STOP=1 < deploy/verify.sql
```

이 검사는 복구 DB에서만 수행한다. 복구본의 실제 예약·감사 건수와 시점을 백업 기록에 대조하고, 격리된 앱에서 읽기 화면과 예약 불변식을 확인한다. `check`만으로 데이터 복구 인수가 끝나지 않는다. 실제 장애 복구는 웹을 중단하고 기존 DB를 보존한 채 별도 DB에 복원·검증한 뒤 승인된 전환을 수행한다. `down -v`, DB 삭제, 원본 덮어쓰기는 이 절차에 포함하지 않는다.

## 패키지 검증

```sh
python3 -m unittest discover -s tests -p test_deployment.py
```

실도메인 DNS/TLS, 대상 호스트 ACL·재부팅 복구·백업 자동화, 실제 개인정보 보존 정책과 운영 인수는 대상 환경에서 별도 검증한다.
