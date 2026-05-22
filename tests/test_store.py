"""测试 subscription_alerts/store.py 的订阅存储逻辑（离线，不依赖校园网）。"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from subscription_alerts.store import (
    SubscriptionStore,
    build_subscription,
)


class TestBuildSubscription:
    def test_invalid_email_raises(self) -> None:
        with pytest.raises(ValueError, match="邮箱"):
            build_subscription({"email": "not-an-email"}, 20)

    def test_missing_room_name_raises(self) -> None:
        with pytest.raises(ValueError, match="房间号"):
            build_subscription(
                {
                    "email": "test@email.szu.edu.cn",
                    "client": "192.168.1.1",
                    "campus_name": "粤海",
                    "building_id": "7126",
                    "building_name": "风槐斋",
                    # room_name intentionally missing
                },
                20,
            )

    def test_zero_threshold_raises(self) -> None:
        with pytest.raises(ValueError, match="阈值"):
            build_subscription(
                {
                    "email": "test@email.szu.edu.cn",
                    "client": "192.168.1.1",
                    "campus_name": "粤海",
                    "building_id": "7126",
                    "building_name": "风槐斋",
                    "room_name": "713",
                    "threshold_kwh": "0",
                },
                20,
            )

    def test_valid_subscription_built(self) -> None:
        sub = build_subscription(
            {
                "email": "test@email.szu.edu.cn",
                "client": "192.168.1.1",
                "campus_name": "粤海",
                "building_id": "7126",
                "building_name": "风槐斋",
                "room_name": "713",
            },
            20,
        )
        assert sub.email == "test@email.szu.edu.cn"
        assert sub.room_name == "713"
        assert sub.threshold_kwh == 20
        assert sub.verification_token
        assert sub.unsubscribe_token
        assert not sub.verified


class TestStoreSaveAndVerify:
    def test_save_creates_pending_subscription(self, temp_csv_path: Path) -> None:
        fixed_temp_path = temp_csv_path.with_suffix(".tmp")
        fixed_temp_path.write_text("sentinel", encoding="utf-8")
        store = SubscriptionStore(temp_csv_path)
        result = store.save(
            {
                "email": "test@email.szu.edu.cn",
                "client": "192.168.1.1",
                "campus_name": "粤海",
                "building_id": "7126",
                "building_name": "风槐斋",
                "room_name": "713",
            },
            default_threshold=20,
        )
        assert result.status == "pending_verification"
        assert result.verification_required is True
        assert result.subscription.email == "test@email.szu.edu.cn"
        # CSV 文件应已写入
        assert temp_csv_path.is_file()
        assert fixed_temp_path.read_text(encoding="utf-8") == "sentinel"

    def test_verify_activates_subscription(self, temp_csv_path: Path) -> None:
        store = SubscriptionStore(temp_csv_path)
        saved = store.save(
            {
                "email": "verify@email.szu.edu.cn",
                "client": "192.168.1.1",
                "campus_name": "粤海",
                "building_id": "7126",
                "building_name": "风槐斋",
                "room_name": "713",
            },
            default_threshold=20,
        )
        token = saved.subscription.verification_token
        assert token

        status, sub = store.verify(token)
        assert status == "verified"
        assert sub is not None
        assert sub.is_active

    def test_verify_invalid_token_returns_invalid(self, temp_csv_path: Path) -> None:
        store = SubscriptionStore(temp_csv_path)
        status, sub = store.verify("bogus-token")
        assert status == "invalid"
        assert sub is None

    def test_verify_expired_token_clears_token_and_saves(
        self, temp_csv_path: Path
    ) -> None:
        store = SubscriptionStore(temp_csv_path)
        saved = store.save(
            {
                "email": "expired@email.szu.edu.cn",
                "client": "192.168.1.1",
                "campus_name": "Campus A",
                "building_id": "7126",
                "building_name": "Building A",
                "room_name": "713",
            },
            default_threshold=20,
        )
        token = saved.subscription.verification_token
        rows = store.list_all()
        rows[0].verification_token_expires_at = (
            datetime.now() - timedelta(minutes=1)
        ).isoformat()
        store._write(rows)

        status, sub = store.verify(token)

        assert status == "expired"
        assert sub is None
        expired = store.list_all()[0]
        assert expired.verification_token == ""
        assert expired.verification_token_expires_at == ""
        assert expired.verified is False

    def test_duplicate_save_keeps_existing_active(self, temp_csv_path: Path) -> None:
        store = SubscriptionStore(temp_csv_path)
        # First save + verify
        saved = store.save(
            {
                "email": "dup@email.szu.edu.cn",
                "client": "192.168.1.1",
                "campus_name": "粤海",
                "building_id": "7126",
                "building_name": "风槐斋",
                "room_name": "713",
            },
            default_threshold=20,
        )
        store.verify(saved.subscription.verification_token)

        # Second save with same key
        result2 = store.save(
            {
                "email": "dup@email.szu.edu.cn",
                "client": "192.168.1.1",
                "campus_name": "粤海",
                "building_id": "7126",
                "building_name": "风槐斋",
                "room_name": "713",
            },
            default_threshold=30,
        )
        assert result2.status == "active"
        assert result2.subscription.threshold_kwh == 30
        assert result2.subscription.is_active


class TestStoreUnsubscribe:
    def test_unsubscribe_disables_subscription(self, temp_csv_path: Path) -> None:
        store = SubscriptionStore(temp_csv_path)
        saved = store.save(
            {
                "email": "unsub@email.szu.edu.cn",
                "client": "192.168.1.1",
                "campus_name": "粤海",
                "building_id": "7126",
                "building_name": "风槐斋",
                "room_name": "713",
            },
            default_threshold=20,
        )
        store.verify(saved.subscription.verification_token)

        # 此时应出现在 enabled 列表中
        assert len(store.list_enabled()) == 1

        # 退订
        status, sub = store.unsubscribe(saved.subscription.unsubscribe_token)
        assert status == "unsubscribed"
        assert sub is not None
        assert sub.enabled is False

        # 不再出现在 enabled 列表
        assert len(store.list_enabled()) == 0

    def test_unsubscribe_bogus_token(self, temp_csv_path: Path) -> None:
        store = SubscriptionStore(temp_csv_path)
        status, sub = store.unsubscribe("bogus")
        assert status == "invalid"
        assert sub is None
