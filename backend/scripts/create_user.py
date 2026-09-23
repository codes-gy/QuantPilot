"""단일 사용자 계정을 생성하는 CLI 스크립트.

QuantPilot은 개인용 프로젝트라 공개 회원가입 엔드포인트를 두지 않는다 — 계정은
운영자(본인)만 이 스크립트로 한 번 생성한다. 이메일이 이미 존재하면 비밀번호만 갱신한다.

실행 (컨테이너 안에서):
    docker compose exec api python -m scripts.create_user user@example.com

또는 로컬 가상환경에서:
    cd backend && python -m scripts.create_user user@example.com
"""

import argparse
import asyncio
import getpass

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.features.account.repository import SqlAlchemyUserRepository
from app.features.account.service import AccountService


async def _create_or_update_user(email: str, password: str) -> None:
    async with AsyncSessionLocal() as db:
        repo = SqlAlchemyUserRepository(db)
        service = AccountService(repo)
        existing = await repo.get_by_email(email)
        if existing is not None:
            existing.hashed_password = hash_password(password)
            await db.commit()
            print(f"기존 사용자 비밀번호 갱신 완료: {email}")
            return

        await service.create_user(email, password)
        print(f"사용자 생성 완료: {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantPilot 사용자 계정 생성/갱신")
    parser.add_argument("email", help="로그인에 사용할 이메일")
    args = parser.parse_args()

    password = getpass.getpass("비밀번호: ")
    confirm = getpass.getpass("비밀번호 확인: ")
    if password != confirm:
        raise SystemExit("비밀번호가 일치하지 않습니다.")
    if len(password) < 8:
        raise SystemExit("비밀번호는 8자 이상이어야 합니다.")

    asyncio.run(_create_or_update_user(args.email, password))


if __name__ == "__main__":
    main()
