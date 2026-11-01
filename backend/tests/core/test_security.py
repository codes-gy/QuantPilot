from app.core.security import hash_password, verify_password


def test_password_hash_roundtrip():
    # passlib/bcrypt 버전이 어긋나면 해시 생성 자체가 실패해 계정 생성이 막힌다 (bcrypt 5.x).
    hashed = hash_password("correct horse battery")
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong password", hashed)
