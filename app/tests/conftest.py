import pytest
from fastapi.testclient import TestClient
from sklearn.datasets import load_digits

from main import create_app
from train import train


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory):
    directory = tmp_path_factory.mktemp("model")
    train(directory, model_version="test")
    return directory


@pytest.fixture(scope="session")
def client(model_dir):
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("MODEL_DIR", str(model_dir))
        with TestClient(create_app(), follow_redirects=False) as test_client:
            yield test_client


@pytest.fixture(scope="session")
def digits():
    return load_digits()
