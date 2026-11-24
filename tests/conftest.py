import pytest

import config


@pytest.fixture(scope="session", autouse=True)
def isolate_app_data(tmp_path_factory):
    app_data = tmp_path_factory.mktemp("dayflow")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(config, "APP_DATA_DIR", app_data)
        patch.setattr(config, "DATABASE_PATH", app_data / "dayflow.db")
        patch.setattr(config, "CHUNKS_DIR", app_data / "chunks")
        config.ensure_directories()
        yield
