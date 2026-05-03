"""
================================================================================
درع الأرض (Earth Shield) — Defensethon Project
نظام البلاطة الذكية للكشف عن التهديدات الأمنية
================================================================================

7 حساسات + Cosine Similarity + SQLite + AI Report
"""
import json
import asyncio
import logging
import random
import sqlite3
import time
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import deque, Counter
from typing import Dict, List, Set, Tuple

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("defensethon")

DASHBOARD_PATH = Path(__file__).parent.parent / "dashboard" / "index.html"
DB_PATH = Path(__file__).parent / "events.db"

CONFIDENCE_THREAT = 0.85
CONFIDENCE_SUSPICIOUS = 0.50
SENSOR_FUSION_MIN = 1
SENSOR_ELEVATED_THRESHOLD = 0.6

# ============================================================================
# Riyadh Strategic Hubs — مراكز التحكم الإقليمية في الرياض
# Each hub represents a regional command center supervising a wider local network
# ============================================================================
SITE_LAYOUT = [
    {"id": "TILE-S01", "name": "مطار الملك خالد الدولي", "x": 50, "y": 10, "zone": "airport"},
    {"id": "TILE-S02", "name": "المدينة الرقمية", "x": 30, "y": 35, "zone": "tech"},
    {"id": "TILE-K01", "name": "المدينة المالية (KAFD)", "x": 35, "y": 30, "zone": "financial"},
    {"id": "TILE-D01", "name": "حي السفارات", "x": 20, "y": 50, "zone": "diplomatic"},
    {"id": "TILE-M01", "name": "محطة قطار سار", "x": 65, "y": 25, "zone": "metro"},
    {"id": "TILE-V01", "name": "استاد الملك فهد الدولي", "x": 80, "y": 30, "zone": "venue"},
    {"id": "TILE-B01", "name": "البوليفارد سيتي", "x": 40, "y": 32, "zone": "entertainment"},
    {"id": "TILE-H01", "name": "المستشفى التخصصي", "x": 50, "y": 60, "zone": "hospital"},
    {"id": "TILE-G02", "name": "وزارة الداخلية", "x": 55, "y": 65, "zone": "government"},
    {"id": "TILE-P01", "name": "حديقة الملك سلمان", "x": 60, "y": 55, "zone": "park"},
    {"id": "TILE-G01", "name": "قصر الحكم", "x": 65, "y": 80, "zone": "royal"},
    {"id": "TILE-H02", "name": "مستشفى قوى الأمن", "x": 70, "y": 60, "zone": "hospital"},
    {"id": "TILE-H03", "name": "مستشفى الأمير سلطان الطبي", "x": 58, "y": 58, "zone": "hospital"},
]

# ============================================================================
# THREAT SIGNATURES
# ============================================================================
THREAT_SIGNATURES = {
    "EXPLOSIVE": {
        "name_ar": "مادة متفجرة",
        "vector": [0.05, 0.95, 0.20, 0.10, 0.05, 0.70, 0.10],
        "color": "#ef4444",
        "icon": "💥",
    },
    "WEAPON": {
        "name_ar": "سلاح ناري",
        "vector": [0.10, 0.15, 0.05, 0.05, 0.05, 0.92, 0.30],
        "color": "#f97316",
        "icon": "🔫",
    },
    "NARCOTIC": {
        "name_ar": "مخدرات",
        "vector": [0.05, 0.20, 0.15, 0.90, 0.30, 0.10, 0.05],
        "color": "#a855f7",
        "icon": "💊",
    },
    "TOXIC_GAS": {
        "name_ar": "غاز سام",
        "vector": [0.05, 0.10, 0.92, 0.10, 0.10, 0.05, 0.05],
        "color": "#eab308",
        "icon": "☣️",
    },
    "ALCOHOL": {
        "name_ar": "كحول ممنوع",
        "vector": [0.05, 0.05, 0.20, 0.10, 0.90, 0.05, 0.05],
        "color": "#ec4899",
        "icon": "🍷",
    },
    "INTRUSION": {
        "name_ar": "تسلل / اختراق",
        "vector": [0.85, 0.05, 0.05, 0.05, 0.05, 0.30, 0.75],
        "color": "#06b6d4",
        "icon": "🚨",
    },
    "VEHICLE": {
        "name_ar": "مركبة ثقيلة",
        "vector": [0.90, 0.05, 0.05, 0.05, 0.05, 0.60, 0.65],
        "color": "#3b82f6",
        "icon": "🚛",
    },
    "FOOTSTEP": {
        "name_ar": "خطوات إنسان",
        "vector": [0.55, 0.05, 0.10, 0.05, 0.10, 0.10, 0.45],
        "color": "#10b981",
        "icon": "🚶",
    },
    "NORMAL": {
        "name_ar": "طبيعي",
        "vector": [0.10, 0.05, 0.10, 0.05, 0.05, 0.10, 0.15],
        "color": "#10b981",
        "icon": "✓",
    },
}

