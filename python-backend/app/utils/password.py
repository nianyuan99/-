"""
密码加密工具
"""

import hashlib

SALT = "yupi"


def encrypt_password(password: str) -> str:
    """
    密码加密（MD5 + 盐值）

    注意：Python 版拼接顺序是 password + SALT，与 Java 版（SALT + password）不同
    """
    salted_password = password + SALT
    return hashlib.md5(salted_password.encode("utf-8")).hexdigest()
