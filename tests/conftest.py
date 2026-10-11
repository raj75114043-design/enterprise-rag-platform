import os
import shutil
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp()
shutil.copytree(Path(__file__).resolve().parents[1] / "corpus", Path(_tmp) / "corpus")
os.environ.update({"DATABASE_URL": f"sqlite:///{_tmp}/test.db", "CORPUS_DIR": f"{_tmp}/corpus", "LLM_PROVIDER": "none",
                   "API_KEYS": "op:operator,an:qa_analyst,hd:qa_head"})


@pytest.fixture(scope="session")
def container():
    from ragp.pipeline import get_container
    return get_container()


@pytest.fixture(scope="session")
def corpus_dir():
    return Path(_tmp) / "corpus"