# ============================================================================
# SCENARIO PROFILES (active+noise pattern)
# ============================================================================
SCENARIOS = {
    "normal": {
        "name_ar": "نشاط طبيعي",
        "active": {"vibration": (0.05, 0.15)},
    },
    "footstep": {
        "name_ar": "خطوات إنسان",
        "active": {"vibration": (0.45, 0.65), "acoustic": (0.35, 0.55)},
    },
    "vehicle": {
        "name_ar": "مركبة ثقيلة",
        "active": {"vibration": (0.80, 0.95), "metal_em": (0.50, 0.70), "acoustic": (0.55, 0.75)},
    },
    "explosive": {
        "name_ar": "🚨 مادة متفجرة",
        "active": {"explosive": (0.85, 1.00), "metal_em": (0.50, 0.80), "vibration": (0.0, 0.15)},
    },
    "weapon": {
        "name_ar": "🚨 سلاح ناري",
        "active": {"metal_em": (0.85, 1.00), "vibration": (0.10, 0.25), "acoustic": (0.15, 0.30)},
    },
    "narcotic": {
        "name_ar": "🚨 مخدرات",
        "active": {"narcotic": (0.85, 1.00), "alcohol": (0.20, 0.40)},
    },
    "toxic_gas": {
        "name_ar": "🚨 غاز سام",
        "active": {"toxic_gas": (0.85, 1.00)},
    },
    "alcohol": {
        "name_ar": "🚨 كحول ممنوع",
        "active": {"alcohol": (0.85, 1.00)},
    },
    "intrusion": {
        "name_ar": "🚨 تسلل / اختراق",
        "active": {"vibration": (0.75, 0.95), "acoustic": (0.65, 0.90), "metal_em": (0.20, 0.40)},
    },
}

SENSOR_NAMES_AR = {
    "vibration": "الاهتزاز",
    "explosive": "المتفجرات",
    "toxic_gas": "الغازات السامة",
    "narcotic":  "المواد المخدرة",
    "alcohol":   "الكحول",
    "metal_em":  "المعادن/كهرومغناطيسي",
    "acoustic":  "البصمة الصوتية",
}
SENSOR_NAMES_EN = {
    "vibration": "Vibration",
    "explosive": "Explosive",
    "toxic_gas": "Toxic Gas",
    "narcotic":  "Narcotic",
    "alcohol":   "Alcohol",
    "metal_em":  "Metal/EM",
    "acoustic":  "Acoustic",
}
SENSOR_ORDER = ["vibration", "explosive", "toxic_gas", "narcotic",
                "alcohol", "metal_em", "acoustic"]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    a = np.array(v1)
    b = np.array(v2)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm < 1e-9:
        return 0.0
    return float(np.dot(a, b) / norm)


