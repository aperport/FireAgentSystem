"""
JSON 持久化工具单元测试（json_save.py）

测试覆盖：
    1. save_json() 覆盖写入
    2. load_json() 读取
    3. append_json_item() 追加（含文件不存在时自动初始化的分支）
"""

import json
import os

import pytest

from graph_rag import json_save

pytestmark = pytest.mark.asyncio


class TestJsonSave:
    """save_json / load_json 写入与读取测试"""

    async def test_save_and_load_roundtrip(self, tmp_path):
        dir_name = str(tmp_path) + os.sep
        data = {"query": "查询B栋3层烟感设备状态", "result": [1, 2, 3]}
        await json_save.save_json(data, dir_name=dir_name, file_name="T")
        # 找到写入的文件
        files = list(tmp_path.glob("T*.json"))
        assert len(files) == 1
        loaded = await json_save.load_json(str(files[0]))
        assert loaded == data

    async def test_save_default_dir_when_no_dir(self, tmp_path, monkeypatch):
        """未指定 dir_name 时写入 ./data/ 目录"""
        monkeypatch.chdir(tmp_path)
        await json_save.save_json({"a": 1})
        assert (tmp_path / "data").exists()

    async def test_save_overwrites_existing_file(self, tmp_path):
        dir_name = str(tmp_path) + os.sep
        await json_save.save_json({"v": 1}, dir_name=dir_name, file_name="T")
        await json_save.save_json({"v": 2}, dir_name=dir_name, file_name="T")
        files = list(tmp_path.glob("T*.json"))
        assert len(files) == 1
        loaded = await json_save.load_json(str(files[0]))
        assert loaded == {"v": 2}

    async def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            await json_save.load_json(str(tmp_path / "not_exist.json"))


class TestAppendJsonItem:
    """append_json_item 追加写入测试"""

    async def test_append_creates_new_file(self, tmp_path):
        dir_name = str(tmp_path) + os.sep
        await json_save.append_json_item(dir_name, {"q": "first"}, "T")
        files = list(tmp_path.glob("T*.json"))
        assert len(files) == 1
        loaded = await json_save.load_json(str(files[0]))
        assert loaded == [{"q": "first"}]

    async def test_append_to_existing_file(self, tmp_path):
        dir_name = str(tmp_path) + os.sep
        await json_save.append_json_item(dir_name, {"q": "first"}, "T")
        await json_save.append_json_item(dir_name, {"q": "second"}, "T")
        files = list(tmp_path.glob("T*.json"))
        assert len(files) == 1
        loaded = await json_save.load_json(str(files[0]))
        assert len(loaded) == 2
        assert loaded[1] == {"q": "second"}

    async def test_append_preserves_existing_items(self, tmp_path):
        dir_name = str(tmp_path) + os.sep
        # 预置当天日期的文件
        from datetime import datetime

        today = datetime.now().strftime("%Y%m%d")
        file_name = f"T{today}.json"
        file_path = dir_name + file_name
        os.makedirs(tmp_path, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump([{"old": True}], f)
        await json_save.append_json_item(dir_name, {"new": True}, "T")
        loaded = await json_save.load_json(file_path)
        assert loaded == [{"old": True}, {"new": True}]
