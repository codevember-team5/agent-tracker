"""Sincronizzazione con MongoDB"""

import pymongo
from typing import List, Tuple, Dict
from config.settings import Config
from datetime import datetime, timezone
from pymongo import ReturnDocument
from pymongo import DESCENDING


class MongoSyncManager:
    """Gestisce la sincronizzazione con MongoDB"""

    def __init__(self, config: Config, gui_manager=None):
        self.config = config
        self.client = pymongo.MongoClient(config.MONGO_URI)
        self.db = self.client[config.MONGO_DB]
        self.gui = gui_manager
        self._init_indexes()

    def _init_indexes(self):
        """Crea gli indici necessari"""
        self.db[self.config.PROCESS_WINDOW_TABLE].create_index(
            [("device_id", 1), ("process", 1), ("window_title", 1)], unique=True
        )
        self.db[self.config.DEVICES_TABLE].create_index([("device_id", 1)], unique=True)

    def sync_device(self):
        """Sincronizza le informazioni del device"""
        try:
            self.db[self.config.DEVICES_TABLE].update_one(
                {"device_id": self.config.DEVICE_ID},
                {
                    "$setOnInsert": {
                        "device_id": self.config.DEVICE_ID,
                        "system": self.config.SYSTEM,
                        "device_name": self.config.DEVICE_NAME,
                        "user_id": None,
                    }
                },
                upsert=True,
            )
            print(f"[DEVICE SYNC] {self.config.DEVICE_ID}")
        except Exception as e:
            print(f"[DEVICE SYNC ERROR] {e}")

    def close_last_open_activity(self, stop_time):
        last_open = self.db[self.config.ACTIVITY_LOGS_TABLE].find_one(
            {"stop_time": None}, sort=[("start_time", -1)]
        )

        if last_open:
            self.db[self.config.ACTIVITY_LOGS_TABLE].update_one(
                {"_id": last_open["_id"]},
                {"$set": {"stop_time": stop_time}},
            )

    def sync_activities(self, records: List[Tuple]):
        """Sincronizza i record di attività"""
        if not records:
            return

        def parse_ts(ts: str | None):
            if ts is None:
                return None
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))

        docs = [
            {
                "start_time": parse_ts(r[1]),
                "stop_time": parse_ts(r[2]),
                "process": r[3],
                "window_title": r[4],
                "cpu_percent": r[5],
                "device_id": r[7],
                "username": r[8],
            }
            for r in records
        ]

        # Chiudi ultima attività aperta
        self.close_last_open_activity(docs[0]["start_time"])

        # Inserisci attività
        self.db[self.config.ACTIVITY_LOGS_TABLE].insert_many(docs)

        # Aggiorna tabella processi
        for doc in docs:
            try:
                if doc["process"] in self.config.PROCESS_BLACKLIST:
                    continue

                result = self.db[self.config.PROCESS_WINDOW_TABLE].find_one_and_update(
                    {
                        "device_id": doc["device_id"],
                        "process": doc["process"],
                        "window_title": doc["window_title"],
                    },
                    {
                        "$setOnInsert": {
                            "device_id": doc["device_id"],
                            "process": doc["process"],
                            "window_title": doc["window_title"],
                            "level": 5,
                            "active": True,
                        }
                    },
                    upsert=True,
                    return_document=ReturnDocument.AFTER,
                )

                if self.gui:
                    row = len(self.gui.indicators) + 1
                    self.gui.add_process_row(row, result)

            except Exception as e:
                print(f"[PROCESS UPSERT ERROR] {e}")

        print(f"[SYNC] {len(docs)} record sincronizzati")

    def get_process_windows(self) -> List[Dict]:
        """Recupera i processi/finestre dal database"""
        return list(
            self.db[self.config.PROCESS_WINDOW_TABLE].find(
                {
                    "device_id": self.config.DEVICE_ID,
                    "process": {"$not": {"$regex": r"\[PAUSE\]|\[RESUME\]|unknown"}},
                },
                {"_id": 1, "process": 1, "window_title": 1, "level": 1},
            )
        )

    def update_level(self, voce_id, level: int):
        """Aggiorna il livello di attenzione"""
        try:
            result = self.db[self.config.PROCESS_WINDOW_TABLE].update_one(
                {"_id": voce_id}, {"$set": {"level": level}}
            )
            if result.modified_count:
                print(f"✅ Aggiornato {voce_id} → level {level}")
        except Exception as e:
            print(f"[SET LEVEL ERROR] {e}")