def classify_reading(sensor_values: Dict[str, float]) -> Dict:
    reading_vector = [sensor_values[s] for s in SENSOR_ORDER]
    similarities = {}
    for threat_type, sig in THREAT_SIGNATURES.items():
        sim = cosine_similarity(reading_vector, sig["vector"])
        similarities[threat_type] = round(sim, 4)

    best = max(similarities.items(), key=lambda x: x[1])
    best_type = best[0]
    confidence = best[1]

    elevated_sensors = [s for s in SENSOR_ORDER
                        if sensor_values[s] > SENSOR_ELEVATED_THRESHOLD]

    is_threat_signature = best_type in ["EXPLOSIVE", "WEAPON", "NARCOTIC",
                                          "TOXIC_GAS", "ALCOHOL", "INTRUSION"]

    if is_threat_signature and confidence >= CONFIDENCE_THREAT and len(elevated_sensors) >= SENSOR_FUSION_MIN:
        classification = "THREAT"
    elif is_threat_signature and confidence >= CONFIDENCE_SUSPICIOUS:
        classification = "SUSPICIOUS"
    else:
        classification = "NORMAL"

    return {
        "threat_type": best_type,
        "confidence": confidence,
        "classification": classification,
        "all_similarities": similarities,
        "elevated_sensors": elevated_sensors,
        "fusion_count": len(elevated_sensors),
    }


