from __future__ import annotations

from ntb_marimo_console.runtime_profiles import list_runtime_profiles


def main() -> None:
    for profile in list_runtime_profiles():
        adapter_text = profile.default_model_adapter_ref or "n/a"
        print(
            f"{profile.profile_id}\tmode={profile.runtime_mode}\tcontract={profile.contract}\t"
            f"session_date={profile.session_date}\tadapter={adapter_text}"
        )


if __name__ == "__main__":
    main()
