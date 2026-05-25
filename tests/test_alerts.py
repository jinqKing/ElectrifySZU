from __future__ import annotations

from pathlib import Path

from electrifyszu.subscription.alerts import AlertRunner


def _subscription_values(
    *,
    email: str,
    client: str,
    campus_name: str,
    building_id: str = "7126",
    room_name: str = "713",
) -> dict[str, object]:
    return {
        "email": email,
        "client": client,
        "campus_name": campus_name,
        "building_id": building_id,
        "building_name": "Building A",
        "room_name": room_name,
        "threshold_kwh": 20,
    }


def test_runner_groups_by_client_campus_building_and_room(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SUBSCRIPTIONS_CSV", str(tmp_path / "subscriptions.csv"))
    monkeypatch.setenv("ALERT_MODE", "testing")

    runner = AlertRunner(tmp_path)
    for values in (
        _subscription_values(
            email="a@email.szu.edu.cn",
            client="10.0.0.1",
            campus_name="Campus A",
        ),
        _subscription_values(
            email="b@email.szu.edu.cn",
            client="10.0.0.2",
            campus_name="Campus A",
        ),
        _subscription_values(
            email="c@email.szu.edu.cn",
            client="10.0.0.1",
            campus_name="Campus B",
        ),
    ):
        saved = runner.store.save(values, default_threshold=20)
        runner.store.verify(saved.subscription.verification_token)

    fetch_keys: list[tuple[str, str, str, str]] = []

    def fake_fetch(subscription, *, force=False):
        fetch_keys.append(
            (
                subscription.client,
                subscription.campus_name,
                subscription.building_id,
                subscription.room_name,
            )
        )
        return {
            "remaining": 100.0,
            "room_name": subscription.room_name,
        }

    monkeypatch.setattr(runner, "_fetch_room_data", fake_fetch)

    stats = runner.run_once(skip_recent=False)

    assert stats["checked"] == 3
    assert sorted(fetch_keys) == [
        ("10.0.0.1", "Campus A", "7126", "713"),
        ("10.0.0.1", "Campus B", "7126", "713"),
        ("10.0.0.2", "Campus A", "7126", "713"),
    ]