# ============================================================================
# SQLite
# ============================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tile_id TEXT NOT NULL,
            tile_name TEXT,
            zone TEXT,
            timestamp TEXT NOT NULL,
            classification TEXT NOT NULL,
            threat_type TEXT,
            confidence REAL,
            vibration REAL, explosive REAL, toxic_gas REAL,
            narcotic REAL, alcohol REAL, metal_em REAL, acoustic REAL,
            elevated_sensors TEXT,
            fusion_count INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_health (
            tile_id TEXT NOT NULL,
            sensor TEXT NOT NULL,
            status TEXT,
            last_check TEXT,
            PRIMARY KEY (tile_id, sensor)
        )
    """)
    conn.commit()
    conn.close()


def db_log_event(tile, reading, classification_result):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO events (
                tile_id, tile_name, zone, timestamp,
                classification, threat_type, confidence,
                vibration, explosive, toxic_gas, narcotic,
                alcohol, metal_em, acoustic,
                elevated_sensors, fusion_count
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            tile["id"], tile["name"], tile["zone"],
            datetime.now(timezone.utc).isoformat(),
            classification_result["classification"],
            classification_result["threat_type"],
            classification_result["confidence"],
            reading["vibration"], reading["explosive"],
            reading["toxic_gas"], reading["narcotic"],
            reading["alcohol"], reading["metal_em"], reading["acoustic"],
            ",".join(classification_result["elevated_sensors"]),
            classification_result["fusion_count"],
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"DB log error: {e}")


def db_get_analytics():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM events")
        total_events = c.fetchone()[0]
        c.execute("""SELECT classification, COUNT(*) FROM events
                     GROUP BY classification""")
        by_class = dict(c.fetchall())
        c.execute("""SELECT threat_type, COUNT(*) FROM events
                     WHERE classification IN ('THREAT', 'SUSPICIOUS')
                     GROUP BY threat_type ORDER BY COUNT(*) DESC""")
        by_threat = c.fetchall()
        c.execute("""SELECT zone, tile_name, COUNT(*) FROM events
                     WHERE classification = 'THREAT'
                     GROUP BY zone, tile_name ORDER BY COUNT(*) DESC LIMIT 5""")
        hotspots = c.fetchall()
        c.execute("""SELECT timestamp, tile_name, threat_type, confidence
                     FROM events WHERE classification = 'THREAT'
                     ORDER BY id DESC LIMIT 10""")
        recent_threats = c.fetchall()
        conn.close()
        return {
            "total_events": total_events,
            "by_classification": by_class,
            "by_threat_type": [{"type": t, "count": c} for t, c in by_threat],
            "hotspots": [{"zone": z, "tile": t, "count": c} for z, t, c in hotspots],
            "recent_threats": [
                {"timestamp": ts, "tile": tn, "type": tt, "confidence": round(cf, 2)}
                for ts, tn, tt, cf in recent_threats
            ],
        }
    except Exception as e:
        log.error(f"DB analytics error: {e}")
        return {"error": str(e)}


def db_get_heatmap_data():
    """عدد التهديدات لكل بلاطة - للخريطة الحرارية"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT tile_id, COUNT(*) FROM events
                     WHERE classification = 'THREAT'
                     GROUP BY tile_id""")
        result = dict(c.fetchall())
        conn.close()
        return result
    except Exception as e:
        return {}


def generate_ai_report():
    """تقرير AI ديناميكي - يحلل الوضع الحالي ويعطي توصيات"""
    try:
        analytics = db_get_analytics()
        total = analytics.get("total_events", 0)
        by_class = analytics.get("by_classification", {})
        threats_count = by_class.get("THREAT", 0)
        suspicious_count = by_class.get("SUSPICIOUS", 0)
        normal_count = by_class.get("NORMAL", 0)

        threat_pct = (threats_count / total * 100) if total else 0
        susp_pct = (suspicious_count / total * 100) if total else 0

        # تحديد مستوى التهديد
        if threat_pct > 5:
            risk_level = "حرج (CRITICAL)"
            risk_color = "#ef4444"
            risk_emoji = "🔴"
        elif threat_pct > 1:
            risk_level = "مرتفع (HIGH)"
            risk_color = "#f97316"
            risk_emoji = "🟠"
        elif susp_pct > 5:
            risk_level = "متوسط (MEDIUM)"
            risk_color = "#eab308"
            risk_emoji = "🟡"
        else:
            risk_level = "منخفض (LOW)"
            risk_color = "#10b981"
            risk_emoji = "🟢"

        # أكثر تهديد متكرر
        by_threat = analytics.get("by_threat_type", [])
        top_threat = by_threat[0] if by_threat else None
        top_threat_name = ""
        if top_threat:
            sig = THREAT_SIGNATURES.get(top_threat["type"], {})
            top_threat_name = sig.get("name_ar", top_threat["type"])

        # نقطة الضعف الأكثر تعرضاً
        hotspots = analytics.get("hotspots", [])
        weakest_point = hotspots[0] if hotspots else None

        # توصيات ذكية
        recommendations = []
        if threats_count > 50:
            recommendations.append("⚠️ زيادة كثافة الدوريات الأمنية في المناطق الحرجة")
            recommendations.append("📡 تفعيل بروتوكول الاستجابة السريعة")
        if top_threat and top_threat["type"] == "EXPLOSIVE":
            recommendations.append("🐕 نشر فرق كلاب الكشف عن المتفجرات")
            recommendations.append("🚧 تكثيف نقاط التفتيش بأجهزة ETD")
        if top_threat and top_threat["type"] == "WEAPON":
            recommendations.append("🔍 تعزيز أجهزة كشف المعادن")
            recommendations.append("📹 مراجعة كاميرات المراقبة في النقاط الحرجة")
        if top_threat and top_threat["type"] == "NARCOTIC":
            recommendations.append("🐕 نشر كلاب كشف المخدرات في الأمتعة")
            recommendations.append("📦 تكثيف فحص الشحنات الواردة")
        if top_threat and top_threat["type"] == "TOXIC_GAS":
            recommendations.append("💨 فحص أنظمة التهوية والصيانة الدورية")
            recommendations.append("🚨 تجهيز فرق الدفاع المدني للاستجابة")
        if weakest_point:
            recommendations.append(f"📍 تركيز موارد إضافية على: {weakest_point['tile']}")
        if not recommendations:
            recommendations.append("✅ الوضع مستقر - الاستمرار في المراقبة الاعتيادية")

        # حساب فعالية النظام
        if total > 0:
            detection_rate = ((threats_count + suspicious_count) / total * 100)
        else:
            detection_rate = 0

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "risk_level": risk_level,
            "risk_color": risk_color,
            "risk_emoji": risk_emoji,
            "summary": {
                "total_events": total,
                "threats": threats_count,
                "suspicious": suspicious_count,
                "normal": normal_count,
                "threat_percentage": round(threat_pct, 2),
                "suspicious_percentage": round(susp_pct, 2),
                "detection_rate": round(detection_rate, 2),
            },
            "top_threat": {
                "type": top_threat["type"] if top_threat else None,
                "name_ar": top_threat_name,
                "count": top_threat["count"] if top_threat else 0,
            },
            "weakest_point": weakest_point,
            "recommendations": recommendations,
            "narrative": generate_narrative(total, threats_count, suspicious_count,
                                              top_threat_name, weakest_point, risk_level),
        }
    except Exception as e:
        log.error(f"AI report error: {e}")
        return {"error": str(e)}


def generate_narrative(total, threats, suspicious, top_threat_name, weakest_point, risk_level):
    """ملخص نصي ديناميكي يشبه تقارير المحللين"""
    parts = []
    parts.append(f"تحليل الوضع الأمني الحالي - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    parts.append("")
    parts.append(f"رصد النظام إجمالي {total:,} حدث أمني عبر شبكة البلاطات الذكية في الرياض، "
                 f"منها {threats:,} تهديد مؤكد و{suspicious:,} حالة مشبوهة.")
    parts.append("")
    parts.append(f"مستوى التهديد العام: {risk_level}")

    if top_threat_name and threats > 0:
        parts.append(f"النمط الأكثر تكراراً: {top_threat_name}، مما يشير إلى نشاط غير اعتيادي "
                     f"يستوجب مراجعة بروتوكولات المواجهة.")

    if weakest_point:
        parts.append(f"النقطة الأكثر تعرضاً للتهديدات: {weakest_point['tile']} "
                     f"بإجمالي {weakest_point['count']} حادثة، مما يستدعي تركيز الموارد الأمنية فيها.")

    parts.append("")
    parts.append("النظام يعمل بكفاءة عالية باستخدام تقنية Cosine Similarity مع 7 حساسات متخصصة، "
                 "ويتم توثيق كل حدث في قاعدة بيانات SQLite لأغراض التحليل والمراجعة.")

    return "\n".join(parts)


# ============================================================================
# Reading Generator
# ============================================================================
def rand(low, high):
    return max(0.0, min(1.0,
        random.uniform(low, high) + random.gauss(0, (high - low) * 0.04)))


def generate_reading(scenario: str) -> Dict[str, float]:
    p = SCENARIOS[scenario]
    active = p.get("active", {})
    reading = {}
    for sensor in SENSOR_ORDER:
        if sensor in active:
            lo, hi = active[sensor]
            reading[sensor] = round(rand(lo, hi), 3)
        else:
            reading[sensor] = round(random.uniform(0.0, 0.05), 3)
    return reading


def sensor_self_check(tile_id: str) -> Dict[str, str]:
    statuses = {}
    for s in SENSOR_ORDER:
        r = random.random()
        if r > 0.99:
            statuses[s] = "FAULT"
        elif r > 0.96:
            statuses[s] = "WARNING"
        else:
            statuses[s] = "OK"
    return statuses


# ============================================================================
# State
# ============================================================================
class State:
    def __init__(self):
        self.tiles: Dict[str, dict] = {}
        self.tile_scenarios: Dict[str, str] = {t["id"]: "normal" for t in SITE_LAYOUT}
        self.alerts: deque = deque(maxlen=100)
        self.clients: Set[WebSocket] = set()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.stats = {
            "total_readings": 0,
            "total_alerts": 0,
            "threats": 0,
            "suspicious": 0,
        }
        for t in SITE_LAYOUT:
            self.tiles[t["id"]] = {
                **t,
                "scenario": "normal",
                "classification": "NORMAL",
                "threat_type": "NORMAL",
                "confidence": 0.0,
                "sensors": {s: 0.1 for s in SENSOR_ORDER},
                "elevated_sensors": [],
                "fusion_count": 0,
                "sensor_health": {s: "OK" for s in SENSOR_ORDER},
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }

state = State()


async def simulation_loop():
    health_counter = 0
    while True:
        try:
            for tile_meta in SITE_LAYOUT:
                tile_id = tile_meta["id"]
                scenario = state.tile_scenarios[tile_id]
                reading = generate_reading(scenario)
                cls_result = classify_reading(reading)

                ts = datetime.now(timezone.utc).isoformat()
                state.stats["total_readings"] += 1

                state.tiles[tile_id].update({
                    "scenario": scenario,
                    "classification": cls_result["classification"],
                    "threat_type": cls_result["threat_type"],
                    "confidence": cls_result["confidence"],
                    "sensors": reading,
                    "elevated_sensors": cls_result["elevated_sensors"],
                    "fusion_count": cls_result["fusion_count"],
                    "last_seen": ts,
                })

                if cls_result["classification"] != "NORMAL":
                    db_log_event(tile_meta, reading, cls_result)
                    alert = {
                        "alert_id": f"ALT-{int(time.time()*1000)}-{random.randint(100,999)}",
                        "tile_id": tile_id,
                        "tile_name": tile_meta["name"],
                        "zone": tile_meta["zone"],
                        "timestamp": ts,
                        "classification": cls_result["classification"],
                        "threat_type": cls_result["threat_type"],
                        "confidence": cls_result["confidence"],
                        "elevated_sensors": cls_result["elevated_sensors"],
                        "sensors": reading,
                    }
                    state.alerts.append(alert)
                    state.stats["total_alerts"] += 1
                    if cls_result["classification"] == "THREAT":
                        state.stats["threats"] += 1
                    else:
                        state.stats["suspicious"] += 1
                    try:
                        state.queue.put_nowait({"type": "alert", "data": alert})
                    except asyncio.QueueFull:
                        pass

                try:
                    state.queue.put_nowait({"type": "tile_update",
                                             "data": state.tiles[tile_id]})
                except asyncio.QueueFull:
                    pass

            health_counter += 1
            if health_counter % 20 == 0:
                for tile_meta in SITE_LAYOUT:
                    state.tiles[tile_meta["id"]]["sensor_health"] = sensor_self_check(tile_meta["id"])

            await asyncio.sleep(0.6)
        except Exception as e:
            log.error(f"sim error: {e}")
            await asyncio.sleep(1)


# ============================================================================
# FastAPI app
# ============================================================================
app = FastAPI(title="Defensethon — Earth Shield", version="4.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root():
    if DASHBOARD_PATH.exists():
        return FileResponse(DASHBOARD_PATH)
    return {"service": "Earth Shield", "status": "ok"}


@app.get("/api/scenarios")
async def get_scenarios():
    return {k: {"name_ar": v.get("name_ar", k)} for k, v in SCENARIOS.items()}


@app.get("/api/threats")
async def get_threats():
    return {k: {"name_ar": v["name_ar"], "icon": v["icon"], "color": v["color"]}
            for k, v in THREAT_SIGNATURES.items()}


@app.get("/api/sensor_meta")
async def get_sensor_meta():
    return {
        "order": SENSOR_ORDER,
        "names_ar": SENSOR_NAMES_AR,
        "names_en": SENSOR_NAMES_EN,
    }


@app.post("/api/tile/{tile_id}/scenario/{scenario}")
async def set_tile_scenario(tile_id: str, scenario: str):
    if tile_id not in state.tile_scenarios:
        return JSONResponse({"error": "tile not found"}, status_code=404)
    if scenario not in SCENARIOS:
        return JSONResponse({"error": "scenario not found"}, status_code=404)
    state.tile_scenarios[tile_id] = scenario
    return {"status": "ok", "tile_id": tile_id, "scenario": scenario}


@app.post("/api/reset")
async def reset_all():
    for tid in state.tile_scenarios:
        state.tile_scenarios[tid] = "normal"
    state.alerts.clear()
    state.stats["total_alerts"] = 0
    state.stats["threats"] = 0
    state.stats["suspicious"] = 0
    return {"status": "reset"}


@app.post("/api/scenario/preset/{preset}")
async def apply_preset(preset: str):
    tile_ids = list(state.tile_scenarios.keys())
    if preset == "normal_day":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "normal"
        for tid in random.sample(tile_ids, 4):
            state.tile_scenarios[tid] = "footstep"
    elif preset == "active":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "footstep"
        state.tile_scenarios[random.choice(tile_ids)] = "vehicle"
    elif preset == "explosive":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "footstep"
        state.tile_scenarios[random.choice(tile_ids)] = "explosive"
    elif preset == "weapon":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "footstep"
        state.tile_scenarios[random.choice(tile_ids)] = "weapon"
    elif preset == "narcotic":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "footstep"
        state.tile_scenarios[random.choice(tile_ids)] = "narcotic"
    elif preset == "toxic_gas":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "normal"
        target = random.choice(tile_ids)
        state.tile_scenarios[target] = "toxic_gas"
    elif preset == "alcohol":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "footstep"
        state.tile_scenarios[random.choice(tile_ids)] = "alcohol"
    elif preset == "intrusion":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "normal"
        state.tile_scenarios[random.choice(tile_ids)] = "intrusion"
    elif preset == "multi_threat":
        for tid in tile_ids:
            state.tile_scenarios[tid] = "footstep"
        threats = ["explosive", "weapon", "narcotic", "toxic_gas"]
        targets = random.sample(tile_ids, len(threats))
        for tid, scn in zip(targets, threats):
            state.tile_scenarios[tid] = scn
    return {"status": "ok", "preset": preset}


@app.get("/api/state")
async def get_state():
    return {
        "tiles": list(state.tiles.values()),
        "alerts": list(state.alerts)[-30:],
        "stats": state.stats,
        "layout": SITE_LAYOUT,
    }


@app.get("/api/analytics")
async def get_analytics():
    return db_get_analytics()


@app.get("/api/heatmap")
async def get_heatmap():
    return db_get_heatmap_data()


@app.get("/api/ai_report")
async def get_ai_report():
    return generate_ai_report()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    state.clients.add(ws)
    try:
        await ws.send_json({
            "type": "initial_state",
            "data": {
                "tiles": list(state.tiles.values()),
                "alerts": list(state.alerts)[-20:],
                "stats": state.stats,
                "layout": SITE_LAYOUT,
                "sensor_order": SENSOR_ORDER,
                "sensor_names_ar": SENSOR_NAMES_AR,
                "threats": {k: {"name_ar": v["name_ar"], "icon": v["icon"], "color": v["color"]}
                           for k, v in THREAT_SIGNATURES.items()},
            },
        })
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        state.clients.discard(ws)


@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(simulation_loop())
    asyncio.create_task(broadcast_loop())
    print("\n" + "=" * 65)
    print("  🛡️  درع الأرض (Earth Shield) — Defensethon v4.0")
    print("=" * 65)
    print(f"  🌐 افتح في المتصفح:  http://localhost:8000")
    print(f"  📡 7 حساسات × {len(SITE_LAYOUT)} مركز تحكم في الرياض")
    print(f"  🧠 Cosine Similarity + AI Insights")
    print(f"  💾 SQLite event database: {DB_PATH.name}")
    print("=" * 65 + "\n")


async def broadcast_loop():
    while True:
        event = await state.queue.get()
        dead = set()
        for c in list(state.clients):
            try:
                await c.send_json(event)
            except Exception:
                dead.add(c)
        state.clients -= dead


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
