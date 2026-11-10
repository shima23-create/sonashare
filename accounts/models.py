from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, user_name, password=None, **extra_fields):
        if not email:
            raise ValueError("メールアドレスは必須です")

        email = self.normalize_email(email)
        user = self.model(email=email, user_name=user_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, user_name, password=None, **extra_fields):
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, user_name, password, **extra_fields)

    def create_superuser(self, email, user_name, password=None, **extra_fields):
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, user_name, password, **extra_fields)


class User(AbstractBaseUser):
    # ユーザーID
    user_id = models.AutoField(primary_key=True)
    # ユーザー名
    user_name = models.CharField(max_length=50)
    # メールアドレス
    email = models.EmailField(max_length=50, unique=True)
    # パスワードハッシュ
    password = models.CharField(max_length=255, db_column="password_hash")
    # アカウント有効状態
    is_active = models.BooleanField(default=True)
    # 登録日時
    created_at = models.DateTimeField(auto_now_add=True)
    # 更新日時
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["user_name"]

    class Meta:
        db_table = "user"
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー一覧"

    def __str__(self):
        return self.user_name
